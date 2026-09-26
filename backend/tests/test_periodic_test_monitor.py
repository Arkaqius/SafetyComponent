"""Operator attestations are durable, explicit, and never actuator commands."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from components.core.periodic_test_monitor import PeriodicTestMonitor
from components.notification_manager.state_store import InMemoryNotificationStateStore


def _monitor(store: object | None = None) -> tuple:
    hass, mqtt, observer = Mock(), Mock(), Mock()
    hass.localizer = None
    monitor = PeriodicTestMonitor(hass, mqtt, {"notification_delivery": True, "backup_restore": False}, intervals={"notification_delivery": 30, "backup_restore": 180}, state_store=store or InMemoryNotificationStateStore(), status_observer=observer)
    return monitor, hass, mqtt, observer


def test_due_pass_failure_and_restart_persist_without_sending() -> None:
    store = InMemoryNotificationStateStore()
    monitor, hass, mqtt, observer = _monitor(store)
    monitor.start()
    observer.assert_called_with("notification_delivery", "due")
    monitor.handle_test_result("safety_periodic_test_result", {"test_key": "notification_delivery", "outcome": "passed"})
    assert mqtt.publish_sensor_state.call_args.args[1] == "current"
    restored, _, _, next_observer = _monitor(store)
    restored.start()
    next_observer.assert_called_with("notification_delivery", "current")
    restored.handle_test_result("safety_periodic_test_result", {"test_key": "notification_delivery", "outcome": "failed"})
    next_observer.assert_called_with("notification_delivery", "failed")
    hass.call_service.assert_not_called()


@pytest.mark.parametrize("timestamp", ["bad", "2026-01-01T00:00:00", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()])
def test_corrupt_future_or_naive_history_unknown_and_not_overwritten(timestamp: str) -> None:
    store = Mock()
    store.load.return_value = {"version": 1, "records": {"notification_delivery": {"outcome": "passed", "source": "operator_attestation", "completed_at": timestamp}}}
    monitor, _, mqtt, observer = _monitor(store)
    monitor.start()
    assert mqtt.publish_sensor_state.call_args.args[1] == "unknown"
    observer.assert_called_with("notification_delivery", "unknown")
    monitor.handle_test_result("event", {"test_key": "notification_delivery", "outcome": "passed"})
    store.save.assert_not_called()


def test_overdue_disabled_checks_and_invalid_events() -> None:
    store = InMemoryNotificationStateStore({"version": 1, "records": {"notification_delivery": {"outcome": "passed", "source": "operator_attestation", "completed_at": (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()}}})
    monitor, _, _, observer = _monitor(store)
    monitor.start()
    observer.assert_called_with("notification_delivery", "overdue")
    old = store.load()
    monitor.handle_test_result("event", {"test_key": "backup_restore", "outcome": "passed"})
    monitor.handle_test_result("event", {"test_key": "notification_delivery", "outcome": "clear"})
    assert store.load() == old


def test_failed_persistence_does_not_claim_success_and_stop_releases_handles() -> None:
    store = Mock()
    store.load.return_value = {}
    store.save.side_effect = OSError("unavailable")
    monitor, hass, mqtt, observer = _monitor(store)
    monitor.start()
    monitor.handle_test_result("event", {"test_key": "notification_delivery", "outcome": "passed"})
    assert monitor.records == {}
    observer.assert_called_once_with("notification_delivery", "due")
    assert mqtt.publish_sensor_state.call_args.args[1] == "attention"
    monitor.stop()
    hass.cancel_timer.assert_called_once()
    hass.cancel_listen_event.assert_called_once()


@pytest.mark.parametrize("payload", [[], ["corrupt"], {"version": 999, "records": {}}, {"version": 1, "records": []}])
def test_malformed_persistent_root_is_unknown(payload: object) -> None:
    store = Mock()
    store.load.return_value = payload
    monitor, _, mqtt, _ = _monitor(store)
    monitor.start()
    assert mqtt.publish_sensor_state.call_args.args[1] == "unknown"


def test_all_disabled_is_not_configured_and_invalid_interval_rejected() -> None:
    monitor = PeriodicTestMonitor(Mock(), Mock(), {}, intervals={}, state_store=InMemoryNotificationStateStore())
    monitor.start()
    assert monitor.mqtt_entities.publish_sensor_state.call_args.args[1] == "not_configured"
    with pytest.raises(ValueError):
        PeriodicTestMonitor(Mock(), Mock(), {"notification_delivery": True}, intervals={"notification_delivery": 0}, state_store=InMemoryNotificationStateStore())
