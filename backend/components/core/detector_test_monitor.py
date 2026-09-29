"""Persistent, observation-only records for periodic detector tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from components.notification_manager.state_store import NotificationStateStore

TEST_RESULT_EVENT = "safety_detector_test_result"
TEST_SUMMARY_ENTITY_ID = "sensor.safety_detector_tests"
_STATE_VERSION = 1
_ALLOWED_HAZARDS = {"smoke", "flammable_gas", "carbon_monoxide"}


class DetectorTestMonitor:
    """Track test outcomes without altering detector alarms or controls."""

    def __init__(
        self,
        hass_app: Any,
        mqtt_entities: Any,
        detectors: Mapping[str, Mapping[str, Any]],
        *,
        interval_days: int,
        state_store: NotificationStateStore,
        status_observer: Callable[[str, str], None] | None = None,
    ) -> None:
        if interval_days < 1:
            raise ValueError("Detector test interval must be positive")
        self.hass_app = hass_app
        self.mqtt_entities = mqtt_entities
        self.detectors = {
            key: dict(value)
            for key, value in detectors.items()
            if value.get("hazard") in _ALLOWED_HAZARDS and value.get("enabled", True)
        }
        self.interval_days = interval_days
        self.state_store = state_store
        self.status_observer = status_observer
        self.records: dict[str, dict[str, str]] = {}
        self._storage_error = False
        self._listener_handle: Any = None
        self._timer_handle: Any = None

    def start(self) -> None:
        """Restore durable records and start listening for operator attestations."""

        try:
            snapshot = self.state_store.load()
            if snapshot:
                if not isinstance(snapshot, dict):
                    raise ValueError("Detector test state must be an object")
                if snapshot.get("version") != _STATE_VERSION:
                    raise ValueError("Unsupported detector test state version")
                records = snapshot.get("records")
                if not isinstance(records, dict):
                    raise ValueError("Detector test records must be an object")
                self.records = {
                    key: self._validated_record(value)
                    for key, value in records.items()
                    if key in self.detectors
                }
        except (OSError, ValueError, TypeError) as exc:
            self.hass_app.log(f"Unable to restore detector tests: {exc}", level="ERROR")
            self.records = {}
            self._storage_error = True
        self.mqtt_entities.register_sensor(
            TEST_SUMMARY_ENTITY_ID,
            "Safety Detector Tests",
            state="unknown",
            icon="mdi:clipboard-check-outline",
            entity_category="diagnostic",
        )
        self._listener_handle = self.hass_app.listen_event(
            self.handle_test_result, TEST_RESULT_EVENT
        )
        self._timer_handle = self.hass_app.run_every(self.publish, "now", 3600)
        self.publish()

    def stop(self) -> None:
        """Release listeners without changing alarm state."""

        if self._listener_handle is not None:
            cancel = getattr(self.hass_app, "cancel_listen_event", None)
            if callable(cancel):
                cancel(self._listener_handle)
            self._listener_handle = None
        if self._timer_handle is not None:
            cancel = getattr(self.hass_app, "cancel_timer", None)
            if callable(cancel):
                cancel(self._timer_handle)
            self._timer_handle = None

    def handle_test_result(
        self,
        event_name: str,
        data: Mapping[str, Any],
        callback_kwargs: Mapping[str, Any] | None = None,
        **_: Any,
    ) -> None:
        """Persist one explicit test outcome sent through authenticated HA."""

        del event_name, callback_kwargs
        if not isinstance(data, Mapping):
            return
        key = data.get("detector_key")
        outcome = data.get("outcome")
        if not isinstance(key, str) or key not in self.detectors:
            return
        if outcome not in ("passed", "failed"):
            return
        if self._storage_error:
            self.hass_app.log(
                "Detector test result rejected: stored history cannot be read",
                level="ERROR",
            )
            return
        record = {
            "outcome": outcome,
            "source": "operator_attestation",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        updated = {**self.records, key: record}
        try:
            self.state_store.save({"version": _STATE_VERSION, "records": updated})
        except Exception as exc:
            self.hass_app.log(f"Unable to save detector test: {exc}", level="ERROR")
            return
        self.records = updated
        self.publish()

    def publish(self, **_: Any) -> None:
        """Publish due, overdue, and failed tests without implying alarm clear."""

        now = datetime.now(timezone.utc)
        tests: list[dict[str, Any]] = []
        for key, detector in self.detectors.items():
            record = self.records.get(key)
            due_at = None
            if self._storage_error:
                status = "unknown"
            elif record is None:
                status = "due"
            else:
                completed = datetime.fromisoformat(record["completed_at"])
                due = completed + timedelta(days=self.interval_days)
                due_at = due.isoformat()
                status = (
                    "failed"
                    if record["outcome"] == "failed"
                    else "overdue"
                    if now >= due
                    else "current"
                )
            tests.append(
                {
                    "detector_key": key,
                    "friendly_name": str(detector.get("friendly_name", key)),
                    "hazard": detector["hazard"],
                    "status": status,
                    "last_result": record["outcome"] if record else None,
                    "last_test_at": record["completed_at"] if record else None,
                    "source": record["source"] if record else None,
                    "due_at": due_at,
                }
            )
            if self.status_observer is not None:
                self.status_observer(key, status)
        overall = (
            "unknown"
            if self._storage_error
            else "attention"
            if any(test["status"] in {"due", "overdue", "failed"} for test in tests)
            else "current"
            if tests
            else "not_configured"
        )
        self.mqtt_entities.publish_sensor_state(
            TEST_SUMMARY_ENTITY_ID,
            overall,
            attributes={
                "tests": tests,
                "test_interval_days": self.interval_days,
                "storage_error": self._storage_error,
            },
        )

    @staticmethod
    def _validated_record(value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            raise ValueError("Detector test record must be an object")
        outcome = value.get("outcome")
        source = value.get("source")
        completed_at = value.get("completed_at")
        if outcome not in ("passed", "failed") or source != "operator_attestation":
            raise ValueError("Invalid detector test result")
        if not isinstance(completed_at, str):
            raise ValueError("Detector test time must be a string")
        parsed = datetime.fromisoformat(completed_at)
        if parsed.tzinfo is None:
            raise ValueError("Detector test time must include a timezone")
        return {"outcome": outcome, "source": source, "completed_at": completed_at}
