"""Track completed evaluations without confusing them with application heartbeat."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Any, Callable


class EvaluationProgress:
    """Keep bounded, per-component evidence of completed safety evaluations."""

    def __init__(
        self,
        expected_intervals: dict[str, int | None],
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._clock = clock
        self._lock = Lock()
        self._records: dict[str, dict[str, Any]] = {
            name: {
                "expected_interval_seconds": interval,
                "last_completed_at": None,
                "last_completed_monotonic": None,
                "last_result": "not_evaluated",
                "completed_count": 0,
                "failure_count": 0,
                "missed_deadline_count": 0,
                "deadline_missed": False,
            }
            for name, interval in expected_intervals.items()
        }

    def record(self, component: str, *, success: bool) -> None:
        """Record an actual callback completion, including failed callbacks."""

        with self._lock:
            record = self._records.get(component)
            if record is None:
                return
            record["last_completed_at"] = datetime.now(timezone.utc).isoformat()
            record["last_completed_monotonic"] = self._clock()
            record["last_result"] = "completed" if success else "error"
            record["completed_count"] += 1
            if not success:
                record["failure_count"] += 1
            record["deadline_missed"] = False

    def snapshot(self) -> dict[str, Any]:
        """Return current progress, never promoting missing evidence to healthy."""

        with self._lock:
            now = self._clock()
            components: dict[str, dict[str, Any]] = {}
            for name, record in self._records.items():
                last = record["last_completed_monotonic"]
                interval = record["expected_interval_seconds"]
                age = None if last is None else max(0.0, now - last)
                overdue = bool(interval is not None and age is not None and age > interval)
                if overdue and not record["deadline_missed"]:
                    record["missed_deadline_count"] += 1
                    record["deadline_missed"] = True
                if record["last_result"] == "error":
                    status = "error"
                elif overdue:
                    status = "overdue"
                elif last is None:
                    status = "unknown"
                else:
                    status = "observed"
                components[name] = {
                    "status": status,
                    "last_completed_at": record["last_completed_at"],
                    "last_result": record["last_result"],
                    "age_seconds": None if age is None else round(age, 1),
                    "expected_interval_seconds": interval,
                    "completed_count": record["completed_count"],
                    "failure_count": record["failure_count"],
                    "missed_deadline_count": record["missed_deadline_count"],
                    "evaluation_mode": "periodic" if interval is not None else "event_driven",
                }
            statuses = {item["status"] for item in components.values()}
            overall = (
                "attention"
                if statuses & {"error", "overdue"}
                else "unknown"
                if "unknown" in statuses or not components
                else "observed"
            )
            return {"status": overall, "components": components}
