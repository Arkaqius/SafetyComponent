"""Owner-side mobile receipts and bounded persistence during stalled responses."""

from unittest.mock import Mock
import pytest

from components.core.service_dispatcher import Lane, ProcessLeaseRegistry, ResourceSpec, ServiceDispatcher
from components.core.snapshot_writer import SnapshotWriter
from components.core.types_common import FaultState
from components.notification_manager.mobile_push_provider import MobilePushProvider
from components.notification_manager.notification_manager import NotificationManager
from components.notification_manager.schema import NotificationConfig
from components.notification_manager.state_store import InMemoryNotificationStateStore
from safety_lifecycle_support import CallbackServiceAdapter, ControlledExecutor, LifecycleHass


def build_manager():
    app, transport, executor = LifecycleHass(), CallbackServiceAdapter(), ControlledExecutor()
    app.call_service, app.get_state = transport.call_service, Mock(return_value="off")
    services = ("notify/stalled", "notify/healthy")
    broker = ServiceDispatcher(app, [ResourceSpec(s, Lane.MOBILE, frozenset({s})) for s in services],
                               clock=app.clock, registry=ProcessLeaseRegistry())
    broker.start()
    config = NotificationConfig.model_validate({"mobile": {"services": services}}).model_dump()
    store = InMemoryNotificationStateStore()
    manager = NotificationManager(
        app, config, mobile_provider=MobilePushProvider(app, config["mobile"], dispatcher=broker),
        state_store=store, snapshot_writer=SnapshotWriter(executor), clock=app.clock,
    )
    manager.start()
    return manager, broker, app, transport, executor, store


def test_stalled_storage_and_mobile_target_do_not_block_admission_or_healthy_receipt() -> None:
    manager, broker, _, transport, executor, store = build_manager()
    manager.notify("Fixture", 1, FaultState.SET, {}, "fixture")
    assert "fixture" in manager.active_notification
    assert store.load() == {} and len(executor.jobs) == 1
    assert transport.calls == [] and manager._counters["accepted_attempts"] == 0
    broker.tick()
    transport.complete(1, {"success": True, "result": None})
    assert manager._counters["accepted_attempts"] == 0
    broker.tick()
    assert manager._counters["accepted_attempts"] == 1
    assert next(iter(manager.pending_deliveries.values())).target_services == ("notify/stalled",)
    executor.finish(0)
    manager.tick()
    assert manager._durable_revision > 0 and len(executor.jobs) == 2


def test_stop_fences_actual_ingress_and_unsent_work_even_when_final_snapshot_throws():
    manager, broker, app, transport, _, _ = build_manager()
    manager.notify("Fixture", 1, FaultState.SET, {}, "fixture")
    callbacks = [record[1] for record in app.handles.values()]
    manager._persist_state = Mock(side_effect=RuntimeError("fictional final snapshot failure"))
    with pytest.raises(RuntimeError):
        manager.stop()
    assert not manager.scope.eligible and not manager._started
    assert not manager.local_annunciator._enabled
    for callback in callbacks:
        callback()
    broker.tick()
    assert not transport.calls and "fixture" in manager.active_notification


def test_ambiguous_completion_never_accepts_and_failed_write_stays_visible() -> None:
    manager, broker, _, transport, executor, _ = build_manager()
    manager.state_store.save = Mock(side_effect=OSError("fixture"))
    manager.notify("Fixture", 2, FaultState.SET, {}, "fixture")
    broker.tick()
    for index in range(2):
        transport.complete(index, None)
    broker.tick()
    assert manager._counters["accepted_attempts"] == 0
    assert manager._counters["failed_attempts"] == 2
    executor.finish(0)
    manager.tick()
    assert manager._durability_error == "OSError"
    assert manager._durable_revision == 0 and manager.active_notification


def test_new_alarm_supersedes_unsent_clear_and_old_receipts_cannot_apply_after_stop() -> None:
    manager, broker, app, transport, _, _ = build_manager()
    manager.notify("Fixture", 1, FaultState.SET, {}, "fixture")
    manager.notify("Fixture", 1, FaultState.CLEARED, {}, "fixture")
    manager.notify("Fixture", 1, FaultState.SET, {}, "fixture")
    broker.tick()
    assert len(transport.calls) == 2
    assert all("message" in payload and "clear_notification" != payload["message"] for _, payload in transport.calls)
    owned = manager.scope.handle_count
    callbacks = [item[1] for item in app.handles.values() if item[0] in {"periodic", "event"}]
    assert owned == 5
    manager.start()
    assert manager.scope.handle_count == owned
    manager.stop()
    manager.start()
    before = manager._counters.copy()
    for index in range(2):
        transport.complete(index, {"success": True})
    broker.tick()
    for callback in callbacks:
        callback()
    assert manager._counters == before
    assert manager.scope.handle_count == owned


def test_changed_pending_content_replaces_queued_payload_without_resetting_deadline() -> None:
    manager, broker, app, transport, _, _ = build_manager()
    manager.notify("Fixture", 1, FaultState.SET, {"Location": "First"}, "fixture")
    original = next(iter(manager.pending_deliveries.values())).deadline_at
    app.clock.advance(2)
    manager.notify("Fixture", 1, FaultState.SET, {"Location": "Latest"}, "fixture")
    broker.tick()
    assert all("Latest" in payload["title"] for _, payload in transport.calls)
    assert next(iter(manager.pending_deliveries.values())).deadline_at == original


def test_retiring_tag_invalidates_queued_alert_without_sending_a_false_clear() -> None:
    manager, broker, _, transport, _, _ = build_manager()
    manager.notify("Fixture", 1, FaultState.SET, {}, "fixture")
    manager.retire_fault("fixture")
    broker.tick()
    assert not transport.calls and not manager.active_notification


def test_old_write_success_cannot_hide_rejected_newer_snapshot() -> None:
    manager, _, _, _, executor, _ = build_manager()
    manager._persist_state()
    manager._last_error = "x" * (1024 * 1024)
    manager._persist_state()
    assert manager._durability_error == "snapshot_admission_rejected"
    executor.finish(0)
    manager._drain_persistence()
    assert manager._durable_revision < manager._write_revision
    assert manager._durability_error == "snapshot_admission_rejected"


def test_unsent_rejections_and_deadlines_do_not_invent_submission_history() -> None:
    manager, broker, app, transport, _, _ = build_manager()
    manager.notification_config["level_one_repeat"]["enabled"] = False
    broker.stop()
    manager.notify("Fixture", 1, FaultState.SET, {}, "fixture")
    assert not manager.notification_history and not transport.calls
    broker.start()
    app.clock.advance(1000)
    manager.tick()
    broker.tick()
    assert not manager.notification_history and not transport.calls


def test_old_content_acceptance_does_not_extend_a_new_warning_absolute_deadline() -> None:
    manager, broker, app, transport, _, _ = build_manager()
    manager.notify("Fixture", 2, FaultState.SET, {"response_deadline_monotonic": 120}, "fixture")
    broker.tick()
    for index in range(2):
        transport.complete(index, {"success": True})
    broker.tick()
    app.clock.advance(200)
    manager.notify("Fixture", 2, FaultState.SET, {
        "location": "New opening", "response_deadline_monotonic": 190,
    }, "fixture")
    app.clock.advance(1)
    manager.tick()
    broker.tick()
    assert len(transport.calls) == 2
    assert manager._counters["deadline_misses"] == 1
