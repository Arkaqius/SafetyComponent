"""Normalize configured HA inputs without product recognition or control APIs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any, Callable, Mapping

from .schema import BOOLEAN_ROLES, TEMPERATURE_ROLES, TEXT_ROLES, HeatingInput


@dataclass(frozen=True)
class HeatingObservation:
    """Immutable normalized value with source quality and observation provenance."""

    value: bool | float | str | None
    quality: str
    observed_at: float | None
    entity_id: str
    independence_group: str
    evidence_kind: str
    maximum_age_seconds: int = 120

    @property
    def qualified(self) -> bool:
        """Whether this evidence has a qualified original observation time."""
        return self.quality == "valid"

    @property
    def source_time(self) -> float:
        """Expose the original time only after caller qualification."""
        assert self.qualified and self.observed_at is not None
        return self.observed_at

    @property
    def number(self) -> float:
        """Expose normalized numeric or binary evidence after qualification."""
        assert self.qualified and isinstance(self.value, (float, int))
        return float(self.value)


def timestamp(value: Any) -> float | None:
    """Read ISO timestamps with timezone or epoch seconds; reject naive time."""
    try:
        if isinstance(value, bool):
            return None
        if (
            isinstance(value, (int, float))
            or isinstance(value, str)
            and value.replace(".", "", 1).isdigit()
        ):
            result = float(value)
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return None
            result = parsed.astimezone(timezone.utc).timestamp()
        return result if math.isfinite(result) and 0 <= result <= 253402300799 else None
    except (ValueError, TypeError, OverflowError):
        return None


class HeatingInputReader:
    """Resolve literal configured selectors and preserve unknown raw values."""

    def __init__(self, read_state: Callable[[str], Any]) -> None:
        self._read_state = read_state
        self._latest: dict[str, tuple[float, Any]] = {}

    def read(self, role: str, binding: HeatingInput, now: float) -> HeatingObservation:
        """Return one value; HA publication timestamps never imply observation age."""
        observed_at: float | None = None

        def result(value: Any, quality: str) -> HeatingObservation:
            return HeatingObservation(
                value,
                quality,
                observed_at,
                binding.entity_id,
                binding.independence_group,
                binding.evidence_kind,
                binding.max_age_seconds,
            )

        try:
            record = self._read_state(binding.entity_id)
            if not isinstance(record, Mapping) or str(
                record.get("state", "")
            ).lower() in {"", "unknown", "unavailable", "none"}:
                return result(None, "unavailable")
            attributes = record.get("attributes", {})
            if binding.attribute and not isinstance(attributes, Mapping):
                return result(None, "invalid_value")
            raw = (
                attributes.get(binding.attribute)
                if binding.attribute and isinstance(attributes, Mapping)
                else record.get("state")
            )
            if raw is None or str(raw).strip().lower() in {
                "",
                "unknown",
                "unavailable",
                "none",
            }:
                return result(None, "unavailable")
            value: Any = raw
            if binding.value_map:
                key = str(raw).lower() if isinstance(raw, bool) else str(raw)
                if key not in binding.value_map:
                    return result(None, "unmapped")
                value = binding.value_map[key]
            if role in BOOLEAN_ROLES:
                if not isinstance(value, bool):
                    return result(None, "invalid_value")
            elif role in TEXT_ROLES:
                if not isinstance(value, str):
                    return result(None, "invalid_value")
                allowed = (
                    {
                        "idle",
                        "starting",
                        "heating",
                        "dhw",
                        "pump_overrun",
                        "inhibited",
                        "unknown",
                    }
                    if role == "boiler_state"
                    else {"none", "startup", "anti_cycle"}
                    if role == "inhibition_reason"
                    else {"clear", "fault"}
                    if role == "device_status"
                    else {"clear", "maintenance"}
                )
                if value not in allowed:
                    return result(None, "unmapped")
            else:
                if isinstance(value, bool):
                    return result(None, "invalid_value")
                value = float(value)
                if not math.isfinite(value):
                    return result(None, "invalid_value")
                source_unit = binding.unit or (
                    attributes.get("unit_of_measurement")
                    if isinstance(attributes, Mapping)
                    else None
                )
                if role in TEMPERATURE_ROLES:
                    if source_unit == "°F":
                        value = (value - 32) * 5 / 9
                    elif source_unit == "K":
                        value -= 273.15
                    elif source_unit != "°C":
                        return result(None, "invalid_unit")
                elif role == "power_percent" and source_unit != "%":
                    return result(None, "invalid_unit")
                elif role == "power_w":
                    if source_unit == "kW":
                        value *= 1000
                    elif source_unit != "W":
                        return result(None, "invalid_unit")
                value = value * binding.scale + binding.offset
                if not math.isfinite(value) or (
                    role in TEMPERATURE_ROLES and not -273.15 < value < 1000
                ):
                    return result(None, "invalid_value")
                if role == "power_percent" and not 0 <= value <= 100:
                    return result(None, "invalid_value")
                if role == "power_w" and value < 0:
                    return result(None, "invalid_value")
                if role.startswith("burner_starts") and (
                    value < 0 or value != int(value)
                ):
                    return result(None, "invalid_value")
            if binding.freshness == "availability_only":
                return result(value, "availability_only")
            stamp_record = (
                self._read_state(binding.observed_at_entity_id)
                if binding.observed_at_entity_id
                else record
            )
            if not isinstance(stamp_record, Mapping) or str(
                stamp_record.get("state", "")
            ).lower() in {"unknown", "unavailable"}:
                return result(None, "invalid_timestamp")
            stamp_attributes = stamp_record.get("attributes", {})
            if binding.observed_at_attribute and not isinstance(
                stamp_attributes, Mapping
            ):
                return result(None, "invalid_timestamp")
            stamp = (
                stamp_attributes.get(binding.observed_at_attribute)
                if binding.observed_at_attribute
                and isinstance(stamp_attributes, Mapping)
                else stamp_record.get("state")
            )
            observed_at = timestamp(stamp)
            if observed_at is None:
                return result(None, "invalid_timestamp")
            if observed_at > now:
                return result(None, "future")
            if now - observed_at > binding.max_age_seconds:
                return result(None, "stale")
            key = f"{binding.entity_id}|{binding.attribute}|{role}"
            previous = self._latest.get(key)
            if previous and (
                observed_at < previous[0]
                or (observed_at == previous[0] and value != previous[1])
            ):
                return result(None, "replayed")
            self._latest[key] = (observed_at, value)
            return result(value, "valid")
        except Exception:
            # A failed read is unavailable evidence, including integration errors.
            return result(None, "invalid_value")
