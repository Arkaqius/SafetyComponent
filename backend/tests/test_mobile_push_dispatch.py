"""Mobile target admission and lifecycle ordering through the bounded broker."""

from components.core.service_dispatcher import Lane, ProcessLeaseRegistry, ResourceSpec, ServiceDispatcher
from components.notification_manager.mobile_push_provider import MobilePushProvider
from components.notification_manager.models import DeliveryDisposition
from components.notification_manager.schema import NotificationConfig
from safety_lifecycle_support import CallbackServiceAdapter, LifecycleHass


def build_provider(names: tuple[str, ...] = ("notify/fixture",)) -> tuple[
    MobilePushProvider, ServiceDispatcher, LifecycleHass, CallbackServiceAdapter,
]:
    app, adapter = LifecycleHass(), CallbackServiceAdapter()
    app.call_service = adapter.call_service
    broker = ServiceDispatcher(
        app, [ResourceSpec(name, Lane.MOBILE, frozenset({name})) for name in names],
        clock=app.clock, registry=ProcessLeaseRegistry(),
    )
    broker.start()
    config = NotificationConfig.model_validate({"mobile": {"services": names}})
    return MobilePushProvider(app, config.mobile.model_dump(), dispatcher=broker), broker, app, adapter


def test_scheduling_is_queued_until_owner_validates_explicit_success() -> None:
    provider, broker, _, adapter = build_provider(("notify/a", "notify/b"))
    adapter.mode, adapter.result = "immediate", {"success": True, "result": None}
    received = []
    result = provider.send(level=1, title="Fixture", message="Alarm", tag="tag",
                           acknowledgement_title="Ack", on_complete=received.append)
    assert not result.accepted
    assert all(target.disposition == DeliveryDisposition.QUEUED for target in result.targets)
    assert not adapter.calls and not received
    broker.tick()
    assert len(adapter.calls) == 2 and not received
    broker.tick()
    assert len(received) == 2
    assert all(target.disposition == DeliveryDisposition.ACCEPTED for target in received)


def test_stalled_target_exposes_deadline_while_healthy_target_accepts() -> None:
    provider, broker, app, adapter = build_provider(("notify/stalled", "notify/healthy"))
    received = []
    provider.send(level=2, title="Fixture", message="Alarm", tag="tag",
                  acknowledgement_title="Ack", on_complete=received.append, deadline_at=30)
    broker.tick()
    adapter.complete(1, {"success": True})
    broker.tick()
    assert len(received) == 1 and received[0].service == "notify/healthy"
    app.clock.advance(30)
    broker.tick()
    assert received[-1].service == "notify/stalled"
    assert received[-1].deadline_missed
    assert received[-1].disposition != DeliveryDisposition.ACCEPTED
    assert broker.registry.quarantined_count == 1


def test_latest_quiet_update_keeps_undelivered_alert_urgency() -> None:
    provider, broker, _, adapter = build_provider()
    adapter.mode, adapter.result = "immediate", {"success": True}
    provider.send(level=1, title="Original", message="Original", tag="tag", acknowledgement_title="Ack")
    provider.send(level=1, title="Latest", message="Latest", tag="tag", acknowledgement_title="Ack", quiet=True)
    broker.tick()
    assert len(adapter.calls) == 1
    data = adapter.calls[0][1]
    assert data["message"] == "Latest"
    assert data["data"]["priority"] == "high"
    assert "alert_once" not in data["data"]
    broker.tick()
    provider.send(level=1, title="Refresh", message="Refresh", tag="tag", acknowledgement_title="Ack", quiet=True)
    broker.tick()
    assert adapter.calls[-1][1]["data"]["alert_once"] is True


def test_new_alarm_supersedes_unsent_clear_and_stop_never_dispatches_old_work() -> None:
    provider, broker, _, adapter = build_provider()
    provider.clear("tag")
    provider.send(level=1, title="New alarm", message="ALARM", tag="tag", acknowledgement_title="Ack")
    broker.tick()
    assert adapter.calls[0][1]["message"] == "ALARM"
    provider.send(level=1, title="Queued", message="Queued", tag="other", acknowledgement_title="Ack")
    provider.stop()
    provider.start()
    broker.tick()
    assert len(adapter.calls) == 1


def test_rejected_async_payload_has_no_synchronous_fallback() -> None:
    provider, broker, _, adapter = build_provider()
    result = provider.send(level=1, title="Fixture", message="x" * 70000, tag="tag", acknowledgement_title="Ack")
    broker.tick()
    assert not result.accepted
    assert result.targets[0].disposition == DeliveryDisposition.FAILED
    assert not adapter.calls
