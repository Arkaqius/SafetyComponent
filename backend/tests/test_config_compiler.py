"""Tests for separated system and installation configuration sources."""

import json
import sys
from pathlib import Path

import pytest
import yaml

from build_app_config import compile_config as _compile_config, main
from components.safetycomponents.safety_doors.safety_doors_component import (
    SafetyDoorsComponent,
)

BACKEND_DIR = Path(__file__).parents[1]
TEST_CORE_LOCATION = {"latitude": 50.0, "longitude": 20.0}


def compile_config(*args, **kwargs):
    kwargs.setdefault("home_assistant_config", TEST_CORE_LOCATION)
    return _compile_config(*args, **kwargs)


def test_example_installation_config_compiles() -> None:
    compiled = compile_config(
        user_path=BACKEND_DIR / "config" / "user_config.example.yml"
    )

    assert compiled["SafetyFunctions"]["module"] == "SafetyFunctions"
    assert compiled["SafetyFunctions"]["user_config"]["site"]["country_code"] == "PL"
    assert compiled["SafetyFunctions"]["user_config"]["site"]["latitude"] == 50.0
    assert compiled["SafetyFunctions"]["user_config"]["site"]["longitude"] == 20.0
    assert "installation" not in compiled["SafetyFunctions"]["user_config"]
    assert "model_version" not in compiled["SafetyFunctions"]["user_config"]
    assert compiled["SafetyFunctions"]["user_config"]["functional_safety"]["remote_batteries"] == {}
    assert compiled["SafetyFunctions"]["app_config"]["calibration"]["functional_safety"]["memory_low_available_mib"] == 256


def test_functional_safety_bindings_compile_and_reject_invalid_battery(tmp_path) -> None:
    source = yaml.safe_load((BACKEND_DIR / "config" / "user_config.example.yml").read_text(encoding="utf-8"))
    bindings = source["user_config"]["installation"]["functional_safety"]
    bindings["host_memory"] = {
        "available_entity": "sensor.host_memory_available",
        "psi_entity": "sensor.host_memory_psi_some",
    }
    bindings["host_cpu_entity"] = "sensor.host_processor_use"
    bindings["updates"] = {"home_assistant_core": "update.home_assistant_core_update"}
    bindings["remote_batteries"] = {
        "SmokeDetector": {"friendly_name": "Smoke detector", "percentage_entity": "sensor.smoke_battery"}
    }
    path = tmp_path / "user.yml"
    path.write_text(yaml.safe_dump(source), encoding="utf-8")
    compiled = compile_config(user_path=path)["SafetyFunctions"]["user_config"]["functional_safety"]
    assert compiled["host_memory"]["psi_entity"] == "sensor.host_memory_psi_some"
    assert compiled["host_cpu_entity"] == "sensor.host_processor_use"
    assert compiled["updates"]["home_assistant_core"] == "update.home_assistant_core_update"
    assert compiled["remote_batteries"]["SmokeDetector"]["percentage_entity"] == "sensor.smoke_battery"

    bindings["remote_batteries"]["SmokeDetector"] = {"friendly_name": "Smoke detector"}
    path.write_text(yaml.safe_dump(source), encoding="utf-8")
    with pytest.raises(ValueError, match="percentage_entity or low_entity"):
        compile_config(user_path=path)


def test_documented_example_house_compiles() -> None:
    example = BACKEND_DIR.parent / "docs" / "examples" / "example_house_user_config.yml"
    compiled = compile_config(user_path=example)["SafetyFunctions"]["user_config"]
    components = compiled["safety_components"]

    assert set(components["TemperatureComponent"]["rooms"]) == {
        "LivingRoom",
        "Bedroom",
    }
    assert (
        components["TemperatureComponent"]["rooms"]["Bedroom"]["CAL_HIGH_TEMP_THRESHOLD"]
        == 26.0
    )
    assert (
        components["EntityMonitorComponent"]["component_overrides"][
            "SafetyDoorEntranceDoor"
        ]["failure_debounce_seconds"]
        == 10
    )
    door = components["SafetyDoorsComponent"]["doors"]["EntranceDoor"]
    dependencies = SafetyDoorsComponent.get_entity_dependencies(
        [{"EntranceDoor": door}]
    )
    assert "SafetyDoorEntranceDoor" in {item["key"] for item in dependencies}
    assert (
        "UtilityHumidity"
        in components["EntityMonitorComponent"]["explicit_entities"]
    )
    assert (
        "HallSmoke"
        in components["InternalEnvironmentalHazardMonitorComponent"]["detectors"]
    )


def test_site_coordinates_are_read_from_current_home_assistant_config() -> None:
    compiled = compile_config(
        user_path=BACKEND_DIR / "config" / "user_config.example.yml",
        home_assistant_config={"latitude": -12.5, "longitude": 145.25},
    )["SafetyFunctions"]["user_config"]["site"]

    assert (compiled["latitude"], compiled["longitude"]) == (-12.5, 145.25)


def test_site_rejects_missing_or_invalid_home_assistant_coordinates() -> None:
    source = BACKEND_DIR / "config" / "user_config.example.yml"
    with pytest.raises(ValueError, match="Home Assistant Core location is required"):
        _compile_config(user_path=source)
    with pytest.raises(ValueError, match="latitude"):
        _compile_config(
            user_path=source,
            home_assistant_config={"latitude": 100.0, "longitude": 20.0},
        )


def test_user_source_rejects_persisted_coordinates_and_forecast_horizon(
    tmp_path,
) -> None:
    source = yaml.safe_load(
        (BACKEND_DIR / "config" / "user_config.example.yml").read_text(encoding="utf-8")
    )
    source["user_config"]["installation"]["site"]["latitude"] = 50.0
    user_path = tmp_path / "user.yml"
    user_path.write_text(yaml.safe_dump(source), encoding="utf-8")
    with pytest.raises(ValueError, match="latitude"):
        compile_config(user_path=user_path)

    del source["user_config"]["installation"]["site"]["latitude"]
    source["user_config"]["installation"]["component_settings"]["temperature"][
        "forecast_horizon_hours"
    ] = 3
    user_path.write_text(yaml.safe_dump(source), encoding="utf-8")
    with pytest.raises(ValueError, match="forecast_horizon_hours"):
        compile_config(user_path=user_path)

    del source["user_config"]["installation"]["component_settings"]["temperature"][
        "forecast_horizon_hours"
    ]
    source["user_config"]["installation"]["component_settings"]["external_hazard"][
        "hazards"
    ] = ["frost"]
    user_path.write_text(yaml.safe_dump(source), encoding="utf-8")
    with pytest.raises(ValueError, match="hazards"):
        compile_config(user_path=user_path)

    del source["user_config"]["installation"]["component_settings"]["external_hazard"][
        "hazards"
    ]
    source["user_config"]["installation"]["component_settings"]["external_hazard"][
        "weather"
    ] = {"forecast_horizon_hours": 3}
    user_path.write_text(yaml.safe_dump(source), encoding="utf-8")
    with pytest.raises(ValueError, match="forecast_horizon_hours"):
        compile_config(user_path=user_path)


def test_cli_accepts_explicit_app_paths(tmp_path, monkeypatch) -> None:
    output_path = tmp_path / "apps.yaml"
    location_path = tmp_path / "ha-location.json"
    location_path.write_text(json.dumps(TEST_CORE_LOCATION), encoding="utf-8")
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
            "--home-assistant-config",
            str(location_path),
        ],
    )

    main()

    assert yaml.safe_load(output_path.read_text(encoding="utf-8")) == compile_config(
        user_path=BACKEND_DIR / "config" / "user_config.example.yml"
    )


def test_home_assistant_log_level_overrides_packaged_default() -> None:
    compiled = compile_config(
        user_path=BACKEND_DIR / "config" / "user_config.example.yml",
        log_level="DEBUG",
    )

    assert compiled["SafetyFunctions"]["log_level"] == "DEBUG"


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


def test_cli_prints_complete_system_schema(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_app_config.py", "--print-system-schema"],
    )

    main()

    schema = json.loads(capsys.readouterr().out)
    assert schema["title"] == "SystemConfigurationV2"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "system_config",
        "app_definition",
        "validation",
        "calibration",
        "runtime_cfg",
    }
    assert schema["$defs"]["ProviderRuntimeSet"]["additionalProperties"] is False


def test_system_source_rejects_unknown_keys(tmp_path) -> None:
    system = yaml.safe_load(
        (BACKEND_DIR / "config" / "system_config.yml").read_text(encoding="utf-8")
    )
    system["calibration"]["temperature"]["unknown_threshold"] = 1
    system_path = tmp_path / "system.yml"
    system_path.write_text(yaml.safe_dump(system), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown_threshold"):
        compile_config(
            system_path=system_path,
            user_path=BACKEND_DIR / "config" / "user_config.example.yml",
        )


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


@pytest.mark.parametrize("obsolete_field", ["mqtt", "entity_names"])
def test_v2_rejects_removed_user_fields(tmp_path, obsolete_field: str) -> None:
    source = yaml.safe_load(
        (BACKEND_DIR / "config" / "user_config.example.yml").read_text(encoding="utf-8")
    )
    if obsolete_field == "mqtt":
        source["user_config"]["mqtt"] = {"legacy_discovery_entity_ids": []}
    else:
        source["user_config"]["localization"]["entity_names"] = {}
    user_path = tmp_path / "user.yml"
    user_path.write_text(yaml.safe_dump(source), encoding="utf-8")

    with pytest.raises(ValueError, match=obsolete_field):
        compile_config(user_path=user_path)


def test_v2_precedence_is_system_then_installation_then_asset(tmp_path) -> None:
    source = yaml.safe_load(
        (BACKEND_DIR / "config" / "user_config.example.yml").read_text(encoding="utf-8")
    )
    installation = source["user_config"]["installation"]
    installation["component_settings"]["temperature"] = {
        "high_temperature_c": 27.0,
    }
    installation["rooms"]["LivingRoom"]["temperature"] = {
        "high_temperature_c": 26.0,
    }
    installation["component_settings"]["safety_door"] = {"timeout_seconds": 180}
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
    assert temperature["rooms"]["LivingRoom"]["CAL_FORECAST_TIMESPAN"] == 2.0
    assert components["SafetyDoorsComponent"]["defaults"]["timeout_seconds"] == 180
    assert (
        components["SafetyDoorsComponent"]["doors"]["EntranceDoor"]["timeout_seconds"]
        == 240
    )


def test_v2_overrides_system_policy_defaults_from_installation(tmp_path) -> None:
    source = yaml.safe_load(
        (BACKEND_DIR / "config" / "user_config.example.yml").read_text(encoding="utf-8")
    )
    defaults = source["user_config"]["installation"]["component_settings"]
    defaults["entity_monitor"] = {
        "startup_grace_seconds": 15,
        "evaluation_interval_seconds": 2,
    }
    defaults["external_hazard"] = {
        "weather": {
            "frost_watch_c": 3.0,
            "frost_warning_c": 1.0,
        },
        "outdoor_air_quality": {"warning_at": 55},
    }
    source["user_config"]["providers"] = {
        "ImgwWarningsApiComponent": {"enabled": False}
    }
    user_path = tmp_path / "user.yml"
    user_path.write_text(yaml.safe_dump(source), encoding="utf-8")

    compiled = compile_config(user_path=user_path)["SafetyFunctions"]
    entity_monitor = compiled["app_config"]["calibration"]["entity_monitor"]
    policy = compiled["app_config"]["external_hazard_policy"]

    assert entity_monitor["startup_grace_seconds"] == 15
    assert entity_monitor["evaluation_interval_seconds"] == 2
    assert policy["weather"]["frost_watch_c"] == 3.0
    assert policy["weather"]["frost_warning_c"] == 1.0
    assert policy["outdoor_air_quality"]["warning_at"] == 55
    assert (
        compiled["user_config"]["api_components"]["ImgwWarningsApiComponent"]["enabled"]
        is False
    )


def test_generated_runtime_has_one_system_version_contract() -> None:
    compiled = compile_config(
        user_path=BACKEND_DIR / "config" / "user_config.example.yml"
    )["SafetyFunctions"]

    assert "config_version" not in compiled["app_config"]
    assert "strict_validation" not in compiled["app_config"]
    assert compiled["app_config"]["validation"]["strict_validation"] is True
    assert (
        "SM_TC_1_DEBOUNCE_LIMIT"
        not in compiled["app_config"]["calibration"]["temperature"]
    )
    assert (
        compiled["app_config"]["calibration"]["temperature"]["sm_tc_1_debounce_limit"]
        == 2
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
    source["user_config"]["installation"]["component_settings"]["temperature"] = {
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
