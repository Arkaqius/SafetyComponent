"""
Module: types_enums.py

This module defines enumeration types used throughout the Safety Functions application,
particularly within the Home Assistant-based safety management system. These enums
provide a standardized set of possible states for faults (FaultState) and safety mechanisms (SMState),
ensuring consistency and clarity in state management and logic flow across the application.

Enums:
- FaultState: Enumerates the possible states of faults and symptoms, aiding in the
  identification and management of safety system conditions.
- SMState: Defines the operational states of Safety Mechanisms (SMs), offering insight
  into the activity and readiness of these mechanisms.

Usage:
Import the necessary enums into your module to leverage these predefined states for
fault management and safety mechanism state tracking. This centralizes state definitions,
facilitating easier maintenance and updates.
"""

from enum import Enum
from typing import Any, NamedTuple, Dict, List


class FaultState(Enum):
    """
    Represents the possible states of a fault and symptoms within the safety management system.

    Attributes:
        NOT_TESTED: Initial state, indicating the fault has not yet been tested.
        SET: Indicates that the fault condition has been detected.
        CLEARED: Indicates that the fault condition has been resolved.
    """

    NOT_TESTED = 0
    SET = 1
    CLEARED = 2


class SMState(Enum):
    """
    Defines the operational states of Safety Mechanisms (SMs) within the safety management system.

    This enumeration helps to clearly define and track the current status of each safety mechanism,
    facilitating status checks and transitions in response to system events or conditions.

    Attributes:
        ERROR: Represents a state where the safety mechanism has encountered an error.
        NON_INITIALIZED: Indicates that the safety mechanism has not been initialized yet.
        DISABLED: The safety mechanism is initialized but currently disabled, not actively monitoring or acting on safety conditions.
        ENABLED: The safety mechanism is fully operational and actively engaged in monitoring or controlling its designated safety parameters.
    """

    ERROR = 0
    NON_INITIALIZED = 1
    DISABLED = 2
    ENABLED = 3


class RecoveryActionState(Enum):
    DO_NOT_PERFORM = 0
    TO_PERFORM = 1


class RecoveryAction:
    """
    Represents a specific recovery action within the safety management system.

    Each instance of this class represents a discrete recovery action that can be invoked in response to a fault condition.
    The class encapsulates the basic information necessary to identify and describe a recovery action, making it
    easier to manage and invoke these actions within the system.

    Attributes:
        name (str): The name of the recovery action, used to identify and reference the action within the system.
    """

    def __init__(self, name: Any, params: Any, recovery_action: Any) -> None:
        """
        Initializes a new instance of the RecoveryAction with a specific name.

        This constructor sets the name of the recovery action, which is used to identify and manage the action within
        the safety management system. The name should be unique and descriptive enough to clearly indicate the action's purpose.

        Args:
            name (str): The name of the recovery action, providing a unique identifier for the action within the system.
        """
        self.name: Any = name
        self.params: dict = params
        self.rec_fun: Any = recovery_action
        self.current_status: RecoveryActionState = RecoveryActionState.DO_NOT_PERFORM


class Symptom:
    """
    Represents a symptom condition within the system, potentially leading to a fault.

    symptoms are conditions identified as precursors to faults, allowing preemptive actions
    to avoid faults altogether or mitigate their effects.

    Attributes:
        name (str): The name of the symptom.
        sm_name (str): The name of the safety mechanism associated with this symptom.
        module (SafetyComponent): The module where the safety mechanism is defined.
        parameters (dict): Configuration parameters for the symptom.
        recover_actions (Callable | None): The recovery action to execute if this symptom is triggered.
        state (FaultState): The current state of the symptom.
        sm_state (SMState): The operational state of the associated safety mechanism.

    Args:
        name (str): The name identifier of the symptom.
        sm_name (str): The safety mechanism's name associated with this symptom.
        module: The module object where the safety mechanism's logic is implemented.
        parameters (dict): A dictionary of parameters relevant to the symptom condition.
        recover_actions (Callable | None, optional): A callable that executes recovery actions for this symptom. Defaults to None.
    """

    def __init__(
        self,
        name: str,
        sm_name: str,
        module: "SafetyComponent",  # type: ignore
        parameters: dict,
    ) -> None:
        self.name: str = name
        self.sm_name: str = sm_name
        self.module: "SafetyComponent" = module
        self.state: FaultState = FaultState.NOT_TESTED
        self.parameters: dict = parameters
        self.sm_state = SMState.NON_INITIALIZED


class Fault:
    """
    Represents a fault within the safety management system.

    A fault is a condition that has been identified as an error or failure state within
    the system, requiring notification and possibly recovery actions.

    Attributes:
        name (str): The name of the fault.
        state (FaultState): The current state of the fault.
        related_symptoms (list): A list of symptoms related to this fault.
        level (int): The severity level of the fault for notification purposes.

    Args:
        name (str): The name identifier of the fault.
        related_symptoms (list): List of names of safety mechanism that can trigger this fault.
        level (int): The severity level assigned to this fault for notification purposes.
    """

    def __init__(self, name: str, related_symptoms: list, level: int):
        self.name: str = name
        self.state: FaultState = FaultState.NOT_TESTED
        self.previous_val = FaultState.NOT_TESTED
        self.related_symptoms: list = related_symptoms
        self.level: int = level


class RecoveryResult(NamedTuple):
    """
    A named tuple that encapsulates the result of a recovery action.

    Attributes:
        changed_sensors (Dict[str, str]): A dictionary mapping sensor names to their new states.
        changed_actuators (Dict[str, str]): A dictionary mapping actuator names to their new states.
        notifications (List[str]): A list of notifications that provide information about manual actions needed.
    """

    changed_sensors: Dict[str, str]
    changed_actuators: Dict[str, str]
    notifications: List[str]
