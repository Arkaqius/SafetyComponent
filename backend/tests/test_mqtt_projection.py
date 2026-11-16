"""Coherent desired/accepted MQTT state and bounded asynchronous publication."""

import json

from components.core.mqtt_entity_manager import MqttEntityManager
from components.core.mqtt_projection import MAX_GROUPS, MAX_QUEUE_BYTES
from components.core.service_dispatcher import Lane, ProcessLeaseRegistry, ResourceSpec, ServiceDispatcher
from safety_lifecycle_support import CallbackServiceAdapter, LifecycleHass


def build_mqtt():
    app, transport = LifecycleHass(), CallbackServiceAdapter()
    app.call_service = transport.call_service
    broker = ServiceDispatcher(app, [ResourceSpec("mqtt", Lane.MQTT, frozenset({"mqtt/publish"}))],
                               clock=app.clock, registry=ProcessLeaseRegistry())
    broker.start()
    manager = MqttEntityManager(app, dispatcher=broker)
    manager.start()
    return manager, broker, app, transport


def flush(manager, broker, transport, limit=30):
    transport.mode, transport.result = "immediate", {"success": True}
    for _ in range(limit):
        manager.projections.tick()
        broker.tick()


def test_desired_projection_is_detached_and_cache_acknowledges_whole_completed_group() -> None:
    manager, broker, _, transport = build_mqtt()
    attributes = {"active": True}
    manager.register_sensor("sensor.fixture", "Fixture", state="SET", attributes=attributes)
    attributes["active"] = False
    assert manager.entity_states["sensor.fixture"] == "SET"
    assert manager.accepted_states == {} and transport.calls == []
    manager.projections.tick()
    broker.tick()
    assert len(transport.calls) == 1 and manager.accepted_states == {}
    transport.complete(0, {"success": True})
    broker.tick()
    assert manager.accepted_states == {}
    flush(manager, broker, transport)
    assert manager.accepted_states == {"sensor.fixture": "SET"}
    assert manager.accepted_attributes["sensor.fixture"]["active"] is True
    topics = [data["topic"] for _, data in transport.calls]
    assert topics == [manager.discovery_topic("sensor.fixture"), manager.attributes_topic("sensor.fixture"), manager.state_topic("sensor.fixture")]


def test_new_set_coalesces_whole_unsent_group_and_stops_superseded_clear() -> None:
    manager, broker, _, transport = build_mqtt()
    manager.register_sensor("sensor.fixture", "Fixture", state="CLEARED", attributes={"active": False})
    manager.projections.tick()
    broker.tick()
    manager.publish_sensor_state("sensor.fixture", "SET", attributes={"active": True})
    transport.complete(0, {"success": True})
    broker.tick()
    flush(manager, broker, transport)
    states = [data["payload"] for _, data in transport.calls if data["topic"] == manager.state_topic("sensor.fixture")]
    assert states == ["SET"]
    assert manager.accepted_states["sensor.fixture"] == "SET"
    assert manager.projections.accepted_revisions == manager.projections.desired_revisions


def test_failed_topic_does_not_accept_cache_or_allow_online_before_startup_barrier() -> None:
    manager, broker, _, transport = build_mqtt()
    manager.register_sensor("sensor.fixture", "Fixture", state="SET", attributes={"active": True})
    manager.publish_availability()
    manager.projections.tick()
    broker.tick()
    transport.complete(0, {"success": False})
    broker.tick()
    assert manager.accepted_states == {} and manager.projections.uncertain
    flush(manager, broker, transport)
    assert manager.accepted_states == {"sensor.fixture": "SET"}
    assert transport.calls[-1][1]["payload"] == "online"
    assert manager.accepted_availability is True


def test_permanent_hang_preserves_uncertainty_and_process_mqtt_lease() -> None:
    manager, broker, app, transport = build_mqtt()
    manager.register_sensor("sensor.fixture", "Fixture", state="SET")
    manager.publish_availability()
    manager.projections.tick()
    broker.tick()
    app.clock.advance(30)
    broker.tick()
    for _ in range(10):
        manager.projections.tick()
        broker.tick()
    assert len(transport.calls) == 1
    assert broker.registry.quarantined_count == 1
    assert manager.accepted_states == {} and manager.accepted_availability is None
    assert "sensor.fixture" in manager.projections.uncertain


def test_retired_sensor_cleans_all_topics_and_retires_receipts_only_after_success() -> None:
    manager, broker, _, transport = build_mqtt()
    manager.register_sensor("sensor.fixture", "Fixture", state="SET")
    flush(manager, broker, transport)
    manager.remove_sensor("sensor.fixture", remove_legacy_topic=True)
    assert manager.accepted_states == {"sensor.fixture": "SET"}
    before = len(transport.calls)
    flush(manager, broker, transport)
    assert manager.accepted_states == {}
    assert len(transport.calls[before:]) == 4
    assert all(data["payload"] == "" and data["retain"] for _, data in transport.calls[before:])
    assert "sensor.fixture" not in manager.projections.accepted_revisions


def test_pending_count_and_encoded_byte_bounds_reject_before_any_handoff() -> None:
    manager, _, _, transport = build_mqtt()
    queue = manager.projections
    message = {"topic": "fixture", "payload": "SET", "retain": False, "qos": 0}
    for index in range(MAX_GROUPS):
        assert queue.enqueue(f"sensor.fixture_{index}", [message], {})
    assert not queue.enqueue("sensor.overflow", [message], {})
    assert len(queue.pending) == MAX_GROUPS and transport.calls == []
    assert queue.enqueue("sensor.fixture_0", [message], {})
    queue.stop()
    large = {**message, "payload": "x" * 50000}
    admitted = 0
    for index in range(100):
        if queue.enqueue(f"sensor.large_{index}", [large] * 4, {}):
            admitted += 1
    assert 40 <= admitted <= 42 and queue.pending_bytes <= MAX_QUEUE_BYTES
    assert not queue.enqueue("sensor.oversize_group", [large] * 6, {})
    assert not queue.enqueue("sensor.oversize_payload", [{**large, "payload": "x" * 65536}], {})
    assert transport.calls == []


def test_heartbeat_uses_current_coherent_desired_state_after_failed_projection() -> None:
    manager, broker, _, transport = build_mqtt()
    manager.register_sensor("sensor.fixture", "Fixture", state="CLEARED", attributes={"active": False})
    manager.publish_heartbeat()
    manager.publish_sensor_state("sensor.fixture", "SET", attributes={"active": True})
    manager.publish_heartbeat_batch()
    flush(manager, broker, transport)
    assert manager.accepted_states["sensor.fixture"] == "SET"
    attrs = [json.loads(data["payload"]) for _, data in transport.calls if "/attributes/" in data["topic"]]
    assert attrs and all(value["active"] is True for value in attrs)


def test_reload_offline_barrier_cannot_bypass_old_quarantined_call() -> None:
    old, old_broker, app, transport = build_mqtt()
    old.register_sensor("sensor.fixture", "Fixture", state="SET")
    old.projections.tick()
    old_broker.tick()
    old.stop()
    old_broker.stop()
    app.clock.advance(31)
    fresh_broker = ServiceDispatcher(
        app, [ResourceSpec("mqtt", Lane.MQTT, frozenset({"mqtt/publish"}))],
        clock=app.clock, registry=old_broker.registry,
    )
    fresh_broker.start()
    fresh = MqttEntityManager(app, dispatcher=fresh_broker)
    fresh.start()
    fresh.register_sensor("sensor.fixture", "Fixture", state="SET")
    fresh.publish_availability()
    for _ in range(4):
        fresh.projections.tick()
        fresh_broker.tick()
    assert len(transport.calls) == 1
    assert fresh_broker.registry.quarantined_count == 1
    assert fresh.accepted_availability is None
    transport.complete(0, {"success": True})
    fresh_broker.tick()
    assert transport.calls[1][1]["payload"] == "offline"
    assert old.accepted_states == {} and fresh.accepted_states == {}
    transport.complete(1, {"success": True})
    fresh_broker.tick()
    flush(fresh, fresh_broker, transport)
    assert fresh.accepted_states == {"sensor.fixture": "SET"}
    assert fresh.accepted_availability is True
    assert fresh_broker.registry.next_mqtt_fence() is None


def test_failed_offline_fence_never_authorizes_online_or_releases_barrier_early() -> None:
    manager, broker, _, transport = build_mqtt()
    broker.registry.mqtt_offline_fence({"topic": "fixture/status", "payload": "offline", "retain": True, "qos": 0})
    manager.publish_availability()
    manager.projections.tick()
    broker.tick()
    transport.complete(0, None)
    broker.tick()
    assert broker.registry.next_mqtt_fence() is not None
    assert manager.accepted_availability is None
    manager.projections.tick()
    broker.tick()
    assert transport.calls[-1][1]["payload"] == "offline"
    transport.complete(1, {"success": True})
    broker.tick()
    flush(manager, broker, transport)
    assert transport.calls[-1][1]["payload"] == "online"


def test_rejected_new_danger_fences_older_queued_clear_and_preserves_uncertainty() -> None:
    manager, broker, _, transport = build_mqtt()
    manager.register_sensor("sensor.fixture", "Fixture", state="CLEARED", attributes={"active": False})
    manager.publish_sensor_state("sensor.fixture", "SET", attributes={"active": True, "detail": "x" * 70000})
    flush(manager, broker, transport)
    assert not transport.calls and not manager.accepted_states
    assert "sensor.fixture" in manager.projections.uncertain
    manager.publish_sensor_state("sensor.fixture", "SET", attributes={"active": True})
    flush(manager, broker, transport)
    assert manager.accepted_states == {"sensor.fixture": "SET"}
    assert "sensor.fixture" not in manager.projections.uncertain


def test_failed_online_publication_retries_current_availability() -> None:
    manager, broker, _, transport = build_mqtt()
    manager.publish_availability()
    manager.projections.tick()
    broker.tick()
    transport.complete(0, {"success": False})
    broker.tick()
    flush(manager, broker, transport)
    assert manager.accepted_availability is True and not manager.projections.uncertain


def test_startup_offline_is_not_coalesced_by_online_and_idle_stop_hands_off_offline() -> None:
    manager, broker, _, transport = build_mqtt()
    manager.publish_availability(False)
    manager.register_sensor("sensor.fixture", "Fixture", state="SET")
    manager.publish_availability(True)
    flush(manager, broker, transport)
    availability = [data["payload"] for _, data in transport.calls if data["topic"] == manager.availability_topic]
    assert availability == ["offline", "online"]
    manager.stop()
    assert transport.calls[-1][1]["payload"] == "offline"
    assert not manager.projections.scope.eligible
    broker.tick()
    assert broker.registry.next_mqtt_fence() is None
