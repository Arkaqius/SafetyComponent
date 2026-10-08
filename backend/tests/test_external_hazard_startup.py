"""Production-shape startup integration for External Hazard Monitoring."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


def test_example_external_hazard_startup_is_wired_before_polling(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "SafetyFunctions.JsonFunctionalSafetyDiagnosticsStore",
        lambda: JsonFunctionalSafetyDiagnosticsStore(tmp_path / "functional_safety.json"),
    )
    backend_dir = Path(__file__).parents[1]
    raw = compile_config(
        user_path=backend_dir / "config" / "user_config.example.yml",
        home_assistant_config={"latitude": 50.0, "longitude": 20.0},
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

    assert sorted(app.api_modules) == [
        "ImgwWarningsApiComponent",
        "OpenMeteoAirQualityApiComponent",
        "OpenMeteoWeatherApiComponent",
    ]
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
