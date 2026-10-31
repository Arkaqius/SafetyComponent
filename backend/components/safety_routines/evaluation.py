"""Pure evidence qualification and checks reusable by scenario execution."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Mapping

from .schema import Reading, RoutineCheck

INVALID_STATES = {"", "unknown", "unavailable", "none", "null", "nan", "inf", "-inf"}


def timestamp(value: Any) -> datetime | None:
    """Accept an original UTC epoch or timezone-aware ISO observation time."""
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, timezone.utc)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def read_value(
    binding: Reading, states: Mapping[str, Any], now: datetime
) -> tuple[Any, str | None, str | None]:
    """Read a value only when its source and original timestamp are usable."""
    source = states.get(binding.entity_id)
    if (
        not isinstance(source, dict)
        or str(source.get("state", "")).lower() in INVALID_STATES
    ):
        return None, None, "unavailable"
    attributes = source.get("attributes")
    if not isinstance(attributes, dict):
        return None, None, "malformed"
    value = (
        attributes.get(binding.attribute) if binding.attribute else source.get("state")
    )
    if (
        not isinstance(value, (str, int, float, bool))
        or str(value).strip().lower() in INVALID_STATES
    ):
        return None, None, "malformed"
    if isinstance(value, str) and len(value) > 128:
        return None, None, "malformed"
    if isinstance(value, float) and not math.isfinite(value):
        return None, None, "malformed"
    if binding.observed_at_entity_id:
        time_source = states.get(binding.observed_at_entity_id)
        raw_time = time_source.get("state") if isinstance(time_source, dict) else None
    else:
        raw_time = attributes.get(binding.observed_at_attribute)
    observed = timestamp(raw_time)
    if observed is None:
        return value, None, "timestamp_missing"
    age = (now - observed).total_seconds()
    if age < 0:
        return value, observed.isoformat(), "future_timestamp"
    if age > binding.max_age_seconds:
        return value, observed.isoformat(), "stale"
    return value, observed.isoformat(), None


def evaluate_check(
    check_id: str, check: RoutineCheck, states: Mapping[str, Any], now: datetime
) -> dict[str, Any]:
    """Return a diagnostic result without setting faults, timers or actuators."""
    result: dict[str, Any] = {
        "check_id": check_id,
        "name": check.name,
        "entity_id": check.entity_id,
        "status": "unknown",
        "reason": "unavailable",
        "value": None,
        "observed_at": None,
        "evaluated_at": now.isoformat(),
        "expected_states": check.expected_states,
        "minimum": check.minimum,
        "maximum": check.maximum,
        "unit": check.unit,
    }
    if check.condition:
        condition_value, condition_time, error = read_value(
            check.condition, states, now
        )
        result["condition"] = {"value": condition_value, "observed_at": condition_time}
        if error:
            result["reason"] = "condition_" + error
            return result
        if str(condition_value) in check.condition.skip_states:
            result.update(status="skipped", reason="condition_not_applicable")
            return result
        if str(condition_value) not in check.condition.pass_states:
            result["reason"] = "condition_unrecognized"
            return result
    value, observed_at, error = read_value(check, states, now)
    result.update(value=value, observed_at=observed_at)
    if error:
        result["reason"] = error
        return result
    if check.kind == "state":
        passed = str(value) in (check.expected_states or [])
    else:
        attributes = states[check.entity_id]["attributes"]
        if attributes.get("unit_of_measurement") != check.unit:
            result["reason"] = "unit_mismatch"
            return result
        try:
            number = float(value) if not isinstance(value, bool) else math.nan
        except (TypeError, ValueError, OverflowError):
            number = math.nan
        if not math.isfinite(number):
            result["reason"] = "not_numeric"
            return result
        result["value"] = number
        passed = (check.minimum is None or number >= check.minimum) and (
            check.maximum is None or number <= check.maximum
        )
    result.update(
        status="pass" if passed else "problem",
        reason="expected" if passed else "unexpected",
    )
    return result


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Preserve both detected problems and missing evidence in the summary."""
    counts = {
        status: sum(item["status"] == status for item in results)
        for status in ("pass", "problem", "unknown", "skipped")
    }
    status = (
        "problem"
        if counts["problem"]
        else "unknown"
        if counts["unknown"]
        else "pass"
        if counts["pass"]
        else "not_applicable"
    )
    return {"status": status, "counts": counts}
