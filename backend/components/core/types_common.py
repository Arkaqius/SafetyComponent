"""
Module: types_enums.py

This module defines enumeration types used throughout the Safety Functions application,
particularly within the Home Assistant-based safety management system. These enums
provide internal symptom/response events (FaultState) and safety mechanism
enablement states (SMState). Fault evaluation status and activation live in
``FaultEvaluation``.

Enums:
- FaultState: Enumerates qualified symptom and fault-response events; it is not
  the published fault evaluation status.
- SMState: Defines the operational states of Safety Mechanisms (SMs), offering insight
  into the activity and readiness of these mechanisms.

Usage:
Import the necessary enums into your module to leverage these predefined states for
fault management and safety mechanism state tracking. This centralizes state definitions,
facilitating easier maintenance and updates.
"""

from enum import Enum
from typing import TYPE_CHECKING, Any, NamedTuple, Dict, List

from components.core.fault_state_policy import (
    FaultCategory,
    FaultEvaluation,
    PRIORITY_PROFILES,
    PriorityProfile,
)

if TYPE_CHECKING:
    from components.safetycomponents.core.safety_component import SafetyComponent


class FaultState(Enum):
    """
    Represents qualified symptom and fault-response events.

    Attributes:
        NOT_TESTED: Symptom has not yet produced a qualified result.
        SET: Qualified positive symptom or activation response event.
        CLEARED: Qualified negative symptom or recovery response event.
        SHADOWED: Response-withdrawal event for an active fault.
    """

    NOT_TESTED = 0
    SET = 1
    CLEARED = 2
    SHADOWED = 3


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
    AWAITING_CONFIRMATION = 2
    EXECUTING = 3
    CONFIRMED = 4
    FAILED = 5
    TIMED_OUT = 6


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
        friendly_name (str): Human-readable fault name used in user interfaces.
        evaluation (FaultEvaluation): The current evaluation and active condition.
        related_symptoms (list): A list of symptoms related to this fault.
        level (int): The severity level of the fault for notification purposes.
        shadows (list[str]): A list of fault names that should be shadowed when this fault is set.

    Args:
        name (str): The name identifier of the fault.
        related_symptoms (list): List of names of safety mechanism that can trigger this fault.
        level (int): The severity level assigned to this fault for notification purposes.
        shadows (list[str] | None): Faults to shadow when this fault is active.
        friendly_name (str | None): Human-readable name shown to users.
    """

    def __init__(
        self,
        name: str,
        related_symptoms: list,
        level: int,
        shadows: list[str] | None = None,
        friendly_name: str | None = None,
        category: FaultCategory = FaultCategory.H,
        related_symptom_ids: list[str] | None = None,
    ):
        if level not in PRIORITY_PROFILES:
            raise ValueError("Fault priority must be one of levels 1..4")
        self.name: str = name
        self.friendly_name: str = friendly_name or name
        self.related_symptoms: list = related_symptoms
        self.related_symptom_ids: tuple[str, ...] = tuple(related_symptom_ids or ())
        self.level: int = level
        self.shadows: list[str] = list(shadows or [])
        self.category: FaultCategory = FaultCategory(category)
        self.priority_profile: PriorityProfile = PRIORITY_PROFILES[level]
        self.evaluation: FaultEvaluation = FaultEvaluation()


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
    instruction: str = ""
    execution_policy: str = "automatic"
    reason: str = ""
    source: str = ""
    valid_until: str = ""
    confirmation_timeout_seconds: int = 120
