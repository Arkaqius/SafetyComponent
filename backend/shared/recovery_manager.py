"""
Recovery Manager Module for Home Assistant Safety System

This module defines the RecoveryManager class, a central component of a safety management system designed to handle the recovery process from fault conditions. 
The RecoveryManager oversees executing recovery actions in response to detected faults, playing a pivotal role in maintaining the operational integrity and safety of the system.

Overview: The RecoveryManager is built with flexibility in mind, enabling it to manage a wide array of fault conditions through customizable recovery actions. 
Each recovery action is encapsulated as a callable function, which can be dynamically invoked by the RecoveryManager along with relevant context or parameters necessary for addressing specific faults.

Key Features:

Dynamic Recovery Action Execution: Allows for the invocation of any callable as a recovery action, offering the flexibility to implement a variety of recovery strategies tailored to specific fault scenarios.
Context-Aware Fault Mitigation: Supports passing additional information to recovery actions, enabling context-aware processing and more effective fault mitigation strategies.
Simplified Fault Recovery Interface: Provides a straightforward method (recovery) for triggering recovery actions, simplifying the integration of the RecoveryManager into larger safety management systems.
Integration with Fault Tagging: Uses the faulttag feature to uniquely identify fault instances during recovery actions. This ensures that notifications, recovery, and fault tracking are handled consistently 
across the system, preventing confusion and ensuring coherent management of fault states.
Usage: The RecoveryManager is intended to be used within larger safety management or fault handling systems where specific recovery actions are defined for various types of faults. By encapsulating recovery 
logic within callable functions and associating them with particular fault conditions, system designers can create a comprehensive fault recovery framework capable of addressing a broad spectrum of operational anomalies.

This module's approach to fault recovery empowers developers to construct robust and adaptable safety mechanisms, enhancing the resilience and reliability of automated systems. The faulttag feature helps uniquely identify each fault scenario, aiding in efficient fault resolution and ensuring accurate system state tracking throughout the recovery process.
"""

from typing import Any, Optional
import appdaemon.plugins.hass.hassapi as hass  # type: ignore
from shared.types_common import (
    RecoveryAction,
    Symptom,
    SMState,
    FaultState,
    Fault,
    RecoveryActionState,
    RecoveryResult,
)
from shared.common_entities import CommonEntities
from shared.fault_manager import FaultManager
from shared.notification_manager import NotificationManager


class RecoveryManager:
    """
    Manages the recovery processes for faults within the safety management system.

    This class is responsible for executing recovery actions associated with faults. It acts upon
    the specified recovery actions by invoking callable functions designed to mitigate or resolve
    the conditions leading to the activation of faults. The RecoveryManager plays a critical role
    in the system's ability to respond to and recover from fault conditions, thereby maintaining
    operational integrity and safety.

    The RecoveryManager is designed to be flexible, allowing recovery actions to be defined as
    callable functions with associated additional information, facilitating customized recovery
    strategies for different fault scenarios.
    """

    def __init__(
        self,
        hass_app: hass.Hass,
        fm: FaultManager,
        recovery_actions: dict,
        common_entities: CommonEntities,
        nm: NotificationManager,
    ) -> None:
        """
        Initializes the RecoveryManager with the necessary application context and recovery configuration.

        The constructor sets up the RecoveryManager by assigning the Home Assistant application context and
        a dictionary that contains configuration details for various recovery actions. This configuration
        dictionary is expected to map fault identifiers or types to specific callable functions that
        represent the recovery actions for those faults.

        Args:
            hass_app (hass.Hass): The Home Assistant application context, providing access to system-wide
                functionality and enabling the RecoveryManager to interact with other components and entities
                within the Home Assistant environment.
            fm (FaultManager): The FaultManager instance for managing fault conditions.
            recovery_actions (dict): A dictionary mapping fault names to their corresponding recovery actions.
            common_entities (CommonEntities): An instance containing common entities required for recovery actions.
            nm (NotificationManager): The NotificationManager instance for managing notifications related to recovery actions.

        This setup allows the RecoveryManager to dynamically execute the appropriate recovery actions
        based on the faults detected within the system, promoting a flexible and responsive fault management
        framework.
        """
        self.hass_app: hass.Hass = hass_app
        self.recovery_actions: dict[str, RecoveryAction] = recovery_actions
        self.common_entities: CommonEntities = common_entities
        self.fm: FaultManager = fm
        self.nm: NotificationManager = nm

        self._init_all_rec_entities()

    def _init_all_rec_entities(self) -> None:
        for _, recovery_actions in self.recovery_actions.items():
            self._set_rec_entity(recovery_actions)

    def _isRecoveryConflict(self, symptom: Symptom) -> bool:
        """
        Determines if there is a conflict between the given symptom's recovery actions and existing faults.

        This method checks whether executing the recovery actions for a given symptom would
        conflict with any existing faults. It considers the priority of the faults and matching
        recovery actions to ensure that the recovery process does not introduce new issues.

        Args:
            symptom (symptom): The symptom object representing the fault to check for conflicts.

        Returns:
            bool: True if a conflict exists, False otherwise.
        """
        matching_actions: list[str] = self._get_matching_actions(symptom)

        if matching_actions:
            rec_fault: Fault | None = self.fm.found_mapped_fault(
                symptom.name, symptom.sm_name
            )
            if rec_fault:
                rec_fault_prio: int = rec_fault.level
                conflict_status: bool = self._check_conflict_with_matching_actions(
                    matching_actions, rec_fault_prio, symptom
                )
                self.hass_app.log(
                    f"Conflict status for {symptom} is {conflict_status}", level="DEBUG"
                )
                return conflict_status

        return False

    def _get_matching_actions(self, symptom: Symptom) -> list[str]:
        """
        Retrieves a list of recovery action names that match the given symptom.

        This method searches for and returns the names of recovery actions that correspond
        to the given symptom. It is used to identify potential conflicts or applicable
        recovery strategies based on the symptom's characteristics.

        Args:
            symptom (symptom): The symptom object representing the fault to match.

        Returns:
            list[str]: A list of matching recovery action names.
        """
        return [
            name
            for name, action in self.recovery_actions.items()
            if action.name in self.recovery_actions[symptom.name].name
        ]

    def _check_conflict_with_matching_actions(
        self, matching_actions: list[str], rec_fault_prio: int, symptom: Symptom
    ) -> bool:
        """
        Checks for conflicts between the given symptom's recovery actions and existing faults based on priorities.

        This method evaluates whether the recovery actions for a given symptom would conflict with
        other existing faults by comparing their priorities. It ensures that higher-priority faults
        are not adversely affected by the recovery actions for lower-priority faults.

        Args:
            matching_actions (list[str]): A list of matching recovery action names.
            rec_fault_prio (int): The priority of the recovery fault.
            symptom (Symptom): The symptom object representing the fault to check for conflicts.

        Returns:
            bool: True if a conflict exists, False otherwise.
        """
        for found_symptom_name in matching_actions:
            # Skip the current symptom to avoid self-comparison
            if found_symptom_name == symptom.name:
                continue

            found_symptom: Symptom = self.fm.symptoms[found_symptom_name]
            if found_symptom:
                found_fault: Fault | None = self.fm.found_mapped_fault(
                    found_symptom.name, found_symptom.sm_name
                )
                if found_fault and found_fault.level > rec_fault_prio:
                    return True

        return False

    def _perform_recovery(
        self,
        symptom: Symptom,
        notifications: list,
        entities_changes: dict[str, str],
        fault_tag: str,
    ) -> None:
        """
        Executes the recovery actions for the given symptom, including notifications and entity changes.

        This method performs the actual recovery process for a given symptom by executing the
        associated recovery actions. It handles sending notifications and making necessary changes
        to system entities to resolve the fault condition.

        Args:
            symptom (symptom): The symptom object representing the fault to recover from.
            notifications (list): A list of notifications to send as part of the recovery process.
            entities_changes (dict[str, str]): A dictionary mapping entity names to their new values as part of the recovery process.
        """
        rec: RecoveryAction | None = self._find_recovery(symptom.name)
        if rec:
            rec.current_status = RecoveryActionState.TO_PERFORM
            self._set_rec_entity(rec)
            # Set entitity actions as recovery
            for entity, value in entities_changes.items():
                try:
                    self.hass_app.set_state(entity, state=value)
                except Exception as err:
                    self.hass_app.log(
                        f"Exception during setting {entity} to {value} value. {err}",
                        level="ERROR",
                    )
            for notification in notifications:
                fault: Fault | None = self.fm.found_mapped_fault(
                    symptom.name, symptom.sm_name
                )
                if fault:
                    self.nm._add_recovery_action(notification, fault_tag)
        else:
            self.hass_app.log(
                f"Recovery action for {symptom.name} was not found!", level="ERROR"
            )

    def _find_recovery(self, symptom_name: str) -> RecoveryAction | None:
        """
        Finds and returns the recovery action associated with the given symptom name.

        This method searches for and retrieves the recovery action that corresponds to the
        specified symptom name. It is used to locate the appropriate recovery strategy
        for a given fault condition.

        Args:
            symptom_name (str): The name of the symptom to find the recovery action for.

        Returns:
            RecoveryAction | None: The recovery action associated with the symptom name, or None if not found.
        """
        for name, rec in self.recovery_actions.items():
            if name == symptom_name:
                return rec
        return None

    def _set_rec_entity(self, recovery: RecoveryAction) -> None:
        """
        Sets the state of the recovery entity in the Home Assistant context.

        This method updates the state of the specified recovery entity in the Home Assistant
        system. It is used to reflect the current status of the recovery process for monitoring
        and tracking purposes.

        Args:
            recovery (RecoveryAction): The recovery action to set the state for.
        """
        sensor_name: str = f"sensor.recovery_{recovery.name}".lower()
        sensor_value: str = str(recovery.current_status.name)
        self.hass_app.set_state(sensor_name, state=sensor_value)

    def _is_dry_test_failed(
        self, prefaul_name: str, entities_changes: dict[str, str]
    ) -> bool:
        """
        Runs a dry test to determine if the given entity changes will trigger new faults.

        This method performs a simulation (dry test) to check whether the proposed changes to
        system entities will cause new faults to be triggered. It ensures that recovery actions
        do not inadvertently introduce new issues.

        Args:
            prefaul_name (str): The name of the symptom to test.
            entities_changes (dict[str, str]): A dictionary mapping entity names to their new values to test.

        Returns:
            bool: True if the entity changes will trigger new faults, False otherwise.
        """
        for symptom_name, symptom_data in self.fm.get_all_symptom().items():
            if symptom_data.sm_state == SMState.ENABLED:
                # Force each sm to get state if possible
                sm_fcn = getattr(symptom_data.module, symptom_data.sm_name)
                isFaultTrigged = sm_fcn(
                    symptom_data.module.safety_mechanisms[symptom_data.name],
                    entities_changes,
                )
                if isFaultTrigged and symptom_name is not prefaul_name:
                    return True
        return False

    def recovery(self, symptom: Symptom, fault_tag) -> None:
        """
        Executes the appropriate recovery action for the given symptom.

        Args:
            symptom (Symptom): The symptom object representing the fault to recover from.
        """
        self.hass_app.log(
            f"Starting recovery process for symptom: {symptom.name}", level="DEBUG"
        )

        if symptom.state == FaultState.CLEARED:
            self.hass_app.log(
                f"Symptom {symptom.name} is in CLEARED state. Handling cleared state.",
                level="DEBUG",
            )
            self._handle_cleared_state(symptom)
            return

        potential_recovery_action: RecoveryResult | None = (
            self._get_potential_recovery_action(symptom)
        )
        if not potential_recovery_action:
            return

        if not self._validate_recovery_action(symptom, potential_recovery_action):
            return

        self.hass_app.log(
            f"Validation successful. Executing recovery action for symptom: {symptom.name}",
            level="DEBUG",
        )
        self._execute_recovery(symptom, potential_recovery_action, fault_tag)
        self.hass_app.log(
            f"Recovery process completed for symptom: {symptom.name}", level="DEBUG"
        )

    def _handle_cleared_state(self, symptom: Symptom) -> None:
        """Handles the cleared state of a symptom by clearing recovery actions."""
        self.hass_app.log(
            f"Clearing recovery actions for symptom: {symptom.name}", level="DEBUG"
        )
        self._recovery_clear(symptom)

    def _get_potential_recovery_action(
        self, symptom: Symptom
    ) -> Optional[RecoveryResult]:
        """Retrieves the potential recovery action for a given symptom."""
        if symptom.name not in self.recovery_actions:
            self.hass_app.log(
                f"No recovery actions defined for symptom: {symptom.name}",
                level="DEBUG",
            )
            return None

        self.hass_app.log(
            f"Retrieving potential recovery action for symptom: {symptom.name}",
            level="DEBUG",
        )
        potential_recovery_action: RecoveryAction = self.recovery_actions[symptom.name]
        potential_recovery_result: Optional[RecoveryResult] = (
            potential_recovery_action.rec_fun(
                self.hass_app,
                symptom,
                self.common_entities,
                **potential_recovery_action.params,
            )
        )

        if not potential_recovery_result:
            self.hass_app.log(
                f"No changes determined for recovery of symptom: {symptom.name}",
                level="DEBUG",
            )
        else:
            self.hass_app.log(
                f"Potential recovery result obtained for symptom: {symptom.name}",
                level="DEBUG",
            )

        return potential_recovery_result

    def _validate_recovery_action(
        self, symptom: Symptom, recovery_result: RecoveryResult
    ) -> bool:
        """Validates if the recovery action can be safely executed without conflicts."""
        self.hass_app.log(
            f"Validating potential recovery action for symptom: {symptom.name}",
            level="DEBUG",
        )

        if self._is_dry_test_failed(symptom.name, recovery_result.changed_sensors):
            self.hass_app.log(
                f"Recovery action for symptom {symptom.name} will trigger another fault. Aborting recovery.",
                level="DEBUG",
            )
            return False

        if self._isRecoveryConflict(symptom):
            self.hass_app.log(
                f"Recovery action for symptom {symptom.name} conflicts with existing faults. Aborting recovery.",
                level="DEBUG",
            )
            return False

        self.hass_app.log(
            f"Recovery action for symptom {symptom.name} validated successfully.",
            level="DEBUG",
        )
        return True

    def _execute_recovery(
        self, symptom: Symptom, recovery_result: RecoveryResult, fault_tag: str
    ) -> None:
        """Executes the recovery action for a given symptom."""
        self.hass_app.log(
            f"Executing recovery for symptom: {symptom.name}", level="DEBUG"
        )
        self._perform_recovery(
            symptom,
            recovery_result.notifications,
            recovery_result.changed_actuators,
            fault_tag,
        )
        self.hass_app.log(
            f"Recovery performed for symptom: {symptom.name}. Setting up listeners for changes.",
            level="DEBUG",
        )
        self._listen_to_changes(
            symptom,
            recovery_result.changed_sensors | recovery_result.changed_actuators,
        )
        self.hass_app.log(f"Listeners set for symptom: {symptom.name}", level="DEBUG")

    def _recovery_clear(self, symptom: Symptom) -> None:
        """
        Clears the recovery action for the given symptom.

        This method clears the internal register and updates the system state to indicate that
        the recovery action for the specified symptom has been completed and should no longer
        be performed.

        Args:
            symptom (symptom): The symptom object representing the fault to clear the recovery action for.
        """
        if symptom.name in self.recovery_actions:
            # Clear internal register
            self.recovery_actions[symptom.name].current_status = (
                RecoveryActionState.DO_NOT_PERFORM
            )
            # Set HA entity
            self._set_rec_entity(self.recovery_actions[symptom.name])

    def _listen_to_changes(self, symptom: Symptom, entities_changes: dict) -> None:
        """
        Sets up listeners for state changes in the specified entities to monitor recovery action completion.

        This method establishes listeners on the specified entities to detect when the state changes
        as part of the recovery process. It ensures that the system can respond to and track the completion
        of recovery actions.

        Args:
            symptom (symptom): The symptom object representing the fault being recovered from.
            entities_changes (dict): A dictionary mapping entity names to their new values to monitor.
        """
        for name in entities_changes:
            self.hass_app.listen_state(self._recovery_performed, name, symptom=symptom)

    def _recovery_performed(
        self, _: Any, __: Any, ___: Any, ____: Any, cb_args: dict
    ) -> None:
        """
        Callback function invoked when a recovery action is performed.

        This method is called when a state change is detected in one of the monitored entities,
        indicating that a recovery action has been performed. It clears the recovery action for
        the corresponding symptom.

        Args:
            _ (Any): Placeholder for the first callback argument (not used).
            __ (Any): Placeholder for the second callback argument (not used).
            ___ (Any): Placeholder for the third callback argument (not used).
            ____ (Any): Placeholder for the fourth callback argument (not used).
            cb_args (dict): A dictionary containing callback arguments, including the symptom to clear.
        """
        self._recovery_clear(cb_args["symptom"])
