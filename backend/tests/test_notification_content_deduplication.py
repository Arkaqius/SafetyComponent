"""Quiet updates follow actual per-target acceptance, not queued intentions."""

from unittest.mock import Mock

import pytest

from components.core.types_common import FaultState
from components.notification_manager.notification_manager import NotificationManager
from components.notification_manager.state_store import InMemoryNotificationStateStore


def make_manager(services=None, store=None):
    app = Mock()
    app.call_service.return_value = {"success": True}
    clock = Mock(return_value=1000.0)
    config = {"mobile": {"services": services}} if services else {}
    manager = NotificationManager(app, config, clock=clock, state_store=store)
    return manager, app, clock


def test_identical_set_and_guidance_refreshes_do_not_submit_or_change_counters():
    manager, app, clock = make_manager()
    manager.notify("Window unavailable", 3, FaultState.SET, None, "window")
    counters = dict(manager._counters)
    for _ in range(6):
        clock.return_value += 60
        manager.notify("Window unavailable", 3, FaultState.SET, None, "window")
        manager.tick()
    assert app.call_service.call_count == 1
    assert len(manager.notification_history) == 1
    assert manager._counters == counters
    assert not manager.pending_deliveries

    manager.upsert_recovery_guidance("inspect", "Inspect the window", "window")
    clock.return_value += 1
    manager.tick()
    manager.upsert_recovery_guidance("inspect", "Inspect the window", "window")
    clock.return_value += 60
    manager.tick()
    assert app.call_service.call_count == 2
    assert len(manager.notification_history) == 2
    assert not manager.pending_deliveries


def test_return_to_accepted_content_cancels_unsent_update():
    manager, app, clock = make_manager()
    manager.notify("Window", 3, FaultState.SET, None, "window")
    manager.upsert_recovery_guidance("inspect", "Inspect the window", "window")
    assert manager.pending_deliveries
    manager.remove_recovery_guidance("inspect", "window")
    assert not manager.pending_deliveries
    clock.return_value += 120
    manager.tick()
    assert app.call_service.call_count == 1
    assert manager._counters["deadline_misses"] == 0


def test_accepted_content_survives_restart_and_legacy_state_does_not_assume_acceptance():
    store = InMemoryNotificationStateStore()
    manager, _, _ = make_manager(store=store)
    manager.notify("Window", 3, FaultState.SET, None, "window")
    restored, app, clock = make_manager(store=store)
    restored.notify("Window", 3, FaultState.SET, None, "window")
    assert not restored.pending_deliveries
    assert app.call_service.call_count == 0
    # Older snapshots have no full-content acceptance evidence.
    snapshot = store.load()
    del snapshot["active_notifications"]["window"]["_accepted_content_by_service"]
    store.save(snapshot)
    legacy, app, clock = make_manager(store=store)
    legacy.notify("Window", 3, FaultState.SET, None, "window")
    clock.return_value += 1
    legacy.tick()
    assert app.call_service.call_count == 1
    legacy.notify("Window", 3, FaultState.SET, None, "window")
    assert not legacy.pending_deliveries


@pytest.mark.parametrize("cache", [None, "invalid", {"notify/mobile_app_example_phone": "invalid"}])
def test_malformed_acceptance_cache_is_not_positive_acceptance_evidence(cache):
    store = InMemoryNotificationStateStore()
    manager, _, _ = make_manager(store=store)
    manager.notify("Window", 3, FaultState.SET, None, "window")
    snapshot = store.load()
    snapshot["active_notifications"]["window"]["_accepted_content_by_service"] = cache
    store.save(snapshot)
    restored, _, _ = make_manager(store=store)
    restored.notify("Window", 3, FaultState.SET, None, "window")
    assert restored.pending_deliveries


def test_duplicate_update_preserves_undelivered_new_alarm_and_its_deadline():
    manager, app, clock = make_manager(["notify/one", "notify/two"])
    app.call_service.side_effect = lambda service, **_: {"success": service != "notify/two"}
    manager.notify("Window", 3, FaultState.SET, None, "window")
    pending = manager.pending_deliveries["window:active"]
    original = (pending.created_at, pending.deadline_at, pending.next_attempt_at)
    app.call_service.reset_mock()
    manager.notify("Window", 3, FaultState.SET, None, "window")
    assert list(manager.pending_deliveries) == ["window:active"]
    assert pending.kind == "new"
    assert pending.target_services == ("notify/two",)
    assert (pending.created_at, pending.deadline_at, pending.next_attempt_at) == original
    app.call_service.side_effect = None
    clock.return_value = pending.next_attempt_at
    manager.tick()
    assert app.call_service.call_count == 1
    assert app.call_service.call_args.args == ("notify/two",)
    assert "alert_once" not in app.call_service.call_args.kwargs["data"]


def test_partial_update_deduplicates_successful_target_but_retries_failed_target():
    manager, app, clock = make_manager(["notify/one", "notify/two"])
    manager.notify("Window", 3, FaultState.SET, None, "window")
    manager.upsert_recovery_guidance("inspect", "Inspect window", "window")
    app.call_service.side_effect = lambda service, **_: {"success": service != "notify/two"}
    clock.return_value += 1
    manager.tick()
    pending = manager.pending_deliveries["window:active"]
    original = (pending.deadline_at, pending.next_attempt_at)
    app.call_service.reset_mock()
    manager.upsert_recovery_guidance("inspect", "Inspect window", "window")
    assert pending.target_services == ("notify/two",)
    assert (pending.deadline_at, pending.next_attempt_at) == original
    app.call_service.side_effect = None
    clock.return_value = pending.next_attempt_at
    manager.tick()
    assert app.call_service.call_count == 1
    assert app.call_service.call_args.args == ("notify/two",)
    assert not manager.pending_deliveries


def test_new_content_reaches_previously_successful_target_without_extending_retry():
    manager, app, clock = make_manager(["notify/one", "notify/two"])
    manager.notify("Window", 3, FaultState.SET, None, "window")
    manager.upsert_recovery_guidance("inspect", "Old instruction", "window")
    app.call_service.side_effect = lambda service, **_: {"success": service != "notify/two"}
    clock.return_value += 1
    manager.tick()
    pending = manager.pending_deliveries["window:active"]
    original = (pending.deadline_at, pending.next_attempt_at)
    manager.upsert_recovery_guidance("inspect", "New instruction", "window")
    assert pending.target_services == ("notify/one", "notify/two")
    assert (pending.deadline_at, pending.next_attempt_at) == original
    app.call_service.side_effect = None
    app.call_service.reset_mock()
    clock.return_value = pending.next_attempt_at
    manager.tick()
    assert app.call_service.call_count == 2
    assert all("New instruction" in call.kwargs["message"] for call in app.call_service.call_args_list)


def test_withdrawal_escalation_resolution_and_reopening_are_not_suppressed():
    manager, app, clock = make_manager()
    manager.notify("Window", 3, FaultState.SET, None, "window")
    manager.upsert_recovery_guidance("inspect", "Inspect window", "window")
    clock.return_value += 1
    manager.tick()
    manager.remove_recovery_guidance("inspect", "window")
    clock.return_value += 1
    manager.tick()
    assert "Inspect window" not in manager.notification_history[-1]["message"]
    manager.notify("Window", 2, FaultState.SET, None, "window")
    assert manager.notification_history[-1]["kind"] == "new"
    assert "alert_once" not in app.call_service.call_args.kwargs["data"]
    manager.notify("Window", 2, FaultState.CLEARED, None, "window")
    assert manager.notification_history[-1]["kind"] == "resolved"
    manager.notify("Window", 2, FaultState.SET, None, "window")
    assert manager.notification_history[-1]["kind"] == "new"


def test_full_content_is_compared_even_when_journal_text_is_truncated():
    manager, app, clock = make_manager()
    manager.notify("Window", 3, FaultState.SET, {"location": "X" * 5000 + "A"}, "window")
    manager.notify("Window", 3, FaultState.SET, {"location": "X" * 5000 + "B"}, "window")
    clock.return_value += 1
    manager.tick()
    assert app.call_service.call_count == 2
    assert app.call_service.call_args.kwargs["message"].endswith("B")
