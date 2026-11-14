"""Production-shape startup integration for External Hazard Monitoring."""

from __future__ import annotations

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


def _target_raw(tmp_path, *, dummy=None, component_enabled=True, all_disabled=False, rename_opening=False):
    root = Path(__file__).parents[2]
    source = yaml.safe_load((root / "backend/config/user_config.example.yml").read_text(encoding="utf-8"))
    config = source["user_config"]
    for name in config["components_enabled"]:
        config["components_enabled"][name] = name == ("ExternalHazardComponent" if component_enabled else "EntityMonitorComponent")
    if all_disabled:
        config["external_sources"] = {key: None for key in config["external_sources"]}
    if rename_opening:
        config["installation"]["openings"]["OtherWindow"] = config["installation"]["openings"].pop("LivingRoomWindow")
        for room in config["installation"]["rooms"].values():
            if room.get("window") == "LivingRoomWindow":
                room["window"] = "OtherWindow"
    if dummy is not None:
        config["installation"]["site"] = {"country_code": "DE", "timezone": "Europe/Berlin"}
        config["external_sources"] = {
            "WeatherPointModel": None,
            "OfficialWeatherWarnings": "GermanyDummyWarningsApiComponent",
            "OutdoorAirQuality": None,
        }
        config["provider_parameters"] = {
            "GermanyDummyWarningsApiComponent": {"region_code": "TestRegion", "scenario": dummy},
        }
    path = tmp_path / "target.yml"
    path.write_text(yaml.safe_dump(source), encoding="utf-8")
    raw = compile_config(user_path=path, home_assistant_config={"latitude": 52.52, "longitude": 13.405})["SafetyFunctions"]
    policy = raw["app_config"]["calibration"]["functional_safety"]
    for key in ("battery_fault_catalog_file", "periodic_test_state_file", "detector_test_state_file"):
        policy[key] = str(tmp_path / f"{key}.json")
    raw["app_config"]["fault_evidence"]["state_file"] = str(tmp_path / "fault_evidence.json")
    raw["user_config"]["notification"]["persistence"]["state_file"] = str(tmp_path / "notify.json")
    raw["user_config"]["recovery"]["persistence"]["state_file"] = str(tmp_path / "recovery.json")
    return raw


def _start_target(raw, tmp_path, monkeypatch):
    monkeypatch.setattr("SafetyFunctions.JsonFunctionalSafetyDiagnosticsStore", lambda: JsonFunctionalSafetyDiagnosticsStore(tmp_path / "diagnostics.json"))
    monkeypatch.setattr("SafetyFunctions.HomeAssistantStateProvider.from_environment", lambda: None)
    app = SafetyFunctions(args=raw)
    app.get_state = lambda entity_id, **_: "22" if entity_id.startswith("sensor.") else "on"
    app.render_template = lambda *_args, **_kwargs: "Controlled area"
    calls = []
    app.call_service = lambda service, **kwargs: calls.append((service, kwargs))
    app._external_api_runtime_cls = StubExternalRuntime
    app.initialize()
    return app, calls


def test_invalid_startup_invalidates_retained_selection_before_validation(tmp_path, monkeypatch):
    raw = _target_raw(tmp_path)
    raw["user_config"].pop("external_sources")
    app, calls = _start_target(raw, tmp_path, monkeypatch)
    topic = app.mqtt_entities.state_topic("sensor.external_source_selection")
    states = [data["payload"] for service, data in calls
              if service == "mqtt/publish" and data.get("topic") == topic]
    assert states and states[-1] == "unknown"


@pytest.mark.parametrize("scenario", ["empty", "warning", "unavailable", "stale"])
def test_dummy_full_startup_preview_has_no_real_safety_effect(tmp_path, monkeypatch, scenario):
    """Real bundled selection reaches preview with no real fault or action changes."""
    raw = _target_raw(tmp_path, dummy=scenario)
    app, calls = _start_target(raw, tmp_path, monkeypatch)
    assert app.degradation.binding_errors == {}
    assert set(app.api_modules) == {"GermanyDummyWarningsApiComponent"}
    assert app.provider_definitions == {}
    before = {key: (value.evaluation.active, value.evaluation.status) for key, value in app.faults.items()}
    call_offset = len(calls)
    adapter = app.api_modules["GermanyDummyWarningsApiComponent"]
    result = adapter.poll()
    app.event_bus.publish("external_api_test_result", result=result)
    assert {key: (value.evaluation.active, value.evaluation.status) for key, value in app.faults.items()} == before
    assert app._external_assertions == {}
    assert all(service == "mqtt/publish" for service, _ in calls[call_offset:])
    assert "sensor.external_hazard_test_state" in app.mqtt_entities.discovered_entities
    assert not app.reco_man._proposals
    app.terminate()
    assert not app.external_api_runtime.started


@pytest.mark.parametrize("mode", ["component_disabled", "sources_disabled", "synthetic", "removed_opening", "corrupt", "missing", "fresh_closure"])
def test_real_assertion_survives_source_disable_restart_without_false_clear(tmp_path, monkeypatch, mode):
    """Active real danger is restored before initial publication while monitoring is off."""
    from components.external_apis.core.models import (
        ApiResult, ExternalObservation, HazardType, Measurement,
        ProviderHealth, ProviderHealthState, WarningUrgency,
    )
    from components.core.types_common import FaultState

    app, _ = _start_target(_target_raw(tmp_path), tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    provider = "ImgwWarningsApiComponent"
    observation = ExternalObservation(provider, "real-wind", HazardType.WIND, "3",
        {"event_name": Measurement("Real wind")}, now, now, now + timedelta(minutes=15),
        now, authority_confirmed=True, warning_urgency=WarningUrgency.IMMEDIATE)
    health = ProviderHealth(provider, ProviderHealthState.OK, now, now, 0, stale_after_seconds=900)
    app.event_bus.publish("external_api_result", result=ApiResult(provider, (observation,), health))
    component = app.sm_modules["ExternalHazardComponent"]
    symptom_id = "ExternalWeatherExposureWindLivingRoomWindow"
    assert component.symptom_states[symptom_id] == FaultState.SET
    assert symptom_id in app.real_assertion_store.records
    assert app.faults["ExternalWeatherExposure"].evaluation.active
    app.terminate()
    if mode in {"corrupt", "missing"}:
        app.real_assertion_store.storage.save({"broken": True} if mode == "corrupt" else {})
    raw = _target_raw(tmp_path,
        component_enabled=mode not in {"component_disabled", "corrupt", "missing"},
        all_disabled=mode in {"sources_disabled", "fresh_closure"},
        dummy="empty" if mode == "synthetic" else None,
        rename_opening=mode == "removed_opening")
    restarted, calls = _start_target(raw, tmp_path, monkeypatch)
    if mode in {"component_disabled", "corrupt", "missing"}:
        assert "ExternalHazardComponent" not in restarted.sm_modules
    assert restarted.faults["ExternalWeatherExposure"].evaluation.active
    assert restarted.faults["ExternalWeatherExposure"].evaluation.status.value == "UNEVALUABLE"
    assert all(service == "mqtt/publish" or (mode == "corrupt" and service.startswith("notify/")) for service, _ in calls)
    assert symptom_id not in restarted.reco_man._proposals
    assert all(key.startswith("AppHealth") for key in restarted.reco_man._proposals)
    for key in restarted.degradation._symptoms:
        restarted.degradation.observe(symptom_id=key, state=FaultState.CLEARED)
    assert restarted._external_coverage_snapshot()["state"] != "FULL"
    import json
    fault_entity = "sensor.fault_ExternalWeatherExposure"
    fault_states = [data["payload"] for service, data in calls
        if service == "mqtt/publish" and data.get("topic") == restarted.mqtt_entities.state_topic(fault_entity)]
    fault_attributes = [json.loads(data["payload"]) for service, data in calls
        if service == "mqtt/publish" and data.get("topic") == restarted.mqtt_entities.attributes_topic(fault_entity)]
    assert fault_states and all(state == "UNEVALUABLE" for state in fault_states)
    assert fault_attributes and all(data["active"] for data in fault_attributes)
    if mode in {"corrupt", "missing"}:
        assert all(data["retained_hazard_unknown"] for data in fault_attributes)
    system_states = [data["payload"] for service, data in calls
        if service == "mqtt/publish" and data.get("topic") == restarted.mqtt_entities.state_topic("sensor.safetysystem_state")]
    assert system_states and "no_faults" not in system_states
    if mode == "fresh_closure":
        component = restarted.sm_modules["ExternalHazardComponent"]
        restarted.get_state = lambda entity_id, **_: "22" if entity_id.startswith("sensor.") else "off"
        component._evaluate_all()
        for key, (token, _) in tuple(component._clear_handles.items()):
            component._finish_clear(symptom_id=key, token=token)
        assert not restarted.faults["ExternalWeatherExposure"].evaluation.active
        assert not restarted.real_assertion_store.records
        assert restarted.fm.retained_assertions("ExternalWeatherExposure") == []
    restarted.terminate()
