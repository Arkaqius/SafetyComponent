# tests/test_temperature_component.py
# mypy: ignore-errors

from typing import Iterator, List
import pytest
from shared.types_common import FaultState, SMState
from unittest.mock import Mock
from .fixtures.hass_fixture import (
    mock_get_state,
    MockBehavior,
    update_mocked_get_state,
)  # Import utilities from conftest.py

from shared.notification_manager import NotificationManager

@pytest.mark.parametrize(
    "test_size,temperature, expected_symptom_state, expected_fault_state, prefault_title, prefault_message",
    [
        (
            5,
            ["35", "36", "37", "8", "9"],
            FaultState.CLEARED,
            FaultState.CLEARED,
            None,
            None,
        ),
        (
            5,
            ["5", "6", "7", "8", "9"],
            FaultState.SET,
            FaultState.SET,
            "Hazard!",
            'Fault: RiskyTemperature\nlocation: Office\n',
        ),
        (
            6,
            ["5", "6", "7", "8", "9", "34", "34", "34", "34", "34", "34", "34"],
            FaultState.CLEARED,
            FaultState.CLEARED,
            "Hazard!",
            'Fault: RiskyTemperature\nlocation: Office\n has been cleared.',
        ),
    ],
)
def test_temp_comp_notification(
    mocked_hass_app_with_temp_component,
    test_size,
    temperature,
    expected_symptom_state,
    expected_fault_state,
    prefault_title,
    prefault_message,
):
    """
    Test Case: Verify symptom and fault states based on temperature input.

    Scenario:
        - Input: Temperature sequences with varying levels.
        - Expected Result: Symptom and fault states should match expected values based on temperature.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )

    test_mock_behaviours: List[MockBehavior[str, Iterator[str]]] = [
        MockBehavior("sensor.office_temperature", iter(temperature))
    ]
    mock_behaviors_default: List[MockBehavior] = update_mocked_get_state(
        mock_behaviors_default, test_mock_behaviours
    )

    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id, mock_behaviors_default
    )
    app_instance.initialize()

    for _ in range(test_size):
        app_instance.sm_modules["TemperatureComponent"].sm_tc_1(
            app_instance.sm_modules["TemperatureComponent"].safety_mechanisms[
                "RiskyTemperatureOffice"
            ]
        )

    assert (
        app_instance.fm.check_symptom("RiskyTemperatureOffice")
        == expected_symptom_state
    )
    assert app_instance.fm.check_fault("RiskyTemperature") == expected_fault_state

    # Check notification
    if prefault_title:
        notify_call = [
            call
            for call in app_instance.call_service.call_args_list
            if "notify" in call.args[0]
        ]
        # Check last one
        assert notify_call[-1].kwargs["title"] == prefault_title
        assert notify_call[-1].kwargs["message"] == prefault_message
        
def test_notify_fault_set(mocked_hass_app_with_temp_component):
    """
    Test Case: Notify when fault is set.

    Scenario:
        - Fault is in FaultState.SET.
        - Expected Result: The notification is processed and the correct services are called.
    """
    notification_config: dict[str, str] = {
        "light_entity": "light.warning_light",
        "alarm_entity": "alarm_control_panel.safety_alarm",
        "dashboard_1_entity": "sensor.dash_emergency",
    }
    app_instance, _, __, ___, mock_behaviors_default = (
    mocked_hass_app_with_temp_component
    )
    
    notification_manager = NotificationManager(app_instance, notification_config)
    app_instance.call_service = Mock()
    app_instance.set_state = Mock()
    app_instance.log = Mock()

    fault_name = "TestFault"
    fault_level = 1
    fault_status = FaultState.SET
    fault_tag = "BAAD"
    additional_info: dict[str, str] = {"Location": "Office"}

    # Call notify to simulate a fault being set
    notification_manager.notify(fault_name, fault_level, fault_status, additional_info, fault_tag)

    # Validate that the correct services were called
    app_instance.call_service.assert_any_call(
        "alarm_control_panel/alarm_trigger",
        entity_id=notification_config["alarm_entity"],
    )
    app_instance.call_service.assert_any_call(
        "light/turn_on",
        entity_id=notification_config["light_entity"],
        color_name="red",
    )
    
def test_notify_fault_cleared(mocked_hass_app_with_temp_component):
    """
    Test Case: Notify when fault is cleared.

    Scenario:
        - Fault is in FaultState.CLEARED.
        - Expected Result: A cleared notification message is sent.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    notification_config = {
        "dashboard_1_entity": "sensor.dash_emergency",
    }

    notification_manager = NotificationManager(app_instance, notification_config)
    app_instance.call_service = Mock()
    app_instance.set_state = Mock()
    app_instance.log = Mock()

    fault_name = "TestFault"
    fault_level = 1
    fault_status = FaultState.CLEARED
    additional_info = {"Location": "Office"}

    # Call notify to simulate a fault being cleared
    notification_manager.notify(fault_name, fault_level, fault_status, additional_info, "00")

    
def test_notify_no_level_defined(mocked_hass_app_with_temp_component):
    """
    Test Case: No notification level defined.

    Scenario:
        - Notification level has no defined handler.
        - Expected Result: A warning is logged.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    notification_config = {}

    notification_manager = NotificationManager(app_instance, notification_config)
    app_instance.log = Mock()

    fault_name = "TestFault"
    fault_level = 4
    fault_status = FaultState.SET

    # Call notify to simulate a fault with undefined notification level
    notification_manager.notify(fault_name, fault_level, fault_status, None, "00")

    
def test_notify_company_app(mocked_hass_app_with_temp_component):
    """
    Test Case: Notify company app based on different levels.

    Scenario:
        - Send notifications for different levels and ensure correct behavior.
        - Level 4 should not send any notification.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    notification_config = {
        "dashboard_1_entity": "sensor.dash_emergency",
    }

    notification_manager = NotificationManager(app_instance, notification_config)
    app_instance.call_service = Mock()
    app_instance.log = Mock()

    # Test for different levels
    fault_name = "TestFault"
    message = "Test message"
    fault_state = FaultState.SET

    # Level 4 should not send notifications
    notification_manager._notify_company_app(4, message, fault_name, fault_state)
    app_instance.call_service.assert_not_called()

    # Level 1 should send notifications
    notification_manager._notify_company_app(1, message, fault_name, fault_state)
    app_instance.call_service.assert_called()
    
    
def test_notify_invalid_fault_status(mocked_hass_app_with_temp_component):
    """
    Test Case: Invalid fault status.

    Scenario:
        - Fault status is neither SET nor CLEARED.
        - Expected Result: A warning is logged indicating an invalid fault status.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    notification_config = {}

    notification_manager = NotificationManager(app_instance, notification_config)
    app_instance.log = Mock()

    fault_name = "TestFault"
    fault_level = 1
    fault_status = "INVALID_STATUS"  # Use an invalid status that is not in FaultState

    # Call notify with an invalid fault status
    notification_manager.notify(fault_name, fault_level, fault_status, None, "00")

    # Verify that a warning log was triggered for the invalid fault status
    app_instance.log.assert_called_with(f"Invalid fault status '{fault_status}'", level="WARNING")
    
def test_set_dashboard_notification(mocked_hass_app_with_temp_component):
    """
    Test Case: Set dashboard notification.

    Scenario:
        - Set a notification on the dashboard based on severity level.
        - Expected Result: The dashboard entity state is updated, or a warning is logged if the entity is not configured.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    notification_config = {
        "dashboard_1_entity": "sensor.dash_emergency"
    }

    notification_manager = NotificationManager(app_instance, notification_config)
    app_instance.set_state = Mock()
    app_instance.log = Mock()

    message = "Test Dashboard Message"
    level = 1

    # Call _set_dashboard_notification with a valid level
    notification_manager._set_dashboard_notification(message, level)

    # Verify that the dashboard entity state was set
    app_instance.set_state.assert_called_with("sensor.dash_emergency", state=message)
    app_instance.log.assert_called_with(
        f"Dashboard entity sensor.dash_emergency was changed to {message}", level="DEBUG"
    )

    # Call _set_dashboard_notification with an invalid level (not configured)
    level = 2
    notification_manager._set_dashboard_notification(message, level)

    # Verify that a warning log was triggered for missing dashboard entity configuration
    app_instance.log.assert_called_with(
        f"No dashboard entity configured for level '{level}'", level="WARNING"
    )
    
def test_notify_company_app_no_notification_data(mocked_hass_app_with_temp_component):
    """
    Test Case: No notification data available.

    Scenario:
        - Notification data is not available for the given level.
        - Expected Result: A warning is logged indicating that no notification configuration exists for the given level.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    notification_config = {}

    notification_manager = NotificationManager(app_instance, notification_config)
    app_instance.log = Mock()

    level = 999  # Level without a configuration
    message = "Test message"
    fault_tag = "TestFaultTag"
    fault_state = FaultState.SET

    # Call _notify_company_app with no available notification data
    notification_manager._notify_company_app(level, message, fault_tag, fault_state)

    # Verify that a warning log was triggered for missing notification configuration
    app_instance.log.assert_called_with(
        f"No notification configuration for level {level}", level="WARNING"
    )

def test_clear_symptom_msg(mocked_hass_app_with_temp_component):
    """
    Test Case: Clear symptom message.

    Scenario:
        - Update the notification message to indicate recovery and resend the notification.
        - Expected Result: The notification message is updated and sent.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    notification_config = {}

    notification_manager = NotificationManager(app_instance, notification_config)
    app_instance.log = Mock()
    app_instance.call_service = Mock()

    notification_data = {
        "title": "Test Notification",
        "message": "Original message",
        "data": {}
    }
    notification_msg = "Recovery message"

    # Call _clear_symptom_msg to update and resend the notification
    notification_manager._clear_symptom_msg(notification_data, notification_msg)

    # Verify that the notification message was updated
    assert notification_data["message"] == f" {notification_msg}"

    # Verify that the notification was resent
    app_instance.call_service.assert_called_with(
        "notify/notify",
        title=notification_data["title"],
        message=notification_data["message"],
        data=notification_data["data"]
    )
