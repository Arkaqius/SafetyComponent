"""Detector maintenance records do not replace live alarm evidence."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from components.core.detector_test_monitor import DetectorTestMonitor
from components.notification_manager.state_store import InMemoryNotificationStateStore


def _monitor(store: InMemoryNotificationStateStore | None = None) -> tuple[DetectorTestMonitor, Mock, Mock]:
    hass = Mock()
    mqtt = Mock()
    monitor = DetectorTestMonitor(
        hass,
        mqtt,
        {"KitchenSmoke": {"hazard": "smoke", "friendly_name": "Kitchen smoke"}},
        interval_days=180,
        state_store=store or InMemoryNotificationStateStore(),
    )
    return monitor, hass, mqtt


def test_missing_test_is_due_and_manual_result_is_persisted() -> None:
    store = InMemoryNotificationStateStore()
    monitor, _, mqtt = _monitor(store)
    monitor.start()
    assert mqtt.publish_sensor_state.call_args.kwargs["attributes"]["tests"][0]["status"] == "due"

    monitor.handle_test_result(
        "safety_detector_test_result",
        {"detector_key": "KitchenSmoke", "outcome": "passed"},
    )
    assert store.load()["records"]["KitchenSmoke"]["outcome"] == "passed"
    assert mqtt.publish_sensor_state.call_args.kwargs["attributes"]["tests"][0]["status"] == "current"


def test_invalid_or_unbound_attestation_is_ignored() -> None:
    store = InMemoryNotificationStateStore()
    monitor, _, _ = _monitor(store)
    monitor.handle_test_result("safety_detector_test_result", {"detector_key": "Other", "outcome": "passed"})
    monitor.handle_test_result("safety_detector_test_result", {"detector_key": "KitchenSmoke", "outcome": "clear_alarm"})
    assert store.load() == {}


def test_persistence_failure_does_not_claim_test_was_recorded() -> None:
    store = Mock()
    store.save.side_effect = OSError("disk unavailable")
    monitor, hass, mqtt = _monitor(store)
    monitor.handle_test_result(
        "safety_detector_test_result",
        {"detector_key": "KitchenSmoke", "outcome": "passed"},
    )
    assert monitor.records == {}
    mqtt.publish_sensor_state.assert_not_called()
    hass.log.assert_called_once()


def test_corrupt_history_is_unknown_and_is_not_overwritten() -> None:
    store = Mock()
    store.load.side_effect = ValueError("corrupt")
    monitor, _, mqtt = _monitor(store)
    monitor.start()
    assert mqtt.publish_sensor_state.call_args.args[1] == "unknown"
    assert mqtt.publish_sensor_state.call_args.kwargs["attributes"]["tests"][0]["status"] == "unknown"

    monitor.handle_test_result(
        "safety_detector_test_result",
        {"detector_key": "KitchenSmoke", "outcome": "passed"},
    )
    store.save.assert_not_called()


def test_test_status_is_reported_to_maintenance_fault_owner() -> None:
    observer = Mock()
    monitor = DetectorTestMonitor(
        Mock(), Mock(),
        {"KitchenSmoke": {"hazard": "smoke", "friendly_name": "Kitchen smoke"}},
        interval_days=180,
        state_store=InMemoryNotificationStateStore(),
        status_observer=observer,
    )
    monitor.start()
    observer.assert_called_with("KitchenSmoke", "due")
    monitor.handle_test_result(
        "safety_detector_test_result",
        {"detector_key": "KitchenSmoke", "outcome": "passed"},
    )
    observer.assert_called_with("KitchenSmoke", "current")


def test_persisted_outcomes_restore_and_overdue_tests_remain_visible() -> None:
    old = (datetime.now(timezone.utc) - timedelta(days=181)).isoformat()
    store = InMemoryNotificationStateStore()
    store.save({
        "version": 1,
        "records": {
            "KitchenSmoke": {
                "outcome": "passed",
                "source": "operator_attestation",
                "completed_at": old,
            },
            "RemovedDetector": {
                "outcome": "failed",
                "source": "operator_attestation",
                "completed_at": old,
            },
        },
    })
    monitor, hass, mqtt = _monitor(store)
    monitor.start()
    tests = mqtt.publish_sensor_state.call_args.kwargs["attributes"]["tests"]
    assert len(tests) == 1
    assert tests[0]["status"] == "overdue"
    assert tests[0]["due_at"] is not None
    monitor.stop()
    hass.cancel_listen_event.assert_called_once()
    hass.cancel_timer.assert_called_once()


@pytest.mark.parametrize("snapshot", [
    ["invalid"],
    {"version": 2, "records": {}},
    {"version": 1, "records": []},
    {"version": 1, "records": {"KitchenSmoke": []}},
    {"version": 1, "records": {"KitchenSmoke": {"outcome": "passed", "source": "other", "completed_at": "2026-01-01T00:00:00+00:00"}}},
    {"version": 1, "records": {"KitchenSmoke": {"outcome": "passed", "source": "operator_attestation", "completed_at": 42}}},
    {"version": 1, "records": {"KitchenSmoke": {"outcome": "passed", "source": "operator_attestation", "completed_at": "2026-01-01T00:00:00"}}},
])
def test_invalid_persistent_records_never_become_current(snapshot: object) -> None:
    store = Mock()
    store.load.return_value = snapshot
    monitor, _, mqtt = _monitor(store)
    monitor.start()
    assert mqtt.publish_sensor_state.call_args.kwargs["attributes"]["tests"][0]["status"] == "unknown"
    assert mqtt.publish_sensor_state.call_args.kwargs["attributes"]["storage_error"] is True
    store.save.assert_not_called()
