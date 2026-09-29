"""Explicit test and destructive reset contracts, without live HA actions."""

from unittest.mock import Mock

from components.core.types_common import FaultState
from components.notification_manager.notification_manager import NotificationManager
from components.notification_manager.state_store import InMemoryNotificationStateStore


def manager() -> NotificationManager:
    """Use deterministic time and an accepted HA transport stub."""
    app = Mock()
    app.call_service.return_value = {"success": True, "result": {}}
    app.get_state.return_value = None
    return NotificationManager(app, {}, clock=lambda: 1000)


def test_test_requires_confirmation_and_does_not_attest_or_actuate() -> None:
    subject = manager()
    subject.handle_test_notification("test", {})
    subject.hass_app.call_service.assert_not_called()
    subject.handle_test_notification("test", {"confirmed": True})
    assert subject.active_notification == {}
    assert subject.notification_history[-1]["fault_state"] == "TEST"
    assert subject.notification_history[-1]["kind"] == "test"
    calls = subject.hass_app.call_service.call_args_list
    assert all(call.args[0].startswith("notify/") for call in calls)
    assert "actions" not in calls[-1].kwargs["data"]
    subject.handle_test_notification("test", {"confirmed": True})
    assert subject.hass_app.call_service.call_args_list == calls


def test_reset_removes_old_journal_and_reissues_active_faults_without_local_control() -> (
    None
):
    subject = manager()
    subject.notify("Smoke", 1, FaultState.SET, {}, "active-tag")
    subject.handle_ui_acknowledgement("ack", {"tag": "active-tag"})
    old_ids = {row["id"] for row in subject.notification_history}
    subject.local_annunciator = Mock()
    subject.state_store = InMemoryNotificationStateStore()
    subject.handle_reset_notifications("reset", {"confirmed": True})
    assert not old_ids.intersection(row["id"] for row in subject.notification_history)
    assert subject.active_notification["active-tag"]["acknowledged"] is False
    assert subject.notification_history[-1]["kind"] == "new"
    assert subject._counters["accepted_attempts"] == 1
    subject.local_annunciator.activate.assert_not_called()
    subject.local_annunciator.clear.assert_not_called()
    stored = subject.state_store.load()
    assert stored["notification_history"] == subject.notification_history
    assert stored["active_notifications"]["active-tag"]["acknowledged"] is False


def test_reset_clears_offline_queue_and_preserves_active_warning_retry() -> None:
    subject = manager()
    subject.wan_online = False
    subject.notify("Smoke", 1, FaultState.SET, {}, "active-tag")
    subject.handle_test_notification("test", {"confirmed": True})
    subject._counters["failed_attempts"] = 17
    subject.handle_reset_notifications("reset", {"confirmed": True})
    assert len(subject.pending_deliveries) == 1
    assert next(iter(subject.pending_deliveries.values())).tag == "active-tag"
    assert subject.notification_history == []
    assert subject._counters["failed_attempts"] == 0


def test_unconfirmed_reset_preserves_state() -> None:
    subject = manager()
    subject.notify("Door", 3, FaultState.SET, {}, "door")
    history = list(subject.notification_history)
    subject.handle_reset_notifications("reset", {"confirmed": "true"})
    assert subject.notification_history == history
    assert "door" in subject.active_notification


def test_reset_without_active_faults_is_unknown_and_cooldowns_survive_restart() -> None:
    subject = manager()
    subject.state_store = InMemoryNotificationStateStore()
    subject.handle_test_notification("test", {"confirmed": True})
    subject.handle_reset_notifications("reset", {"confirmed": True})
    assert subject.notification_history == []
    assert subject._last_result == "reset"
    restored = NotificationManager(
        subject.hass_app, {}, state_store=subject.state_store, clock=lambda: 1001
    )
    restored.hass_app.call_service.reset_mock()
    restored.handle_test_notification("test", {"confirmed": True})
    restored.handle_reset_notifications("reset", {"confirmed": True})
    restored.hass_app.call_service.assert_not_called()
    assert restored.notification_history == []
