"""Regression tests for installation-specific production calibration."""

from pathlib import Path

import yaml


def _production_config() -> dict:
    config_path = Path(__file__).parents[1] / "app_cfg.yaml"
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))["SafetyFunctions"]


def test_production_door_timeouts_match_reviewed_calibration() -> None:
    safety_doors = _production_config()["user_config"]["safety_components"][
        "SafetyDoorsComponent"
    ]
    default_timeout = safety_doors["defaults"]["timeout_seconds"]
    doors = safety_doors["doors"]

    assert doors["GarageGate"]["timeout_seconds"] == 300
    assert doors["ExternalGate"]["timeout_seconds"] == 600
    assert doors["LivingRoomTerraceDoor"].get(
        "timeout_seconds", default_timeout
    ) == 120
    assert doors["GarageDoor"]["timeout_seconds"] == 900


def test_production_localization_and_area_references_are_explicit() -> None:
    user_config = _production_config()["user_config"]
    components = user_config["safety_components"]

    assert user_config["localization"]["language"] == "pl"
    assert all(
        room["area_id"]
        for room in components["TemperatureComponent"]["rooms"].values()
    )
    assert all(
        door["area_id"]
        for door in components["SafetyDoorsComponent"]["doors"].values()
    )


def test_production_entity_health_keys_are_explicitly_monitored() -> None:
    entities = _production_config()["user_config"]["safety_components"][
        "EntityMonitorComponent"
    ]["explicit_entities"]

    assert {
        "SmartHeatingAppHealth": "sensor.sh_health",
        "GarageDoorAppHealth": "sensor.garage_door_health_2",
        "ExternalGateAppHealth": "sensor.external_gate_health_2",
        "ExternalOpeningBedroomLeftWindow": (
            "binary_sensor.bedroom_windowleft_sensor_contact"
        ),
        "ExternalOpeningKidsRoomWindow": (
            "binary_sensor.kidsroom_window_contact_contact"
        ),
        "ExternalOpeningKitchenWindow": (
            "binary_sensor.kitchen_window_contact_contact"
        ),
        "ExternalOpeningLivingRoomTerraceDoor": (
            "binary_sensor.livingroom_door_contact_contact"
        ),
        "ExternalOpeningOfficeWindow": (
            "binary_sensor.office_window_contact_contact"
        ),
        "ExternalOpeningUpperBathroomWindow": (
            "binary_sensor.upperbathroom_window_contact_contact"
        ),
        "SafetyDoorGarageGate": (
            "binary_sensor.garage_gatedoorlow_contact_contact"
        ),
    } == {key: value["entity_id"] for key, value in entities.items()}


def test_production_mqtt_cleanup_removes_replaced_entities() -> None:
    legacy_entities = set(
        _production_config()["user_config"]["mqtt"][
            "legacy_discovery_entity_ids"
        ]
    )

    assert {
        "sensor.recovery_closeexternalopeningexternalgate",
        "sensor.recovery_closeexternalopeninggaragegate",
        "sensor.fault_entityhealthtemperaturewindowupperbathroom",
        "sensor.entity_health_temperature_window_upperbathroom",
        "sensor.fault_entityhealthtemperaturewindowbedroom",
        "sensor.entity_health_temperature_window_bedroom",
        "sensor.fault_entityhealthtemperaturewindowkidsroom",
        "sensor.entity_health_temperature_window_kidsroom",
        "sensor.fault_entityhealthtemperaturewindowkitchen",
        "sensor.entity_health_temperature_window_kitchen",
        "sensor.fault_entityhealthtemperaturewindowlivingroom",
        "sensor.entity_health_temperature_window_livingroom",
        "sensor.fault_entityhealthtemperaturewindowoffice",
        "sensor.entity_health_temperature_window_office",
        "sensor.fault_entityhealthtemperaturewindowgarage",
        "sensor.entity_health_temperature_window_garage",
    } <= legacy_entities


def test_production_internal_hazard_bindings_are_distinct_binary_channels() -> None:
    config = _production_config()
    component = config["user_config"]["safety_components"][
        "InternalEnvironmentalHazardMonitorComponent"
    ]
    detectors = component["detectors"]

    assert config["user_config"]["components_enabled"][
        "InternalEnvironmentalHazardMonitorComponent"
    ] is True
    assert detectors["BathroomFlammableGas"] == {
        "area_id": "bathroom",
        "entity_id": "binary_sensor.bathroom_gasleak_detector",
        "friendly_name": "Czujnik gazu w łazience",
        "hazard": "flammable_gas",
        "profile": "home_assistant_binary_alarm",
        "gas_identity": "flammable_gas_unspecified",
    }
    assert detectors["BathroomCarbonMonoxide"] == {
        "area_id": "bathroom",
        "entity_id": "binary_sensor.bathroom_carbonoxide_detector",
        "friendly_name": "Czujnik tlenku węgla w łazience",
        "hazard": "carbon_monoxide",
        "profile": "home_assistant_binary_alarm",
    }
