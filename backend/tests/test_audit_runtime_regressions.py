"""Regressions for live heartbeat starvation and stale notification guidance."""

import hashlib
from unittest.mock import Mock

import pytest

from components.core.battery_fault_catalog import BatteryFaultCatalog, reconcile_battery_faults
from components.core.mqtt_entity_manager import MqttEntityManager
from components.core.types_common import FaultState
from components.notification_manager.notification_manager import NotificationManager
from components.notification_manager.state_store import InMemoryNotificationStateStore


def test_large_heartbeat_yields_and_reads_latest_values_without_reviving_retired_entities(monkeypatch):
    clock = Mock(return_value=1000.0)
    monkeypatch.setattr("components.core.mqtt_entity_manager.time.monotonic", clock)
    app = Mock()
    mqtt = MqttEntityManager(app)
    for index in range(437):
        mqtt.register_sensor(f"sensor.item_{index}", "Item", state="old", attributes={"value": 1})
    app.call_service.reset_mock()
    mqtt.publish_heartbeat_batch()
    assert app.call_service.call_count == 16
    mqtt.publish_sensor_state("sensor.item_30", "new", attributes={"value": 2})
    mqtt.remove_sensor("sensor.item_31")
    app.call_service.reset_mock()
    for second in range(1, 60):
        clock.return_value = 1000.0 + second
        mqtt.publish_heartbeat_batch()
    calls = app.call_service.call_args_list
    assert not any(c.kwargs["topic"].endswith("item_31") for c in calls)
    refreshed = [c.kwargs["payload"] for c in calls if c.kwargs["topic"] == "safety_component/state/item_30"]
    assert refreshed == ["new"]
    assert not mqtt._heartbeat_queue
    before = len(calls)
    mqtt.publish_heartbeat_batch()
    assert app.call_service.call_count == before


def test_failed_heartbeat_message_is_retried_before_advancing(monkeypatch):
    monkeypatch.setattr("components.core.mqtt_entity_manager.time.monotonic", lambda: 1000)
    app = Mock()
    mqtt = MqttEntityManager(app)
    mqtt.register_sensor("sensor.health", "Health", state="running")
    app.call_service.side_effect = OSError("offline")
    with pytest.raises(OSError):
        mqtt.publish_heartbeat_batch()
    app.call_service.side_effect = None
    app.call_service.reset_mock()
    mqtt.publish_heartbeat_batch()
    assert app.call_service.call_args_list[0].kwargs["payload"] == "running"
    assert not mqtt._heartbeat_queue


def make_manager():
    app = Mock()
    app.call_service.return_value = {"success": True}
    clock = Mock(return_value=1000.0)
    return NotificationManager(app, {}, clock=clock), clock


def test_guidance_withdrawal_coalesces_final_snapshot_without_delaying_new_alarm():
    subject, clock = make_manager()
    subject.notify("Weather", 2, FaultState.SET, {"location": "Salon, łazienka"}, "tag")
    assert len(subject.notification_history) == 1
    subject.upsert_recovery_guidance("salon", "Close salon", "tag")
    subject.upsert_recovery_guidance("bathroom", "Close bathroom", "tag")
    subject.notify("Weather", 2, FaultState.SET, {"location": "Łazienka"}, "tag")
    subject.remove_recovery_guidance("salon", "tag")
    pending = subject.pending_deliveries["tag:active"]
    assert pending.created_at == 1000
    subject.tick()
    assert len(subject.notification_history) == 1
    clock.return_value = 1001
    subject.tick()
    assert len(subject.notification_history) == 2
    last = subject.notification_history[-1]
    assert last["kind"] == "update"
    assert "Close bathroom" in last["message"]
    assert "Close salon" not in last["message"]
    assert subject.hass_app.call_service.call_args.kwargs["data"]["push"]["interruption-level"] == "passive"


def test_withdrawal_alone_refreshes_phone_and_resolution_cancels_pending_update():
    subject, clock = make_manager()
    subject.notify("Weather", 2, FaultState.SET, None, "tag")
    subject.upsert_recovery_guidance("window", "Close window", "tag")
    clock.return_value = 1001
    subject.tick()
    subject.remove_recovery_guidance("window", "tag")
    clock.return_value = 1002
    subject.tick()
    assert "Close window" not in subject.notification_history[-1]["message"]
    subject.upsert_recovery_guidance("window", "Close window", "tag")
    subject.notify("Weather", 2, FaultState.CLEARED, None, "tag")
    clock.return_value = 1003
    subject.tick()
    assert subject.notification_history[-1]["kind"] == "resolved"
    assert not subject.pending_deliveries


def test_retired_battery_reconciles_restored_notification_without_false_clear(tmp_path):
    subject, _ = make_manager()
    name = "RemoteBatteryLowBattery" + "a" * 32
    tag = hashlib.sha256(name.encode()).hexdigest()
    store = InMemoryNotificationStateStore()
    subject.state_store = store
    subject.notify("Phone", 4, FaultState.SET, None, tag)
    history = list(subject.notification_history)
    restored = NotificationManager(subject.hass_app, {}, state_store=store)
    catalog = BatteryFaultCatalog(tmp_path / "catalog.json")
    catalog.save({name}, set())
    retired = reconcile_battery_faults(catalog, Mock(), current=set(), explicitly_inactive=set(), inventory_complete=True)
    for fault in retired:
        restored.retire_fault(hashlib.sha256(fault.encode()).hexdigest())
    assert not restored.active_notification
    assert not store.load()["active_notifications"]
    assert restored.notification_history == history
    assert subject.hass_app.call_service.call_count == 0


def test_quiet_update_keeps_original_deadline_and_retry_targets():
    subject, clock = make_manager()
    subject.notify("Weather", 2, FaultState.SET, None, "tag")
    subject.upsert_recovery_guidance("window", "Close window", "tag")
    first = subject.pending_deliveries["tag:active"]
    first.target_services = ("notify/remaining_phone",)
    first.next_attempt_at = 1010
    original = (first.created_at, first.deadline_at)
    clock.return_value = 1005
    subject.remove_recovery_guidance("window", "tag")
    assert (first.created_at, first.deadline_at) == original
    assert first.next_attempt_at == 1010
    assert first.target_services == ("notify/remaining_phone",)
