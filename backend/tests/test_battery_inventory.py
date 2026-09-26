"""Verify device discovery, source quality, exclusions, and stable fault ownership."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from components.core.functional_safety_monitor import FunctionalSafetyMonitor
from components.core.types_common import FaultState, SMState
from components.external_apis.battery_inventory import group_batteries, resolve_batteries
from configuration_model import BatteryMonitoring
from tests.test_functional_safety_monitor import FakeBus, FakeEntities, FakeHass, POLICY, snapshot

DEVICE = "a" * 32


def row(entity="sensor.battery", state="70"):
    """Build an eligible device-associated battery report."""
    return {
        "entity_id": entity, "device_id": DEVICE, "friendly_name": "Test device",
        "state": state, "last_reported": datetime.now(timezone.utc).isoformat(),
        "attributes": {"device_class": "battery", "unit_of_measurement": "%"},
    }


def test_group_percentage_and_binary_sources_into_one_device():
    inventory = group_batteries([row(), row("binary_sensor.battery_low", "off")])
    assert inventory["status"] == "ready"
    assert len(inventory["devices"]) == 1
    assert inventory["devices"][0]["low_entities"] == ["binary_sensor.battery_low"]
    assert group_batteries([]) == {"status": "ready", "devices": []}


@pytest.mark.parametrize("rows", [None, {}, [None], [row(), row()], [row()] * 513,
                                  [{**row(), "device_id": "invalid"}],
                                  [{**row(), "attributes": {"device_class": "battery", "unit_of_measurement": "V"}}]])
def test_invalid_inventory_is_not_a_successful_empty_discovery(rows):
    assert group_batteries(rows) == {"status": "error", "devices": []}


def test_manual_owner_keeps_identity_and_collects_all_sources_without_duplicates():
    inventory = group_batteries([row(), row("binary_sensor.battery_low", "on")])
    manual = {"Remote": {"friendly_name": "Manual name", "percentage_entity": "sensor.battery"},
              "Duplicate": {"friendly_name": "Duplicate", "low_entity": "binary_sensor.battery_low"}}
    resolved = resolve_batteries(manual, inventory, [])
    assert resolved["Remote"]["friendly_name"] == "Manual name"
    assert resolved["Remote"]["low_entities"] == ["binary_sensor.battery_low"]
    assert resolved["Duplicate"]["enabled"] is False
    excluded = resolve_batteries(manual, inventory, [DEVICE])
    assert all(not binding["enabled"] for binding in excluded.values())
    assert "enabled" not in manual["Remote"]


def test_configuration_defaults_and_device_identity_validation():
    assert BatteryMonitoring().enabled is True
    assert BatteryMonitoring(excluded_devices=[DEVICE, DEVICE]).excluded_devices == [DEVICE]
    with pytest.raises(ValidationError):
        BatteryMonitoring(excluded_devices=["sensor.battery"])
    with pytest.raises(ValidationError):
        BatteryMonitoring(unknown=True)


def make_discovered_monitor(*, excluded=False, enabled=True, failed=False):
    """Initialize generated symptoms against a read-only provider."""
    states = {"sensor.battery": snapshot("70", unit="%", kind="battery"),
              "binary_sensor.battery_low": snapshot("on", kind="battery")}
    class Provider:
        def discover_batteries(self):
            return group_batteries(None if failed else [row(), row("binary_sensor.battery_low", "on")])

        def poll(self, entities):
            return {entity: states[entity] for entity in entities if entity in states}

    bus, mqtt = FakeBus(), FakeEntities()
    monitor = FunctionalSafetyMonitor(FakeHass(states), bus, mqtt,
        {"battery_monitoring": {"enabled": enabled, "excluded_devices": [DEVICE] if excluded else []}},
        POLICY, wan_entity=None, state_provider=Provider())
    symptoms, _ = monitor.get_symptoms_data({monitor.component_name: monitor}, {})
    for name, symptom in symptoms.items():
        monitor.init_safety_mechanism(symptom.sm_name, name, {})
        monitor.enable_safety_mechanism(name, SMState.ENABLED)
    return monitor, bus, mqtt, states


def test_generated_fault_is_l4_and_unknown_source_does_not_heal_it():
    monitor, bus, mqtt, states = make_discovered_monitor()
    monitor.evaluate()
    assert len(bus.events) == 1
    assert bus.events[-1]["state"] == FaultState.SET
    assert next(iter(monitor.get_fault_definitions().values()))["level"] == 4
    states["binary_sensor.battery_low"] = snapshot("off", kind="battery", old=True)
    monitor.evaluate()
    assert len(bus.events) == 1
    assert mqtt.states[-1][2]["remote_batteries"][f"Battery{DEVICE}"]["status"] == "unknown"
    states["binary_sensor.battery_low"] = snapshot("off", kind="battery")
    monitor.evaluate()
    assert bus.events[-1]["state"] == FaultState.CLEARED


@pytest.mark.parametrize("options,status", [({"excluded": True}, "observed"),
                                           ({"enabled": False}, "disabled"),
                                           ({"failed": True}, "unknown")])
def test_exclusion_disabled_and_failed_discovery_do_not_create_faults(options, status):
    monitor, bus, mqtt, _ = make_discovered_monitor(**options)
    monitor.evaluate()
    assert not bus.events
    assert not any(fault.startswith("RemoteBatteryLow") for fault in monitor.get_fault_definitions())
    assert mqtt.states[-1][2]["battery_discovery"]["status"] == status
