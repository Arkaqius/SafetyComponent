"""Production-shape startup integration for External Hazard Monitoring."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from SafetyFunctions import SafetyFunctions


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


def test_production_external_hazard_startup_is_wired_before_polling() -> None:
    raw = yaml.safe_load(
        (Path(__file__).parents[1] / "app_cfg.yaml").read_text(encoding="utf-8")
    )["SafetyFunctions"]
    app = SafetyFunctions(args=raw)
    service_calls: list[str] = []

    def fake_state(entity_id: str, **_: Any) -> str:
        if entity_id.endswith("_rate") or entity_id.endswith("_rateofrate"):
            return "0"
        return "22" if entity_id.startswith("sensor.") else "off"

    app.get_state = fake_state
    app.render_template = lambda *_args, **_kwargs: "Resolved area"
    app.call_service = lambda service, **_kwargs: service_calls.append(service)
    app._external_api_runtime_cls = StubExternalRuntime

    app.initialize()

    assert sorted(app.api_modules) == [
        "ImgwWarningsApiComponent",
        "OpenMeteoAirQualityApiComponent",
        "OpenMeteoWeatherApiComponent",
    ]
    assert "ExternalHazardComponent" in app.sm_modules
    assert app.external_api_runtime.started is True
    assert not any(service != "mqtt/publish" for service in service_calls)

    app.terminate()
    assert app.external_api_runtime.started is False
