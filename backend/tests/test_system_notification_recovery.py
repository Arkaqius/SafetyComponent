"""System-level tests for notification and recovery manager integration."""

import copy
from typing import Any
from unittest.mock import MagicMock

from components.core.types_common import FaultState, RecoveryActionState

from .fixtures.hass_fixture import (
    MockBehavior,
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
    return state_store


def _notify_calls(app_instance: Any) -> list[Any]:
    return [
        call
        for call in app_instance.call_service.call_args_list
        if call.args and call.args[0] == "notify/notify"
    ]


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
    state_store = _install_stateful_hass(app_instance, mock_behaviors_default)

    app_instance.initialize()
    app_instance.call_service.reset_mock()
    app_instance.set_state.reset_mock()

    app_instance.fm.set_symptom("RiskyTemperatureOffice", {"location": "Office"})

    notify_calls = _notify_calls(app_instance)
    assert len(app_instance.notify_man.active_notification) == 1
    fault_tag = next(iter(app_instance.notify_man.active_notification))
    assert notify_calls[-1].kwargs["title"] == "Hazard!"
    assert (
        notify_calls[-1].kwargs["message"]
        == "Fault: RiskyTemperature\nlocation: Office\n"
    )
    assert notify_calls[-1].kwargs["data"]["tag"] == fault_tag

    app_instance.fm.set_symptom("RiskyTemperatureKitchen", {"location": "Kitchen"})

    notify_calls = _notify_calls(app_instance)
    assert list(app_instance.notify_man.active_notification) == [fault_tag]
    assert (
        notify_calls[-1].kwargs["message"]
        == "Fault: RiskyTemperature\nlocation: Office, Kitchen\n"
    )
    assert notify_calls[-1].kwargs["data"]["tag"] == fault_tag
    assert (
        app_instance.mqtt_entities.get_attributes("sensor.fault_RiskyTemperature")[
            "location"
        ]
        == "Office, Kitchen"
    )

    app_instance.fm.clear_symptom("RiskyTemperatureOffice", {"location": "Office"})

    notify_calls = _notify_calls(app_instance)
    assert app_instance.fm.check_fault("RiskyTemperature") == FaultState.SET
    assert list(app_instance.notify_man.active_notification) == [fault_tag]
    assert (
        notify_calls[-1].kwargs["message"]
        == "Fault: RiskyTemperature\nlocation: Kitchen\n"
    )
    assert (
        app_instance.mqtt_entities.get_attributes("sensor.fault_RiskyTemperature")[
            "location"
        ]
        == "Kitchen"
    )

    app_instance.fm.clear_symptom("RiskyTemperatureKitchen", {"location": "Kitchen"})

    notify_calls = _notify_calls(app_instance)
    assert app_instance.fm.check_fault("RiskyTemperature") == FaultState.CLEARED
    assert app_instance.notify_man.active_notification == {}
    assert notify_calls[-1].kwargs["message"].endswith(" has been cleared.")
    assert notify_calls[-1].kwargs["data"]["tag"] == fault_tag
    assert (
        mqtt_payloads(
            app_instance,
            mqtt_topic_for("sensor.fault_RiskyTemperature"),
        )[-1]
        == "Cleared"
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
            MockBehavior("sensor.dom_temperature", iter(["1"])),
            MockBehavior(
                "sensor.office_window_contact_contact",
                iter(["on", "on", "on"]),
            ),
        ],
    )
    _install_stateful_hass(app_instance, mock_behaviors)

    app_instance.initialize()
    app_instance.reco_man._is_dry_test_failed = MagicMock(return_value=False)
    app_instance.reco_man._isRecoveryConflict = MagicMock(return_value=False)
    app_instance.call_service.reset_mock()
    app_instance.listen_state.reset_mock()

    app_instance.fm.set_symptom("RiskyTemperatureOffice", {"location": "Office"})

    symptom = app_instance.symptoms["RiskyTemperatureOffice"]
    recovery_action = app_instance.reco_man.recovery_actions["RiskyTemperatureOffice"]
    assert recovery_action.current_status == RecoveryActionState.TO_PERFORM
    assert (
        mqtt_payloads(
            app_instance,
            mqtt_topic_for("sensor.recovery_ManipulateWindowOffice"),
        )[-1]
        == "TO_PERFORM"
    )
    app_instance.call_service.assert_any_call(
        "cover/close_cover", entity_id="cover.office_window"
    )
    assert not mqtt_payloads(
        app_instance,
        "safety_component/command/cover_office_window/set",
    )
    app_instance.listen_state.assert_any_call(
        app_instance.reco_man._recovery_performed,
        "sensor.office_window_contact_contact",
        new="off",
        symptom=symptom,
        confirmation_entity="sensor.office_window_contact_contact",
        expected_state="off",
    )
