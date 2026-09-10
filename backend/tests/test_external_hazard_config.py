"""Fail-fast configuration tests for the complete C-EXT contract."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from components.app_config_validator.app_cfg_validator import (
    AppCfgValidationError,
    AppCfgValidator,
)


def _production_config() -> dict:
    return yaml.safe_load(
        (Path(__file__).parents[1] / "app_cfg.yaml").read_text(encoding="utf-8")
    )["SafetyFunctions"]


def test_external_hazard_config_normalizes_all_three_independent_providers() -> None:
    runtime = AppCfgValidator.validate(_production_config())

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
    assert len(external["openings"]) == 10
    assert all(
        opening["actuator_entity_id"] is None
        for opening in external["openings"].values()
    )


def test_enabled_external_hazard_rejects_a_missing_provider_binding() -> None:
    config = copy.deepcopy(_production_config())
    del config["user_config"]["api_components"]["ImgwWarningsApiComponent"]

    with pytest.raises(AppCfgValidationError, match="ImgwWarningsApiComponent"):
        AppCfgValidator.validate(config)


def test_external_hazard_rejects_unconfirmed_or_non_cover_actuation() -> None:
    config = copy.deepcopy(_production_config())
    opening = config["user_config"]["safety_components"][
        "ExternalHazardComponent"
    ]["openings"]["BathroomWindow"]
    opening["kind"] = "garage_door"
    opening["execution_policy"] = "user_confirmed"
    opening["actuator_entity_id"] = (
        "button.garaz_przekaznik_bramy_garazowej_garage_gate_pulse"
    )

    with pytest.raises(AppCfgValidationError, match="cover actuator_entity_id"):
        AppCfgValidator.validate(config)
