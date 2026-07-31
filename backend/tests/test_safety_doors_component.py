"""Tests for configured Safety Doors timeout monitoring."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from components.core.event_bus import EventBus
from components.core.mqtt_entity_manager import MqttEntityManager
from components.core.types_common import FaultState, SMState
from components.safetycomponents.safety_doors.safety_doors_component import (
    SafetyDoorsComponent,
)


def _build_component(
    state: dict[str, str],
    *,
    now: datetime,
    timeout_seconds: int = 60,
    condition: dict[str, object] | None = None,
    condition_state: dict[str, str] | None = None,
) -> tuple[SafetyDoorsComponent, MagicMock, list[dict]]:
    hass_app = MagicMock()
    entity_states = {"binary_sensor.garage_gate": state}
    if condition is not None:
        entity_states[str(condition["entity_id"])] = condition_state
    hass_app.get_state.side_effect = (
        lambda entity_id, **_kwargs: entity_states.get(entity_id)
    )
    hass_app.run_in.return_value = "door-timer"
    mqtt_entities = MqttEntityManager(hass_app)
    event_bus = EventBus()
    events: list[dict] = []
    event_bus.subscribe("symptom", lambda **payload: events.append(payload))

    component = SafetyDoorsComponent(
        hass_app,
        MagicMock(),
        event_bus,
        mqtt_entities,
    )
    component._now = lambda: now  # type: ignore[method-assign]
    modules = {component.component_name: component}
    parameters: dict[str, object] = {
        "entity_id": "binary_sensor.garage_gate",
        "timeout_seconds": timeout_seconds,
    }
    if condition is not None:
        parameters["condition"] = condition

    symptoms, recoveries = component.get_symptoms_data(
        modules,
        [
            {
                "GarageGate": parameters
            }
        ],
    )
    assert recoveries == {}
    symptom = symptoms["SafetyDoorOpenTimeoutGarageGate"]
    assert component.init_safety_mechanism(
        symptom.sm_name,
        symptom.name,
        symptom.parameters,
    )
    assert component.enable_safety_mechanism(symptom.name, SMState.ENABLED)
    return component, hass_app, events


def _published_states(hass_app: MagicMock) -> list[str]:
    return [
        call.kwargs["payload"]
        for call in hass_app.call_service.call_args_list
        if call.args
        and call.args[0] == "mqtt/publish"
        and call.kwargs.get("topic")
        == "safety_component/state/safety_door_garagegate"
    ]


def _published_attributes(hass_app: MagicMock) -> list[dict]:
    return [
        json.loads(call.kwargs["payload"])
        for call in hass_app.call_service.call_args_list
        if call.args
        and call.args[0] == "mqtt/publish"
        and call.kwargs.get("topic")
        == "safety_component/attributes/safety_door_garagegate"
        and call.kwargs.get("payload")
    ]


def _condition() -> dict[str, object]:
    return {
        "entity_id": "sensor.home_monitor_occupancy",
        "pass_states": ["empty"],
        "blocked_states": ["occupied"],
    }


def test_open_door_becomes_active_after_configured_timeout() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    component, hass_app, events = _build_component(
        {
            "state": "on",
            "last_changed": (now - timedelta(seconds=61)).isoformat(),
        },
        now=now,
    )
    mechanism = component.safety_mechanisms[
        "SafetyDoorOpenTimeoutGarageGate"
    ]

    assert component.sm_safety_door_open_timeout(mechanism) is True
    assert component.symptom_states[mechanism.name] == FaultState.SET
    assert _published_states(hass_app)[-1] == "active"
    assert events[-1]["additional_info"]["location"] == "GarageGate"


def test_open_door_stays_inactive_and_schedules_remaining_timeout() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    component, hass_app, events = _build_component(
        {
            "state": "open",
            "last_changed": (now - timedelta(seconds=20)).isoformat(),
        },
        now=now,
    )
    mechanism = component.safety_mechanisms[
        "SafetyDoorOpenTimeoutGarageGate"
    ]

    assert component.sm_safety_door_open_timeout(mechanism) is False
    assert component.symptom_states[mechanism.name] == FaultState.CLEARED
    assert _published_states(hass_app)[-1] == "inactive"
    hass_app.run_in.assert_called_once_with(
        component._timeout_reached,
        40,
        sm_name=mechanism.name,
    )
    assert events[-1]["state"] == FaultState.CLEARED


def test_closing_active_door_clears_condition_and_timer() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    component, hass_app, events = _build_component(
        {
            "state": "on",
            "last_changed": (now - timedelta(seconds=61)).isoformat(),
        },
        now=now,
    )
    mechanism = component.safety_mechanisms[
        "SafetyDoorOpenTimeoutGarageGate"
    ]
    component.sm_safety_door_open_timeout(mechanism)

    hass_app.get_state.side_effect = lambda entity_id, **_kwargs: {
        "state": "off",
        "last_changed": now.isoformat(),
    }
    assert component.sm_safety_door_open_timeout(mechanism) is False

    assert component.symptom_states[mechanism.name] == FaultState.CLEARED
    assert _published_states(hass_app)[-1] == "inactive"
    assert [event["state"] for event in events[-2:]] == [
        FaultState.SET,
        FaultState.CLEARED,
    ]


def test_unavailable_door_is_reported_without_new_open_fault() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    component, hass_app, events = _build_component(
        {"state": "unavailable", "last_changed": now.isoformat()},
        now=now,
    )
    mechanism = component.safety_mechanisms[
        "SafetyDoorOpenTimeoutGarageGate"
    ]

    assert component.sm_safety_door_open_timeout(mechanism) is False
    assert component.symptom_states[mechanism.name] == FaultState.NOT_TESTED
    assert _published_states(hass_app)[-1] == "unavailable"
    assert events == []


def test_blocked_condition_suspends_timeout_and_clears_fault() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    component, hass_app, events = _build_component(
        {
            "state": "open",
            "last_changed": (now - timedelta(seconds=120)).isoformat(),
        },
        now=now,
        condition=_condition(),
        condition_state={
            "state": "occupied",
            "last_changed": (now - timedelta(seconds=30)).isoformat(),
        },
    )
    mechanism = component.safety_mechanisms[
        "SafetyDoorOpenTimeoutGarageGate"
    ]

    assert component.sm_safety_door_open_timeout(mechanism) is False
    assert component.symptom_states[mechanism.name] == FaultState.CLEARED
    assert _published_states(hass_app)[-1] == "blocked"
    assert _published_attributes(hass_app)[-1]["condition_result"] == "blocked"
    assert _published_attributes(hass_app)[-1]["condition_state"] == "occupied"
    hass_app.run_in.assert_not_called()
    assert events[-1]["state"] == FaultState.CLEARED


def test_pass_condition_starts_timeout_when_condition_became_pass() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    component, hass_app, _events = _build_component(
        {
            "state": "open",
            "last_changed": (now - timedelta(seconds=100)).isoformat(),
        },
        now=now,
        condition=_condition(),
        condition_state={
            "state": "empty",
            "last_changed": (now - timedelta(seconds=20)).isoformat(),
        },
    )
    mechanism = component.safety_mechanisms[
        "SafetyDoorOpenTimeoutGarageGate"
    ]

    assert component.sm_safety_door_open_timeout(mechanism) is False
    hass_app.run_in.assert_called_once_with(
        component._timeout_reached,
        40,
        sm_name=mechanism.name,
    )
    attributes = _published_attributes(hass_app)[-1]
    assert attributes["condition_result"] == "pass"
    assert attributes["open_duration_seconds"] == 20


def test_condition_entity_is_monitored_for_state_changes() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    _component, hass_app, _events = _build_component(
        {"state": "closed", "last_changed": now.isoformat()},
        now=now,
        condition=_condition(),
        condition_state={"state": "empty", "last_changed": now.isoformat()},
    )

    listened_entities = [
        call.args[1] for call in hass_app.listen_state.call_args_list
    ]
    assert listened_entities == [
        "binary_sensor.garage_gate",
        "sensor.home_monitor_occupancy",
    ]


def test_unsupported_condition_state_does_not_start_new_fault() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    component, hass_app, events = _build_component(
        {
            "state": "open",
            "last_changed": (now - timedelta(seconds=120)).isoformat(),
        },
        now=now,
        condition=_condition(),
        condition_state={
            "state": "guest",
            "last_changed": now.isoformat(),
        },
    )
    mechanism = component.safety_mechanisms[
        "SafetyDoorOpenTimeoutGarageGate"
    ]

    assert component.sm_safety_door_open_timeout(mechanism) is False
    assert component.symptom_states[mechanism.name] == FaultState.NOT_TESTED
    assert _published_states(hass_app)[-1] == "unavailable"
    assert _published_attributes(hass_app)[-1]["condition_state"] == "guest"
    hass_app.run_in.assert_not_called()
    assert events == []
