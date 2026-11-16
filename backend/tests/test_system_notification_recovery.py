"""System-level tests for notification and recovery manager integration."""

import copy
from time import perf_counter
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest

from components.core.types_common import FaultState, RecoveryActionState
from components.core.fault_state_policy import FaultEvaluationStatus
from safety_lifecycle_support import FakeMonotonicClock

from .fixtures.hass_fixture import (
    drain_responses,
    MockBehavior,
    default_mock_behaviors,
    mock_get_state,
    mqtt_payloads,
    mqtt_topic_for,
    update_mocked_get_state,
)


class _StatefulHassState:
    """Small state store that makes set_state writes visible to get_state reads."""

    def __init__(self, mock_behaviors: list[MockBehavior]) -> None:
        self.entities: dict[str, dict[str, Any]] = {}
        self.mock_behaviors = mock_behaviors

    def set_state(
        self,
        entity_id: str,
        state: Any = None,
        attributes: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        entity_state = self.entities.setdefault(
            entity_id, {"state": None, "attributes": {}}
        )
        entity_state["state"] = state
        if attributes is not None:
            entity_state["attributes"] = attributes

    def get_state(self, entity_id: str, **kwargs: Any) -> Any:
        attribute = kwargs.get("attribute")
        stored_state = self.entities.get(entity_id)

        if attribute == "all":
            if stored_state is None:
                sensor_value = mock_get_state(entity_id, self.mock_behaviors)
                if sensor_value is None:
                    return None
                return {"state": sensor_value, "attributes": {}}
            return {
                "state": stored_state["state"],
                "attributes": stored_state.get("attributes", {}),
            }

        if stored_state is not None:
            if attribute:
                return stored_state.get("attributes", {}).get(attribute)
            return stored_state["state"]

        return mock_get_state(entity_id, self.mock_behaviors)


def _install_stateful_hass(app_instance: Any, mock_behaviors: list[MockBehavior]) -> _StatefulHassState:
    state_store = _StatefulHassState(mock_behaviors)
    app_instance.get_state = MagicMock(side_effect=state_store.get_state)
    app_instance.set_state = MagicMock(side_effect=state_store.set_state)
    app_instance.call_service.return_value = {"success": True, "result": {}}
    return state_store


def _notify_calls(app_instance: Any) -> list[Any]:
    drain_responses(app_instance)
    return [
        call
        for call in app_instance.call_service.call_args_list
        if call.args and call.args[0] == "notify/mobile_app_example_phone"
    ]


def test_throwing_response_consumer_does_not_block_notification_or_recovery(
    mocked_hass_app_with_temp_component,
):
    app, *_ = mocked_hass_app_with_temp_component
    _install_stateful_hass(app, default_mock_behaviors())
    app.initialize()
    admitted = []

    def broken_consumer(*, fault_name, **_):
        if fault_name != "RiskyTemperature":
            return
        admitted.append("broken")
        raise RuntimeError("fictional consumer failure")

    app.event_bus.subscribe("fault", broken_consumer, priority=-10, isolated=True)
    app.event_bus.subscribe("fault", lambda **data: admitted.append("last")
                            if data["fault_name"] == "RiskyTemperature" else None, priority=100)
    app.fm.set_symptom("RiskyTemperatureOffice", {"location": "Office"})
    assert admitted == ["broken", "last"]
    assert app.event_bus.admission_failures == 1
    assert app.notify_man.active_notification
    assert app.faults["RiskyTemperature"].evaluation.active


def test_root_stalled_target_and_storage_leave_healthy_target_and_recovery_admission_live(
    mocked_hass_app_with_temp_component,
):
    app, *_ = mocked_hass_app_with_temp_component
    app.args = copy.deepcopy(app.args)
    app.args["user_config"]["notification"]["mobile"] = {
        "services": ["notify/fixture_stalled", "notify/fixture_healthy"],
    }
    app.initialize()
    clock = FakeMonotonicClock()
    app.service_dispatcher.clock = clock
    completions = []

    def transport(service, **payload):
        callback = payload["callback"]
        if service == "notify/fixture_stalled":
            completions.append(callback)
        else:
            callback({"success": True, "result": None})
        return "scheduled-fixture"

    app.call_service.side_effect = transport
    admitted = []
    app.event_bus.subscribe("fault", lambda **data: admitted.append(bool(app.notify_man.active_notification))
                            if data["fault_name"] == "RiskyTemperature" else None, priority=5, isolated=True)
    started = perf_counter()
    app.fm.set_symptom("RiskyTemperatureOffice", {"location": "Office"})
    assert perf_counter() - started < 1
    assert admitted == [True] and app.faults["RiskyTemperature"].evaluation.active
    assert not app.notify_man._durable_revision
    # Deliberately leave the one storage job unfinished throughout this flow.
    for _ in range(8):
        app.mqtt_entities.projections.tick()
        app.service_dispatcher.tick()
    tag = app.fm._generate_fault_tag("RiskyTemperature")
    healthy = [call for call in app.call_service.call_args_list if call.args[0] == "notify/fixture_healthy"
               and call.kwargs["data"]["tag"] == tag]
    assert len(healthy) == 1 and completions
    assert app.notify_man._counters["accepted_attempts"] >= 1
    assert len(app._snapshot_executors["notification_state"].jobs) == 1
    clock.advance(121)
    app.service_dispatcher.tick()
    assert app.service_dispatcher.registry.quarantined_count >= 1
    assert app.notify_man._counters["deadline_misses"] >= 1
    completions[0]({"success": True})
    app.service_dispatcher.tick()
    assert not any(entry["service"] == "notify/fixture_stalled" and entry["tag"] == tag
                   and entry["result"] == "accepted_by_home_assistant" for entry in app.notify_man.notification_history)


def test_notification_updates_single_fault_notification_for_prefault_lifecycle(
    mocked_hass_app_with_temp_component,
):
    """
    Verify the end-to-end notification lifecycle for one fault with multiple prefaults.

    A second prefault for the same fault should update the existing notification
    description, and the notification should only switch to cleared after the last
    contributing prefault is cleared.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    app_instance.args = copy.deepcopy(app_instance.args)
    _install_stateful_hass(app_instance, mock_behaviors_default)

    app_instance.initialize()
    notification_clock = Mock(return_value=1000.0)
    app_instance.notify_man._clock = notification_clock
    app_instance.call_service.reset_mock()
    app_instance.set_state.reset_mock()

    app_instance.fm.set_symptom("RiskyTemperatureOffice", {"location": "Office"})

    notify_calls = _notify_calls(app_instance)
    assert len(app_instance.notify_man.active_notification) == 1
    fault_tag = next(iter(app_instance.notify_man.active_notification))
    assert notify_calls[-1].kwargs["title"] == "Unsafe temperature — Office"
    assert (
        notify_calls[-1].kwargs["message"]
        == "Check the details in Safety Home."
    )
    assert notify_calls[-1].kwargs["data"]["tag"] == fault_tag

    app_instance.fm.set_symptom("RiskyTemperatureKitchen", {"location": "Kitchen"})
    notification_clock.return_value += 1
    app_instance.notify_man.tick()

    notify_calls = _notify_calls(app_instance)
    assert list(app_instance.notify_man.active_notification) == [fault_tag]
    assert (
        notify_calls[-1].kwargs["title"]
        == "Unsafe temperature — Office, Kitchen"
    )
    assert notify_calls[-1].kwargs["data"]["tag"] == fault_tag
    assert (
        app_instance.mqtt_entities.get_attributes("sensor.fault_RiskyTemperature")[
            "location"
        ]
        == "Office, Kitchen"
    )

    app_instance.fm.clear_symptom("RiskyTemperatureOffice", {"location": "Office"})
    notification_clock.return_value += 1
    app_instance.notify_man.tick()

    notify_calls = _notify_calls(app_instance)
    assert app_instance.fm.check_fault("RiskyTemperature") is FaultEvaluationStatus.FAIL
    assert list(app_instance.notify_man.active_notification) == [fault_tag]
    assert (
        notify_calls[-1].kwargs["title"]
        == "Unsafe temperature — Kitchen"
    )
    assert (
        app_instance.mqtt_entities.get_attributes("sensor.fault_RiskyTemperature")[
            "location"
        ]
        == "Kitchen"
    )

    app_instance.fm.clear_symptom("RiskyTemperatureKitchen", {"location": "Kitchen"})

    notify_calls = _notify_calls(app_instance)
    assert app_instance.fm.check_fault("RiskyTemperature") is FaultEvaluationStatus.PASS
    assert app_instance.notify_man.active_notification == {}
    assert notify_calls[-1].kwargs["message"].startswith(
        "Unsafe temperature."
    )
    assert notify_calls[-1].kwargs["data"]["tag"] == fault_tag
    assert (
        mqtt_payloads(
            app_instance,
            mqtt_topic_for("sensor.fault_RiskyTemperature"),
        )[-1]
        == "PASS"
    )
    assert (
        app_instance.mqtt_entities.get_attributes("sensor.fault_RiskyTemperature")[
            "location"
        ]
        == ""
    )


def test_recovery_manager_sets_recovery_state_and_actuator_entities(
    mocked_hass_app_with_temp_component,
):
    """
    Verify that recovery evaluates the temperature context and writes recovery entities.

    With outside temperature lower than the room temperature, the recovery action should
    request the configured window actuator to close and mark the recovery as pending.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    app_instance.args = copy.deepcopy(app_instance.args)
    office_cfg = app_instance.args["user_config"]["safety_components"][
        "TemperatureComponent"
    ]["rooms"]["Office"]
    office_cfg["actuator"] = "cover.office_window"

    mock_behaviors = update_mocked_get_state(
        mock_behaviors_default,
        [
            MockBehavior("sensor.office_temperature", iter(["5"])),
            MockBehavior("sensor.example_outdoor_temperature", iter(["1"])),
            MockBehavior(
                "binary_sensor.example_office_window",
                iter(["on", "on", "on"]),
            ),
        ],
    )
    state_store = _install_stateful_hass(app_instance, mock_behaviors)
    state_store.set_state("cover.office_window", state="open")
    state_store.set_state("binary_sensor.example_office_window", state="on")

    app_instance.initialize()
    for diagnostic_id, binding in app_instance.degradation._bindings.items():
        if any(
            target.symptom_id == "RiskyTemperatureOffice"
            for target in binding.targets
        ):
            app_instance.degradation.observe(
                symptom_id=diagnostic_id, state=FaultState.CLEARED
            )
    app_instance.degradation.observe(
        symptom_id="RiskyTemperatureOffice", state=FaultState.SET
    )
    app_instance.reco_man._is_dry_test_failed = MagicMock(return_value=False)
    app_instance.reco_man._isRecoveryConflict = MagicMock(return_value=False)
    app_instance.call_service.reset_mock()
    app_instance.listen_state.reset_mock()

    app_instance.fm.set_symptom("RiskyTemperatureOffice", {"location": "Office"})

    recovery_action = app_instance.reco_man.recovery_actions["RiskyTemperatureOffice"]
    assert recovery_action.current_status == RecoveryActionState.EXECUTING
    assert (
        mqtt_payloads(
            app_instance,
            mqtt_topic_for("sensor.recovery_ManipulateWindowOffice"),
        )[-1]
        == "EXECUTING"
    )
    cover_calls = [call for call in app_instance.call_service.call_args_list if call.args[0] == "cover/close_cover"]
    assert len(cover_calls) == 1 and cover_calls[0].kwargs["entity_id"] == "cover.office_window"
    assert not mqtt_payloads(
        app_instance,
        "safety_component/command/cover_office_window/set",
    )
    listeners = [call for call in app_instance.listen_state.call_args_list if call.args[1] == "binary_sensor.example_office_window"]
    assert any(getattr(call.args[0], "__wrapped__", None) == app_instance.reco_man._recovery_performed
               and call.kwargs.get("expected_state") == "off" for call in listeners)


@pytest.mark.parametrize(
    "actuator_state, contact_state, outside_state, completion",
    [
        ("unavailable", "on", "1", "entity_state"),
        ("unknown", "on", "1", "entity_state"),
        ("open", "unavailable", "1", "operator_report"),
        ("open", "on", "unavailable", "operator_report"),
    ],
)
def test_temperature_recovery_falls_back_to_manual_work_without_actuator_commands(
    mocked_hass_app_basic,
    actuator_state,
    contact_state,
    outside_state,
    completion,
):
    """Keep useful manual work visible when command or window evidence is missing."""

    app_instance, _, __ = mocked_hass_app_basic
    behaviors = default_mock_behaviors()
    app_instance.args = copy.deepcopy(app_instance.args)
    app_instance.args["user_config"]["safety_components"]["TemperatureComponent"]["rooms"]["Office"][
        "actuator"
    ] = "cover.office_window"
    state_store = _install_stateful_hass(app_instance, behaviors)
    for entity_id, state in (
        ("sensor.office_temperature", "5"),
        ("sensor.example_outdoor_temperature", outside_state),
        ("binary_sensor.example_office_window", contact_state),
        ("cover.office_window", actuator_state),
    ):
        state_store.set_state(entity_id, state=state)
    app_instance.initialize()
    app_instance.reco_man._is_dry_test_failed = MagicMock(return_value=False)
    app_instance.reco_man._isRecoveryConflict = MagicMock(return_value=False)
    app_instance.call_service.reset_mock()

    app_instance.fm.set_symptom("RiskyTemperatureOffice", {"location": "Office"})

    proposal = app_instance.reco_man._proposals["RiskyTemperatureOffice"]
    assert proposal["execution_policy"] == "manual"
    assert proposal["status"] == "TO_PERFORM"
    assert proposal["completion_condition"] == completion
    assert not proposal["actuator_targets"]
    assert proposal["instruction"]
    if completion == "operator_report":
        assert proposal["manual_report_allowed"]
        assert not proposal["expected_postconditions"]
    else:
        assert proposal["expected_postconditions"] == {"binary_sensor.example_office_window": "off"}
    assert app_instance.symptoms["RiskyTemperatureOffice"].state == FaultState.SET
    assert not [
        call for call in app_instance.call_service.call_args_list
        if call.kwargs.get("entity_id") == "cover.office_window"
        or (call.args and call.args[0].startswith(("cover/", "switch/", "climate/", "fan/")))
    ]
