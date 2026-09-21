"""Contract tests for independent internal binary hazard alarms."""

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import MagicMock

from components.core.event_bus import EventBus
from components.core.mqtt_entity_manager import MqttEntityManager
from components.core.types_common import FaultState, SMState
from components.safetycomponents.internal_environmental_hazard.internal_environmental_hazard_monitor_component import (
    InternalEnvironmentalHazardMonitorComponent,
)
from components.safetycomponents.internal_environmental_hazard.state_store import (
    InMemoryInternalEnvironmentStateStore,
)


GAS_ENTITY = "binary_sensor.bathroom_gasleak_detector"
CO_ENTITY = "binary_sensor.bathroom_carbonoxide_detector"


def _configuration(*, health_failure_seconds: int = 5) -> dict:
    return {
        "profiles": {
            "binary": {
                "version": "1.0",
                "provenance": "test contract",
                "alarm_states": ["on"],
                "clear_states": ["off"],
                "test_states": ["test"],
                "unavailable_states": ["unknown", "unavailable"],
                "clear_duration_seconds": 30,
                "authoritative_clear": True,
            }
        },
        "detectors": {
            "BathroomFlammableGas": {
                "area_id": "bathroom",
                "area_name": "Łazienka",
                "entity_id": GAS_ENTITY,
                "friendly_name": "Czujnik gazu w łazience",
                "hazard": "flammable_gas",
                "profile": "binary",
                "gas_identity": "flammable_gas_unspecified",
                "enabled": True,
            },
            "BathroomCarbonMonoxide": {
                "area_id": "bathroom",
                "area_name": "Łazienka",
                "entity_id": CO_ENTITY,
                "friendly_name": "Czujnik tlenku węgla w łazience",
                "hazard": "carbon_monoxide",
                "profile": "binary",
                "enabled": True,
            },
        },
        "health_failure_debounce_seconds": health_failure_seconds,
        "health_recovery_debounce_seconds": 60,
        "persistence": {
            "enabled": False,
            "state_file": "unused.json",
            "maximum_detectors": 8,
        },
    }


def _snapshot(state: str, at: datetime) -> dict:
    return {
        "state": state,
        "last_changed": at.isoformat(),
        "last_updated": at.isoformat(),
        "attributes": {},
    }


def _build_component(
    states: dict[str, dict],
    *,
    now: datetime,
    health_failure_seconds: int = 5,
) -> tuple[InternalEnvironmentalHazardMonitorComponent, MagicMock, list[dict]]:
    hass_app = MagicMock()
    hass_app.localizer = None
    hass_app.get_state.side_effect = lambda entity_id, **_kwargs: states.get(entity_id)
    hass_app.run_in.side_effect = lambda callback, delay, **kwargs: (
        callback,
        delay,
        kwargs,
    )
    event_bus = EventBus()
    events: list[dict] = []
    event_bus.subscribe("symptom", lambda **payload: events.append(payload))
    component = InternalEnvironmentalHazardMonitorComponent(
        hass_app,
        MagicMock(),
        event_bus,
        MqttEntityManager(hass_app),
    )
    component._now = lambda: now  # type: ignore[method-assign]
    symptoms, recovery = component.get_symptoms_data(
        {component.component_name: component},
        _configuration(health_failure_seconds=health_failure_seconds),
    )
    assert recovery == {}
    for symptom in symptoms.values():
        assert component.init_safety_mechanism(
            symptom.sm_name, symptom.name, symptom.parameters
        )
        assert component.enable_safety_mechanism(symptom.name, SMState.ENABLED)
    events.clear()
    hass_app.reset_mock()
    hass_app.get_state.side_effect = lambda entity_id, **_kwargs: states.get(entity_id)
    hass_app.run_in.side_effect = lambda callback, delay, **kwargs: (
        callback,
        delay,
        kwargs,
    )
    return component, hass_app, events


def _event(events: list[dict], symptom_id: str) -> dict:
    return next(event for event in reversed(events) if event["symptom_id"] == symptom_id)


def test_flammable_gas_alarm_sets_independently_of_normal_co_detector() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("on", now),
        CO_ENTITY: _snapshot("off", now),
    }
    component, hass_app, events = _build_component(states, now=now)

    gas = component.safety_mechanisms[
        "InternalEnv_flammable_gas_BathroomFlammableGas"
    ]
    co = component.safety_mechanisms[
        "InternalEnv_carbon_monoxide_BathroomCarbonMonoxide"
    ]
    assert component.sm_iehm_flammable_gas(gas) is True
    assert component.sm_iehm_carbon_monoxide(co) is False

    gas_event = _event(
        events, "InternalEnv_flammable_gas_BathroomFlammableGas"
    )
    assert gas_event["state"] == FaultState.SET
    assert gas_event["additional_info"]["hazard"] == "flammable gas"
    assert gas_event["additional_info"]["gas_identity"] == (
        "flammable_gas_unspecified"
    )
    non_mqtt_calls = [
        call
        for call in hass_app.call_service.call_args_list
        if not call.args or call.args[0] != "mqtt/publish"
    ]
    assert non_mqtt_calls == []


def test_co_binary_alarm_does_not_require_numeric_measurement() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("off", now),
        CO_ENTITY: _snapshot("on", now),
    }
    component, _hass_app, events = _build_component(states, now=now)
    mechanism = component.safety_mechanisms[
        "InternalEnv_carbon_monoxide_BathroomCarbonMonoxide"
    ]

    assert component.sm_iehm_carbon_monoxide(mechanism) is True
    event = _event(events, mechanism.name)
    assert event["state"] == FaultState.SET
    assert "observed_value" not in event["additional_info"]


def test_unavailable_or_test_state_never_clears_active_alarm() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("on", now),
        CO_ENTITY: _snapshot("off", now),
    }
    component, hass_app, events = _build_component(states, now=now)
    mechanism = component.safety_mechanisms[
        "InternalEnv_flammable_gas_BathroomFlammableGas"
    ]
    component.sm_iehm_flammable_gas(mechanism)

    states[GAS_ENTITY] = _snapshot("unknown", now)
    component.sm_iehm_flammable_gas(mechanism)
    states[GAS_ENTITY] = _snapshot("test", now)
    component.sm_iehm_flammable_gas(mechanism)

    assert component._detectors["BathroomFlammableGas"].alarm_active is True
    assert [event["state"] for event in events if event["symptom_id"] == mechanism.name] == [
        FaultState.SET
    ]
    hass_app.cancel_timer.assert_not_called()


def test_state_event_latches_alarm_edge_without_rereading_newer_clear() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("off", now),
        CO_ENTITY: _snapshot("off", now),
    }
    component, _hass_app, events = _build_component(states, now=now)

    component._entity_changed(
        GAS_ENTITY,
        "all",
        _snapshot("off", now),
        _snapshot("on", now),
    )

    event = _event(
        events, "InternalEnv_flammable_gas_BathroomFlammableGas"
    )
    assert event["state"] == FaultState.SET
    assert component._detectors["BathroomFlammableGas"].alarm_active is True


def test_authoritative_clear_requires_full_profile_interval() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("on", now),
        CO_ENTITY: _snapshot("off", now),
    }
    component, _hass_app, events = _build_component(states, now=now)
    mechanism = component.safety_mechanisms[
        "InternalEnv_flammable_gas_BathroomFlammableGas"
    ]
    component.sm_iehm_flammable_gas(mechanism)

    clear_at = now + timedelta(seconds=1)
    states[GAS_ENTITY] = _snapshot("off", clear_at)
    component._now = lambda: clear_at  # type: ignore[method-assign]
    component.sm_iehm_flammable_gas(mechanism)
    assert component._detectors["BathroomFlammableGas"].alarm_active is True

    component._now = lambda: clear_at + timedelta(seconds=30)  # type: ignore[method-assign]
    component._alarm_clear_elapsed(detector_key="BathroomFlammableGas")

    assert component._detectors["BathroomFlammableGas"].alarm_active is False
    assert _event(events, mechanism.name)["state"] == FaultState.CLEARED
    assert component._detectors["BathroomFlammableGas"].gas_switching_inhibited is True


def test_alarm_state_is_healthy_detector_operation() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("on", now),
        CO_ENTITY: _snapshot("off", now),
    }
    component, _hass_app, events = _build_component(states, now=now)
    health = component.safety_mechanisms[
        "InternalEnv_detector_health_BathroomFlammableGas"
    ]

    assert component.sm_iehm_detector_health(health) is False
    assert _event(events, health.name)["state"] == FaultState.CLEARED


def test_unavailable_detector_raises_separate_health_symptom() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("unknown", now),
        CO_ENTITY: _snapshot("off", now),
    }
    component, _hass_app, events = _build_component(
        states, now=now, health_failure_seconds=0
    )
    health = component.safety_mechanisms[
        "InternalEnv_detector_health_BathroomFlammableGas"
    ]

    assert component.sm_iehm_detector_health(health) is True
    assert _event(events, health.name)["state"] == FaultState.SET
    assert component.symptom_states[
        "InternalEnv_flammable_gas_BathroomFlammableGas"
    ] == FaultState.NOT_TESTED


def test_persisted_alarm_is_reasserted_when_current_state_is_unknown() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("unknown", now),
        CO_ENTITY: _snapshot("off", now),
    }
    component, _hass_app, events = _build_component(states, now=now)
    store = InMemoryInternalEnvironmentStateStore(
        {
            "version": 1,
            "detectors": {
                "BathroomFlammableGas": {
                    "alarm_active": True,
                    "health_active": False,
                    "gas_switching_inhibited": True,
                    "last_authoritative_clear_at": None,
                }
            },
        }
    )
    component._state_store = store
    component._restore_state()
    mechanism = component.safety_mechanisms[
        "InternalEnv_flammable_gas_BathroomFlammableGas"
    ]

    assert component.sm_iehm_flammable_gas(mechanism) is True
    assert _event(events, mechanism.name)["state"] == FaultState.SET


def test_group_b_dependencies_are_diagnostic_only_and_keep_stable_fault_owner() -> None:
    dependencies = (
        InternalEnvironmentalHazardMonitorComponent.get_entity_dependencies(
            _configuration()
        )
    )

    assert {item["entity_id"] for item in dependencies} == {GAS_ENTITY, CO_ENTITY}
    assert {item["fault_owner"] for item in dependencies} == {"none"}
    assert {item["detection_budget_seconds"] for item in dependencies} == {60}


def test_unconfigured_hazard_fault_is_inactive() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    component, _hass_app, _events = _build_component(
        {GAS_ENTITY: _snapshot("off", now), CO_ENTITY: _snapshot("off", now)},
        now=now,
    )

    assert component.get_inactive_fault_names() == {"InternalSmokeDetected"}


def test_diagnostic_payload_keeps_alarm_and_health_separate() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("on", now),
        CO_ENTITY: _snapshot("off", now),
    }
    component, hass_app, _events = _build_component(states, now=now)
    mechanism = component.safety_mechanisms[
        "InternalEnv_flammable_gas_BathroomFlammableGas"
    ]
    component.sm_iehm_flammable_gas(mechanism)
    payloads = [
        json.loads(call.kwargs["payload"])
        for call in hass_app.call_service.call_args_list
        if call.args
        and call.args[0] == "mqtt/publish"
        and call.kwargs.get("topic")
        == "safety_component/attributes/internal_environment_bathroom_flammable_gas"
    ]

    assert payloads[-1]["alarm_active"] is True
    assert payloads[-1]["health_fault_active"] is False
    assert payloads[-1]["gas_switching_inhibited"] is True
