"""Contract tests for functional safety evidence and policy faults."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from components.core.functional_safety_monitor import FunctionalSafetyMonitor
from components.core.types_common import FaultState, SMState


class FakeHass:
    """Expose only read-only state and timer methods to the monitor."""

    def __init__(self, states: dict[str, dict[str, Any]]) -> None:
        self.states = states

    def get_state(self, entity: str, **_: Any) -> dict[str, Any] | None:
        return self.states.get(entity)

    def run_every(self, callback: Any, start: str, interval: int) -> tuple[Any, str, int]:
        return callback, start, interval


class FakeBus:
    """Collect policy transitions without a notification side effect."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def publish(self, _: str, **kwargs: Any) -> None:
        self.events.append(kwargs)


class FakeEntities:
    """Record diagnostic publication."""

    def __init__(self) -> None:
        self.states: list[tuple[str, str, dict[str, Any]]] = []

    def register_sensor(self, *_: Any, **__: Any) -> None:
        return None

    def publish_sensor_state(self, entity: str, state: str, *, attributes: dict[str, Any]) -> None:
        self.states.append((entity, state, attributes))


POLICY = {
    "evaluation_interval_seconds": 15,
    "memory_low_available_mib": 256,
    "memory_recovery_available_mib": 384,
    "memory_high_psi_percent": 10,
    "memory_recovery_psi_percent": 5,
    "memory_qualification_seconds": 1,
    "memory_recovery_seconds": 1,
    "cpu_high_percent": 90,
    "cpu_recovery_percent": 70,
    "cpu_qualification_seconds": 1,
    "cpu_recovery_seconds": 1,
    "wan_qualification_seconds": 1,
    "wan_recovery_seconds": 1,
    "battery_low_percent": 15,
    "resource_stale_after_seconds": 180,
    "wan_stale_after_seconds": 180,
    "update_stale_after_seconds": 180,
    "battery_stale_after_seconds": 180,
    "memory_fault_level": 2,
    "wan_fault_level": 3,
    "maintenance_fault_level": 4,
    "cpu_fault_level": 4,
}


def snapshot(value: str, *, unit: str | None = None, kind: str | None = None, old: bool = False) -> dict[str, Any]:
    """Build HA's full-state shape with an explicit sample timestamp."""

    observed = datetime.now(timezone.utc) - (timedelta(hours=1) if old else timedelta(seconds=1))
    return {
        "state": value,
        "attributes": {"unit_of_measurement": unit, "device_class": kind},
        "last_updated": observed.isoformat(),
        "last_reported": observed.isoformat(),
    }


def make_monitor(states: dict[str, dict[str, Any]]) -> tuple[FunctionalSafetyMonitor, FakeBus, FakeEntities]:
    """Configure one host, WAN, update, and remote device."""

    bus, mqtt = FakeBus(), FakeEntities()
    monitor = FunctionalSafetyMonitor(
        FakeHass(states), bus, mqtt,
        {
            "host_memory": {"available_entity": "sensor.memory", "psi_entity": "sensor.psi"},
            "updates": {"home_assistant_core": "update.core"},
            "remote_batteries": {"Remote": {"friendly_name": "Remote", "percentage_entity": "sensor.battery"}},
        },
        POLICY,
        wan_entity="binary_sensor.wan",
    )
    symptoms, _ = monitor.get_symptoms_data({monitor.component_name: monitor}, {})
    for name, symptom in symptoms.items():
        assert monitor.init_safety_mechanism(symptom.sm_name, name, {})
        assert monitor.enable_safety_mechanism(name, SMState.ENABLED)
    return monitor, bus, mqtt


def test_missing_and_wrong_unit_sources_remain_unknown_without_faults() -> None:
    monitor, bus, mqtt = make_monitor({
        "sensor.memory": snapshot("100", unit="%", kind="data_size"),
        "sensor.psi": snapshot("40", unit="%"),
        "binary_sensor.wan": snapshot("unavailable"),
        "update.core": snapshot("unavailable"),
        "sensor.battery": snapshot("unavailable", unit="%", kind="battery"),
    })

    monitor.evaluate()

    assert not bus.events
    assert mqtt.states[-1][1] == "unknown"
    assert mqtt.states[-1][2]["memory"]["reason"] == "wrong_unit"
    assert mqtt.states[-1][2]["updates"]["home_assistant_core"]["status"] == "unknown"


def test_update_and_low_battery_are_separate_level_four_conditions() -> None:
    monitor, bus, mqtt = make_monitor({
        "sensor.memory": snapshot("800", unit="MiB", kind="data_size"),
        "sensor.psi": snapshot("1", unit="%"),
        "binary_sensor.wan": snapshot("on"),
        "update.core": snapshot("on"),
        "sensor.battery": snapshot("10", unit="%", kind="battery"),
    })

    monitor.evaluate()

    faults = monitor.get_fault_definitions()
    assert faults["UpdateAvailableHomeAssistantCore"]["level"] == 4
    assert faults["RemoteBatteryLowRemote"]["level"] == 4
    assert {item["symptom_id"] for item in bus.events if item["state"] == FaultState.SET} == {
        "fsm_UpdateAvailableHomeAssistantCore", "fsm_RemoteBatteryLowRemote"
    }
    assert mqtt.states[-1][2]["memory"]["status"] == "normal"


def test_stale_update_cannot_clear_existing_fault() -> None:
    states = {"update.core": snapshot("on")}
    monitor, bus, mqtt = make_monitor(states)
    monitor.evaluate()
    assert any(item["symptom_id"] == "fsm_UpdateAvailableHomeAssistantCore" and item["state"] == FaultState.SET for item in bus.events)

    states["update.core"] = snapshot("off", old=True)
    monitor.evaluate()

    assert not any(item["symptom_id"] == "fsm_UpdateAvailableHomeAssistantCore" and item["state"] == FaultState.CLEARED for item in bus.events)
    assert mqtt.states[-1][2]["updates"]["home_assistant_core"]["status"] == "unknown"


def test_detector_maintenance_fault_does_not_control_or_clear_alarm() -> None:
    bus, mqtt = FakeBus(), FakeEntities()
    monitor = FunctionalSafetyMonitor(
        FakeHass({}), bus, mqtt, {}, POLICY,
        wan_entity=None, detector_names={"KitchenSmoke": "Kitchen smoke"},
    )
    symptoms, _ = monitor.get_symptoms_data({monitor.component_name: monitor}, {})
    symptom = symptoms["fsm_DetectorTestDueKitchenSmoke"]
    monitor.init_safety_mechanism(symptom.sm_name, symptom.name, {})
    monitor.enable_safety_mechanism(symptom.name, SMState.ENABLED)

    monitor.observe_detector_test("KitchenSmoke", "due")
    monitor.observe_detector_test("KitchenSmoke", "unknown")
    monitor.observe_detector_test("KitchenSmoke", "current")

    assert monitor.get_fault_definitions()["DetectorTestDueKitchenSmoke"]["level"] == 4
    assert [item["state"] for item in bus.events] == [FaultState.SET, FaultState.CLEARED]


def test_cpu_pressure_needs_duration_and_valid_recovery(monkeypatch) -> None:
    clock = [100.0]
    monkeypatch.setattr("components.core.functional_safety_monitor.monotonic", lambda: clock[0])
    states = {"sensor.cpu": snapshot("95", unit="%")}
    bus, mqtt = FakeBus(), FakeEntities()
    monitor = FunctionalSafetyMonitor(
        FakeHass(states), bus, mqtt,
        {"host_cpu_entity": "sensor.cpu"}, POLICY, wan_entity=None,
    )
    symptoms, _ = monitor.get_symptoms_data({monitor.component_name: monitor}, {})
    symptom = symptoms["fsm_HostCpuPressure"]
    monitor.init_safety_mechanism(symptom.sm_name, symptom.name, {})
    monitor.enable_safety_mechanism(symptom.name, SMState.ENABLED)

    monitor.evaluate()
    assert not bus.events
    clock[0] = 101.0
    monitor.evaluate()
    assert bus.events[-1]["state"] == FaultState.SET
    states["sensor.cpu"] = snapshot("65", unit="%", old=True)
    clock[0] = 102.0
    monitor.evaluate()
    assert bus.events[-1]["state"] == FaultState.SET
    states["sensor.cpu"] = snapshot("65", unit="%")
    monitor.evaluate()
    clock[0] = 103.0
    monitor.evaluate()
    assert bus.events[-1]["state"] == FaultState.CLEARED


def test_wan_requires_sustained_outage_and_recovery(monkeypatch) -> None:
    clock = [100.0]
    monkeypatch.setattr("components.core.functional_safety_monitor.monotonic", lambda: clock[0])
    states = {"binary_sensor.wan": snapshot("off")}
    monitor, bus, mqtt = make_monitor(states)

    monitor.evaluate()
    assert mqtt.states[-1][2]["wan"]["status"] == "qualifying"
    assert not any(event["symptom_id"] == "fsm_WanUnavailable" for event in bus.events)
    clock[0] = 101.0
    monitor.evaluate()
    assert mqtt.states[-1][2]["wan"]["status"] == "offline"
    assert any(event["symptom_id"] == "fsm_WanUnavailable" and event["state"] == FaultState.SET for event in bus.events)

    states["binary_sensor.wan"] = snapshot("on", old=True)
    monitor.evaluate()
    assert mqtt.states[-1][2]["wan"]["status"] == "unknown"
    assert not any(event["symptom_id"] == "fsm_WanUnavailable" and event["state"] == FaultState.CLEARED for event in bus.events)
    states["binary_sensor.wan"] = snapshot("on")
    monitor.evaluate()
    assert mqtt.states[-1][2]["wan"]["status"] == "recovering"
    clock[0] = 102.0
    monitor.evaluate()
    assert mqtt.states[-1][2]["wan"]["status"] == "online"
    assert bus.events[-1] == {"symptom_id": "fsm_WanUnavailable", "state": FaultState.CLEARED}


def test_binary_battery_and_disabled_device_do_not_duplicate_faults() -> None:
    bus, mqtt = FakeBus(), FakeEntities()
    states = {"binary_sensor.remote_battery": snapshot("on", kind="battery")}
    monitor = FunctionalSafetyMonitor(
        FakeHass(states), bus, mqtt,
        {"remote_batteries": {
            "Remote": {"friendly_name": "Remote", "low_entity": "binary_sensor.remote_battery"},
            "Excluded": {"friendly_name": "Excluded", "low_entity": "binary_sensor.other", "enabled": False},
        }},
        POLICY,
        wan_entity=None,
    )
    symptoms, _ = monitor.get_symptoms_data({monitor.component_name: monitor}, {})
    symptom = symptoms["fsm_RemoteBatteryLowRemote"]
    monitor.init_safety_mechanism(symptom.sm_name, symptom.name, {})
    monitor.enable_safety_mechanism(symptom.name, SMState.ENABLED)
    monitor.evaluate()
    monitor.evaluate()
    assert len(bus.events) == 1
    assert mqtt.states[-1][2]["remote_batteries"]["Remote"]["status"] == "low"
    assert "Excluded" not in mqtt.states[-1][2]["remote_batteries"]

    states["binary_sensor.remote_battery"] = snapshot("off")
    monitor.evaluate()
    assert bus.events[-1]["state"] == FaultState.SET
    assert mqtt.states[-1][2]["remote_batteries"]["Remote"]["status"] == "unknown"
    states["binary_sensor.remote_battery"] = snapshot("off", kind="battery")
    monitor.evaluate()
    assert bus.events[-1]["state"] == FaultState.CLEARED
