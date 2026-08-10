"""Safety-policy tests for notification-only External Hazard Monitoring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from components.core.event_bus import EventBus
from components.core.localization import Localizer
from components.core.types_common import Fault, FaultState, RecoveryResult, SMState, Symptom
from components.external_apis.core.models import (
    ApiResult,
    ExternalObservation,
    HazardType,
    Measurement,
    ProviderHealth,
    ProviderHealthState,
)
from components.safetycomponents.external_hazard.external_hazard_component import ExternalHazardComponent
from components.faults_manager.fault_manager import FaultManager


class FakeHass:
    def __init__(self) -> None:
        self.states = {"binary_sensor.office_window": "on"}
        self.localizer = Localizer({"language": "pl"})
        self.service_calls: list[tuple[str, dict[str, Any]]] = []
        self.logs: list[tuple[str, str]] = []

    def get_state(self, entity_id: str, **_: Any) -> Any:
        return self.states.get(entity_id)

    def listen_state(self, callback: Any, entity: str, **kwargs: Any) -> Any:
        return callback, entity, kwargs

    def run_in(self, callback: Any, delay: int, **kwargs: Any) -> Any:
        return callback, delay, kwargs

    def cancel_timer(self, _: Any) -> None:
        return None

    def call_service(self, service: str, **kwargs: Any) -> None:
        self.service_calls.append((service, kwargs))

    def log(self, message: str, *, level: str = "INFO", **_: Any) -> None:
        self.logs.append((level, message))


class FakeMqtt:
    def __init__(self) -> None:
        self.states: dict[str, tuple[str, dict[str, Any]]] = {}

    def register_sensor(self, entity_id: str, _: str, **kwargs: Any) -> str:
        self.states.setdefault(entity_id.lower(), (str(kwargs.get("state", "")), {}))
        return entity_id.lower()

    def publish_sensor_state(
        self, entity_id: str, state: Any, *, attributes: dict[str, Any] | None = None
    ) -> None:
        self.states[entity_id] = (str(state), dict(attributes or {}))

    def get_attributes(self, entity_id: str) -> dict[str, Any]:
        return dict(self.states.get(entity_id, ("", {}))[1])


POLICY = {
    "notification_only": True,
    "clear_delay_seconds": 0,
    "weather": {
        "frost_watch_c": 2.0,
        "frost_warning_c": 0.0,
        "gust_watch_m_s": 15.0,
        "gust_warning_m_s": 20.0,
        "precipitation_warning_mm_h": 2.5,
    },
    "outdoor_air_quality": {
        "warning_at": 60,
        "gios_warning_level": 3,
    },
    "radiation": {
        "raw_anomaly_enabled": False,
        "raw_anomaly_usv_h": 0.3,
        "raw_anomaly_min_stations": 2,
    },
}


def _health(provider: str, state: ProviderHealthState = ProviderHealthState.OK) -> ProviderHealth:
    now = datetime.now(timezone.utc)
    return ProviderHealth(
        provider=provider,
        state=state,
        last_attempt_at=now,
        last_success_at=now if state == ProviderHealthState.OK else None,
        consecutive_failures=0 if state == ProviderHealthState.OK else 1,
        detail_code=None if state == ProviderHealthState.OK else "timeout",
        stale_after_seconds=900,
    )


def _observation(
    provider: str,
    hazard: HazardType,
    values: dict[str, Measurement],
    *,
    confirmed: bool = False,
) -> ExternalObservation:
    now = datetime.now(timezone.utc)
    return ExternalObservation(
        provider=provider,
        observation_id=f"{provider}-{hazard.value}",
        hazard_type=hazard,
        provider_level="2" if confirmed else None,
        values=values,
        observed_at=now,
        valid_from=now - timedelta(minutes=1),
        valid_to=now + timedelta(hours=1),
        retrieved_at=now,
        authority_confirmed=confirmed,
        source_reference="https://example.invalid/source",
    )


def _component() -> tuple[ExternalHazardComponent, FakeHass, FakeMqtt, list[dict[str, Any]]]:
    hass = FakeHass()
    mqtt = FakeMqtt()
    bus = EventBus()
    events: list[dict[str, Any]] = []
    bus.subscribe("symptom", lambda **payload: events.append(payload))
    component = ExternalHazardComponent(hass, object(), bus, mqtt)
    config = {
        "policy": POLICY,
        "openings": {
            "OfficeWindow": {
                "area_id": "office",
                "area_name": "Biuro",
                "entity_id": "binary_sensor.office_window",
                "friendly_name": "Okno biura",
                "kind": "window",
                "hazards": ["frost", "wind", "rain", "storm", "outdoor_air_pollution"],
            }
        },
    }
    symptoms, recovery = component.get_symptoms_data(
        {component.component_name: component}, config
    )
    assert recovery == {}
    for symptom in symptoms.values():
        assert component.init_safety_mechanism(
            symptom.sm_name, symptom.name, symptom.parameters
        )
        assert component.enable_safety_mechanism(symptom.name, SMState.ENABLED)
    return component, hass, mqtt, events


def test_active_wind_and_open_window_sets_exposure_and_never_calls_actuator() -> None:
    component, hass, mqtt, events = _component()
    wind = _observation(
        "OpenMeteoWeatherApiComponent",
        HazardType.WIND,
        {
            "current_wind_gust": Measurement(18.0, "m/s"),
            "forecast_max_wind_gust": Measurement(22.0, "m/s"),
        },
    )
    component.handle_external_api_result(
        result=ApiResult(
            provider=wind.provider,
            observations=(wind,),
            health=_health(wind.provider),
        )
    )

    symptom_id = "ExternalWeatherExposureWindOfficeWindow"
    assert component.symptom_states[symptom_id] == FaultState.SET
    assert any(event["symptom_id"] == symptom_id and event["state"] == FaultState.SET for event in events)
    assert mqtt.states["sensor.external_hazard_state"][0] == "warning"
    provider_attributes = mqtt.states["sensor.external_provider_open_meteo_weather"][1]
    assert provider_attributes["observations"] == [
        {
            "id": "OpenMeteoWeatherApiComponent-wind",
            "hazard_type": "wind",
            "provider_level": None,
            "observed_at": wind.observed_at.isoformat(),
            "valid_to": wind.valid_to.isoformat(),
            "display_value": None,
            "display_unit": None,
        }
    ]
    assert hass.service_calls == []


def test_air_quality_observation_summary_exposes_current_operator_value() -> None:
    component, _, mqtt, _ = _component()
    air_quality = _observation(
        "GiosAirQualityApiComponent",
        HazardType.OUTDOOR_AIR_POLLUTION,
        {
            "polish_index_name": Measurement("Dobry"),
            "polish_index_level": Measurement(1),
        },
    )

    component.handle_external_api_result(
        result=ApiResult(
            provider=air_quality.provider,
            observations=(air_quality,),
            health=_health(air_quality.provider),
        )
    )

    summary = mqtt.states["sensor.external_provider_gios_air_quality"][1][
        "observations"
    ][0]
    assert summary["hazard_type"] == "outdoor_air_pollution"
    assert summary["display_value"] == "Dobry"
    assert summary["display_unit"] is None


def test_provider_diagnostic_observation_summaries_are_bounded() -> None:
    component, _, mqtt, _ = _component()
    observation = _observation(
        "GiosAirQualityApiComponent",
        HazardType.OUTDOOR_AIR_POLLUTION,
        {"polish_index_name": Measurement("Dobry")},
    )

    component.handle_external_api_result(
        result=ApiResult(
            provider=observation.provider,
            observations=(observation,) * 65,
            health=_health(observation.provider),
        )
    )

    attributes = mqtt.states["sensor.external_provider_gios_air_quality"][1]
    assert attributes["observation_count"] == 65
    assert len(attributes["observations"]) == 64


def test_aggregate_remains_unavailable_until_every_provider_is_healthy() -> None:
    component, _, mqtt, _ = _component()

    component.handle_external_api_result(
        result=ApiResult(
            provider="PaaRadiationApiComponent",
            observations=(),
            health=_health(
                "PaaRadiationApiComponent", ProviderHealthState.UNAVAILABLE
            ),
        )
    )

    assert mqtt.states["sensor.external_hazard_state"][0] == "unavailable"


def test_provider_failure_cannot_clear_active_hazard_but_closed_window_can() -> None:
    component, hass, _, events = _component()
    wind = _observation(
        "OpenMeteoWeatherApiComponent",
        HazardType.WIND,
        {
            "current_wind_gust": Measurement(21.0, "m/s"),
            "forecast_max_wind_gust": Measurement(21.0, "m/s"),
        },
    )
    component.handle_external_api_result(
        result=ApiResult(wind.provider, (wind,), _health(wind.provider))
    )
    events.clear()
    component.handle_external_api_result(
        result=ApiResult(
            wind.provider,
            (),
            _health(wind.provider, ProviderHealthState.UNAVAILABLE),
        )
    )

    symptom_id = "ExternalWeatherExposureWindOfficeWindow"
    assert component.symptom_states[symptom_id] == FaultState.SET
    assert not any(event["symptom_id"] == symptom_id and event["state"] == FaultState.CLEARED for event in events)

    hass.states["binary_sensor.office_window"] = "off"
    component._evaluate_all()
    assert component.symptom_states[symptom_id] == FaultState.CLEARED


def test_official_radiation_warning_ignores_aperture_state_and_raw_data_is_not_official() -> None:
    component, hass, _, events = _component()
    hass.states["binary_sensor.office_window"] = "off"
    official = _observation(
        "PaaRadiationApiComponent",
        HazardType.IONIZING_RADIATION,
        {
            "status": Measurement("official alert"),
            "message": Measurement("Follow PAA instructions"),
        },
        confirmed=True,
    )
    component.handle_external_api_result(
        result=ApiResult(official.provider, (official,), _health(official.provider))
    )
    assert component.symptom_states["IonizingRadiationAlertPaa"] == FaultState.SET

    fresh_component, _, _, raw_events = _component()
    raw = _observation(
        "PaaRadiationApiComponent",
        HazardType.RADIATION_ANOMALY,
        {
            "station_id": Measurement("KRK-1"),
            "dose_rate": Measurement(9.0, "µSv/h"),
        },
    )
    fresh_component.handle_external_api_result(
        result=ApiResult(raw.provider, (raw,), _health(raw.provider))
    )
    assert not any(
        event["symptom_id"] == "IonizingRadiationAlertPaa"
        and event["state"] == FaultState.SET
        for event in raw_events
    )


def test_active_external_hazard_inhibits_only_opening_recovery_proposals() -> None:
    component, _, _, _ = _component()
    pollution = _observation(
        "OpenMeteoAirQualityApiComponent",
        HazardType.OUTDOOR_AIR_POLLUTION,
        {
            "current_european_aqi": Measurement(75.0, "EAQI"),
        },
    )
    component.handle_external_api_result(
        result=ApiResult(
            pollution.provider,
            (pollution,),
            _health(pollution.provider),
        )
    )

    opening = component.evaluate_recovery_policy(
        RecoveryResult(
            changed_sensors={"binary_sensor.office_window": "on"},
            changed_actuators={},
            notifications=["Otwórz okno"],
        )
    )
    closing = component.evaluate_recovery_policy(
        RecoveryResult(
            changed_sensors={"binary_sensor.office_window": "off"},
            changed_actuators={},
            notifications=["Zamknij okno"],
        )
    )

    assert opening.allowed is False
    assert "outdoor_air_pollution" in str(opening.reason)
    assert closing.allowed is True


def test_imgw_provider_diagnostic_publishes_local_warning_evidence() -> None:
    component, _, mqtt, _ = _component()
    warnings = [
        {
            "id": "imgw-local",
            "event_name": "Burze",
            "regions": ["1219"],
            "locally_applicable": True,
        },
    ]

    component.handle_external_api_result(
        result=ApiResult(
            provider="ImgwWarningsApiComponent",
            observations=(),
            health=_health("ImgwWarningsApiComponent"),
            evidence={"warnings": warnings, "warning_count": 1},
        )
    )

    attributes = mqtt.states["sensor.external_provider_imgw_warnings"][1]
    assert attributes["warning_count"] == 1
    assert attributes["warnings"] == warnings


def test_fault_context_refresh_replaces_old_observation_and_keeps_other_openings() -> None:
    hass = FakeHass()
    mqtt = FakeMqtt()
    bus = EventBus()
    module = object()
    symptoms = {
        "ExternalWeatherExposureWindOffice": Symptom(
            "ExternalWeatherExposureWindOffice", "sm_ext_weather_exposure", module, {}
        ),
        "ExternalWeatherExposureWindKitchen": Symptom(
            "ExternalWeatherExposureWindKitchen", "sm_ext_weather_exposure", module, {}
        ),
    }
    faults = {
        "ExternalWeatherExposure": Fault(
            "ExternalWeatherExposure", ["sm_ext_weather_exposure"], 2
        )
    }
    manager = FaultManager(hass, {}, symptoms, faults, bus, mqtt)

    manager.set_symptom(
        "ExternalWeatherExposureWindOffice",
        {"openings": "Okno biura", "observed_value": "21 m/s"},
    )
    manager.set_symptom(
        "ExternalWeatherExposureWindOffice",
        {"openings": "Okno biura", "observed_value": "22 m/s"},
    )
    manager.set_symptom(
        "ExternalWeatherExposureWindKitchen",
        {"openings": "Okno kuchni", "observed_value": "23 m/s"},
    )

    attributes = mqtt.get_attributes("sensor.fault_ExternalWeatherExposure")
    assert attributes["openings"] == "Okno biura, Okno kuchni"
    assert attributes["observed_value"] == "22 m/s, 23 m/s"
    assert "21 m/s" not in attributes["observed_value"]
