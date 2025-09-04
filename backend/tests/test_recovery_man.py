# tests/test_recovery_man.py
# mypy: ignore-errors

from shared.types_common import FaultState, RecoveryResult, RecoveryActionState, Fault, Symptom, RecoveryAction
from unittest.mock import Mock


def test_recovery_cleared_state(mocked_hass_app_with_temp_component):
    """
    Test Case: Execute recovery process when symptom is in CLEARED state.

    Scenario:
        - Symptom is in FaultState.CLEARED.
        - Expected Result: `_handle_cleared_state` should be called.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    symptom = Mock()
    symptom.state = FaultState.CLEARED
    fault_tag = "00"
    app_instance.initialize()

    recovery_manager = app_instance.reco_man
    recovery_manager._handle_cleared_state = Mock()

    recovery_manager.recovery(symptom,"00")

    recovery_manager._handle_cleared_state.assert_called_once_with(symptom)


def test_recovery_action_not_found(mocked_hass_app_with_temp_component):
    """
    Test Case: No recovery action found for the given symptom.

    Scenario:
        - Symptom name does not exist in `recovery_actions`.
        - Expected Result: Log the absence of a recovery action.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    symptom = Mock()
    symptom.name = "NonExistentSymptom"
    symptom.state = FaultState.SET

    app_instance.initialize()

    recovery_manager = app_instance.reco_man
    recovery_manager.hass_app.log = Mock()

    recovery_manager.recovery(symptom,"00")

    recovery_manager.hass_app.log.assert_called_with(
        "No recovery actions defined for symptom: NonExistentSymptom", level="DEBUG"
    )


def test_no_recovery_changes_needed(mocked_hass_app_with_temp_component):
    """
    Test Case: No changes needed for recovery.

    Scenario:
        - Recovery action returns `None`.
        - Expected Result: Log message indicates no changes are needed.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    symptom = Mock()
    symptom.name = "TestSymptom"
    symptom.state = FaultState.SET

    app_instance.initialize()

    recovery_manager = app_instance.reco_man
    recovery_action = Mock()
    recovery_action.rec_fun.return_value = None
    recovery_action.params = {}  # Ensure that params attribute is a valid dictionary
    recovery_manager.recovery_actions = {symptom.name: recovery_action}
    recovery_manager.hass_app.log = Mock()

    recovery_manager.recovery(symptom,"00")

    recovery_manager.hass_app.log.assert_called_with(
        f"No changes determined for recovery of symptom: {symptom.name}", level="DEBUG"
    )


def test_recovery_validation_fails(mocked_hass_app_with_temp_component):
    """
    Test Case: Recovery action validation fails.

    Scenario:
        - `_is_dry_test_failed()` or `_isRecoveryConflict()` returns True.
        - Expected Result: Recovery is aborted.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    symptom = Mock()
    symptom.name = "TestSymptom"
    symptom.state = FaultState.SET

    app_instance.initialize()

    recovery_manager = app_instance.reco_man
    recovery_action = Mock()
    recovery_result = Mock()
    recovery_action.rec_fun.return_value = recovery_result
    recovery_action.params = {}  # Ensure that params attribute is a valid dictionary
    recovery_manager.recovery_actions = {symptom.name: recovery_action}
    recovery_manager._is_dry_test_failed = Mock(return_value=True)
    recovery_manager._isRecoveryConflict = Mock(return_value=False)
    recovery_manager._execute_recovery = Mock()

    recovery_manager.recovery(symptom,"00")

    recovery_manager._execute_recovery.assert_not_called()


def test_successful_recovery_execution(mocked_hass_app_with_temp_component):
    """
    Test Case: Successful recovery action execution.

    Scenario:
        - Recovery validation passes.
        - Expected Result: Recovery is executed successfully.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    symptom = Mock()
    symptom.name = "TestSymptom"
    symptom.state = FaultState.SET

    app_instance.initialize()

    recovery_manager = app_instance.reco_man
    recovery_action = Mock()
    recovery_result = Mock()
    recovery_action.rec_fun.return_value = recovery_result
    recovery_action.params = {}  # Ensure that params attribute is a valid dictionary
    recovery_manager.recovery_actions = {symptom.name: recovery_action}
    recovery_manager._is_dry_test_failed = Mock(return_value=False)
    recovery_manager._isRecoveryConflict = Mock(return_value=False)
    recovery_manager._execute_recovery = Mock()

    recovery_manager.recovery(symptom,"00")

    recovery_manager._execute_recovery.assert_called_once_with(symptom, recovery_result)


def test_dry_test_failure_aborts_recovery(mocked_hass_app_with_temp_component):
    """
    Test Case: Recovery aborted when `_is_dry_test_failed()` returns True.

    Scenario:
        - `_is_dry_test_failed()` returns True.
        - Expected Result: Recovery is aborted, `_execute_recovery()` is not called.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    symptom = Mock()
    symptom.name = "ComplexSymptom"
    symptom.state = FaultState.SET

    app_instance.initialize()

    recovery_manager = app_instance.reco_man
    recovery_action = Mock()
    recovery_result = Mock()
    recovery_action.rec_fun.return_value = recovery_result
    recovery_action.params = {}
    recovery_manager.recovery_actions = {symptom.name: recovery_action}

    # Simulate `_is_dry_test_failed` returning True, indicating a validation failure
    recovery_manager._is_dry_test_failed = Mock(return_value=True)
    recovery_manager._isRecoveryConflict = Mock(return_value=False)
    recovery_manager._execute_recovery = Mock()

    # Execute recovery
    recovery_manager.recovery(symptom,"00")

    # Assert that recovery execution did not proceed
    recovery_manager._execute_recovery.assert_not_called()
    recovery_manager._is_dry_test_failed.assert_called_once_with(
        symptom.name, recovery_result.changed_sensors
    )
    recovery_manager._isRecoveryConflict.assert_not_called()  # Since `_is_dry_test_failed` failed, `_isRecoveryConflict` should not be called


def test_recovery_conflict_aborts_recovery(mocked_hass_app_with_temp_component):
    """
    Test Case: Recovery aborted when `_isRecoveryConflict()` returns True.

    Scenario:
        - `_is_dry_test_failed()` returns False.
        - `_isRecoveryConflict()` returns True.
        - Expected Result: Recovery is aborted, `_execute_recovery()` is not called.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    symptom = Mock()
    symptom.name = "ComplexSymptom"
    symptom.state = FaultState.SET

    app_instance.initialize()

    recovery_manager = app_instance.reco_man
    recovery_action = Mock()
    recovery_result = Mock()
    recovery_action.rec_fun.return_value = recovery_result
    recovery_action.params = {}
    recovery_manager.recovery_actions = {symptom.name: recovery_action}

    # Simulate `_is_dry_test_failed` returning False and `_isRecoveryConflict` returning True
    recovery_manager._is_dry_test_failed = Mock(return_value=False)
    recovery_manager._isRecoveryConflict = Mock(return_value=True)
    recovery_manager._execute_recovery = Mock()

    # Execute recovery
    recovery_manager.recovery(symptom,"00")

    # Assert that recovery execution did not proceed
    recovery_manager._execute_recovery.assert_not_called()
    recovery_manager._is_dry_test_failed.assert_called_once_with(
        symptom.name, recovery_result.changed_sensors
    )
    recovery_manager._isRecoveryConflict.assert_called_once_with(symptom)


def test_successful_recovery_execution(mocked_hass_app_with_temp_component):
    """
    Test Case: Successful recovery execution when all checks pass.

    Scenario:
        - `_is_dry_test_failed()` returns False.
        - `_isRecoveryConflict()` returns False.
        - Expected Result: Recovery is executed, `_execute_recovery()` is called.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    fault_tag = "BEEF"
    symptom = Mock()
    symptom.name = "ComplexSymptom"
    symptom.state = FaultState.SET

    app_instance.initialize()

    recovery_manager = app_instance.reco_man
    recovery_action = Mock()
    recovery_result = Mock()
    recovery_action.rec_fun.return_value = recovery_result
    recovery_action.params = {}
    recovery_manager.recovery_actions = {symptom.name: recovery_action}

    # Simulate `_is_dry_test_failed` and `_isRecoveryConflict` both returning False
    recovery_manager._is_dry_test_failed = Mock(return_value=False)
    recovery_manager._isRecoveryConflict = Mock(return_value=False)
    recovery_manager._execute_recovery = Mock()

    # Execute recovery
    recovery_manager.recovery(symptom,fault_tag)

    # Assert that recovery execution proceeded
    recovery_manager._execute_recovery.assert_called_once_with(symptom, recovery_result, fault_tag)


def test_recovery_execution_multiple_entities(mocked_hass_app_with_temp_component):
    """
    Test Case: Recovery execution with multiple entities being updated.

    Scenario:
        - The recovery action makes changes to multiple sensors and actuators.
        - Expected Result: All entities should have their states set correctly.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    symptom = Mock()
    symptom.name = "MultipleEntitiesSymptom"
    symptom.state = FaultState.SET

    app_instance.initialize()

    recovery_manager = app_instance.reco_man
    recovery_result = RecoveryResult(
        changed_sensors={"sensor.test_1": "on", "sensor.test_2": "off"},
        changed_actuators={"actuator_1": "active", "actuator_2": "inactive"},
        notifications=[],
    )
    recovery_action = Mock()
    recovery_action.rec_fun.return_value = recovery_result
    recovery_action.params = {}
    recovery_manager.recovery_actions = {symptom.name: recovery_action}
    recovery_manager._is_dry_test_failed = Mock(return_value=False)
    recovery_manager._isRecoveryConflict = Mock(return_value=False)

    recovery_manager.recovery(symptom,"00")

    # Validate that all entities are updated correctly
    app_instance.set_state.assert_any_call("actuator_1", state="active")
    app_instance.set_state.assert_any_call("actuator_2", state="inactive")


def test_integration_with_fault_and_notification_managers(
    mocked_hass_app_with_temp_component,
):
    """
    Test Case: Integration with FaultManager and NotificationManager.

    Scenario:
        - The recovery action makes changes and issues notifications.
        - Expected Result: Notifications are properly sent, and recovery actions are registered.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )

    # Create and initialize the symptom to be registered in FaultManager
    symptom = Mock()
    symptom.name = "IntegrationSymptom"
    symptom.state = FaultState.SET
    symptom.sm_name = "sm_integration"

    app_instance.initialize()

    # Register the symptom in the FaultManager
    fault_manager = app_instance.fm
    fault_manager.symptoms = {symptom.name: symptom}

    # Prepare the RecoveryManager and NotificationManager
    recovery_manager = app_instance.reco_man
    recovery_result = RecoveryResult(
        changed_sensors={},  # No sensor changes
        changed_actuators={"actuator_1": "active"},
        notifications=["Manual intervention required for actuator_1."],
    )
    recovery_action = Mock()
    recovery_action.rec_fun.return_value = recovery_result
    recovery_action.params = {}
    recovery_manager.recovery_actions = {symptom.name: recovery_action}

    # Prepare FaultManager to return an existing fault for this symptom
    fault = Fault("IntegrationFault", [symptom.sm_name], 1)
    fault_manager.faults = {fault.name: fault}
    fault_manager.found_mapped_fault = Mock(return_value=fault)
    fault_tag = '00'

    # Mock NotificationManager to validate the notification actions
    notification_manager = app_instance.notify_man
    notification_manager._add_recovery_action = Mock()

    # Execute recovery
    recovery_manager._is_dry_test_failed = Mock(return_value=False)
    recovery_manager._isRecoveryConflict = Mock(return_value=False)
    recovery_manager.recovery(symptom,fault_tag)

    # Validate that actuators are updated correctly
    app_instance.set_state.assert_any_call("actuator_1", state="active")

    # Validate that the notification action was called correctly
    notification_manager._add_recovery_action.assert_called_once_with(
        "Manual intervention required for actuator_1.", fault_tag
    )


def test_recovery_action_state_transition(mocked_hass_app_with_temp_component):
    """
    Test Case: Validate the transition of `RecoveryActionState`.

    Scenario:
        - Check that the `RecoveryActionState` transitions from `DO_NOT_PERFORM` to `TO_PERFORM` during execution.
        - Expected Result: RecoveryActionState is updated correctly.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    symptom = Mock()
    symptom.name = "StateTransitionSymptom"
    symptom.state = FaultState.SET

    app_instance.initialize()

    recovery_manager = app_instance.reco_man
    recovery_result = RecoveryResult(
        changed_sensors={"sensor.test_1": "on", "sensor.test_2": "off"},
        changed_actuators={"actuator_1": "active", "actuator_2": "inactive"},
        notifications=[],
    )
    recovery_action = Mock()
    recovery_action.rec_fun.return_value = recovery_result
    recovery_action.params = {}
    recovery_action.current_status = RecoveryActionState.DO_NOT_PERFORM
    recovery_manager.recovery_actions = {symptom.name: recovery_action}
    recovery_manager._is_dry_test_failed = Mock(return_value=False)
    recovery_manager._isRecoveryConflict = Mock(return_value=False)

    # Execute the recovery process
    recovery_manager.recovery(symptom,"00")

    # Assert that the recovery action state is updated to `TO_PERFORM`
    assert recovery_action.current_status == RecoveryActionState.TO_PERFORM
    # Verify that the recovery function (`rec_fun`) was called
    recovery_action.rec_fun.assert_called_once_with(
        recovery_manager.hass_app,
        symptom,
        recovery_manager.common_entities,
        **recovery_action.params,
    )
    
def test_check_conflict_with_higher_priority(mocked_hass_app_with_temp_component):
    """
    Test Case: Conflict detected with higher priority fault.

    Scenario:
        - The recovery action has matching actions.
        - One of the matching faults has a higher priority than the current recovery fault.
        - Expected Result: The function returns True, indicating a conflict.
    """
    app_instance, _, __, ___, mock_behaviors_default = mocked_hass_app_with_temp_component

    # Create a mock for a symptom and fault
    symptom = Mock()
    symptom.name = "TestSymptom"
    symptom.sm_name = "sm_test"

    app_instance.initialize()

    # Mock the RecoveryManager instance and required methods
    recovery_manager = app_instance.reco_man

    # Mock FaultManager to include a matching fault with higher priority
    found_symptom = Mock()
    found_symptom.name = "MatchingSymptom"
    
    higher_priority_fault = Mock()
    higher_priority_fault.level = 5  # Set higher priority
    
    # Set the fault manager's symptoms and found_fault method to match
    recovery_manager.fm.symptoms = {
        "MatchingSymptom": found_symptom
    }
    recovery_manager.fm.found_mapped_fault = Mock(return_value=higher_priority_fault)

    # Define a list of matching actions that includes the "MatchingSymptom"
    matching_actions = ["MatchingSymptom"]
    
    # The current fault's priority is lower than the mocked fault
    rec_fault_prio = 3

    # Call `_check_conflict_with_matching_actions` and check the result
    conflict = recovery_manager._check_conflict_with_matching_actions(
        matching_actions,
        rec_fault_prio,
        symptom
    )

    # Assert that conflict is True due to higher priority fault being present
    assert conflict is True

def test_recovery_conflict_with_higher_priority(mocked_hass_app_with_temp_component):
    """
    Test Case: Recovery process is aborted due to a higher-priority conflict.

    Scenario:
        - The recovery action has matching actions.
        - One of the matching faults has a higher priority than the current recovery fault.
        - Expected Result: The recovery is not performed because of the conflict.
    """
    app_instance, _, __, ___, mock_behaviors_default = mocked_hass_app_with_temp_component

    # Create mock symptom
    symptom = Mock()
    symptom.name = "TestSymptom"
    symptom.state = FaultState.SET
    symptom.sm_name = "sm_test"

    app_instance.initialize()

    recovery_manager = app_instance.reco_man

    # Mock the RecoveryAction
    recovery_result = RecoveryResult(
        changed_sensors={"sensor.test_1": "on"},
        changed_actuators={"actuator_1": "active"},
        notifications=[],
    )
    recovery_action = Mock()
    recovery_action.rec_fun.return_value = recovery_result
    recovery_action.params = {}
    recovery_action.name = "MatchingAction"  # Set name to a non-mock value
    recovery_manager.recovery_actions = {
        symptom.name: recovery_action,  # Include the test symptom in recovery actions
        "MatchingSymptom": recovery_action,  # Also include a mock matching action
    }

    # Mock FaultManager to include a matching fault with higher priority
    found_symptom = Mock()
    found_symptom.name = "MatchingSymptom"
    found_symptom.sm_name = "sm_test"
    found_fault = Mock()
    found_fault.level = 5  # Set higher priority than current recovery fault

    test_fault = Mock()
    test_fault.level = 3  # Priority of the current recovery fault (lower)

    # Set up FaultManager behavior
    recovery_manager.fm.symptoms = {
        "MatchingSymptom": found_symptom,
        "TestSymptom": symptom,
    }

    # Define a side_effect function for found_mapped_fault
    def found_mapped_fault_side_effect(symptom_name, sm_name):
        if symptom_name == "TestSymptom":
            return test_fault
        elif symptom_name == "MatchingSymptom":
            return found_fault
        return None

    recovery_manager.fm.found_mapped_fault = Mock(side_effect=found_mapped_fault_side_effect)

    # Mock `_is_dry_test_failed` to return False, allowing the conflict check to proceed
    recovery_manager._is_dry_test_failed = Mock(return_value=False)
    recovery_manager._execute_recovery = Mock()

    # Call recovery
    recovery_manager.recovery(symptom,"00")

    # Assert that `_execute_recovery` was not called due to the conflict
    recovery_manager._execute_recovery.assert_not_called()
    recovery_manager.fm.found_mapped_fault.assert_any_call(symptom.name, symptom.sm_name)
    recovery_manager.fm.found_mapped_fault.assert_any_call("MatchingSymptom", "sm_test")

import pytest
from unittest.mock import Mock, patch
from shared.types_common import FaultState, RecoveryActionState, RecoveryResult

def test_perform_recovery_with_exception_handling(mocked_hass_app_with_temp_component):
    """
    Test Case: Exception handling during entity state changes in recovery.

    Scenario:
        - An exception is raised during setting an entity state.
        - Expected Result: Proper error logging and continuation of recovery process.
    """
    app_instance, _, __, ___, mock_behaviors_default = mocked_hass_app_with_temp_component
    symptom = Mock()
    symptom.name = "TestSymptomWithException"
    symptom.sm_name = "TestSM"
    symptom.state = FaultState.SET

    app_instance.initialize()

    recovery_manager = app_instance.reco_man
    recovery_result = RecoveryResult(
        changed_sensors={"sensor.test_1": "on", "sensor.test_2": "off"},
        changed_actuators={"actuator_1": "active", "actuator_2": "inactive"},
        notifications=["Test notification"],
    )

    # Mocking a RecoveryAction
    recovery_action = Mock()
    recovery_action.rec_fun.return_value = recovery_result
    recovery_action.params = {}
    recovery_action.current_status = RecoveryActionState.DO_NOT_PERFORM
    recovery_manager.recovery_actions = {symptom.name: recovery_action}

    # Mocking found fault
    found_fault = Mock()
    found_fault.name = "TestFault"
    fault_tag = 'BE'
    recovery_manager.fm.found_mapped_fault = Mock(return_value=found_fault)

    # Mock `set_state` to throw an exception for one of the entities
    def mock_set_state(entity, state):
        if entity == "actuator_1":
            raise Exception("Simulated set_state error")
        else:
            pass

    recovery_manager.hass_app.set_state = Mock(side_effect=mock_set_state)
    recovery_manager.hass_app.log = Mock()
    recovery_manager.nm._add_recovery_action  = Mock()
    
    # Call `_perform_recovery`
    recovery_manager._perform_recovery(symptom, recovery_result.notifications, recovery_result.changed_actuators, fault_tag)

    # Validate that the correct error was logged
    recovery_manager.hass_app.log.assert_any_call(
        "Exception during setting actuator_1 to active value. Simulated set_state error",
        level="ERROR",
    )

    # Assert that `set_state` was called for other entities despite the exception
    recovery_manager.hass_app.set_state.assert_any_call("actuator_1", state="active")
    recovery_manager.hass_app.set_state.assert_any_call("actuator_2", state="inactive")

    # Assert that notifications were processed
    recovery_manager.nm._add_recovery_action.assert_called_once_with("Test notification", fault_tag)


def test_perform_recovery_no_recovery_action_found(mocked_hass_app_with_temp_component):
    """
    Test Case: No recovery action found for the given symptom.

    Scenario:
        - `_find_recovery()` returns None.
        - Expected Result: Proper error logging indicating that no recovery action was found.
    """
    app_instance, _, __, ___, mock_behaviors_default = mocked_hass_app_with_temp_component
    symptom = Mock(spec=Symptom)
    symptom.name = "NonExistentRecoverySymptom"
    symptom.sm_name = "TestSM"
    symptom.state = FaultState.SET
    fault_tag = 'CE'

    app_instance.initialize()

    recovery_manager = app_instance.reco_man

    # Mock `_find_recovery` to return None to simulate that the recovery action was not found
    recovery_manager._find_recovery = Mock(return_value=None)
    recovery_manager.hass_app.log = Mock()

    # Call `_perform_recovery`
    recovery_manager._perform_recovery(symptom, notifications=[], entities_changes={}, fault_tag=fault_tag)

    # Validate that the correct error was logged
    recovery_manager.hass_app.log.assert_called_once_with(
        f"Recovery action for {symptom.name} was not found!", level="ERROR"
    )

def test_perform_recovery_no_action_in_list(mocked_hass_app_with_temp_component):
    """
    Test Case: Symptom without an associated recovery action.

    Scenario:
        - Symptom is not present in the `recovery_actions` list.
        - Expected Result: Proper error logging indicating that no recovery action was found.
    """
    # Set up the mocked instance and symptom
    app_instance, _, __, ___, mock_behaviors_default = mocked_hass_app_with_temp_component
    symptom = Mock(spec=Symptom)
    symptom.name = "NonExistentRecoverySymptom"
    symptom.sm_name = "TestSM"
    symptom.state = FaultState.SET

    app_instance.initialize()

    # Set up the RecoveryManager instance
    recovery_manager = app_instance.reco_man
    fault_tag = '00'

    # Prepare recovery_actions list with entries for other symptoms, but not the one we're testing
    recovery_action_1 = Mock(spec=RecoveryAction)
    recovery_action_1.name = "ExistingRecoveryAction"
    recovery_manager.recovery_actions = {
        "OtherSymptom": recovery_action_1  # No entry for "NonExistentRecoverySymptom"
    }

    # Mock logging for assertions
    recovery_manager.hass_app.log = Mock()

    # Call `_perform_recovery`
    recovery_manager._perform_recovery(symptom, notifications=[], entities_changes={},fault_tag=fault_tag)

    # Validate that the correct error was logged
    recovery_manager.hass_app.log.assert_called_once_with(
        f"Recovery action for {symptom.name} was not found!", level="ERROR"
    )
    
def test_perform_recovery_no_matching_action(mocked_hass_app_with_temp_component):
    """
    Test Case: Indirectly test `_find_recovery()` returning `None`.

    Scenario:
        - Symptom is not present in the `recovery_actions` dictionary.
        - Expected Result: Proper logging indicating that no recovery action was found.
    """
    # Set up the mocked app instance and initialize it
    app_instance, _, __, ___, mock_behaviors_default = mocked_hass_app_with_temp_component
    app_instance.initialize()

    # Set up the recovery manager with no recovery actions
    recovery_manager = app_instance.reco_man
    recovery_manager.recovery_actions = {}  # No recovery actions available

    # Create a mock Symptom object that is not in recovery_actions
    symptom = Mock(spec=Symptom)
    symptom.name = "NonExistingSymptom"
    symptom.sm_name = "TestSM"
    symptom.state = FaultState.SET
    fault_tag = '78'

    # Mock `hass_app` logging to verify log calls
    recovery_manager.hass_app.log = Mock()

    # Call `_perform_recovery` with the mock Symptom
    recovery_manager._perform_recovery(symptom, notifications=[], entities_changes={},fault_tag=fault_tag)

    # Validate that the correct log message is printed
    recovery_manager.hass_app.log.assert_called_once_with(
        f"Recovery action for {symptom.name} was not found!", level="ERROR"
    )
    
def test_no_recovery_conflict(mocked_hass_app_with_temp_component):
    """
    Test Case: Indirectly test `_isRecoveryConflict()` returning `False`.

    Scenario:
        - `_get_matching_actions()` returns an empty list, meaning no conflicting actions are found.
        - Expected Result: `_isRecoveryConflict()` should return `False`, indicating no conflict exists.
    """
    # Set up the mocked app instance and initialize it
    app_instance, _, __, ___, mock_behaviors_default = mocked_hass_app_with_temp_component
    app_instance.initialize()

    # Set up the recovery manager
    recovery_manager = app_instance.reco_man

    # Mock the symptom that we will pass to `_isRecoveryConflict`
    symptom = Mock(spec=Symptom)
    symptom.name = "NoConflictSymptom"
    symptom.sm_name = "TestSM"
    symptom.state = FaultState.SET

    # Mock `hass_app` logging to verify log calls
    recovery_manager.hass_app.log = Mock()

    # Mock `_get_matching_actions` to return an empty list (indicating no matching actions)
    recovery_manager._get_matching_actions = Mock(return_value=[])

    # Mock `found_mapped_fault` to return `None`, to bypass other checks
    recovery_manager.fm.found_mapped_fault = Mock(return_value=None)

    # Call `recovery()` with the symptom to indirectly trigger `_isRecoveryConflict()`
    recovery_manager._isRecoveryConflict(symptom)

    # Since `_get_matching_actions` returns an empty list, `_isRecoveryConflict` should return False
    recovery_manager._get_matching_actions.assert_called_once_with(symptom)
    
def test_recovery_performed_callback(mocked_hass_app_with_temp_component):
    """
    Test Case: Validate the behavior of `_recovery_performed()` callback.

    Scenario:
        - `_recovery_performed()` is invoked, simulating an entity state change.
        - Expected Result: `_recovery_clear()` is called with the correct symptom.
    """
    # Set up the mocked app instance and initialize it
    app_instance, _, __, ___, mock_behaviors_default = mocked_hass_app_with_temp_component
    app_instance.initialize()

    # Set up the recovery manager
    recovery_manager = app_instance.reco_man

    # Mock the `_recovery_clear` method to track if it is called
    recovery_manager._recovery_clear = Mock()

    # Define the symptom that will be passed in `cb_args`
    symptom = Mock()
    symptom.name = "TestSymptom"

    # Call `_recovery_performed` directly with the mock callback arguments
    cb_args = {"symptom": symptom}

    # Invoke the callback function directly
    recovery_manager._recovery_performed(None, None, None, None, cb_args)

    # Assert that `_recovery_clear` was called with the expected symptom
    recovery_manager._recovery_clear.assert_called_once_with(symptom)