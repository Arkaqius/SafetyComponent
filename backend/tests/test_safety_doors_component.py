"""Tests for configured Safety Doors timeout monitoring."""

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
) -> tuple[SafetyDoorsComponent, MagicMock, list[dict]]:
    hass_app = MagicMock()
    hass_app.get_state.return_value = state
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
    symptoms, recoveries = component.get_symptoms_data(
        modules,
        [
            {
                "GarageGate": {
                    "entity_id": "binary_sensor.garage_gate",
                    "timeout_seconds": timeout_seconds,
                }
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

    hass_app.get_state.return_value = {
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
