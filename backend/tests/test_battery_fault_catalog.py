"""Regression tests for retiring battery fault MQTT identities."""

import json
from unittest.mock import Mock

import pytest

from components.core.battery_fault_catalog import (
    BatteryFaultCatalog,
    reconcile_battery_faults,
)
from components.core.mqtt_entity_manager import MqttEntityManager


PHONE = "RemoteBatteryLowBattery" + "a" * 32
OTHER = "RemoteBatteryLowBattery" + "b" * 32


class FakeMqtt:
    """Record retained-topic cleanup requests."""

    def __init__(self) -> None:
        self.removed: list[tuple[str, bool]] = []
        self.fail = False

    def remove_sensor(self, entity_id: str, *, remove_legacy_topic: bool) -> None:
        if self.fail:
            raise RuntimeError("MQTT unavailable")
        self.removed.append((entity_id, remove_legacy_topic))


def test_exclusion_tombstones_preexisting_fault_without_catalog(tmp_path) -> None:
    catalog = BatteryFaultCatalog(tmp_path / "battery_faults.json")
    mqtt = FakeMqtt()

    reconcile_battery_faults(
        catalog, mqtt, current={OTHER}, explicitly_inactive={PHONE},
        inventory_complete=True,
    )

    assert mqtt.removed == [(f"sensor.fault_{PHONE}", True)]
    assert catalog.load() == ({OTHER}, {PHONE})
    mqtt.removed.clear()
    reconcile_battery_faults(
        catalog, mqtt, current={OTHER}, explicitly_inactive={PHONE},
        inventory_complete=True,
    )
    assert mqtt.removed == [(f"sensor.fault_{PHONE}", True)]


def test_removed_device_is_retired_and_reactivation_restores_identity(tmp_path) -> None:
    catalog = BatteryFaultCatalog(tmp_path / "battery_faults.json")
    mqtt = FakeMqtt()
    catalog.save({PHONE, OTHER}, set())

    reconcile_battery_faults(
        catalog, mqtt, current={OTHER}, explicitly_inactive=set(),
        inventory_complete=True,
    )
    assert catalog.load() == ({OTHER}, {PHONE})
    assert mqtt.removed == [(f"sensor.fault_{PHONE}", True)]

    mqtt.removed.clear()
    reconcile_battery_faults(
        catalog, mqtt, current={PHONE, OTHER}, explicitly_inactive=set(),
        inventory_complete=True,
    )
    assert catalog.load() == ({PHONE, OTHER}, set())
    assert mqtt.removed == []


def test_discovery_error_preserves_prior_dynamic_faults(tmp_path) -> None:
    catalog = BatteryFaultCatalog(tmp_path / "battery_faults.json")
    mqtt = FakeMqtt()
    catalog.save({PHONE}, set())

    reconcile_battery_faults(
        catalog, mqtt, current=set(), explicitly_inactive=set(),
        inventory_complete=False,
    )
    assert catalog.load() == ({PHONE}, set())
    assert mqtt.removed == []

    reconcile_battery_faults(
        catalog, mqtt, current=set(), explicitly_inactive=set(),
        inventory_complete=True,
    )
    assert catalog.load() == (set(), {PHONE})


def test_failed_cleanup_does_not_commit_new_catalog(tmp_path) -> None:
    catalog = BatteryFaultCatalog(tmp_path / "battery_faults.json")
    catalog.save({PHONE}, set())
    mqtt = FakeMqtt()
    mqtt.fail = True

    with pytest.raises(RuntimeError, match="MQTT unavailable"):
        reconcile_battery_faults(
            catalog, mqtt, current=set(), explicitly_inactive=set(),
            inventory_complete=True,
        )
    assert catalog.load() == ({PHONE}, set())


def test_malformed_catalog_cannot_delete_arbitrary_entity(tmp_path) -> None:
    path = tmp_path / "battery_faults.json"
    path.write_text(
        json.dumps({"version": 1, "active": ["SafetyDoorOpenTimeout"], "retired": []}),
        encoding="utf-8",
    )
    mqtt = FakeMqtt()
    with pytest.raises(ValueError, match="identities"):
        reconcile_battery_faults(
            BatteryFaultCatalog(path), mqtt, current=set(),
            explicitly_inactive=set(), inventory_complete=True,
        )
    assert mqtt.removed == []


def test_retirement_clears_all_retained_mqtt_topics(tmp_path) -> None:
    app = Mock()
    mqtt = MqttEntityManager(app)
    catalog = BatteryFaultCatalog(tmp_path / "battery_faults.json")

    reconcile_battery_faults(
        catalog, mqtt, current=set(), explicitly_inactive={PHONE},
        inventory_complete=False,
    )

    published = {
        call.kwargs["topic"]: call.kwargs
        for call in app.call_service.call_args_list
    }
    object_id = f"fault_{PHONE}".lower()
    for topic in (
        f"homeassistant/sensor/safety_component_{object_id}/config",
        f"homeassistant/sensor/{object_id}/config",
        f"safety_component/state/{object_id}",
        f"safety_component/attributes/{object_id}",
    ):
        assert published[topic]["payload"] == ""
        assert published[topic]["retain"] is True
