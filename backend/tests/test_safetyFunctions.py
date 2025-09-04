from typing import Iterator, List
import pytest
from shared.types_common import FaultState, SMState
from shared.temperature_component import TemperatureComponent
import SafetyFunctions
from unittest.mock import Mock, patch
from .fixtures.hass_fixture import (
    mock_get_state,
    MockBehavior,
    update_mocked_get_state,
)  # Import utilities from conftest.py
from unittest.mock import ANY

def test_safety_functions_initialization(mocked_hass_app_with_temp_component) -> None:

    app_instance, mocked_hass, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    app_instance.initialize()

    # Assert the 'symptoms' dictionary content
    symptom = app_instance.symptoms["RiskyTemperatureOffice"]
    assert symptom.name == "RiskyTemperatureOffice"
    assert symptom.sm_name == "sm_tc_1"
    assert symptom.parameters["CAL_LOW_TEMP_THRESHOLD"] == 18.0

    # Assert the 'faults' dictionary content
    fault = app_instance.fault_dict["RiskyTemperature"]
    assert fault["name"] == "Unsafe temperature"
    assert fault["level"] == 2
    assert fault["related_sms"][0] == "sm_tc_1"

    # Assert the 'notification_cfg' dictionary content
    notification = app_instance.notification_cfg
    assert notification["light_entity"] == "light.warning_light"

    # Ensure that the correct common entity was used
    assert app_instance.common_entities_cfg["outside_temp"] == "sensor.dom_temperature"

    # Verify that safety mechanisms are initialized and enabled
    mocked_hass.set_state.assert_any_call("sensor.safety_app_health", state="init")
    mocked_hass.set_state.assert_any_call("sensor.safety_app_health", state="running",attributes = ANY)

    # Verify TemperatureComponent configurations are set up correctly
    assert "TemperatureComponent" in app_instance.sm_modules

    # Verify that TemperatureComponent received the correct configuration
    temp_comp_cfg = app_instance.safety_components_cfg["TemperatureComponent"][0]
    assert "Office" in temp_comp_cfg
    assert temp_comp_cfg["Office"]["temperature_sensor"] == "sensor.office_temperature"
    assert (
        temp_comp_cfg["Office"]["window_sensor"]
        == "sensor.office_window_contact_contact"
    )

    assert "Kitchen" in temp_comp_cfg
    assert (
        temp_comp_cfg["Kitchen"]["temperature_sensor"] == "sensor.kitchen_temperature"
    )
    assert (
        temp_comp_cfg["Kitchen"]["window_sensor"]
        == "sensor.kitchen_window_contact_contact"
    )

    # Verify the NotificationManager is initialized with the correct entity
    assert (
        app_instance.notify_man.notification_config["light_entity"]
        == "light.warning_light"
    )

    # Verify that common entities are properly initialized in CommonEntities
    assert "outside_temp" in app_instance.common_entities_cfg
    assert app_instance.common_entities_cfg["outside_temp"] == "sensor.dom_temperature"


def test_fault_and_symptom_registration(mocked_hass_app_with_temp_component):
    """Ensure all configured faults and symptoms are correctly registered in FaultManager."""
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()

    # Assert that all symptoms are registered
    for symptom_name in app_instance.symptoms:
        symptom = app_instance.symptoms[symptom_name]
        assert app_instance.fm.check_symptom(symptom_name) == FaultState.NOT_TESTED

    # Assert that all faults are registered
    for fault_name in app_instance.faults:
        fault = app_instance.faults[fault_name]
        assert fault.name is not None
        assert fault.level >= 0


def test_trigger_symptom_sets_fault(mocked_hass_app_with_temp_component):
    """Test triggering a symptom results in fault state being set."""
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()

    # Manually trigger a symptom
    app_instance.fm.set_symptom("RiskyTemperatureOffice", None)

    # Check if the corresponding fault is set to 'SET'
    assert app_instance.fm.check_fault("RiskyTemperature") == FaultState.SET


def test_recovery_process_execution(mocked_hass_app_with_temp_component):
    """Test that recovery actions are executed when faults are triggered."""
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()

    # Mock the recovery action to track if it's called
    app_instance.reco_man.recovery = Mock()
    # Bind new Mock with recovery_interface
    app_instance.fm.recovery_interface = app_instance.reco_man.recovery

    # Manually trigger a symptom
    app_instance.fm.set_symptom("RiskyTemperatureOffice", None)

    # Extract the call arguments
    recovery_call_args = app_instance.reco_man.recovery.call_args

    # Verify only the first argument of the call, which should be the symptom object
    assert recovery_call_args[0][0] == app_instance.symptoms["RiskyTemperatureOffice"]


def test_app_initialization_health_state(mocked_hass_app_with_temp_component):
    """Test health state transitions during app initialization."""
    app_instance, mocked_hass, __, ___, _ = mocked_hass_app_with_temp_component

    app_instance.initialize()

    # Verify that health state transitions from 'init' to 'good'
    mocked_hass.set_state.assert_any_call("sensor.safety_app_health", state="init")
    mocked_hass.set_state.assert_any_call("sensor.safety_app_health", state="running",attributes = ANY)

def test_common_entities_lookup(mocked_hass_app_with_temp_component):
    """Test that common entities are properly initialized and accessible."""
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()

    # Access the common entity and ensure it matches the configured value
    assert app_instance.common_entities_cfg["outside_temp"] == "sensor.dom_temperature"


def test_initialize_no_faults_or_safety_components(mocked_hass_app_with_temp_component):
    """
    Test Case: No faults or safety components defined in configuration.

    Scenario:
        - The configuration does not include any faults or safety components.
        - Expected Result: The app stops, logging an appropriate warning, setting the app state to 'invalid_cfg', and calling terminate.
    """
    app_instance, mocked_hass, _, _, _ = mocked_hass_app_with_temp_component

    # Modify the configuration to remove 'faults' and 'safety_components'
    app_instance.args['app_config']['faults'] = {}  # No faults defined
    app_instance.args['user_config']['safety_components'] = {}  # No safety components defined

    mocked_hass.stop_app = Mock()
    # Call initialize to test behavior
    app_instance.initialize()

    # Check if the warning log was called
    app_instance.log.assert_called_with("No faults or safety components defined. Stopping the app.", level="WARNING")

    # Check if the app state was set to 'invalid_cfg'
    mocked_hass.set_state.assert_called_with("sensor.safety_app_health", state="invalid_cfg")