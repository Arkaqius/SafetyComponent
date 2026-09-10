"""Tests for configured Safety Doors timeout monitoring."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from components.core.event_bus import EventBus
from components.core.mqtt_entity_manager import MqttEntityManager
from components.core.types_common import FaultState, SMState
from components.safetycomponents.safety_doors.safety_doors_component import (
    SafetyDoorsComponent,
)
from components.safetycomponents.safety_doors.schema import (
    SafetyDoorCondition,
    SafetyDoorConfig,
    validate_safety_doors_config,
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
        "area_id": "garage",
        "area_name": "Garaż",
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
    assert events[-1]["additional_info"]["location"] == "Garaż"
    attributes = _published_attributes(hass_app)[-1]
    assert attributes["area_id"] == "garage"
    assert attributes["area_name"] == "Garaż"


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


def test_recovery_dry_run_accepts_overrides_without_runtime_side_effects() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    component, hass_app, events = _build_component(
        {
            "state": "open",
            "last_changed": (now - timedelta(seconds=120)).isoformat(),
        },
        now=now,
    )
    mechanism = component.safety_mechanisms[
        "SafetyDoorOpenTimeoutGarageGate"
    ]
    runtime_before = (
        component._door_runtime[mechanism.name].opened_at,
        component._door_runtime[mechanism.name].timer_handle,
        component._door_runtime[mechanism.name].active,
    )
    calls_before = list(hass_app.call_service.call_args_list)

    assert (
        component.sm_safety_door_open_timeout(
            mechanism,
            {"binary_sensor.garage_gate": "closed"},
        )
        is False
    )

    runtime_after = component._door_runtime[mechanism.name]
    assert (
        runtime_after.opened_at,
        runtime_after.timer_handle,
        runtime_after.active,
    ) == runtime_before
    assert hass_app.call_service.call_args_list == calls_before
    hass_app.run_in.assert_not_called()
    hass_app.cancel_timer.assert_not_called()
    assert events == []


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


def test_rejects_unknown_duplicate_and_incomplete_mechanisms() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    component, hass_app, _events = _build_component(
        {"state": "closed", "last_changed": now.isoformat()},
        now=now,
    )
    existing_name = "SafetyDoorOpenTimeoutGarageGate"

    assert component.init_safety_mechanism("unknown", "Unknown", {}) is False
    assert (
        component.init_safety_mechanism(
            "sm_safety_door_open_timeout", existing_name, {}
        )
        is False
    )
    assert (
        component.init_safety_mechanism(
            "sm_safety_door_open_timeout", "IncompleteDoor", {}
        )
        is False
    )
    assert hass_app.log.call_count >= 3


def test_enable_rejects_unknown_name_and_invalid_state() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    component, _hass_app, _events = _build_component(
        {"state": "closed", "last_changed": now.isoformat()},
        now=now,
    )
    name = "SafetyDoorOpenTimeoutGarageGate"

    assert component.enable_safety_mechanism("missing", SMState.ENABLED) is False
    assert component.enable_safety_mechanism(name, "invalid") is False  # type: ignore[arg-type]


def test_disabled_mechanism_does_not_evaluate_and_cancels_timer() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    component, hass_app, events = _build_component(
        {"state": "open", "last_changed": now.isoformat()},
        now=now,
    )
    name = "SafetyDoorOpenTimeoutGarageGate"
    mechanism = component.safety_mechanisms[name]
    component._door_runtime[name].timer_handle = "pending-timer"

    assert component.enable_safety_mechanism(name, SMState.DISABLED) is True
    assert component.sm_safety_door_open_timeout(mechanism) is False
    hass_app.cancel_timer.assert_called_once_with("pending-timer")
    assert events == []


def test_timeout_callback_ignores_removed_mechanism_and_rechecks_known_one() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    component, _hass_app, _events = _build_component(
        {
            "state": "open",
            "last_changed": (now - timedelta(seconds=61)).isoformat(),
        },
        now=now,
    )
    name = "SafetyDoorOpenTimeoutGarageGate"

    component._timeout_reached(sm_name="missing")
    component._door_runtime[name].timer_handle = "elapsed-timer"
    component._timeout_reached(sm_name=name)

    assert component._door_runtime[name].timer_handle is None
    assert component.symptom_states[name] == FaultState.SET


def test_timer_cancellation_failure_is_logged_and_runtime_is_cleared() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    component, hass_app, _events = _build_component(
        {"state": "closed", "last_changed": now.isoformat()},
        now=now,
    )
    name = "SafetyDoorOpenTimeoutGarageGate"
    component._door_runtime[name].timer_handle = "bad-timer"
    hass_app.cancel_timer.side_effect = RuntimeError("scheduler unavailable")

    component._cancel_timer(name)

    assert component._door_runtime[name].timer_handle is None
    hass_app.log.assert_called_with(
        f"Unable to cancel Safety Doors timer {name}: scheduler unavailable",
        level="WARNING",
    )


def test_duplicate_symptom_state_is_not_published_twice() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    component, _hass_app, events = _build_component(
        {"state": "closed", "last_changed": now.isoformat()},
        now=now,
    )
    mechanism = component.safety_mechanisms["SafetyDoorOpenTimeoutGarageGate"]

    component.sm_safety_door_open_timeout(mechanism)
    component.sm_safety_door_open_timeout(mechanism)

    assert len(events) == 1


def test_condition_read_exception_and_scalar_door_state_are_safe() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    component, hass_app, _events = _build_component(
        {"state": "closed", "last_changed": now.isoformat()},
        now=now,
        condition=_condition(),
        condition_state={"state": "empty", "last_changed": now.isoformat()},
    )
    mechanism = component.safety_mechanisms["SafetyDoorOpenTimeoutGarageGate"]
    hass_app.get_state.side_effect = RuntimeError("HA unavailable")

    assert component._read_condition_state(mechanism) == (
        "unavailable",
        "unavailable",
        None,
    )

    hass_app.get_state.side_effect = None
    hass_app.get_state.return_value = "ajar"
    assert component._read_door_state("binary_sensor.garage_gate") == (
        "unavailable",
        None,
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("not-a-date", None),
        (
            "2026-07-29T12:00:00",
            datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc),
        ),
    ],
)
def test_parse_datetime_handles_invalid_and_naive_values(value, expected) -> None:
    assert SafetyDoorsComponent._parse_datetime(value) == expected


@pytest.mark.parametrize(
    "condition",
    [
        "invalid",
        {"entity_id": 123, "pass_states": ["empty"], "blocked_states": ["occupied"]},
        {"entity_id": "sensor.mode", "pass_states": "empty", "blocked_states": ["occupied"]},
        {"entity_id": "", "pass_states": ["empty"], "blocked_states": ["occupied"]},
        {"entity_id": "sensor.mode", "pass_states": [""], "blocked_states": ["occupied"]},
        {"entity_id": "sensor.mode", "pass_states": ["empty"], "blocked_states": ["empty"]},
    ],
)
def test_normalize_condition_rejects_invalid_runtime_data(condition) -> None:
    with pytest.raises((KeyError, ValueError)):
        SafetyDoorsComponent._normalize_condition(condition)


@pytest.mark.parametrize(
    "condition",
    [
        {"entity_id": "sensor.mode", "pass_states": [""], "blocked_states": ["occupied"]},
        {"entity_id": "sensor.mode", "pass_states": ["empty", "EMPTY"], "blocked_states": ["occupied"]},
        {"entity_id": "sensor.mode", "pass_states": ["empty"], "blocked_states": ["EMPTY"]},
    ],
)
def test_condition_schema_rejects_empty_duplicate_and_overlapping_states(
    condition,
) -> None:
    with pytest.raises(ValueError):
        SafetyDoorCondition.model_validate(condition)


def test_door_schema_rejects_empty_area_id() -> None:
    with pytest.raises(ValueError, match="area_id"):
        SafetyDoorConfig.model_validate(
            {"area_id": " ", "entity_id": "binary_sensor.garage_gate"}
        )


def test_nonstrict_schema_logs_nested_extra_keys() -> None:
    log = MagicMock()

    runtime = validate_safety_doors_config(
        {
            "defaults": {"timeout_seconds": 120, "future_default": True},
            "doors": {
                "GarageGate": {
                    "area_id": "garage",
                    "entity_id": "binary_sensor.garage_gate",
                    "future_door": True,
                    "condition": {
                        "entity_id": "sensor.home_monitor_occupancy",
                        "pass_states": ["empty"],
                        "blocked_states": ["occupied"],
                        "future_condition": True,
                    },
                }
            },
            "future_component": True,
        },
        strict_validation=False,
        log=log,
    )

    assert runtime[0]["GarageGate"]["timeout_seconds"] == 120
    assert log.call_count >= 4
