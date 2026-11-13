"""Production-shape startup integration for External Hazard Monitoring."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

from build_app_config import compile_config
from SafetyFunctions import SafetyFunctions
from components.core.functional_safety_diagnostics import JsonFunctionalSafetyDiagnosticsStore


class StubExternalRuntime:
    """No-network runtime used to assert startup and shutdown ordering."""

    def __init__(self, app: SafetyFunctions, event_bus: Any, components: dict[str, Any]) -> None:
        self.app = app
        self.event_bus = event_bus
        self.components = components
        self.started = False

    def start(self) -> None:
        assert "sensor.external_hazard_state" in self.app.mqtt_entities.discovered_entities
        assert "fault" in self.event_bus._subscribers
        self.started = True

    def stop(self) -> None:
        self.started = False


@pytest.mark.parametrize(
    ("example", "location", "expected"),
    [
        ("backend/config/user_config.example.yml", {"latitude": 50.0, "longitude": 20.0},
         ["ImgwWarningsApiComponent", "OpenMeteoAirQualityApiComponent", "OpenMeteoWeatherApiComponent"]),
        ("backend/tests/fixtures/external_apis/legacy_user_config.yml", {"latitude": 50.0, "longitude": 20.0},
         ["ImgwWarningsApiComponent", "OpenMeteoAirQualityApiComponent", "OpenMeteoWeatherApiComponent"]),
        ("docs/examples/berlin_user_config.yml", {"latitude": 52.52, "longitude": 13.405},
         ["OpenMeteoAirQualityApiComponent", "OpenMeteoWeatherApiComponent"]),
    ],
)
def test_example_external_hazard_startup_is_wired_before_polling(tmp_path, monkeypatch, example, location, expected) -> None:
    monkeypatch.setattr(
        "SafetyFunctions.JsonFunctionalSafetyDiagnosticsStore",
        lambda: JsonFunctionalSafetyDiagnosticsStore(tmp_path / "functional_safety.json"),
    )
    root = Path(__file__).parents[2]
    raw = compile_config(
        user_path=root / example,
        home_assistant_config=location,
    )["SafetyFunctions"]
    raw["app_config"]["calibration"]["functional_safety"][
        "battery_fault_catalog_file"
    ] = str(tmp_path / "battery_fault_catalog.json")
    for key in ("periodic_test_state_file", "detector_test_state_file"):
        raw["app_config"]["calibration"]["functional_safety"][key] = str(tmp_path / f"{key}.json")
    state_file = tmp_path / "notification_state.json"
    raw["user_config"]["notification"]["persistence"]["state_file"] = str(
        state_file
    )
    recovery_state_file = tmp_path / "recovery_state.json"
    raw["user_config"]["recovery"]["persistence"]["state_file"] = str(
        recovery_state_file
    )
    raw["app_config"]["fault_evidence"]["state_file"] = str(
        tmp_path / "fault_evidence_state.json"
    )
    app = SafetyFunctions(args=raw)
    service_calls: list[str] = []
    publications: list[dict[str, Any]] = []

    def fake_state(entity_id: str, **_: Any) -> str:
        if entity_id.endswith("_rate") or entity_id.endswith("_rateofrate"):
            return "0"
        return "22" if entity_id.startswith("sensor.") else "off"

    app.get_state = fake_state
    app.render_template = lambda *_args, **_kwargs: "Resolved area"
    def capture_service(service: str, **kwargs: Any) -> None:
        service_calls.append(service)
        if service == "mqtt/publish":
            publications.append(kwargs)

    app.call_service = capture_service
    app._external_api_runtime_cls = StubExternalRuntime

    app.initialize()

    assert app.degradation.binding_errors == {}

    assert sorted(app.api_modules) == expected
    assert "ExternalHazardComponent" in app.sm_modules
    assert "SelfDiagnosticsComponent" in app.sm_modules
    assert {
        "ExternalDataUnavailable",
    }.issubset(app.faults)
    retired_names = (
        "TemperatureMonitoringUnavailable", "SafetyDoorMonitoringUnavailable",
        "ExternalOpeningMonitoringUnavailable", "CommonInputUnavailable",
        "ExternalHazardDataUnavailable", "ExternalProviderUnavailableOpenMeteoWeather",
        "ExternalProviderUnavailableImgwWarnings", "ExternalProviderUnavailableOpenMeteoAirQuality",
    )
    assert not set(retired_names).intersection(app.faults)
    for name in retired_names:
        entity_id = f"sensor.fault_{name}"
        for topic in (
            app.mqtt_entities.discovery_topic(entity_id),
            app.mqtt_entities.legacy_discovery_topic(entity_id),
            app.mqtt_entities.state_topic(entity_id),
            app.mqtt_entities.attributes_topic(entity_id),
        ):
            assert any(item["topic"] == topic and item["payload"] == "" for item in publications)
    assert app.external_api_runtime.started is True
    assert not any(service != "mqtt/publish" for service in service_calls)

    app.terminate()
    assert app.external_api_runtime.started is False
    assert not state_file.exists()
    assert app.state_database.path == tmp_path / "safety_state.sqlite3"
    assert app.state_database.path.exists()
    assert app.notify_man.state_store.load()["version"] == 1


def test_regional_plugin_import_save_startup_health_and_shutdown(tmp_path, monkeypatch) -> None:
    """A new provider crosses real config persistence and the complete app boundary."""
    from components.external_apis.core import registry
    from components.external_apis.core.models import (
        ApiResult, ExternalObservation, HazardType, Measurement, ProviderHealth, ProviderHealthState,
    )
    from tests.provider_plugin_support import PeerRegionalWarnings, RegionalWarnings, provider_policy
    from user_config_api import UserConfigStore

    monkeypatch.setattr(registry, "_API_COMPONENT_REGISTRY", registry.get_registered_api_components())
    for plugin in (RegionalWarnings, PeerRegionalWarnings):
        registry.register_api_component(plugin)
    root = Path(__file__).parents[2]
    system = yaml.safe_load((root / "backend/config/system_config.yml").read_text(encoding="utf-8"))
    source = yaml.safe_load((root / "docs/examples/berlin_user_config.yml").read_text(encoding="utf-8"))
    for plugin in (RegionalWarnings, PeerRegionalWarnings):
        name = plugin.component_name
        system["runtime_cfg"]["providers"][name] = provider_policy(feed_variant="integration")
        source["user_config"].setdefault("providers", {})[name] = {
            "enabled": True, "parameters": {"region_code": "Berlin"},
        }
    system_path = tmp_path / "system_config.yml"
    system_path.write_text(yaml.safe_dump(system), encoding="utf-8")
    user_path = tmp_path / "user_config.yml"
    location = {"latitude": 52.52, "longitude": 13.405}
    store = UserConfigStore(user_path, system_path, home_assistant_config_provider=lambda: location)
    imported = store.import_yaml(yaml.safe_dump(source))
    assert not user_path.exists()
    saved = store.save(imported["user_config"], "absent")
    original_bytes = user_path.read_bytes()
    invalid = deepcopy(saved["user_config"])
    invalid["providers"][RegionalWarnings.component_name]["parameters"] = {}
    with pytest.raises(ValueError, match="region_code"):
        store.save(invalid, saved["revision"])
    with pytest.raises(ValueError, match="region_code"):
        store.import_yaml(yaml.safe_dump({"user_config": invalid}))
    assert user_path.read_bytes() == original_bytes
    assert store.read()["revision"] == saved["revision"]

    raw = compile_config(system_path, user_path, home_assistant_config=location)["SafetyFunctions"]
    functional = raw["app_config"]["calibration"]["functional_safety"]
    for key in ("battery_fault_catalog_file", "periodic_test_state_file", "detector_test_state_file"):
        functional[key] = str(tmp_path / f"{key}.json")
    raw["app_config"]["fault_evidence"]["state_file"] = str(tmp_path / "fault_evidence.json")
    raw["user_config"]["notification"]["persistence"]["state_file"] = str(tmp_path / "notify.json")
    raw["user_config"]["recovery"]["persistence"]["state_file"] = str(tmp_path / "recovery.json")
    monkeypatch.setattr("SafetyFunctions.JsonFunctionalSafetyDiagnosticsStore", lambda: JsonFunctionalSafetyDiagnosticsStore(tmp_path / "diagnostics.json"))
    monkeypatch.setattr("SafetyFunctions.HomeAssistantStateProvider.from_environment", lambda: None)
    app = SafetyFunctions(args=raw)
    app.get_state = lambda entity_id, **_: "22" if entity_id.startswith("sensor.") else "on"
    app.render_template = lambda *_args, **_kwargs: "Controlled area"
    calls: list[str] = []
    app.call_service = lambda service, **_: calls.append(service)
    app._external_api_runtime_cls = StubExternalRuntime
    app.initialize()
    assert app.degradation.binding_errors == {}
    assert app.external_api_runtime.started
    assert RegionalWarnings.component_name in app.api_modules
    assert PeerRegionalWarnings.component_name in app.api_modules
    now = datetime.now(timezone.utc)
    observation = ExternalObservation(
        RegionalWarnings.component_name, "controlled-wind", HazardType.WIND, "1",
        {"event_name": Measurement("Controlled wind")}, now, now,
        now + timedelta(minutes=5), now, authority_confirmed=True,
    )
    health = ProviderHealth(RegionalWarnings.component_name, ProviderHealthState.OK, now, now, 0, stale_after_seconds=900)
    app.event_bus.publish("external_api_result", result=ApiResult(RegionalWarnings.component_name, (observation,), health))
    peer = PeerRegionalWarnings.component_name
    failed_health = ProviderHealth(peer, ProviderHealthState.UNAVAILABLE, now, None, 1, stale_after_seconds=900)
    app.event_bus.publish("external_api_result", result=ApiResult(peer, (), failed_health))
    assert app.self_diagnostics._observed[app.self_diagnostics._symptom_id(peer)] is True
    assert app.self_diagnostics._observed[app.self_diagnostics._symptom_id(RegionalWarnings.component_name)] is False
    component = app.sm_modules["ExternalHazardComponent"]
    from components.core.types_common import FaultState
    assert component.symptom_states["ExternalWeatherExposureWindLivingRoomWindow"] == FaultState.SET
    app.terminate()
    assert not app.external_api_runtime.started
    assert all(service == "mqtt/publish" or service.startswith("notify/") for service in calls), calls
