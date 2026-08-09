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


def test_external_hazard_config_normalizes_all_five_independent_providers() -> None:
    runtime = AppCfgValidator.validate(_production_config())

    assert set(runtime["user_config"]["api_components"]) == {
        "OpenMeteoWeatherApiComponent",
        "ImgwWarningsApiComponent",
        "GiosAirQualityApiComponent",
        "OpenMeteoAirQualityApiComponent",
        "PaaRadiationApiComponent",
    }
    external = runtime["user_config"]["safety_components"][
        "ExternalHazardComponent"
    ]
    assert external["policy"]["notification_only"] is True
    assert external["enabled_providers"] == [
        "GiosAirQualityApiComponent",
        "ImgwWarningsApiComponent",
        "OpenMeteoAirQualityApiComponent",
        "OpenMeteoWeatherApiComponent",
    ]
    assert runtime["user_config"]["api_components"]["PaaRadiationApiComponent"]["enabled"] is False
    assert len(external["openings"]) == 11


def test_enabled_external_hazard_rejects_a_missing_provider_binding() -> None:
    config = copy.deepcopy(_production_config())
    del config["user_config"]["api_components"]["PaaRadiationApiComponent"]

    with pytest.raises(AppCfgValidationError, match="PaaRadiationApiComponent"):
        AppCfgValidator.validate(config)


def test_external_hazard_rejects_any_attempt_to_enable_actuation() -> None:
    config = copy.deepcopy(_production_config())
    config["app_config"]["external_hazard_policy"]["notification_only"] = False

    with pytest.raises(AppCfgValidationError, match="notification_only"):
        AppCfgValidator.validate(config)
