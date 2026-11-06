"""Safety-policy tests for External Hazard Monitoring recommendations."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from components.core.event_bus import EventBus
from components.core.localization import Localizer
from components.core.types_common import Fault, FaultState, RecoveryResult, SMState, Symptom
from components.external_apis import get_registered_api_components
from components.external_apis.core.models import (
    ApiResult,
    ExternalObservation,
    HazardType,
    Measurement,
    ProviderHealth,
    ProviderHealthState,
    WarningUrgency,
)
from components.safetycomponents.external_hazard.external_hazard_component import ExternalHazardComponent
from components.faults_manager.fault_manager import FaultManager


class FakeHass:
    def __init__(self) -> None:
        self.states = {"binary_sensor.office_window": "on"}
        self.localizer = Localizer({"language": "pl"})
        self.service_calls: list[tuple[str, dict[str, Any]]] = []
        self.logs: list[tuple[str, str]] = []
        self.listeners: list[tuple[Any, str, dict[str, Any]]] = []
        self.timers: list[tuple[Any, int, dict[str, Any]]] = []

    def get_state(self, entity_id: str, **_: Any) -> Any:
        return self.states.get(entity_id)

    def listen_state(self, callback: Any, entity: str, **kwargs: Any) -> Any:
        listener = (callback, entity, kwargs)
        self.listeners.append(listener)
        return listener

    def cancel_listen_state(self, handle: Any) -> None:
        self.listeners.remove(handle)

    def run_in(self, callback: Any, delay: int, **kwargs: Any) -> Any:
        timer = (callback, delay, kwargs)
        self.timers.append(timer)
        return timer

    def cancel_timer(self, _: Any) -> None:
        return None

    def change_contact(self, state: str, *, readback: str | None = None) -> None:
        entity = "binary_sensor.office_window"
        old = self.states[entity]
        self.states[entity] = state if readback is None else readback
        for callback, listened_entity, kwargs in self.listeners:
            if listened_entity == entity:
                callback(entity, "state", old, state, **kwargs)

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
    "actuation_mode": "manual_and_user_confirmed",
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
    },
}


def test_confirmed_opening_declares_separate_recovery_health() -> None:
    """Contact and actuator failures have distinct component fault owners."""

    dependencies = ExternalHazardComponent.get_entity_dependencies(
        {
            "openings": {
                "GarageGate": {
                    "entity_id": "binary_sensor.garage_gate",
                    "execution_policy": "user_confirmed",
                    "actuator_entity_id": "cover.garage_gate",
                }
            }
        }
    )

    assert [item["fault_name"] for item in dependencies] == [
        "InputMonitoringUnavailable",
        "ExternalRecoveryUnavailable",
    ]


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


def _component(
    kind: str = "window",
) -> tuple[ExternalHazardComponent, FakeHass, FakeMqtt, list[dict[str, Any]]]:
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
                "kind": kind,
                "hazards": ["frost", "wind", "rain", "storm", "outdoor_air_pollution"],
            }
        },
    }
    symptoms, recovery = component.get_symptoms_data(
        {component.component_name: component}, config
    )
    assert set(recovery) == set(symptoms)
    for symptom in symptoms.values():
        assert component.init_safety_mechanism(
            symptom.sm_name, symptom.name, symptom.parameters
        )
        assert component.enable_safety_mechanism(symptom.name, SMState.ENABLED)
    return component, hass, mqtt, events


@pytest.fixture
def opening_clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    elapsed = [0.0]
    monkeypatch.setattr(
        "components.safetycomponents.external_hazard.external_hazard_component.monotonic",
        lambda: elapsed[0],
    )
    return elapsed


def _wind_result() -> ApiResult:
    wind = _observation(
        "OpenMeteoWeatherApiComponent",
        HazardType.WIND,
        {
            "current_wind_gust": Measurement(22.0, "m/s"),
            "forecast_max_wind_gust": Measurement(22.0, "m/s"),
        },
    )
    return ApiResult(wind.provider, (wind,), _health(wind.provider))


@pytest.mark.parametrize("kind", ["door", "garage_door", "gate"])
def test_external_door_and_gate_qualify_after_one_minute_without_new_poll(
    kind: str, opening_clock: list[float]
) -> None:
    component, hass, _, events = _component(kind)
    hass.states["binary_sensor.office_window"] = "off"
    result = _wind_result()
    component.handle_external_api_result(result=result)
    events.clear()
    hass.change_contact("on")
    callback, delay, kwargs = hass.timers[-1]
    assert delay == 60
    opening_clock[0] = 59.0
    component.handle_external_api_result(result=result)
    assert len(hass.timers) == 1
    assert not any(event["state"] == FaultState.SET for event in events)
    opening_clock[0] = 60.0
    callback(**kwargs)
    assert any(event["state"] == FaultState.SET for event in events)
    assert hass.service_calls == []


@pytest.mark.parametrize("interruption", ["off", "unavailable"])
def test_opening_qualification_restarts_on_close_or_unknown_edge(
    interruption: str, opening_clock: list[float]
) -> None:
    component, hass, _, events = _component("door")
    component.handle_external_api_result(result=_wind_result())
    obsolete_callback, _, obsolete_kwargs = hass.timers[-1]
    opening_clock[0] = 10.0
    # The readback has already changed by the time HA delivers the old edge.
    hass.change_contact(interruption, readback="on")
    fresh_callback, delay, fresh_kwargs = hass.timers[-1]
    assert delay == 60
    opening_clock[0] = 60.0
    obsolete_callback(**obsolete_kwargs)
    assert not any(event["state"] == FaultState.SET for event in events)
    opening_clock[0] = 70.0
    fresh_callback(**fresh_kwargs)
    assert any(event["state"] == FaultState.SET for event in events)


@pytest.mark.parametrize("source_expired", [True, False])
def test_qualification_timer_rejects_unusable_provider_evidence(
    source_expired: bool, opening_clock: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    component, hass, _, events = _component("door")
    result = _wind_result()
    observation = result.observations[0]
    now = result.health.last_success_at
    assert now is not None
    monkeypatch.setattr(component, "_now", lambda: now + timedelta(seconds=opening_clock[0]))
    if source_expired:
        result = replace(result, observations=(replace(observation, valid_to=now + timedelta(seconds=30)),))
    else:
        result = replace(result, health=replace(result.health, stale_after_seconds=30))
    component.handle_external_api_result(result=result)
    callback, _, kwargs = hass.timers[-1]
    opening_clock[0] = 60.0
    callback(**kwargs)
    assert not any(event["state"] == FaultState.SET for event in events)


def test_valid_imgw_degree_three_bypasses_door_qualification() -> None:
    component, _, _, events = _component("door")
    wind = replace(
        _observation("ImgwWarningsApiComponent", HazardType.WIND, {}, confirmed=True),
        provider_level="3",
        warning_urgency=WarningUrgency.IMMEDIATE,
    )
    component.handle_external_api_result(result=ApiResult(wind.provider, (wind,), _health(wind.provider)))
    assert any(event["state"] == FaultState.SET for event in events)


def test_registered_non_imgw_warning_can_qualify_an_open_door(monkeypatch: pytest.MonkeyPatch) -> None:
    plugins = get_registered_api_components()
    name = "BerlinWarningsApiComponent"
    plugins[name] = plugins["ImgwWarningsApiComponent"]
    monkeypatch.setattr(
        "components.safetycomponents.external_hazard.external_hazard_component.get_registered_api_components",
        lambda: plugins,
    )
    component, _, mqtt, events = _component("door")
    component.enabled_providers = {name}
    warning = replace(
        _observation(name, HazardType.WIND, {"event_name": Measurement("Wind warning")}, confirmed=True),
        provider_level="critical",
        warning_urgency=WarningUrgency.IMMEDIATE,
    )
    component.handle_external_api_result(result=ApiResult(name, (warning,), _health(name)))

    assert any(event["state"] == FaultState.SET for event in events)
    attributes = mqtt.states["sensor.external_provider_berlin_warnings"][1]
    assert attributes["capability"] == "OfficialWeatherWarnings"
    assert attributes["warnings"][0]["event_name"] == "Wind warning"


def test_no_provider_cannot_supply_clear_evidence_for_an_open_window() -> None:
    component, _, mqtt, events = _component()
    component.enabled_providers.clear()

    component._evaluate_all()

    assert component._hazard_evidence(HazardType.WIND)[0] == "unknown"
    assert mqtt.states["sensor.external_hazard_state"][0] == "unavailable"
    assert not any(event["state"] == FaultState.CLEARED for event in events)


def test_clear_timer_requires_current_positive_evidence() -> None:
    component, hass, _, events = _component()
    component.policy["clear_delay_seconds"] = 120
    component.handle_external_api_result(result=_wind_result())
    symptom_id = "ExternalWeatherExposureWindOfficeWindow"
    assert component.symptom_states[symptom_id] == FaultState.SET
    hass.change_contact("off")
    callback, _, kwargs = hass.timers[-1]
    hass.states["binary_sensor.office_window"] = "unavailable"
    callback(**kwargs)
    assert component.symptom_states[symptom_id] == FaultState.SET
    hass.change_contact("off")
    callback, _, kwargs = hass.timers[-1]
    callback(**kwargs)
    assert component.symptom_states[symptom_id] == FaultState.CLEARED


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


def test_gate_recovery_requires_confirmation_and_uses_directional_cover() -> None:
    hass = FakeHass()
    hass.states = {"binary_sensor.external_gate": "on"}
    component = ExternalHazardComponent(hass, object(), EventBus(), FakeMqtt())
    config = {
        "policy": POLICY,
        "openings": {
            "ExternalGate": {
                "area_id": "frontyard",
                "area_name": "Przed domem",
                "entity_id": "binary_sensor.external_gate",
                "friendly_name": "Brama zewnętrzna",
                "kind": "gate",
                "hazards": ["wind"],
                "actuator_entity_id": "cover.gate",
                "execution_policy": "user_confirmed",
                "confirmation_timeout_seconds": 180,
            }
        },
    }
    symptoms, recoveries = component.get_symptoms_data(
        {component.component_name: component}, config
    )
    symptom = symptoms["ExternalWeatherExposureWindExternalGate"]
    result = recoveries[symptom.name].rec_fun(
        hass, symptom, object(), **recoveries[symptom.name].params
    )

    assert result.execution_policy == "user_confirmed"
    assert result.changed_sensors == {"binary_sensor.external_gate": "off"}
    assert result.changed_actuators == {"cover.gate": "closed"}
    assert result.confirmation_timeout_seconds == 180
    assert hass.service_calls == []


def test_air_quality_observation_summary_exposes_current_operator_value() -> None:
    component, _, mqtt, _ = _component()
    air_quality = _observation(
        "OpenMeteoAirQualityApiComponent",
        HazardType.OUTDOOR_AIR_POLLUTION,
        {
            "current_european_aqi": Measurement(24, "EAQI"),
        },
    )

    component.handle_external_api_result(
        result=ApiResult(
            provider=air_quality.provider,
            observations=(air_quality,),
            health=_health(air_quality.provider),
        )
    )

    summary = mqtt.states["sensor.external_provider_open_meteo_air_quality"][1][
        "observations"
    ][0]
    assert summary["hazard_type"] == "outdoor_air_pollution"
    assert summary["display_value"] == 24
    assert summary["display_unit"] == "EAQI"


def test_provider_diagnostic_observation_summaries_are_bounded() -> None:
    component, _, mqtt, _ = _component()
    observation = _observation(
        "OpenMeteoAirQualityApiComponent",
        HazardType.OUTDOOR_AIR_POLLUTION,
        {"current_european_aqi": Measurement(24, "EAQI")},
    )

    component.handle_external_api_result(
        result=ApiResult(
            provider=observation.provider,
            observations=(observation,) * 65,
            health=_health(observation.provider),
        )
    )

    attributes = mqtt.states["sensor.external_provider_open_meteo_air_quality"][1]
    assert attributes["observation_count"] == 65
    assert len(attributes["observations"]) == 64


def test_aggregate_remains_unavailable_until_every_provider_is_healthy() -> None:
    component, _, mqtt, _ = _component()

    component.handle_external_api_result(
        result=ApiResult(
            provider="OpenMeteoWeatherApiComponent",
            observations=(),
            health=_health(
                "OpenMeteoWeatherApiComponent", ProviderHealthState.UNAVAILABLE
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
            "regions": ["0000"],
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
