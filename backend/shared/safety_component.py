"""
This module provides foundational structures and functionalities for implementing advanced safety mechanisms within Home Assistant applications. It introduces a systematic approach to handling, debouncing, and managing state changes of Home Assistant entities, enabling the creation of sophisticated safety and fault management strategies.

Components:
- `DebounceState`: A named tuple that stores the current state of a debouncing process, including the debounce counter and a flag indicating the necessity of action.
- `DebounceAction`: An enumeration that defines possible outcomes of the debouncing process, such as setting a symptom condition, clearing it, or taking no action.
- `DebounceResult`: A named tuple that encapsulates the result of a debouncing process, comprising the action to be taken and the updated counter value.
- `SafetyComponent`: A base class for creating domain-specific safety components. It provides methods for entity validation, debouncing logic, and interaction with a fault manager to set or clear symptom conditions based on dynamic sensor data.
- `safety_mechanism_decorator`: A decorator designed to wrap safety mechanism functions, adding pre- and post-execution logic around these functions for enhanced logging and execution control.

Features:
- Flexible monitoring and debouncing of entity states to prevent rapid toggling and ensure reliable fault detection.
- Integration with a fault management system, allowing for dynamic response to fault conditions and the ability to set or clear faults programmatically.
- Extensibility for developing custom safety mechanisms tailored to specific needs and scenarios within the smart home environment.

Usage:
The module's components are intended to be used as building blocks for developing custom safety mechanisms within Home Assistant. By subclassing `SafetyComponent` and utilizing `DebounceState`, `DebounceAction`, and `DebounceResult`, developers can create robust safety features that respond intelligently to changes in the Home Assistant environment.

Example:
A developer might create a `TemperatureSafetyComponent` subclass that monitors temperature sensors and uses the debouncing logic to manage heating elements within the home, ensuring a safe and comfortable environment.

This module streamlines the creation of safety mechanisms, emphasizing reliability, flexibility, and integration with Home Assistant's dynamic ecosystem.
"""

from typing import (
    Type,
    Any,
    get_origin,
    get_args,
    Callable,
    Optional,
    NamedTuple,
    Literal,
)
from enum import Enum

from shared.fault_manager import FaultManager
from shared.types_common import FaultState
import appdaemon.plugins.hass.hassapi as hass  # type: ignore
from shared.types_common import Symptom, RecoveryAction, SMState
from shared.common_entities import CommonEntities
from shared.derivative_monitor import DerivativeMonitor

NO_NEEDED = False


class DebounceState(NamedTuple):
    """
    Purpose: Acts as a memory for a particular safety mechanism. It stores the current state of the debouncing process for a specific mechanism,
    including the debounce counter and a flag indicating whether action should be forced for debouncing purposes.

    Usage: This state is maintained across calls to process_symptom to keep track of how many times a condition has been met or not met,
    helping to stabilize the detection over time by preventing rapid toggling due to transient states.

    Attributes:
        debounce (int): A counter used to stabilize the detection of a condition over time, preventing rapid toggling.
        force_sm (bool): A flag indicating whether sm shall be forced for debouncing purpose
    """

    debounce: int
    force_sm: bool


# Define the named tuple with possible outcomes
class DebounceAction(Enum):
    """
    Enumeration of debouncing actions that can be taken after evaluating a symptom condition.

    Attributes:
        NO_ACTION (int): Indicates that no action should be taken.
        symptom_SET (int): Indicates a symptom condition should be set.
        symptom_HEALED (int): Indicates a symptom condition has been cleared or healed.
    """

    NO_ACTION = 0
    symptom_SET = 1
    symptom_HEALED = -1


class DebounceResult(NamedTuple):
    """
    Represents the result of a debouncing process, encapsulating the action to be taken and the updated counter value.

    Attributes:
        action (DebounceAction): The action determined by the debouncing process.
        counter (int): The updated debounce counter after evaluating the symptom condition.
    """

    action: DebounceAction
    counter: int


class SafetyComponent:
    """
    A base class for creating and managing safety mechanisms within the Home Assistant environment.

    It provides the infrastructure for monitoring entity states, validating entities, debouncing state changes,
    and interacting with a fault management system. Subclasses can implement specific safety logic, such as
    monitoring for hazardous conditions and taking corrective actions.

    Attributes:
        hass_app: Reference to the Home Assistant application instance.
        fault_man: Optional instance of a fault manager for managing fault conditions.

    Methods:
        register_fm: Registers a fault manager instance with the safety component.
        validate_entity: Validates an entity against a specified type.
        validate_entities: Validates multiple entities against their expected types.
        safe_float_convert: Safely converts a string to a float.
        _debounce: Implements debouncing logic for state changes.
        process_symptom: Processes potential symptom conditions based on debouncing logic.
    """

    component_name: str = "UNKNOWN"  # Default value for the parent class

    def __init__(self, hass_app: hass.Hass, common_entities: CommonEntities) -> None:
        """
        Initialize the safety component.

        :param hass_app: The Home Assistant application instance.
        """
        self.hass_app: hass.Hass = hass_app
        self.fault_man: Optional[FaultManager] = None
        self.common_entities: CommonEntities = common_entities
        self.init_common_data()
        self.derivative_monitor = DerivativeMonitor(hass_app)

    def init_common_data(self) -> None:
        # Initialize dictionaries that need to be unique to each instance
        self.safety_mechanisms: dict = {}
        self.debounce_states: dict = {}

    def get_symptoms_data(
        self, modules: dict, component_cfg: list[dict[str, Any]]
    ) -> tuple[dict[str, Symptom], dict[str, RecoveryAction]]:
        """
        Abstract method to retrieve symptom configurations and generate corresponding symptom and recovery action objects.

        Args:
            modules (dict): A dictionary of system modules.
            component_cfg (list[dict[str, Any]]): A list of dictionaries, each containing a location as the key and a configuration dictionary for that location.

        Returns:
            tuple: A tuple containing:
                - dict[str, Symptom]: A dictionary mapping symptom names to Symptom objects.
                - dict[str, RecoveryAction]: A dictionary mapping symptom names to RecoveryAction objects.

        Raises:
            NotImplementedError: This method must be implemented in subclasses.
        """
        raise NotImplementedError

    def init_safety_mechanism(self, sm_name: str, name: str, parameters: dict) -> bool:
        """
        Abstract method to initialize a safety mechanism based on the provided name and parameters.

        Args:
            sm_name (str): The name of the safety mechanism (e.g., "sm_tc_1" or "sm_tc_2").
            name (str): The unique identifier for this safety mechanism.
            parameters (dict): Configuration parameters specific to the safety mechanism.

        Returns:
            bool: True if initialization is successful, False otherwise.

        Raises:
            NotImplementedError: This method must be implemented in subclasses.
        """
        raise NotImplementedError

    def enable_safety_mechanism(self, name: str, state: SMState) -> bool:
        """
        Abstract method to enable or disable a specific safety mechanism.

        Args:
            name (str): The unique identifier for the safety mechanism.
            state (SMState): The desired state for the safety mechanism (ENABLED or DISABLED).

        Returns:
            bool: True if the state change is successful, False otherwise.

        Raises:
            NotImplementedError: This method must be implemented in subclasses.
        """
        raise NotImplementedError

    def register_fm(self, fm: FaultManager) -> None:
        """
        Registers a FaultManager instance with this component, enabling interaction with the fault management system.

        This method associates a FaultManager object with the component, allowing it to set or clear fault conditions
        based on the outcomes of safety mechanism evaluations. The registered FaultManager is essential for the component
        to communicate fault states and recovery actions within the broader safety management system.

        Args:
            fm (FaultManager): An instance of FaultManager that will be used by this component to manage fault conditions.

        Note:
            It's important to register a FaultManager before invoking safety mechanisms that require fault state management
            to ensure the component can appropriately respond to and manage fault conditions.
        """
        self.fault_man = fm

    def validate_entity(
        self, entity_name: str, entity: Any, expected_type: Type
    ) -> bool:
        """
        Validate a single entity against the expected type.

        :param entity: The entity to validate.
        :param expected_type: The expected type (e.g., type, List[type], etc.).
        :return: True if the entity is valid, False otherwise.
        """
        # Check for generic types like List[type]
        if get_origin(expected_type):
            if not isinstance(entity, get_origin(expected_type)):  # type: ignore
                self.hass_app.log(
                    f"Entity {entity_name} should be a {get_origin(expected_type).__name__}",  # type: ignore
                    level="ERROR",
                )
                return False
            element_type = get_args(expected_type)[0]
            if not all(isinstance(item, element_type) for item in entity):
                self.hass_app.log(
                    f"Elements of entity {entity_name} should be {element_type.__name__}",
                    level="ERROR",
                )
                return False
        # Non-generic types
        elif not isinstance(entity, expected_type):
            self.hass_app.log(
                f"Entity {entity_name} should be {expected_type.__name__}",
                level="ERROR",
            )
            return False

        return True

    def validate_entities(
        self, sm_args: dict[str, Any], expected_types: dict[str, Type]
    ) -> bool:
        """
        Validate multiple entities against their expected types based on kwargs.

        This method checks whether each required entity (as specified in `expected_types`)
        is present in `sm_args` and whether each entity conforms to its expected type.

        Example usage:
            sm_args = {
                'window_sensors': ["binary_sensor.window1", "binary_sensor.window2"],
                'temperature_sensor': "sensor.room_temperature",
                'threshold': 25.0
            }

            expected_types = {
                'window_sensors': List[str],  # Expect a list of strings
                'temperature_sensor': str,    # Expect a string
                'threshold': float            # Expect a float
            }

            if not self.validate_entities(sm_args, expected_types):
                # Handle validation failure
                return False

        :param sm_args: The actual keyword arguments passed to the method.
                        It should contain all the entities required for the safety mechanism.
        :param expected_types: A dictionary mapping expected variable names to their expected types.
                               This dict defines what type each entity in `sm_args` should be.
        :return: True if all required entities are present in `sm_args` and valid, False otherwise.
        """
        for entity_name, expected_type in expected_types.items():
            if entity_name not in sm_args:
                self.hass_app.log(
                    f"Missing required argument: {entity_name}", level="ERROR"
                )
                return False
            if not self.validate_entity(
                entity_name, sm_args[entity_name], expected_type
            ):
                # The specific error message will be logged in validate_entity
                return False
        return True

    @staticmethod
    def get_num_sensor_val(hass_app: hass, sensor_id: str) -> float | None:
        """Fetch and convert temperature from a sensor."""
        try:
            return float(hass_app.get_state(sensor_id))
        except (ValueError, TypeError) as e:
            hass_app.log(f"Conversion error: {e}", level="WARNING")
            return None

    @staticmethod
    def change_all_entities_state(entities: list[str], state: str) -> dict[str, str]:
        """Create a dictionary to change the state of entities."""
        return {entity: state for entity in [entities]}  # type: ignore

    def _debounce(
        self, current_counter: int, pr_test: bool, debounce_limit: int = 3
    ) -> DebounceResult:
        """
        Generic debouncing function that updates the counter based on the state
        and returns an action indicating whether a symptom should be set, cleared, or no action taken.

        Args:
            current_counter (int): The current debounce counter for the mechanism.
            pr_test (bool): The result of the symptom test. True if the condition is detected, False otherwise.
            debounce_limit (int, optional): The limit at which the state is considered stable. Defaults to 3.

        Returns:
            DebounceResult: A named tuple containing the action to be taken (DebounceAction) and the updated counter (int).
        """
        if pr_test:
            new_counter: int = min(debounce_limit, current_counter + 1)
            action: (
                Literal[DebounceAction.symptom_SET] | Literal[DebounceAction.NO_ACTION]
            ) = (
                DebounceAction.symptom_SET
                if new_counter >= debounce_limit
                else DebounceAction.NO_ACTION
            )
        else:
            new_counter = max(-debounce_limit, current_counter - 1)
            action = (
                DebounceAction.symptom_HEALED
                if new_counter <= -debounce_limit
                else DebounceAction.NO_ACTION
            )

        return DebounceResult(action=action, counter=new_counter)

    def process_symptom(
        self,
        symptom_id: str,
        current_counter: int,
        pr_test: bool,
        additional_info: dict,
        debounce_limit: int = 2,
    ) -> tuple[int, bool]:
        """
        Handles the debouncing of a symptom condition based on a symptom test (pr_test).

        This method manages the symptom state by updating the debounce counter and
        interacting with the Fault Manager as needed. The symptom state is determined
        by the result of the pr_test and the current state of the debounce counter.
        This method is responsible for calling the necessary interfaces from the Fault
        Manager to set or clear symptom conditions.

        The method returns two values: the updated debounce counter and a boolean
        indicating whether to inhibit further triggers. If inhibition is true,
        further triggers are ignored except for time-based events used for debouncing purposes.

        Args:
            symptom_id (int): The identifier for the symptom condition.
            current_counter (int): The current value of the debounce counter.
            pr_test (bool): The result of the symptom test. True if the symptom
                            condition is detected, False otherwise.
            debounce_limit (int, optional): The threshold for the debounce counter
                                            to consider the state stable. Defaults to 3.

        Returns:
            tuple:
                - int: The updated debounce counter value.
                - bool: A flag indicating whether to safety mechanism shall be forced to trigger.
                        True to force, False to not.

        Raises:
            None
        """

        if not self.fault_man:
            self.hass_app.log("Fault manager not initialized!", level="ERROR")
            return current_counter, False

        # Prepare retVal
        force_sm: bool = False
        debounce_result: DebounceResult = DebounceResult(
            action=DebounceAction.NO_ACTION, counter=current_counter
        )

        # Get current symptom state
        symptom_cur_state: FaultState = self.fault_man.check_symptom(symptom_id)
        # Check if any actions is needed
        if (
            (pr_test and symptom_cur_state == FaultState.CLEARED)
            or (not pr_test and symptom_cur_state == FaultState.SET)
            or (symptom_cur_state == FaultState.NOT_TESTED)
        ):
            debounce_result = self._debounce(current_counter, pr_test, debounce_limit)

            if debounce_result.action == DebounceAction.symptom_SET:
                # Call Fault Manager to set symptom
                self.fault_man.set_symptom(symptom_id, additional_info)
                self.hass_app.log(
                    f"symptom {symptom_id} with {additional_info} was set",
                    level="DEBUG",
                )
                force_sm = False
            elif debounce_result.action == DebounceAction.symptom_HEALED:
                # Call Fault Manager to heal symptom
                self.fault_man.clear_symptom(symptom_id, additional_info)
                self.hass_app.log(
                    f"symptom {symptom_id} with {additional_info} was cleared",
                    level="DEBUG",
                )
                force_sm = False
            elif debounce_result.action == DebounceAction.NO_ACTION:
                force_sm = True
        else:
            # Debouncing not necessary at all (Test failed and symptom already raised or
            #  test passed and fault already cleared)
            pass

        self.hass_app.log(
            f"Leaving  process_symptom for {symptom_id} with counter:{debounce_result.counter} and force_sm {force_sm}",
            level="DEBUG",
        )
        return debounce_result.counter, force_sm

    def sm_recalled(self, **kwargs: dict) -> None:
        """
        This method should be overridden in the subclass to handle the re-execution of safety mechanisms.
        If not overridden, it raises a NotImplementedError to signal that the subclass must implement this method.

        Args:
            **kwargs: A dictionary containing key parameters needed to re-invoke the safety mechanism.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement its own version of sm_recalled."
        )


def safety_mechanism_decorator(func: Callable) -> Callable:
    """
    The safety_mechanism_decorator is a decorator designed to enhance the execution of safety mechanism functions by
    adding pre- and post-execution logic.    This decorator simplifies the handling of safety mechanisms, particularly
    when they need to be called either explicitly by the system or scheduled for repeated execution.

    Key Features:
        Logging: Logs the start and end of the function execution, providing visibility into the operation of the safety mechanism.
        Conditional Execution: Checks whether the safety mechanism is enabled before execution. If it is disabled, the function exits early without performing any actions.
        Debouncing and Symptom Processing: Handles debouncing logic to stabilize the detection of safety conditions over time. This prevents rapid toggling of states due to transient conditions.
        Scheduler Integration: If the safety mechanism requires re-evaluation after a delay, the decorator schedules the sm_recalled function to run the safety mechanism again.
            This is particularly useful for mechanisms that need to assess conditions over time, such as monitoring temperature changes.

    Workflow:
        Initial Logging: Logs that the safety mechanism function has started.
        Check if Enabled: The function checks if the safety mechanism is enabled. If not, it logs this and exits.
        Execute Function: Calls the safety mechanism function and processes the result.
        Debouncing Logic: Uses the process_symptom method to update the debounce counter and determine if any action needs to be taken (e.g., setting or clearing a fault condition).
        Force Re-Evaluation: If the safety mechanism needs to be evaluated again (due to the debouncing logic), the decorator schedules the sm_recalled function to re-execute the safety mechanism after a short delay.
        Final Logging: Logs the completion of the safety mechanism function.

    This decorator effectively manages the complex scheduling requirements of safety mechanisms by ensuring that they are called at appropriate intervals and that their execution is properly logged and controlled. It provides a robust solution for integrating safety mechanisms into a dynamic environment like Home Assistant, where conditions can change rapidly and require careful monitoring.

    Args:
        func (Callable): The safety mechanism function to be decorated.

    Returns:
        Callable: A wrapped version of the input function with added pre- and post-execution logic.
    """

    def safety_mechanism_wrapper(
        self: "SafetyComponent",
        sm: Any,
        entities_changes: dict[str, str] | None = None,
    ) -> Any:
        """
        Wrapper function for the safety mechanism.

        :param self: The instance of the class where the function is defined.
        :param sm: Safety mechanism instance.
        :param entities_changes: Changes in entities, if any.
        :return: The result of the safety mechanism function.
        """
        self.hass_app.log(f"{func.__name__} was started!", level="DEBUG")

        if not sm.isEnabled:
            self.hass_app.log(
                f"{func.__name__} is disabled, skipping execution.", level="DEBUG"
            )
            return False

        if not entities_changes:
            # Retrieve the current debounce state for this mechanism
            current_state: DebounceState = self.debounce_states[sm.name]

            # Get sm result!
            sm_return = func(self, sm, entities_changes)

            # Perform SM logic
            new_debounce: tuple[int, bool] = self.process_symptom(
                symptom_id=sm.name,
                current_counter=current_state.debounce,
                pr_test=sm_return.result,
                additional_info=sm_return.additional_info,
            )

            # Update the debounce state with the new values
            self.debounce_states[sm.name] = DebounceState(
                debounce=new_debounce[0], force_sm=new_debounce[1]
            )
            if new_debounce[1]:
                self.hass_app.log(
                    f"Scheduling {func.__name__} to run again in 5 seconds.",
                    level="DEBUG",
                )
                # If force_sm is true, schedule to run the function again after 30 seconds TODO Cyclic time shall comes from SafetyMechanism config
                self.hass_app.run_in(
                    self.sm_recalled,
                    30,
                    sm_method=func.__name__,
                    sm_name=sm.name,
                    entities_changes=entities_changes,
                )

        else:
            self.hass_app.log(
                f"{func.__name__} running in dry mode with changes: {entities_changes}",
                level="DEBUG",
            )
            sm_return = func(self, sm, entities_changes)

        self.hass_app.log(f"{func.__name__} was ended!", level="DEBUG")
        return sm_return.result

    return safety_mechanism_wrapper


class SafetyMechanismResult(NamedTuple):
    result: bool
    additional_info: Optional[dict[str, Any]] = None
