"""Durable operator attestations for warning delivery and backup restoration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from components.core.maintenance_evidence import aware_time
from components.notification_manager.state_store import NotificationStateStore

TEST_RESULT_EVENT = "safety_periodic_test_result"
TEST_SUMMARY_ENTITY_ID = "sensor.safety_periodic_tests"


class PeriodicTestMonitor:
    """Track completed human checks without sending messages or running restores."""

    def __init__(self, hass_app: Any, mqtt_entities: Any, tests: Mapping[str, bool], *, intervals: Mapping[str, int], state_store: NotificationStateStore, status_observer: Callable[[str, str], None] | None = None) -> None:
        self.hass_app = hass_app
        self.mqtt_entities = mqtt_entities
        self.intervals = {key: intervals[key] for key in ("notification_delivery", "backup_restore") if tests.get(key, False)}
        if any(interval < 1 for interval in self.intervals.values()):
            raise ValueError("Periodic test intervals must be positive")
        self.state_store = state_store
        self.status_observer = status_observer
        self.records: dict[str, dict[str, str]] = {}
        self._storage_error = False
        self._listener_handle: Any = None
        self._timer_handle: Any = None

    def start(self) -> None:
        """Restore records before publishing any claim of a current test."""
        try:
            snapshot = self.state_store.load()
            if not isinstance(snapshot, dict):
                raise ValueError("Periodic test state must be an object")
            if snapshot:
                if not isinstance(snapshot, dict) or snapshot.get("version") != 1 or not isinstance(snapshot.get("records"), dict):
                    raise ValueError("Invalid periodic test state")
                for key, value in snapshot["records"].items():
                    if key in self.intervals:
                        if not isinstance(value, dict) or value.get("outcome") not in {"passed", "failed"} or value.get("source") != "operator_attestation" or aware_time(value.get("completed_at")) is None:
                            raise ValueError("Invalid periodic test record")
                        self.records[key] = value
        except (OSError, ValueError, TypeError) as exc:
            self.hass_app.log(f"Unable to restore periodic tests: {exc}", level="ERROR")
            self.records = {}
            self._storage_error = True
        self.mqtt_entities.register_sensor(TEST_SUMMARY_ENTITY_ID, "Safety Periodic Tests", state="unknown", icon="mdi:clipboard-check-outline", entity_category="diagnostic")
        self._listener_handle = self.hass_app.listen_event(self.handle_test_result, TEST_RESULT_EVENT)
        self._timer_handle = self.hass_app.run_every(self.publish, "now", 3600)
        self.publish()

    def stop(self) -> None:
        """Cancel observation listeners and timers."""
        for attribute, method in (("_listener_handle", "cancel_listen_event"), ("_timer_handle", "cancel_timer")):
            handle = getattr(self, attribute)
            cancel = getattr(self.hass_app, method, None)
            if handle is not None and callable(cancel):
                cancel(handle)
            setattr(self, attribute, None)

    def handle_test_result(self, event_name: str, data: Mapping[str, Any], callback_kwargs: Mapping[str, Any] | None = None, **_: Any) -> None:
        """Commit explicit passed/failed results only after atomic persistence."""
        del event_name, callback_kwargs
        if not isinstance(data, Mapping) or self._storage_error:
            return
        key, outcome = data.get("test_key"), data.get("outcome")
        if not isinstance(key, str) or key not in self.intervals or outcome not in ("passed", "failed"):
            return
        record = {"outcome": outcome, "source": "operator_attestation", "completed_at": datetime.now(timezone.utc).isoformat()}
        updated = {**self.records, key: record}
        try:
            self.state_store.save({"version": 1, "records": updated})
        except Exception as exc:
            self.hass_app.log(f"Unable to save periodic test: {exc}", level="ERROR")
            return
        self.records = updated
        self.publish()

    def publish(self, **_: Any) -> None:
        """Publish deadlines, retaining unknown evidence instead of clearing faults."""
        now = datetime.now(timezone.utc)
        tests: list[dict[str, Any]] = []
        localizer = getattr(self.hass_app, "localizer", None)
        for key, interval in self.intervals.items():
            record = self.records.get(key)
            completed = aware_time(record["completed_at"]) if record else None
            due = completed + timedelta(days=interval) if completed else None
            status = "unknown" if self._storage_error or (record and completed is None) else "due" if record is None else "failed" if record["outcome"] == "failed" else "overdue" if due and now >= due else "current"
            tests.append({"test_key": key, "friendly_name": localizer.text(f"test.{key}") if localizer else key, "status": status, "interval_days": interval, "last_test_at": record["completed_at"] if record else None, "due_at": due.isoformat() if due else None, "last_result": record["outcome"] if record else None, "source": "operator_attestation"})
            if self.status_observer:
                self.status_observer(key, status)
        overall = "attention" if any(test["status"] in {"due", "overdue", "failed"} for test in tests) else "unknown" if self._storage_error or any(test["status"] == "unknown" for test in tests) else "current" if tests else "not_configured"
        self.mqtt_entities.publish_sensor_state(TEST_SUMMARY_ENTITY_ID, overall, attributes={"tests": tests, "storage_error": self._storage_error})
