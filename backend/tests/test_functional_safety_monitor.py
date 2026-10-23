"""Contract tests for functional safety evidence and policy faults."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from components.core.functional_safety_diagnostics import (
    InMemoryFunctionalSafetyDiagnosticsStore,
)
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
        self.unavailable: list[dict[str, Any]] = []

    def publish(self, event_type: str, **kwargs: Any) -> None:
        if event_type == "evaluation_unavailable":
            self.unavailable.append(kwargs)
        else:
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
    # Individual policy tests evaluate each supplied sample immediately.
    "maintenance_poll_interval_seconds": 0,
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
    "warning_fault_level": 3,
    "maintenance_fault_level": 4,
    "cpu_fault_level": 3,
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


@pytest.mark.parametrize("value,expected", [("94", FaultState.CLEARED), ("1", FaultState.SET)])
def test_unchanged_battery_is_evaluated_using_current_device_contact(value, expected):
    """A device heartbeat qualifies its existing value, including a low battery."""
    battery = snapshot(value, unit="%", kind="battery", old=True)
    battery.update(last_contact_source_count=1, last_contact_source_entity="sensor.remote_last_seen",
                   last_contact_at=snapshot("on")["last_reported"])
    monitor, _, mqtt = make_monitor({"sensor.battery": battery})
    monitor.evaluate()
    assert monitor.symptom_states["fsm_RemoteBatteryLowRemote"] == expected
    assert mqtt.states[-1][2]["remote_batteries"]["Remote"]["percentage"] == float(value)


@pytest.mark.parametrize("contact", [
    {"last_contact_source_count": 1},
    {"last_contact_source_count": 2},
    {"last_contact_source_count": 1, "last_contact_at": "unavailable"},
    {"last_contact_source_count": 1, "last_contact_at": "2020-01-01T00:00:00+00:00"},
    {"last_contact_source_count": 1, "last_contact_at": "2999-01-01T00:00:00+00:00"},
])
def test_failed_device_contact_never_falls_back_to_fresh_battery_report(contact):
    """Losing selected contact withdraws evidence instead of clearing a warning."""
    states = {"sensor.battery": snapshot("1", unit="%", kind="battery")}
    monitor, bus, mqtt = make_monitor(states)
    monitor.evaluate()
    assert monitor.symptom_states["fsm_RemoteBatteryLowRemote"] == FaultState.SET
    count = len(bus.events)
    states["sensor.battery"] = {**snapshot("94", unit="%", kind="battery"),
                               "last_contact_source_entity": "sensor.remote_last_seen", **contact}
    monitor.evaluate()
    assert len(bus.events) == count
    assert monitor.symptom_states["fsm_RemoteBatteryLowRemote"] == FaultState.NOT_TESTED
    assert mqtt.states[-1][2]["remote_batteries"]["Remote"]["status"] == "unknown"


@pytest.mark.parametrize("value,unit,kind", [
    ("unavailable", "%", "battery"), ("nan", "%", "battery"),
    ("101", "%", "battery"), ("-1", "%", "battery"),
    ("80", "V", "battery"), ("80", "%", "temperature"),
])
def test_current_device_contact_does_not_replace_invalid_battery_data(value, unit, kind):
    battery = snapshot(value, unit=unit, kind=kind)
    battery.update(last_contact_source_count=1, last_contact_source_entity="sensor.remote_last_seen",
                   last_contact_at=snapshot("on")["last_reported"])
    monitor, bus, _ = make_monitor({"sensor.battery": battery})
    monitor.evaluate()
    assert not bus.events
    assert monitor.symptom_states["fsm_RemoteBatteryLowRemote"] == FaultState.NOT_TESTED


def test_battery_without_device_contact_uses_its_native_report():
    battery = snapshot("90", unit="%", kind="battery")
    battery["last_contact_source_count"] = 0
    monitor, _, _ = make_monitor({"sensor.battery": battery})
    monitor.evaluate()
    assert monitor.symptom_states["fsm_RemoteBatteryLowRemote"] == FaultState.CLEARED


@pytest.mark.parametrize("state,expected", [("on", FaultState.SET), ("off", FaultState.CLEARED)])
def test_binary_low_battery_uses_device_contact(state, expected):
    battery = snapshot(state, kind="battery", old=True)
    battery.update(last_contact_source_count=1, last_contact_source_entity="sensor.remote_last_seen",
                   last_contact_at=snapshot("on")["last_reported"])
    monitor, _, _ = make_monitor({"binary_sensor.battery": battery})
    monitor.bindings["remote_batteries"]["Remote"] = {
        "friendly_name": "Remote", "low_entity": "binary_sensor.battery",
    }
    monitor.evaluate()
    assert monitor.symptom_states["fsm_RemoteBatteryLowRemote"] == expected


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


def test_lost_maintenance_evidence_withdraws_startup_observation_then_requalifies():
    """A queued battery warning must not replay after its input becomes unknown."""
    states = {"sensor.battery": snapshot("10", unit="%", kind="battery")}
    monitor, bus, _ = make_monitor(states)
    monitor.evaluate()
    identity = "fsm_RemoteBatteryLowRemote"
    assert monitor.symptom_states[identity] == FaultState.SET
    states["sensor.battery"] = snapshot("unavailable", unit="%", kind="battery")
    monitor.evaluate()
    assert monitor.symptom_states[identity] == FaultState.NOT_TESTED
    assert bus.unavailable[-1] == {"symptom_id": identity}
    states["sensor.battery"] = snapshot("10", unit="%", kind="battery")
    monitor.evaluate()
    assert monitor.symptom_states[identity] == FaultState.SET
    assert bus.events[-1] == {"symptom_id": identity, "state": FaultState.SET}


def test_battery_summary_omits_raw_source_snapshots_when_stale() -> None:
    monitor, bus, mqtt = make_monitor({"sensor.battery": snapshot("73", unit="%", kind="battery", old=True), "binary_sensor.wan": snapshot("on")})
    monitor.evaluate()
    item = mqtt.states[-1][2]["remote_batteries"]["Remote"]
    assert item["status"] == "unknown"
    assert item["percentage"] is None
    assert item["source_entities"] == ["sensor.battery"]
    assert "sources" not in item
    assert mqtt.states[-1][2]["wan"]["checked_at"]
    assert "sources" not in mqtt.states[-1][2]["wan"]
    assert not any(event["symptom_id"] == "fsm_RemoteBatteryLowRemote" for event in bus.events)


def test_full_diagnostics_store_retains_raw_evidence_outside_entity() -> None:
    monitor, _, mqtt = make_monitor(
        {
            "sensor.battery": snapshot("73", unit="%", kind="battery", old=True),
            "binary_sensor.wan": snapshot("on"),
        }
    )
    store = InMemoryFunctionalSafetyDiagnosticsStore()
    monitor.diagnostics_store = store

    monitor.evaluate()

    payload = store.load()
    battery = payload["diagnostics"]["remote_batteries"]["Remote"]
    assert payload["schema_version"] == 1
    assert payload["overall_state"] == mqtt.states[-1][1]
    assert payload["generated_at"] == mqtt.states[-1][2]["observed_at"]
    assert battery["sources"][0]["state"] == "73"
    assert battery["sources"][0]["last_reported"]
    assert "sources" not in mqtt.states[-1][2]["remote_batteries"]["Remote"]


def test_functional_safety_summary_stays_below_recorder_limit() -> None:
    monitor, _, _ = make_monitor({})
    diagnostics = {
        "memory": {"status": "normal", "sources": [{"state": "raw" * 10_000}]},
        "cpu": {"status": "normal"},
        "disk": {"status": "normal"},
        "host_temperature": {"status": "normal"},
        "backup": {"status": "current"},
        "wan": {"status": "online", "sources": [{"state": "raw" * 10_000}]},
        "updates": {},
        "battery_discovery": {"status": "observed", "device_count": 200},
        "remote_batteries": {
            f"Battery{index:03d}": {
                "status": "low" if index == 199 else "current",
                "friendly_name": "Remote battery " + ("x" * 1_000),
                "percentage": index % 100,
                "source_entities": [f"sensor.battery_{index}_{suffix}" for suffix in range(10)],
                "sources": [{"state": "raw" * 1_000}],
            }
            for index in range(200)
        },
    }

    attributes = monitor._bounded_summary(diagnostics)
    serialized = json.dumps(attributes, ensure_ascii=False).encode("utf-8")

    assert len(serialized) < 16 * 1024
    assert attributes["remote_battery_count"] == 200
    assert attributes["remote_battery_omitted_count"] > 0
    assert next(iter(attributes["remote_batteries"])) == "Battery199"
    assert all("sources" not in item for item in attributes["remote_batteries"].values())


def test_update_warning_and_low_battery_information_are_independent() -> None:
    monitor, bus, mqtt = make_monitor({
        "sensor.memory": snapshot("800", unit="MiB", kind="data_size"),
        "sensor.psi": snapshot("1", unit="%"),
        "binary_sensor.wan": snapshot("on"),
        "update.core": snapshot("on"),
        "sensor.battery": snapshot("10", unit="%", kind="battery"),
    })

    monitor.evaluate()

    faults = monitor.get_fault_definitions()
    assert faults["UpdateAvailableHomeAssistantCore"]["level"] == 3
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
    assert bus.unavailable == [{"symptom_id": "fsm_DetectorTestDueKitchenSmoke"}]
    monitor.observe_detector_test("KitchenSmoke", "current")

    assert monitor.get_fault_definitions()["DetectorTestDueKitchenSmoke"]["level"] == 3
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


def test_cpu_normal_evidence_returns_after_unavailable_without_clearing_a_qualifying_failure() -> None:
    states = {"sensor.cpu": snapshot("20", unit="%")}
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
    assert bus.events[-1]["state"] == FaultState.CLEARED
    states["sensor.cpu"] = snapshot("unavailable", unit="%")
    monitor.evaluate()
    assert bus.unavailable == [{"symptom_id": "fsm_HostCpuPressure"}]
    states["sensor.cpu"] = snapshot("95", unit="%")
    monitor.evaluate()
    assert len(bus.events) == 1
    states["sensor.cpu"] = snapshot("20", unit="%")
    monitor.evaluate()
    assert [row["state"] for row in bus.events] == [FaultState.CLEARED] * 2


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
