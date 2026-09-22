"""Tests for separated system and installation configuration sources."""

import json
import sys
from pathlib import Path

import pytest
import yaml

from build_app_config import compile_config, main

BACKEND_DIR = Path(__file__).parents[1]


def test_example_installation_config_compiles() -> None:
    compiled = compile_config(
        user_path=BACKEND_DIR / "config" / "user_config.example.yml"
    )

    assert compiled["SafetyFunctions"]["module"] == "SafetyFunctions"
    assert compiled["SafetyFunctions"]["user_config"]["site"]["country_code"] == "PL"
    assert "installation" not in compiled["SafetyFunctions"]["user_config"]
    assert "model_version" not in compiled["SafetyFunctions"]["user_config"]


def test_cli_accepts_explicit_app_paths(tmp_path, monkeypatch) -> None:
    output_path = tmp_path / "apps.yaml"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_app_config.py",
            "--system",
            str(BACKEND_DIR / "config" / "system_config.yml"),
            "--user",
            str(BACKEND_DIR / "config" / "user_config.example.yml"),
            "--output",
            str(output_path),
        ],
    )

    main()

    assert yaml.safe_load(output_path.read_text(encoding="utf-8")) == compile_config(
        user_path=BACKEND_DIR / "config" / "user_config.example.yml"
    )


def test_cli_prints_complete_user_schema(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_app_config.py", "--print-user-schema"],
    )

    main()

    schema = json.loads(capsys.readouterr().out)
    assert schema["title"] == "UserConfigurationV2"
    assert set(schema["required"]) == {
        "model_version",
        "components_enabled",
        "notification",
        "installation",
    }
    assert schema["additionalProperties"] is False
    assert "InstallationConfig" in schema["$defs"]
    assert "ExternalHazardRole" in schema["$defs"]
    component_selection = schema["$defs"]["ComponentSelection"]
    assert component_selection["additionalProperties"] is False
    assert set(component_selection["required"]) == {
        "TemperatureComponent",
        "SafetyDoorsComponent",
        "ExternalHazardComponent",
        "EntityMonitorComponent",
        "InternalEnvironmentalHazardMonitorComponent",
    }


def test_user_example_does_not_inherit_production_entity_collections() -> None:
    compiled = compile_config(
        user_path=BACKEND_DIR / "config" / "user_config.example.yml"
    )["SafetyFunctions"]["user_config"]["safety_components"]

    assert set(compiled["TemperatureComponent"]["rooms"]) == {"LivingRoom"}
    assert set(compiled["SafetyDoorsComponent"]["doors"]) == {"EntranceDoor"}
    assert set(compiled["ExternalHazardComponent"]["openings"]) == {"LivingRoomWindow"}
    assert (
        compiled["TemperatureComponent"]["defaults"]["CAL_HIGH_TEMP_THRESHOLD"] == 28.0
    )


def test_v2_installation_generates_shared_component_bindings() -> None:
    compiled = compile_config(
        user_path=BACKEND_DIR / "config" / "user_config.example.yml"
    )["SafetyFunctions"]["user_config"]["safety_components"]

    room = compiled["TemperatureComponent"]["rooms"]["LivingRoom"]
    opening = compiled["ExternalHazardComponent"]["openings"]["LivingRoomWindow"]
    door = compiled["SafetyDoorsComponent"]["doors"]["EntranceDoor"]

    assert room["window_sensor"] == "binary_sensor.living_room_window"
    assert opening["entity_id"] == room["window_sensor"]
    assert opening["hazards"] == [
        "frost",
        "wind",
        "rain",
        "storm",
        "outdoor_air_pollution",
    ]
    assert door["entity_id"] == "binary_sensor.entrance_door"


def test_v2_preserves_installation_owned_mqtt_cleanup_ids(tmp_path) -> None:
    source = yaml.safe_load(
        (BACKEND_DIR / "config" / "user_config.example.yml").read_text(encoding="utf-8")
    )
    source["user_config"]["mqtt"]["legacy_discovery_entity_ids"] = [
        "sensor.old_safety_entity",
        "sensor.old_safety_entity",
    ]
    user_path = tmp_path / "user.yml"
    user_path.write_text(yaml.safe_dump(source), encoding="utf-8")

    mqtt = compile_config(user_path=user_path)["SafetyFunctions"]["user_config"]["mqtt"]

    assert mqtt["legacy_discovery_entity_ids"] == ["sensor.old_safety_entity"]


def test_v2_rejects_invalid_mqtt_cleanup_id(tmp_path) -> None:
    source = yaml.safe_load(
        (BACKEND_DIR / "config" / "user_config.example.yml").read_text(encoding="utf-8")
    )
    source["user_config"]["mqtt"]["legacy_discovery_entity_ids"] = [
        "binary_sensor.not_supported"
    ]
    user_path = tmp_path / "user.yml"
    user_path.write_text(yaml.safe_dump(source), encoding="utf-8")

    with pytest.raises(ValueError, match="lowercase sensor entity IDs"):
        compile_config(user_path=user_path)


def test_v2_precedence_is_system_then_installation_then_asset(tmp_path) -> None:
    source = yaml.safe_load(
        (BACKEND_DIR / "config" / "user_config.example.yml").read_text(encoding="utf-8")
    )
    installation = source["user_config"]["installation"]
    installation["defaults"]["temperature"] = {
        "high_temperature_c": 27.0,
        "forecast_horizon_hours": 3.0,
    }
    installation["rooms"]["LivingRoom"]["temperature"] = {
        "high_temperature_c": 26.0,
    }
    installation["defaults"]["safety_door"] = {"timeout_seconds": 180}
    installation["openings"]["EntranceDoor"]["safety_door"] = {"timeout_seconds": 240}
    user_path = tmp_path / "user.yml"
    user_path.write_text(yaml.safe_dump(source), encoding="utf-8")

    components = compile_config(user_path=user_path)["SafetyFunctions"]["user_config"][
        "safety_components"
    ]

    temperature = components["TemperatureComponent"]
    assert temperature["defaults"]["CAL_LOW_TEMP_THRESHOLD"] == 18.0
    assert temperature["defaults"]["CAL_HIGH_TEMP_THRESHOLD"] == 27.0
    assert temperature["rooms"]["LivingRoom"]["CAL_HIGH_TEMP_THRESHOLD"] == 26.0
    assert temperature["rooms"]["LivingRoom"]["CAL_FORECAST_TIMESPAN"] == 3.0
    assert components["SafetyDoorsComponent"]["defaults"]["timeout_seconds"] == 180
    assert (
        components["SafetyDoorsComponent"]["doors"]["EntranceDoor"]["timeout_seconds"]
        == 240
    )


def test_v2_rejects_unknown_opening_reference(tmp_path) -> None:
    source = yaml.safe_load(
        (BACKEND_DIR / "config" / "user_config.example.yml").read_text(encoding="utf-8")
    )
    source["user_config"]["installation"]["rooms"]["LivingRoom"][
        "window"
    ] = "MissingWindow"
    user_path = tmp_path / "user.yml"
    user_path.write_text(yaml.safe_dump(source), encoding="utf-8")

    with pytest.raises(ValueError, match="references unknown opening"):
        compile_config(user_path=user_path)


def test_v2_rejects_invalid_thresholds_after_inheritance(tmp_path) -> None:
    source = yaml.safe_load(
        (BACKEND_DIR / "config" / "user_config.example.yml").read_text(encoding="utf-8")
    )
    source["user_config"]["installation"]["defaults"]["temperature"] = {
        "low_temperature_c": 30.0
    }
    user_path = tmp_path / "user.yml"
    user_path.write_text(yaml.safe_dump(source), encoding="utf-8")

    with pytest.raises(ValueError, match="must be below"):
        compile_config(user_path=user_path)


def test_v2_rejects_legacy_component_bindings(tmp_path) -> None:
    source = yaml.safe_load(
        (BACKEND_DIR / "config" / "user_config.example.yml").read_text(encoding="utf-8")
    )
    source["user_config"]["safety_components"] = {}
    user_path = tmp_path / "user.yml"
    user_path.write_text(yaml.safe_dump(source), encoding="utf-8")

    with pytest.raises(ValueError, match="safety_components"):
        compile_config(user_path=user_path)


@pytest.mark.parametrize("model_version", [None, 1, 3])
def test_only_model_version_two_is_supported(tmp_path, model_version) -> None:
    source = yaml.safe_load(
        (BACKEND_DIR / "config" / "user_config.example.yml").read_text(encoding="utf-8")
    )
    if model_version is None:
        source["user_config"].pop("model_version")
    else:
        source["user_config"]["model_version"] = model_version
    user_path = tmp_path / "user.yml"
    user_path.write_text(yaml.safe_dump(source), encoding="utf-8")

    with pytest.raises(ValueError, match="supported=2"):
        compile_config(user_path=user_path)


def test_v2_requires_explicit_selection_for_every_component(tmp_path) -> None:
    source = yaml.safe_load(
        (BACKEND_DIR / "config" / "user_config.example.yml").read_text(encoding="utf-8")
    )
    del source["user_config"]["components_enabled"]["EntityMonitorComponent"]
    user_path = tmp_path / "user.yml"
    user_path.write_text(yaml.safe_dump(source), encoding="utf-8")

    with pytest.raises(ValueError, match="EntityMonitorComponent"):
        compile_config(user_path=user_path)
