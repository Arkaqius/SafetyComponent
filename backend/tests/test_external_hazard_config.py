"""Fail-fast configuration tests for the complete C-EXT contract."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from build_app_config import compile_config
from components.app_config_validator.app_cfg_validator import (
    AppCfgValidationError,
    AppCfgValidator,
)
from components.external_apis.core import registry
from components.external_apis.core.api_component import ExternalApiComponent
from components.external_apis.core.models import ProviderCapability
from system_configuration import ProviderRuntimeSource


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


def test_imgw_location_validation_only_applies_when_selected_in_poland() -> None:
    config = _example_config()
    config["user_config"]["site"].pop("teryt_codes")
    with pytest.raises(AppCfgValidationError, match="IMGW requires site.teryt_codes"):
        AppCfgValidator.validate(config)
    config["user_config"]["api_components"]["ImgwWarningsApiComponent"]["enabled"] = False
    assert not AppCfgValidator.validate(config)["user_config"]["api_components"]["ImgwWarningsApiComponent"]["enabled"]


def test_registered_warning_plugin_supplies_its_own_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class BerlinWarnings(ExternalApiComponent):
        component_name = "BerlinWarningsApiComponent"
        config_model = ProviderRuntimeSource
        capability = ProviderCapability.OFFICIAL_WARNINGS
        countries = frozenset({"DE"})

        def fetch_payload(self):
            return []

        def normalize(self, payload, retrieved_at):
            return ()

    monkeypatch.setattr(registry, "_API_COMPONENT_REGISTRY", registry.get_registered_api_components())
    registry.register_api_component(BerlinWarnings)
    name = BerlinWarnings.component_name
    system = yaml.safe_load((BACKEND_DIR / "config/system_config.yml").read_text(encoding="utf-8"))
    system["runtime_cfg"]["providers"][name] = {
        "enabled": True,
        "base_url": "https://example.invalid/warnings",
        "poll_interval_seconds": 300,
        "request_timeout_seconds": 5,
        "max_retries": 0,
        "stale_after_seconds": 900,
    }
    source = yaml.safe_load((BACKEND_DIR.parent / "docs/examples/berlin_user_config.yml").read_text(encoding="utf-8"))
    source["user_config"]["providers"] = {name: {"enabled": True}}
    system_path = tmp_path / "system_config.yml"
    user_path = tmp_path / "user_config.yml"
    system_path.write_text(yaml.safe_dump(system), encoding="utf-8")
    user_path.write_text(yaml.safe_dump(source), encoding="utf-8")
    compiled = compile_config(system_path, user_path, home_assistant_config={"latitude": 52.52, "longitude": 13.405})
    runtime = AppCfgValidator.validate(compiled["SafetyFunctions"])["user_config"]
    active = runtime["safety_components"]["ExternalHazardComponent"]["enabled_providers"]
    assert name in active
    assert "ImgwWarningsApiComponent" not in active


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
