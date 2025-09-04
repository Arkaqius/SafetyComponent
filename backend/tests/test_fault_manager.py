from unittest.mock import Mock, patch
import pytest
from shared.types_common import FaultState, SMState, Symptom, Fault
from shared.fault_manager import FaultManager

@pytest.fixture
def mocked_hass_app():
    return Mock()

@pytest.fixture
def symptom():
    # Creating a mock module for SafetyComponent
    mock_module = Mock()
    return Symptom(name="RiskyTemperatureOffice", sm_name="sm_tc_1", module=mock_module, parameters={"CAL_LOW_TEMP_THRESHOLD": 18.0})

@pytest.fixture
def fault():
    return Fault(name="RiskyTemperature", related_symptoms=["sm_tc_1"], level=2)

@pytest.fixture
def fault_manager(mocked_hass_app, symptom, fault):
    sm_modules = {"TemperatureComponent": Mock()}
    symptom_dict = {"RiskyTemperatureOffice": symptom}
    fault_dict = {"RiskyTemperature": fault}
    return FaultManager(mocked_hass_app, sm_modules, symptom_dict, fault_dict)

def test_fault_manager_initialization(fault_manager, fault, symptom):
    """
    Test if the FaultManager initializes correctly with fault and symptom dictionaries.
    """
    assert fault_manager.faults["RiskyTemperature"] == fault
    assert fault_manager.symptoms["RiskyTemperatureOffice"] == symptom

def test_register_callbacks(fault_manager):
    """
    Test if register_callbacks sets the notify_interface and recovery_interface properly.
    """
    recovery_mock = Mock()
    notify_mock = Mock()
    fault_manager.register_callbacks(recovery_mock, notify_mock)

    assert fault_manager.recovery_interface == recovery_mock
    assert fault_manager.notify_interface == notify_mock

def test_set_symptom(fault_manager, mocked_hass_app):
    """
    Test if set_symptom correctly marks a symptom as SET and triggers the fault.
    """
    fault_manager._set_fault = Mock()

    fault_manager.set_symptom("RiskyTemperatureOffice")
    assert fault_manager.symptoms["RiskyTemperatureOffice"].state == FaultState.SET
    fault_manager._set_fault.assert_called_once_with("RiskyTemperatureOffice", None)

def test_clear_symptom(fault_manager, mocked_hass_app):
    """
    Test if clear_symptom correctly marks a symptom as CLEARED and clears the fault.
    """
    fault_manager._clear_fault = Mock()

    fault_manager.clear_symptom("RiskyTemperatureOffice", {})
    assert fault_manager.symptoms["RiskyTemperatureOffice"].state == FaultState.CLEARED
    fault_manager._clear_fault.assert_called_once_with("RiskyTemperatureOffice", {})

def test_disable_symptom(fault_manager, mocked_hass_app):
    """
    Test if disable_symptom correctly marks a symptom as NOT_TESTED and clears the fault.
    """
    fault_manager._clear_fault = Mock()

    fault_manager.disable_symptom("RiskyTemperatureOffice", {})
    assert fault_manager.symptoms["RiskyTemperatureOffice"].state == FaultState.NOT_TESTED
    fault_manager._clear_fault.assert_called_once_with("RiskyTemperatureOffice", {})

def test_set_fault(fault_manager, mocked_hass_app, fault):
    """
    Test if _set_fault correctly sets the fault and calls notification and recovery.
    """
    additional_info = {"Location": "Office"}
    fault_manager._generate_fault_tag = Mock(return_value="mocked_fault_tag")
    fault_manager.notify_interface = Mock()
    fault_manager.recovery_interface = Mock()

    # Set up the mock for get_state to return appropriate data
    mocked_hass_app.get_state = Mock(return_value={"attributes": {"Location": "Kitchen"}})
    
    fault_manager._set_fault("RiskyTemperatureOffice", additional_info)

    assert fault.state == FaultState.SET
    mocked_hass_app.set_state.assert_any_call(
        "sensor.fault_RiskyTemperature",
        state="Set",
        attributes={"Location": "Kitchen, Office"}
    )
    fault_manager.notify_interface.assert_any_call(
        "RiskyTemperature",
        fault.level,
        FaultState.SET,
        additional_info,
        "mocked_fault_tag"
    )
    fault_manager.recovery_interface.assert_called_once_with(fault_manager.symptoms["RiskyTemperatureOffice"], "mocked_fault_tag")

def test_clear_fault(fault_manager, mocked_hass_app, fault):
    """
    Test if _clear_fault correctly clears the fault and calls notification and recovery.
    """
    additional_info = {"Location": "Office"}
    fault_manager._generate_fault_tag = Mock(return_value="mocked_fault_tag")
    fault_manager.notify_interface = Mock()
    fault_manager.recovery_interface = Mock()

    # Set up the mock for get_state to return appropriate data
    mocked_hass_app.get_state = Mock(return_value={"attributes": {"Location": "Office"}})

    # Set fault first to test clearing it
    fault_manager._set_fault("RiskyTemperatureOffice", additional_info)

    # Now clear the fault
    fault_manager._clear_fault("RiskyTemperatureOffice", additional_info)

    assert fault.state == FaultState.CLEARED
    mocked_hass_app.set_state.assert_any_call(
        "sensor.fault_RiskyTemperature",
        state="Cleared",
        attributes={"Location": ""}
    )
    fault_manager.notify_interface.assert_any_call(
        "RiskyTemperature",
        fault.level,
        FaultState.CLEARED,
        additional_info,
        "mocked_fault_tag"
    )
    fault_manager.recovery_interface.assert_any_call(fault_manager.symptoms["RiskyTemperatureOffice"], "mocked_fault_tag")

def test_found_mapped_fault(fault_manager, fault):
    """
    Test if found_mapped_fault correctly returns the fault mapped from the symptom.
    """
    found_fault = fault_manager.found_mapped_fault("RiskyTemperatureOffice", "sm_tc_1")
    assert found_fault == fault

def test_check_fault(fault_manager):
    """
    Test if check_fault returns the correct fault state.
    """
    assert fault_manager.check_fault("RiskyTemperature") == FaultState.NOT_TESTED

def test_check_symptom(fault_manager):
    """
    Test if check_symptom returns the correct symptom state.
    """
    assert fault_manager.check_symptom("RiskyTemperatureOffice") == FaultState.NOT_TESTED

def test_fault_manager_multiple_symptoms(fault_manager, mocked_hass_app, fault):
    """
    Test the FaultManager with multiple symptoms, ensuring proper state transitions,
    notification, and recovery actions for complex scenarios.
    """
    # Mock the recovery and notification interfaces
    fault_manager._generate_fault_tag = Mock(return_value="mocked_fault_tag")
    fault_manager.notify_interface = Mock()
    fault_manager.recovery_interface = Mock()

    # Define multiple symptoms for testing
    symptom_office = Symptom(
        name="RiskyTemperatureOffice",
        sm_name="sm_tc_1",
        module=Mock(),
        parameters={"CAL_LOW_TEMP_THRESHOLD": 18.0},
    )
    symptom_kitchen = Symptom(
        name="RiskyTemperatureKitchen",
        sm_name="sm_tc_1",
        module=Mock(),
        parameters={"CAL_LOW_TEMP_THRESHOLD": 18.0},
    )

    # Add symptoms to the fault manager
    fault_manager.symptoms["RiskyTemperatureOffice"] = symptom_office
    fault_manager.symptoms["RiskyTemperatureKitchen"] = symptom_kitchen

    # Add a fault that both symptoms relate to
    fault.related_symptoms = ["sm_tc_1"]
    fault_manager.faults["RiskyTemperature"] = fault

    # Set up the mock for get_state to simulate a previous location being set
    mocked_hass_app.get_state = Mock(
        return_value={"attributes": {"Location": "Living Room"}}
    )

    # Set the first symptom (Office)
    additional_info_office = {"Location": "Office"}
    fault_manager.set_symptom("RiskyTemperatureOffice", additional_info_office)

    # Verify the fault state is set and includes both locations (Living Room, Office)
    assert fault.state == FaultState.SET
    mocked_hass_app.set_state.assert_any_call(
        "sensor.fault_RiskyTemperature",
        state="Set",
        attributes={"Location": "Living Room, Office"},
    )
    fault_manager.notify_interface.assert_any_call(
        "RiskyTemperature",
        fault.level,
        FaultState.SET,
        additional_info_office,
        "mocked_fault_tag",
    )
    fault_manager.recovery_interface.assert_any_call(
        symptom_office, "mocked_fault_tag"
    )
    
    # Set the second symptom (Office)
    additional_info_kitchen = {"Location": "Kitchen"}
    fault_manager.set_symptom("RiskyTemperatureKitchen", additional_info_kitchen)
    
    # Verify the fault state is set and includes both locations (Living Room, Office)
    assert fault.state == FaultState.SET
    mocked_hass_app.set_state.assert_any_call(
        "sensor.fault_RiskyTemperature",
        state="Set",
        attributes={"Location": "Living Room, Kitchen"}, # In normal system shall be also included Office but we dont have HA during tests
    )
    fault_manager.notify_interface.assert_any_call(
        "RiskyTemperature",
        fault.level,
        FaultState.SET,
        additional_info_kitchen,
        "mocked_fault_tag",
    )
    fault_manager.recovery_interface.assert_any_call(
        symptom_kitchen, "mocked_fault_tag"
    )

    # Clear the first symptom (Office)
    fault_manager.clear_symptom("RiskyTemperatureOffice", additional_info_office)

    # Verify that fault remains set because the kitchen symptom is not cleared
    assert fault.state == FaultState.SET
    
    # Clear the second symptom (Kitchen)
    fault_manager.clear_symptom("RiskyTemperatureKitchen", additional_info_kitchen)

    # Verify the fault is now cleared as all related symptoms are cleared
    assert fault.state == FaultState.CLEARED
    mocked_hass_app.set_state.assert_any_call(
        "sensor.fault_RiskyTemperature",
        state="Cleared",
        attributes={"Location": ""},
    )
    fault_manager.notify_interface.assert_any_call(
        "RiskyTemperature",
        fault.level,
        FaultState.CLEARED,
        additional_info_kitchen,
        "mocked_fault_tag",
    )
    fault_manager.recovery_interface.assert_any_call(
        symptom_kitchen, "mocked_fault_tag"
    )


def test_fault_manager_state_transitions(fault_manager, mocked_hass_app, fault):
    """
    Test complex state transitions involving multiple symptoms and faults.
    """
    # Mock the recovery and notification interfaces
    fault_manager._generate_fault_tag = Mock(return_value="mocked_fault_tag")
    fault_manager.notify_interface = Mock()
    fault_manager.recovery_interface = Mock()

    # Define two symptoms that relate to different faults
    symptom1 = Symptom(
        name="RiskyTemperatureOffice",
        sm_name="sm_tc_1",
        module=Mock(),
        parameters={"CAL_LOW_TEMP_THRESHOLD": 18.0},
    )
    symptom2 = Symptom(
        name="OverheatingKitchen",
        sm_name="sm_tc_2",
        module=Mock(),
        parameters={"CAL_HIGH_TEMP_THRESHOLD": 30.0},
    )

    # Add symptoms to the fault manager
    fault_manager.symptoms["RiskyTemperatureOffice"] = symptom1
    fault_manager.symptoms["OverheatingKitchen"] = symptom2

    # Add faults that relate to the symptoms
    fault1 = Fault("RiskyTemperature", ["sm_tc_1"], level=2)
    fault2 = Fault("OverheatingFault", ["sm_tc_2"], level=3)
    fault_manager.faults["RiskyTemperature"] = fault1
    fault_manager.faults["OverheatingFault"] = fault2

    # Set up the mock for get_state to simulate a previous location being set
    mocked_hass_app.get_state = Mock(
        return_value={"attributes": {"Location": "Living Room"}}
    )

    # Set symptom1 (RiskyTemperatureOffice)
    additional_info1 = {"Location": "Office"}
    fault_manager.set_symptom("RiskyTemperatureOffice", additional_info1)

    # Verify fault1 is set
    assert fault1.state == FaultState.SET
    fault_manager.notify_interface.assert_any_call(
        "RiskyTemperature",
        fault1.level,
        FaultState.SET,
        additional_info1,
        "mocked_fault_tag",
    )

    # Set symptom2 (OverheatingKitchen)
    additional_info2 = {"Location": "Kitchen"}
    fault_manager.set_symptom("OverheatingKitchen", additional_info2)

    # Verify fault2 is set
    assert fault2.state == FaultState.SET
    fault_manager.notify_interface.assert_any_call(
        "OverheatingFault",
        fault2.level,
        FaultState.SET,
        additional_info2,
        "mocked_fault_tag",
    )

    # Clear symptom1 (RiskyTemperatureOffice)
    fault_manager.clear_symptom("RiskyTemperatureOffice", additional_info1)

    # Verify fault1 is cleared
    assert fault1.state == FaultState.CLEARED
    fault_manager.notify_interface.assert_any_call(
        "RiskyTemperature",
        fault1.level,
        FaultState.CLEARED,
        additional_info1,
        "mocked_fault_tag",
    )

    # Verify fault2 remains set
    assert fault2.state == FaultState.SET

    # Clear symptom2 (OverheatingKitchen)
    fault_manager.clear_symptom("OverheatingKitchen", additional_info2)

    # Verify fault2 is cleared
    assert fault2.state == FaultState.CLEARED
    fault_manager.notify_interface.assert_any_call(
        "OverheatingFault",
        fault2.level,
        FaultState.CLEARED,
        additional_info2,
        "mocked_fault_tag",
    )
    
def test_fault_manager_init_safety_mechanisms_failure(fault_manager):
    """
    Test the FaultManager's init_safety_mechanisms function for a failure scenario where a symptom
    fails to initialize its safety mechanism, setting its state to ERROR.
    """
    # Mock a symptom that will fail to initialize
    symptom = Symptom(
        name="FaultyTemperatureSensor",
        sm_name="sm_tc_faulty",
        module=Mock(),
        parameters={"CAL_LOW_TEMP_THRESHOLD": 18.0},
    )

    # Make the init_safety_mechanism method return False to simulate failure
    symptom.module.init_safety_mechanism = Mock(return_value=False)

    # Add the symptom to the fault manager
    fault_manager.symptoms["FaultyTemperatureSensor"] = symptom

    # Initialize safety mechanisms
    fault_manager.init_safety_mechanisms()

    # Verify that the symptom state is set to ERROR
    assert fault_manager.symptoms["FaultyTemperatureSensor"].sm_state == SMState.ERROR
    
def test_fault_manager_missing_interfaces(fault_manager, mocked_hass_app):
    """
    Test the behavior of the FaultManager when notification or recovery interfaces are missing.
    """
    # Define a symptom
    symptom = Symptom(
        name="RiskyTemperatureOffice",
        sm_name="sm_tc_1",
        module=Mock(),
        parameters={"CAL_LOW_TEMP_THRESHOLD": 18.0},
    )

    # Set up the mock for get_state to simulate a previous location being set
    mocked_hass_app.get_state = Mock(
        return_value={"attributes": {"Location": "Office"}}
    )
    
    # Add the symptom to the fault manager
    fault_manager.symptoms["RiskyTemperatureOffice"] = symptom

    # Add a fault that the symptom relates to
    fault = Fault("RiskyTemperature", ["sm_tc_1"], level=2)
    fault_manager.faults["RiskyTemperature"] = fault

    # Set symptom without recovery and notification interfaces
    fault_manager.set_symptom("RiskyTemperatureOffice", {"Location": "Office"})

    # Verify that fault is set
    assert fault.state == FaultState.SET
    mocked_hass_app.set_state.assert_any_call(
        "sensor.fault_RiskyTemperature",
        state="Set",
        attributes={"Location": "Office"},
    )

    # Verify that no notification or recovery calls are made
    assert fault_manager.notify_interface is None
    assert fault_manager.recovery_interface is None

    # Clear symptom without recovery and notification interfaces
    fault_manager.clear_symptom("RiskyTemperatureOffice", {"Location": "Office"})

    # Verify that fault is cleared
    assert fault.state == FaultState.CLEARED
    mocked_hass_app.set_state.assert_any_call(
        "sensor.fault_RiskyTemperature",
        state="Cleared",
        attributes={"Location": ""},
    )

    # Verify that no notification or recovery calls are made
    assert fault_manager.notify_interface is None
    assert fault_manager.recovery_interface is None
    
def test_fault_manager_cleared_state_determinate_info(fault_manager, mocked_hass_app):
    """
    Test the _determinate_info function for the CLEARED branch.
    """
    # Set up the mock for get_state to simulate current attributes
    mocked_hass_app.get_state = Mock(
        return_value={"attributes": {"Location": "Living Room, Office"}}
    )

    # Define additional information to clear
    additional_info = {"Location": "Office"}

    # Call the _determinate_info method with FaultState.CLEARED
    updated_info = fault_manager._determinate_info(
        "sensor.fault_RiskyTemperature", additional_info, FaultState.CLEARED
    )

    # Verify the updated information
    assert updated_info == {"Location": "Living Room"}

    # Test clearing the last remaining location
    additional_info = {"Location": "Living Room"}
    updated_info = fault_manager._determinate_info(
        "sensor.fault_RiskyTemperature", additional_info, FaultState.CLEARED
    )

    # Verify the updated information is empty
    assert updated_info == {'Location': 'Office'}
    
    
def test_fault_manager_multiple_faults_associated_with_symptom(fault_manager, mocked_hass_app):
    """
    Test the behavior when multiple faults are associated with a single symptom.
    """
    # Define a symptom
    symptom = Symptom(
        name="RiskyTemperatureOffice",
        sm_name="sm_tc_1",
        module=Mock(),
        parameters={"CAL_LOW_TEMP_THRESHOLD": 18.0},
    )
    fault_manager.symptoms["RiskyTemperatureOffice"] = symptom

    # Define multiple faults that are incorrectly associated with the same symptom
    fault1 = Fault("Fault1", ["sm_tc_1"], level=2)
    fault2 = Fault("Fault2", ["sm_tc_1"], level=3)
    fault_manager.faults["Fault1"] = fault1
    fault_manager.faults["Fault2"] = fault2

    # Call found_mapped_fault and verify it returns None due to multiple faults
    result = fault_manager.found_mapped_fault("RiskyTemperatureOffice", "sm_tc_1")
    assert result is None
    mocked_hass_app.log.assert_any_call(
        "Error: Multiple faults found associated with symptom_id 'RiskyTemperatureOffice', indicating a configuration error.",
        level="ERROR",
    )


def test_fault_manager_no_fault_associated_with_symptom(fault_manager, mocked_hass_app):
    """
    Test the behavior when no fault is associated with a symptom.
    """
    # Define a symptom
    symptom = Symptom(
        name="RiskyTemperatureOffice",
        sm_name="sm_tc_1",
        module=Mock(),
        parameters={"CAL_LOW_TEMP_THRESHOLD": 18.0},
    )
    fault_manager.symptoms["RiskyTemperatureOffice"] = symptom

    # Call found_mapped_fault and verify it returns None due to no associated faults
    result = fault_manager.found_mapped_fault("RiskyTemperatureKitchen", "sm_tc_999")
    assert result is None
    mocked_hass_app.log.assert_any_call(
        "Error: No faults associated with symptom_id 'RiskyTemperatureKitchen'. This may indicate a configuration error.",
        level="ERROR",
    )
    
def test_enable_sm_invalid_state(fault_manager, mocked_hass_app):
    """
    Test the behavior when an invalid safety mechanism state is provided.
    """
    # Define a symptom
    symptom = Symptom(
        name="RiskyTemperatureOffice",
        sm_name="sm_tc_1",
        module=Mock(),
        parameters={"CAL_LOW_TEMP_THRESHOLD": 18.0},
    )
    fault_manager.symptoms["RiskyTemperatureOffice"] = symptom

    # Attempt to enable the safety mechanism with an invalid state
    invalid_state = "INVALID_STATE"  # This is not an instance of SMState
    fault_manager.enable_sm("RiskyTemperatureOffice", invalid_state)

    # Verify that the error was logged
    mocked_hass_app.log.assert_any_call(
        f"Error: Unknown SMState '{invalid_state}' for safety mechanism 'RiskyTemperatureOffice'.",
        level="ERROR",
    )
    
def test_enable_sm_failure_case(fault_manager, mocked_hass_app):
    """
    Test the behavior when enabling a safety mechanism fails.
    """
    # Define a symptom
    symptom = Symptom(
        name="RiskyTemperatureOffice",
        sm_name="sm_tc_1",
        module=Mock(),
        parameters={"CAL_LOW_TEMP_THRESHOLD": 18.0},
    )
    # Simulate enabling failure by returning False
    symptom.module.enable_safety_mechanism.return_value = False
    fault_manager.symptoms["RiskyTemperatureOffice"] = symptom

    # Attempt to enable the safety mechanism
    fault_manager.enable_sm("RiskyTemperatureOffice", SMState.ENABLED)

    # Verify that the symptom state is set to ERROR
    assert symptom.sm_state == SMState.ERROR
    
def test_determinate_info_no_NOT_TESTED(fault_manager):
    """
    Test _determinate_info when fault_state doesn't match.
    """
    entity_id = "sensor.fault_test"
    additional_info = {"Location": "Office"}
    fault_state = FaultState.NOT_TESTED  # FaultState is neither SET nor CLEARED
    
    # Set up the mock for `get_state` to return current attributes
    mocked_hass_app.get_state = Mock(return_value={
        "attributes": {"Location": "None"}  # Existing attribute is set as 'None'
    })

    result = fault_manager._determinate_info(entity_id, additional_info, fault_state)
    
    # Verify that the result is None, covering the last line of the function
    assert result is None
    
def test_determinate_info_set_none_value(fault_manager, mocked_hass_app):
    """
    Test _determinate_info when the current attribute exists as 'None' and needs to be updated to a new value.
    """
    entity_id = "sensor.fault_test"
    additional_info = {"Location": "Office"}

    # Set up the mock for `get_state` to return current attributes
    mocked_hass_app.get_state = Mock(return_value={
        "attributes": {"Location": "None"}  # Existing attribute is set as 'None'
    })

    fault_state = FaultState.SET

    result = fault_manager._determinate_info(entity_id, additional_info, fault_state)
    
    # Verify that the attribute "Location" was updated from "None" to "Office"
    assert result == {"Location": "Office"}
    
def test_determinate_info_clear_none_value(fault_manager, mocked_hass_app):
    """
    Test _determinate_info when clearing an attribute that exists as 'None'.
    """
    entity_id = "sensor.fault_test"
    additional_info = {"Location": "Office"}

    # Set up the mock for `get_state` to return current attributes
    mocked_hass_app.get_state = Mock(return_value={
        "attributes": {"Location": "None, Office"}  # Existing attribute contains 'None' and 'Office'
    })

    fault_state = FaultState.CLEARED

    result = fault_manager._determinate_info(entity_id, additional_info, fault_state)
    
    # Verify that the attribute "Location" is cleared correctly
    assert result == {"Location": "None"}