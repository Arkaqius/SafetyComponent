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


def test_other_appdaemon_health_entities_are_explicitly_monitored() -> None:
    entities = _production_config()["user_config"]["safety_components"][
        "EntityMonitorComponent"
    ]["explicit_entities"]

    assert {
        "SmartHeatingAppHealth": "sensor.sh_health",
        "GarageDoorAppHealth": "sensor.garage_door_health",
        "ExternalGateAppHealth": "sensor.external_gate_health",
    } == {key: value["entity_id"] for key, value in entities.items()}
