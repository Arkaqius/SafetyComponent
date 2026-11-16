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

from collections.abc import Iterable
from functools import wraps
from time import monotonic
from typing import (
    Type,
    Any,
    Dict,
    get_origin,
    get_args,
    Callable,
    Optional,
    NamedTuple,
)
from enum import Enum

import appdaemon.plugins.hass.hassapi as hass

from components.core.common_entities import CommonEntities
from components.core.derivative_monitor import DerivativeMonitor
from components.core.event_bus import EventBus
from components.core.lifecycle import CancellationKind, LifecycleScope
from components.core.mqtt_entity_manager import MqttEntityManager
from components.core.types_common import (
    ExecutionOutcome, OutcomeKind, FaultState, Symptom, RecoveryAction, SMState,
)

UNAVAILABLE_NUMERIC_STATES = frozenset({"", "none", "unknown", "unavailable"})

NO_NEEDED = False

_COMPONENT_REGISTRY: Dict[str, Type["SafetyComponent"]] = {}


def register_safety_component(
    cls: Type["SafetyComponent"],
) -> Type["SafetyComponent"]:
    """Register a safety component class by its component_name."""
    name = getattr(cls, "component_name", None)
    if not name or name == "UNKNOWN":
        raise ValueError("SafetyComponent.component_name must be set for registration")
    if name in _COMPONENT_REGISTRY:
        raise ValueError(f"Safety component '{name}' is already registered")
    _COMPONENT_REGISTRY[name] = cls
    return cls


def get_registered_components() -> Dict[str, Type["SafetyComponent"]]:
    """Return a copy of the registered safety components."""
    return dict(_COMPONENT_REGISTRY)


def clear_registered_components() -> None:
    """Clear the safety component registry (primarily for tests)."""
    _COMPONENT_REGISTRY.clear()


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
    _evaluation_depth: int = 0
    _evaluation_success: bool = True

    def __init__(
        self,
        hass_app: hass.Hass,
        common_entities: CommonEntities,
        event_bus: EventBus,
        mqtt_entities: MqttEntityManager,
    ) -> None:
        """
        Initialize the safety component.

        :param hass_app: The Home Assistant application instance.
        """
        self.hass_app: hass.Hass = hass_app
        self.common_entities: CommonEntities = common_entities
        self.event_bus: EventBus = event_bus
        self.mqtt_entities: MqttEntityManager = mqtt_entities
        self.symptom_states: dict[str, FaultState] = {}
        runtime_id = getattr(hass_app, "runtime_id", None)
        self.scope = LifecycleScope(
            self.component_name, runtime_id=runtime_id if isinstance(runtime_id, str) else None,
            enabled=True,
        )
        self.scope.start()
        self.init_common_data()
        self.derivative_monitor = DerivativeMonitor(hass_app, mqtt_entities)

    def init_common_data(self) -> None:
        # Initialize dictionaries that need to be unique to each instance
        self.safety_mechanisms: dict = {}
        self.debounce_states: dict = {}

    def start(self) -> None:
        """Start owned source registrations; mechanisms remain explicitly enabled."""
        self.scope.start()
        self.scope.set_enabled(True)
        for mechanism in self.safety_mechanisms.values():
            mechanism.start()

    def stop(self) -> None:
        """Fence ingress and all child qualification without clearing assertions."""
        self.scope.stop()
        for mechanism in self.safety_mechanisms.values():
            mechanism.stop()

    def own_state_listener(
        self, key: str, callback: Callable[..., Any], entity: str, **kwargs: Any,
    ) -> Any:
        """Register one parent-owned source shared by its child mechanisms."""
        self.scope.declare(
            key, CancellationKind.STATE,
            lambda cb: self.hass_app.listen_state(cb, entity, **kwargs),
            callback, self.hass_app.cancel_listen_state,
        )
        return self.scope.handle(key)

    def own_event_listener(
        self, key: str, callback: Callable[..., Any], event: str, **kwargs: Any,
    ) -> Any:
        """Own raw adapter metadata and connection events across generations."""
        self.scope.declare(
            key, CancellationKind.EVENT,
            lambda cb: self.hass_app.listen_event(cb, event, **kwargs),
            callback, self.hass_app.cancel_listen_event,
        )
        return self.scope.handle(key)

    def own_interval(
        self, key: str, callback: Callable[..., Any], start: Any, interval: float,
    ) -> Any:
        """Own one shared periodic sampler under a stable registration identity."""
        self.scope.declare(
            key, CancellationKind.TIMER,
            lambda cb: self.hass_app.run_every(cb, start, interval),
            callback, self.hass_app.cancel_timer,
        )
        return self.scope.handle(key)

    def own_timeout(
        self, channel: str, callback: Callable[..., Any], delay: float, **kwargs: Any,
    ) -> Any:
        """Own a parent qualification channel without duplicating domain timers."""
        return self.scope.schedule(
            channel, lambda cb: self.hass_app.run_in(cb, delay, **kwargs),
            callback, self.hass_app.cancel_timer,
        )

    def record_evaluation(self, *, success: bool = True) -> None:
        """Report one completed component evaluation to the application monitor."""
        if getattr(self, "_evaluation_depth", 0):
            self._evaluation_success = getattr(self, "_evaluation_success", True) and success
            return
        self._evaluation_serial = getattr(self, "_evaluation_serial", 0) + 1
        reporter = getattr(self.hass_app, "record_safety_evaluation", None)
        if callable(reporter):
            reporter(self.component_name, success=success)

    def execution_outcome(
        self, mechanism: Any, value: "SafetyMechanismResult",
    ) -> ExecutionOutcome:
        """Copy bounded domain evidence into an immutable internal result."""
        scope = getattr(mechanism, "scope", None)
        return ExecutionOutcome.from_result(
            mechanism.name, scope.generation if scope is not None else 0,
            monotonic(), value.result, evaluable=value.is_evaluable,
            kind=value.outcome_kind, reason=value.reason,
            runtime_id=scope.runtime_id if scope is not None else "",
            evidence=value.diagnostic_evidence or value.additional_info,
        )

    def observe_outcome(self, mechanism: Any, value: "SafetyMechanismResult") -> None:
        """Record current qualified evidence without adding debounce or applying HEAL."""
        scope = getattr(mechanism, "scope", None)
        if scope is None or scope.eligible:
            mechanism.last_outcome = self.execution_outcome(mechanism, value)

    def simulate(
        self, mechanism: Any, changes: dict[str, str], *, evaluator: Callable[..., Any] | None = None,
    ) -> ExecutionOutcome:
        """Evaluate an explicitly supported hypothetical kernel without live effects."""
        scope = getattr(mechanism, "scope", None)
        if not mechanism.isEnabled or (scope is not None and not scope.eligible):
            return self.execution_outcome(mechanism, SafetyMechanismResult(
                False, outcome_kind=OutcomeKind.DISABLED,
            ))
        predicate = getattr(evaluator or mechanism.callback, "__wrapped__", None)
        if predicate is None:
            return self.execution_outcome(mechanism, SafetyMechanismResult(
                False, is_evaluable=False, reason="simulation_unsupported",
            ))
        try:
            result = predicate(self, mechanism, changes)
            if not isinstance(result, SafetyMechanismResult):
                raise TypeError("Simulation requires typed domain evidence")
            return self.execution_outcome(mechanism, result)
        except Exception:
            return self.execution_outcome(mechanism, SafetyMechanismResult(
                False, is_evaluable=False, reason="simulation_failed",
            ))

    def record_symptom_observation(
        self, symptom_id: str, state: FaultState,
        additional_info: dict[str, Any] | None = None,
    ) -> None:
        """Report an unchanged qualified result without repeating fault actions."""

        self.event_bus.publish("evaluation_succeeded", symptom_id=symptom_id)
        self.event_bus.publish(
            "symptom_observed", symptom_id=symptom_id, state=state,
            additional_info=additional_info or {},
        )

    def get_symptoms_data(
        self, modules: dict, component_cfg: Any
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

    @classmethod
    def get_entity_dependencies(
        cls, component_cfg: Any
    ) -> list[dict[str, Any]]:
        """Declare Home Assistant entities consumed by this component."""

        return []

    def get_inactive_fault_names(self) -> set[str]:
        """Return configured fault definitions that do not apply at this site."""

        return set()

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

    def register_fm(self, fm: Any) -> None:
        """Deprecated: safety components now publish events via the EventBus."""
        self.hass_app.log(
            "register_fm is deprecated; use EventBus subscriptions instead.",
            level="WARNING",
        )

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
    def get_num_sensor_val(hass_app: hass.Hass, sensor_id: str) -> float | None:
        """Fetch and convert temperature from a sensor."""
        raw_value = hass_app.get_state(sensor_id)
        if raw_value is None or str(raw_value).strip().casefold() in UNAVAILABLE_NUMERIC_STATES:
            return None
        try:
            return float(raw_value)
        except (ValueError, TypeError) as e:
            hass_app.log(f"Conversion error: {e}", level="WARNING")
            return None

    @staticmethod
    def change_all_entities_state(
        entities: str | Iterable[str], state: str
    ) -> dict[str, str]:
        """Map one entity or an iterable of entities to an expected state."""
        entity_ids = [entities] if isinstance(entities, str) else list(entities)
        return {entity_id: state for entity_id in entity_ids}

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
            action: DebounceAction = (
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

    def _invalidate_evaluation(self, symptom_id: str) -> None:
        """Require fresh debounce evidence without clearing an active fault."""
        self.symptom_states[symptom_id] = FaultState.NOT_TESTED
        self.debounce_states[symptom_id] = DebounceState(0, False)
        self.event_bus.publish("evaluation_unavailable", symptom_id=symptom_id)

    def process_symptom(
        self,
        symptom_id: str,
        current_counter: int,
        pr_test: bool,
        additional_info: dict,
        debounce_limit: int = 2,
        diagnostic_evidence: dict[str, Any] | None = None,
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

        if not self.event_bus:
            self.hass_app.log("Event bus not initialized!", level="ERROR")
            return current_counter, False

        # Prepare retVal
        force_sm: bool = False
        debounce_result: DebounceResult = DebounceResult(
            action=DebounceAction.NO_ACTION, counter=current_counter
        )

        # Get current symptom state
        symptom_cur_state: FaultState = self.symptom_states.get(
            symptom_id, FaultState.NOT_TESTED
        )
        # Check if any actions is needed
        if (
            (pr_test and symptom_cur_state == FaultState.CLEARED)
            or (not pr_test and symptom_cur_state == FaultState.SET)
            or (symptom_cur_state == FaultState.NOT_TESTED)
        ):
            debounce_result = self._debounce(current_counter, pr_test, debounce_limit)

            if debounce_result.action == DebounceAction.symptom_SET:
                # Call Fault Manager to set symptom
                self.symptom_states[symptom_id] = FaultState.SET
                self.event_bus.publish(
                    "symptom",
                    symptom_id=symptom_id,
                    state=FaultState.SET,
                    additional_info=additional_info,
                    diagnostic_evidence=diagnostic_evidence,
                )
                self.hass_app.log(
                    f"symptom {symptom_id} with {additional_info} was set",
                    level="DEBUG",
                )
                force_sm = False
            elif debounce_result.action == DebounceAction.symptom_HEALED:
                # Call Fault Manager to heal symptom
                self.symptom_states[symptom_id] = FaultState.CLEARED
                self.event_bus.publish(
                    "symptom",
                    symptom_id=symptom_id,
                    state=FaultState.CLEARED,
                    additional_info=additional_info,
                    diagnostic_evidence=diagnostic_evidence,
                )
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
            self.record_symptom_observation(
                symptom_id, symptom_cur_state, additional_info
            )

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
    """Normalize legacy predicates while keeping their domain debounce unchanged."""

    @wraps(func)
    def safety_mechanism_wrapper(
        self: "SafetyComponent", sm: Any,
        entities_changes: dict[str, str] | None = None,
    ) -> bool:
        """Evaluate once and recheck owner generation before any live application."""
        live = entities_changes is None
        scope = getattr(sm, "scope", None)
        generation = scope.generation if scope is not None else 0
        if not sm.isEnabled or (scope is not None and not scope.eligible):
            return False
        success = False
        try:
            result = func(self, sm, entities_changes)
            outcome = self.execution_outcome(sm, result)
            success = True
            if not live:
                return bool(outcome.result)
            if scope is not None and (
                not scope.eligible or scope.generation != generation
            ):
                return False
            sm.last_outcome = outcome
            if not outcome.is_evaluable:
                self._invalidate_evaluation(sm.name)
                self.event_bus.publish("evaluation_succeeded", symptom_id=sm.name)
                return False
            self.event_bus.publish("evaluation_succeeded", symptom_id=sm.name)
            if scope is not None and (
                not scope.eligible or scope.generation != generation
            ):
                return False
            current = self.debounce_states[sm.name]
            counter, force = self.process_symptom(
                symptom_id=sm.name, current_counter=current.debounce,
                pr_test=result.result, additional_info=result.additional_info,
                debounce_limit=sm.sm_args.get("debounce_limit", 2),
                diagnostic_evidence=result.diagnostic_evidence,
            )
            if scope is not None and (
                not scope.eligible or scope.generation != generation
            ):
                return False
            self.debounce_states[sm.name] = DebounceState(counter, force)
            if force:
                delay = sm.sm_args.get("re_eval_delay_seconds", 30)
                arguments = dict(sm_method=func.__name__, sm_name=sm.name,
                                 entities_changes=None)
                if scope is None:
                    self.hass_app.run_in(self.sm_recalled, delay, **arguments)
                else:
                    sm.run_in("debounce", self.sm_recalled, delay, **arguments)
            elif scope is not None:
                scope.cancel("timer:debounce")
            return result.result
        except Exception:
            success = False
            if live and (scope is None or (
                scope.eligible and scope.generation == generation
            )):
                sm.last_outcome = ExecutionOutcome(
                    sm.name, generation, monotonic(), OutcomeKind.UNEVALUABLE,
                    "evaluation_failed",
                )
                self.event_bus.publish("evaluation_exception", symptom_id=sm.name)
                self._invalidate_evaluation(sm.name)
            raise
        finally:
            if live:
                self.record_evaluation(success=success)

    safety_mechanism_wrapper.__dict__["manages_evaluation"] = True
    return safety_mechanism_wrapper

class SafetyMechanismResult(NamedTuple):
    result: bool
    additional_info: Optional[dict[str, Any]] = None
    is_evaluable: bool = True
    diagnostic_evidence: Optional[dict[str, Any]] = None
    outcome_kind: OutcomeKind | None = None
    reason: str = ""


def evaluation_entry(func: Callable[..., Any]) -> Callable[..., Any]:
    """Report one owner evaluation across nested timer, source and batch paths."""
    @wraps(func)
    def wrapped(self: SafetyComponent, *args: Any, **kwargs: Any) -> Any:
        outer = getattr(self, "_evaluation_depth", 0) == 0
        if outer:
            self._evaluation_success = True
        self._evaluation_depth = getattr(self, "_evaluation_depth", 0) + 1
        success = False
        try:
            result = func(self, *args, **kwargs)
            success = True
            return result
        except Exception:
            if outer:
                for mechanism in self.safety_mechanisms.values():
                    if mechanism.isEnabled:
                        self.observe_outcome(mechanism, SafetyMechanismResult(
                            False, is_evaluable=False, reason="evaluation_failed",
                        ))
            raise
        finally:
            self._evaluation_depth -= 1
            if outer:
                self.record_evaluation(success=success and self._evaluation_success)
    return wrapped


def qualified_safety_mechanism_decorator(func: Callable[..., Any]) -> Callable[..., Any]:
    """Normalize already-qualified domain results without introducing debounce."""
    @wraps(func)
    def wrapped(
        self: SafetyComponent, mechanism: Any,
        entities_changes: dict[str, str] | None = None, *args: Any, **kwargs: Any,
    ) -> bool:
        scope = getattr(mechanism, "scope", None)
        if not mechanism.isEnabled or (scope is not None and not scope.eligible):
            return False
        generation = scope.generation if scope is not None else 0

        @evaluation_entry
        def live_entry(owner: SafetyComponent) -> bool:
            value = func(owner, mechanism, entities_changes, *args, **kwargs)
            if not isinstance(value, SafetyMechanismResult):
                raise TypeError("Qualified evaluation requires typed domain evidence")
            if scope is None or (scope.eligible and scope.generation == generation):
                owner.observe_outcome(mechanism, value)
            return value.result

        if entities_changes is not None:
            value = func(self, mechanism, entities_changes, *args, **kwargs)
            return value.result
        return live_entry(self)
    wrapped.__dict__["manages_evaluation"] = True
    return wrapped
