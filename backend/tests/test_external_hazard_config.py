"""Fail-fast configuration tests for the complete C-EXT contract."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from build_app_config import compile_config
from components.app_config_validator.app_cfg_validator import (
    AppCfgValidationError,
    AppCfgValidator,
)


BACKEND_DIR = Path(__file__).parents[1]


def _example_config() -> dict:
    return compile_config(
        user_path=BACKEND_DIR / "config" / "user_config.example.yml",
        home_assistant_config={"latitude": 50.0, "longitude": 20.0},
    )["SafetyFunctions"]


def test_external_hazard_config_normalizes_all_three_independent_providers() -> None:
    runtime = AppCfgValidator.validate(_example_config())

    assert set(runtime["user_config"]["api_components"]) == {
        "OpenMeteoWeatherApiComponent",
        "ImgwWarningsApiComponent",
        "OpenMeteoAirQualityApiComponent",
    }
    external = runtime["user_config"]["safety_components"][
        "ExternalHazardComponent"
    ]
    assert external["policy"]["actuation_mode"] == "manual_and_user_confirmed"
    assert external["enabled_providers"] == [
        "ImgwWarningsApiComponent",
        "OpenMeteoAirQualityApiComponent",
        "OpenMeteoWeatherApiComponent",
    ]
    assert len(external["openings"]) == 1
    assert all(
        opening["actuator_entity_id"] is None
        for opening in external["openings"].values()
    )


def test_enabled_external_hazard_rejects_a_missing_provider_binding() -> None:
    config = copy.deepcopy(_example_config())
    del config["user_config"]["api_components"]["ImgwWarningsApiComponent"]

    with pytest.raises(AppCfgValidationError, match="ImgwWarningsApiComponent"):
        AppCfgValidator.validate(config)


def test_external_hazard_rejects_unconfirmed_or_non_cover_actuation() -> None:
    config = copy.deepcopy(_example_config())
    opening = config["user_config"]["safety_components"][
        "ExternalHazardComponent"
    ]["openings"]["LivingRoomWindow"]
    opening["kind"] = "garage_door"
    opening["execution_policy"] = "user_confirmed"
    opening["actuator_entity_id"] = (
        "button.example_gate_pulse"
    )

    with pytest.raises(AppCfgValidationError, match="cover actuator_entity_id"):
        AppCfgValidator.validate(config)
