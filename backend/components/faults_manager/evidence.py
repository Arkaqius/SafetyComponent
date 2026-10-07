"""Bounded first-activation evidence, separate from notification history."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Callable, Mapping

from components.core.types_common import Fault, Symptom
from components.faults_manager.evidence_store import FaultEvidenceStore

FORMAT_VERSION = 2
CONTEXT_FIELDS = frozenset(
    {
        "location",
        "doors",
        "source_entity",
        "open_duration_seconds",
        "condition_entity",
        "condition_state",
        "capability",
        "providers",
        "freshness",
        "entity_id",
        "entity_key",
        "consumer_keys",
        "area_name",
        "failed_check",
        "reason",
        "current_value",
        "last_valid_value",
        "last_valid_at",
        "failure_started_at",
        "evaluated_at",
        "freshness_age",
        "observed_value",
        "detector",
        "detector_key",
        "hazard",
        "detector_state",
        "assertion_status",
        "gas_identity",
        "switching_inhibited",
        "health_reason",
        "cause",
        "store",
        "provider",
        "status",
        "subject",
        "threshold",
    }
)
NUMERIC_OR_BINARY_FIELDS = frozenset(
    {
        "current_value",
        "last_valid_value",
        "observed_value",
        "condition_state",
        "detector_state",
        "threshold",
        "state",
    }
)
CONFIG_FIELDS = frozenset(
    {
        "temperature_sensor",
        "entity_id",
        "location",
        "area_id",
        "area_name",
        "door_name",
        "cold_thr",
        "hot_thr",
        "CAL_LOW_TEMP_THRESHOLD",
        "CAL_HIGH_TEMP_THRESHOLD",
        "timeout_seconds",
        "open_timeout_seconds",
        "debounce_limit",
        "re_eval_delay_seconds",
        "forecast_timespan",
        "derivative_sample_minutes",
        "max_abs_rate_c_per_min",
        "max_forecast_delta_c",
        "minimum_temperature_c",
        "maximum_temperature_c",
        "failure_debounce_seconds",
        "recovery_debounce_seconds",
    }
)
SAFE_BINARY = frozenset({"on", "off", "open", "closed", "true", "false", "0", "1"})
SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|bearer\s|authorization|"
    r"https?://|\bAKIA[0-9A-Z]{16}\b|\b(?:ghp_|sk-)[A-Za-z0-9_-]{20,}\b|"
    r"\b[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b)"
)
SOURCE_FIELDS = frozenset(
    {
        "entity_id",
        "state",
        "last_updated",
        "age_seconds",
        "clock_uncertain",
        "observed_value",
        "modeled_value",
        "threshold",
        "unit",
        "rate_per_minute",
        "value_origin",
        "timestamp_relation",
        "quality",
    }
)
FRAME_FIELDS = frozenset(
    {
        "version",
        "captured_at",
        "fault",
        "category",
        "priority",
        "symptom",
        "context",
        "configuration",
        "configuration_fingerprint",
        "source",
        "active_restrictions",
        "subject",
    }
)
LIFECYCLE_FIELDS = frozenset(
    {
        "first_failure_at",
        "last_failure_at",
        "last_valid_pass_at",
        "activation_count",
        "last_reason",
        "active_duration_seconds",
        "clock_uncertain",
    }
)


def _encoded_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _safe_scalar(
    value: Any, *, numeric_or_binary: bool = False
) -> str | int | float | bool | None:
    """Reject nested, nonfinite, secret-like, or unbounded source values."""

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value if abs(value) <= 1e12 and math.isfinite(value) else None
    if not isinstance(value, str) or len(value) > 160 or SECRET_PATTERN.search(value):
        return None
    if numeric_or_binary:
        if value.strip().lower() in SAFE_BINARY:
            return value
        try:
            number = float(value)
        except ValueError:
            return None
        return value if math.isfinite(number) else None
    return value


def _allowlisted(
    values: Mapping[str, Any] | None, allowed: frozenset[str]
) -> dict[str, Any]:
    if not isinstance(values, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key in sorted(allowed.intersection(values)):
        safe = _safe_scalar(
            values[key], numeric_or_binary=key in NUMERIC_OR_BINARY_FIELDS
        )
        if safe is not None:
            result[key] = safe
    return result


def _valid_timestamp(value: Any, *, nullable: bool = False) -> bool:
    if value is None:
        return nullable
    if not isinstance(value, str) or len(value) > 40:
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def _validate_record(name: str, record: dict[str, Any], max_frame_bytes: int) -> None:
    """Do not re-publish arbitrary values from a corrupt or altered state file."""

    if set(record) != {"active", "freeze_frame"} or not isinstance(
        record["active"], bool
    ):
        raise ValueError("Invalid fault evidence record")
    frame = record["freeze_frame"]
    if (
        not isinstance(frame, dict)
        or set(frame) != FRAME_FIELDS | LIFECYCLE_FIELDS
        or frame["version"] != FORMAT_VERSION
    ):
        raise ValueError("Invalid freeze-frame fields")
    if frame["fault"] != name or not re.fullmatch(r"[A-Za-z0-9_]{1,256}", name):
        raise ValueError("Invalid freeze-frame identity")
    if not isinstance(frame["symptom"], str) or not re.fullmatch(
        r"[A-Za-z0-9_]{1,256}", frame["symptom"]
    ):
        raise ValueError("Invalid freeze-frame contributor")
    if (
        frame["category"] not in {"H", "D"}
        or isinstance(frame["priority"], bool)
        or frame["priority"] not in {1, 2, 3, 4}
    ):
        raise ValueError("Invalid freeze-frame fault classification")
    if not _valid_timestamp(frame["captured_at"]):
        raise ValueError("Invalid freeze-frame time")
    for key, allowed in (
        ("context", CONTEXT_FIELDS),
        ("configuration", CONFIG_FIELDS),
        ("source", SOURCE_FIELDS),
    ):
        values = frame[key]
        if not isinstance(values, dict) or values != _allowlisted(values, allowed):
            raise ValueError("Unsafe freeze-frame data")
    if "last_updated" in frame["source"] and not _valid_timestamp(
        frame["source"]["last_updated"]
    ):
        raise ValueError("Invalid source timestamp")
    if (
        not isinstance(frame["subject"], str)
        or _safe_scalar(frame["subject"]) != frame["subject"]
    ):
        raise ValueError("Invalid freeze-frame subject")
    if not isinstance(frame["configuration_fingerprint"], str) or not re.fullmatch(
        r"[a-f0-9]{64}", frame["configuration_fingerprint"]
    ):
        raise ValueError("Invalid freeze-frame fingerprint")
    restrictions = frame["active_restrictions"]
    if (
        not isinstance(restrictions, list)
        or len(restrictions) > 16
        or any(
            not isinstance(item, str) or _safe_scalar(item) != item
            for item in restrictions
        )
    ):
        raise ValueError("Invalid freeze-frame restrictions")
    if _capture_size(frame) > max_frame_bytes:
        raise ValueError("Fault freeze frame exceeds bound")
    if any(
        not _valid_timestamp(frame[key], nullable=key == "last_valid_pass_at")
        for key in ("first_failure_at", "last_failure_at", "last_valid_pass_at")
    ):
        raise ValueError("Invalid freeze-frame timestamp")
    count = frame["activation_count"]
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or not 1 <= count <= 2147483647
    ):
        raise ValueError("Invalid fault activation count")
    if not isinstance(frame["clock_uncertain"], bool):
        raise ValueError("Invalid fault clock flag")
    duration = frame["active_duration_seconds"]
    if duration is not None and (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration < 0
    ):
        raise ValueError("Invalid fault duration")
    reason = frame["last_reason"]
    if reason is not None and (
        not isinstance(reason, str) or _safe_scalar(reason) != reason
    ):
        raise ValueError("Invalid fault reason")


def _migrate_legacy_record(record: dict[str, Any]) -> dict[str, Any]:
    """Combine strictly shaped version-one data without trusting stored values."""

    if set(record) != {"active", "freeze_frame", "extended_data"}:
        raise ValueError("Invalid legacy fault evidence record")
    capture = record["freeze_frame"]
    lifecycle = record["extended_data"]
    if (
        not isinstance(capture, dict)
        or set(capture) != FRAME_FIELDS
        or capture["version"] != 1
        or not isinstance(lifecycle, dict)
        or set(lifecycle) != LIFECYCLE_FIELDS
    ):
        raise ValueError("Invalid legacy freeze-frame fields")
    return {
        "active": record["active"],
        "freeze_frame": {**capture, **lifecycle, "version": FORMAT_VERSION},
    }


def _capture_size(frame: dict[str, Any]) -> int:
    """Keep the existing capture budget independent of lifecycle updates."""

    return _encoded_size({key: frame[key] for key in FRAME_FIELDS})


class FaultEvidenceJournal:
    """Retain one bounded freeze frame with capture and lifecycle fields."""

    def __init__(
        self,
        store: FaultEvidenceStore,
        *,
        max_records: int = 256,
        max_frame_bytes: int = 4096,
        max_total_bytes: int = 1048576,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        elapsed_clock: Callable[[], float] = monotonic,
        log: Callable[..., None] | None = None,
        diagnostics_observer: Callable[..., None] | None = None,
        schedule_flush: Callable[[Callable[[], None], int], None] | None = None,
    ) -> None:
        if (
            max_records < 1
            or max_frame_bytes < 512
            or max_total_bytes < max_frame_bytes
        ):
            raise ValueError("Invalid fault evidence bounds")
        self.store = store
        self.max_records = max_records
        self.max_frame_bytes = max_frame_bytes
        self.max_total_bytes = max_total_bytes
        self.clock = clock
        self.elapsed_clock = elapsed_clock
        self.log = log
        self.diagnostics_observer = diagnostics_observer
        self.schedule_flush = schedule_flush
        self.records: dict[str, dict[str, Any]] = {}
        self._active_since: dict[str, float] = {}
        self._dirty = False
        self._flush_scheduled = False
        self._flushing = False
        self._load()

    def _report(self, failed: bool, operation: str) -> None:
        if self.diagnostics_observer is not None:
            try:
                self.diagnostics_observer(
                    "persistence",
                    failed,
                    detail="fault_evidence_state",
                    operation=operation,
                )
            except Exception as exc:
                if self.log is not None:
                    self.log(
                        f"Unable to report fault evidence storage: {type(exc).__name__}",
                        level="ERROR",
                    )

    def _load(self) -> None:
        try:
            snapshot = self.store.load()
            if not snapshot:
                self._report(False, "load")
                return
            version = snapshot.get("version")
            if (
                not isinstance(version, int)
                or isinstance(version, bool)
                or version not in (1, FORMAT_VERSION)
                or not isinstance(snapshot.get("records"), dict)
            ):
                raise ValueError("Unsupported fault evidence snapshot")
            if _encoded_size(snapshot) > self.max_total_bytes:
                raise ValueError("Fault evidence snapshot exceeds bound")
            records = snapshot["records"]
            if len(records) > self.max_records:
                raise ValueError("Fault evidence record count exceeds bound")
            for name, record in records.items():
                if not isinstance(name, str) or not isinstance(record, dict):
                    raise ValueError("Invalid fault evidence record")
                if version == 1:
                    record = _migrate_legacy_record(record)
                    records[name] = record
                _validate_record(name, record, self.max_frame_bytes)
                if record["active"]:
                    record["freeze_frame"]["clock_uncertain"] = True
                    record["freeze_frame"]["active_duration_seconds"] = None
            if (
                _encoded_size({"version": FORMAT_VERSION, "records": records})
                > self.max_total_bytes
            ):
                raise ValueError("Migrated fault evidence snapshot exceeds bound")
            self.records = records
            if version == 1:
                self._save()
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self.records = {}
            if self.log is not None:
                self.log(
                    f"Unable to load fault evidence: {type(exc).__name__}",
                    level="ERROR",
                )
            self._report(True, "load")
        else:
            self._report(False, "load")

    def get(self, fault_name: str) -> dict[str, Any] | None:
        """Return a detached record so readers cannot mutate original evidence."""

        record = self.records.get(fault_name)
        return json.loads(json.dumps(record)) if record is not None else None

    def _drop_stale_frame(self, fault_name: str) -> None:
        """Never expose an older cleared frame as a new active capture."""

        previous = self.records.get(fault_name)
        if previous is not None and not previous["active"]:
            self.records.pop(fault_name)
            self._save()

    def activate(
        self,
        fault: Fault,
        symptom: Symptom,
        context: Mapping[str, Any] | None,
        *,
        source: Mapping[str, Any] | None = None,
        restrictions: tuple[str, ...] = (),
    ) -> None:
        """Capture only on a new physical activation, including shadowed faults."""

        previous = self.records.get(fault.name)
        if previous is not None and previous["active"]:
            return
        now = self.clock().astimezone(timezone.utc).isoformat()
        config = _allowlisted(symptom.parameters, CONFIG_FIELDS)
        frame: dict[str, Any] = {
            "version": FORMAT_VERSION,
            "captured_at": now,
            "fault": fault.name,
            "category": fault.category.value,
            "priority": fault.level,
            "symptom": symptom.name,
            "context": _allowlisted(context, CONTEXT_FIELDS),
            "configuration": config,
            "configuration_fingerprint": hashlib.sha256(
                json.dumps(config, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "source": _allowlisted(source, SOURCE_FIELDS),
            "active_restrictions": [
                value for value in restrictions[:16] if _safe_scalar(value) == value
            ],
        }
        subject = next(
            (
                frame["context"][key]
                for key in (
                    "location",
                    "area_name",
                    "entity_key",
                    "detector_key",
                    "doors",
                )
                if key in frame["context"]
            ),
            symptom.name,
        )
        frame["subject"] = (
            subject
            if isinstance(subject, str) and _safe_scalar(subject) == subject
            else symptom.name[:160]
        )
        previous_frame = previous["freeze_frame"] if previous is not None else {}
        reason = frame["context"].get("reason") or frame["context"].get("failed_check")
        frame.update(
            first_failure_at=previous_frame.get("first_failure_at", now),
            last_failure_at=now,
            last_valid_pass_at=previous_frame.get("last_valid_pass_at"),
            activation_count=min(
                int(previous_frame.get("activation_count", 0)) + 1, 2147483647
            ),
            last_reason=reason if isinstance(reason, str) else None,
            active_duration_seconds=None,
            clock_uncertain=False,
        )
        while _capture_size(frame) > self.max_frame_bytes and frame["context"]:
            frame["context"].pop(next(reversed(frame["context"])))
        while _capture_size(frame) > self.max_frame_bytes and frame["configuration"]:
            frame["configuration"].pop(next(reversed(frame["configuration"])))
        frame["configuration_fingerprint"] = hashlib.sha256(
            json.dumps(frame["configuration"], sort_keys=True).encode("utf-8")
        ).hexdigest()
        if _capture_size(frame) > self.max_frame_bytes:
            if self.log is not None:
                self.log(
                    f"Fault evidence frame bound reached for {fault.name}",
                    level="ERROR",
                )
            self._drop_stale_frame(fault.name)
            self._report(True, "capacity")
            return

        record = {
            "active": True,
            "freeze_frame": frame,
        }
        candidate = dict(self.records)
        candidate[fault.name] = record
        while (
            len(candidate) > self.max_records
            or _encoded_size({"version": FORMAT_VERSION, "records": candidate})
            > self.max_total_bytes
        ):
            inactive = [
                (name, item)
                for name, item in candidate.items()
                if name != fault.name and not item["active"]
            ]
            if not inactive:
                if self.log is not None:
                    self.log(
                        f"Fault evidence capacity exhausted for {fault.name}",
                        level="ERROR",
                    )
                self._drop_stale_frame(fault.name)
                self._report(True, "capacity")
                return
            oldest = min(
                inactive,
                key=lambda pair: (
                    pair[1]["freeze_frame"].get("last_failure_at", ""),
                    pair[0],
                ),
            )
            candidate.pop(oldest[0])
        self.records = candidate
        self._active_since[fault.name] = self.elapsed_clock()
        self._report(False, "capacity")
        self._save()

    def clear(self, fault_name: str) -> None:
        """Retain the frame while recording a valid pass and ending activity."""

        record = self.records.get(fault_name)
        if record is None or not record["active"]:
            return
        now = self.clock().astimezone(timezone.utc).isoformat()
        record["active"] = False
        frame = record["freeze_frame"]
        frame["last_valid_pass_at"] = now
        start = self._active_since.pop(fault_name, None)
        if start is not None and not frame["clock_uncertain"]:
            frame["active_duration_seconds"] = max(
                0, round(self.elapsed_clock() - start, 3)
            )
        while (
            _encoded_size({"version": FORMAT_VERSION, "records": self.records})
            > self.max_total_bytes
        ):
            inactive = [
                (name, item)
                for name, item in self.records.items()
                if name != fault_name and not item["active"]
            ]
            if not inactive:
                self.records.pop(fault_name)
                break
            oldest = min(
                inactive,
                key=lambda pair: (
                    pair[1]["freeze_frame"].get("last_failure_at", ""),
                    pair[0],
                ),
            )
            self.records.pop(oldest[0])
        self._save()

    def _save(self) -> None:
        self._dirty = True
        if self.schedule_flush is not None:
            if not self._flush_scheduled and not self._flushing:
                self._schedule(0)
            return
        self.flush()

    def _schedule(self, delay_seconds: int) -> None:
        if self.schedule_flush is None or self._flush_scheduled:
            return
        self._flush_scheduled = True
        try:
            self.schedule_flush(self.flush, delay_seconds)
        except Exception as exc:
            self._flush_scheduled = False
            if self.log is not None:
                self.log(
                    f"Unable to schedule fault evidence save: {type(exc).__name__}",
                    level="ERROR",
                )
            self._report(True, "save")

    def flush(self) -> None:
        """Persist the latest snapshot after fault response dispatch."""

        self._flush_scheduled = False
        if not self._dirty or self._flushing:
            return
        self._flushing = True
        try:
            self.store.save({"version": FORMAT_VERSION, "records": self.records})
        except (OSError, ValueError, TypeError) as exc:
            if self.log is not None:
                self.log(
                    f"Unable to save fault evidence: {type(exc).__name__}",
                    level="ERROR",
                )
            self._report(True, "save")
            if self.schedule_flush is not None:
                self._schedule(60)
        else:
            self._dirty = False
            self._report(False, "save")
        finally:
            self._flushing = False
        if (
            self._dirty
            and self.schedule_flush is not None
            and not self._flush_scheduled
        ):
            self._schedule(0)

    def stop(self) -> None:
        """Attempt one final durable write on orderly shutdown."""

        self.schedule_flush = None
        self.flush()
