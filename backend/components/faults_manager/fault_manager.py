"""
Fault Management Module for Home Assistant Safety System

This module defines the core components and logic necessary for managing faults and symptoms within a Home Assistant-based safety system. It facilitates the detection, tracking, and resolution of fault conditions, integrating closely with safety mechanisms to proactively address potential issues before they escalate into faults.

Classes:

symptom: Represents symptom conditions that are potential precursors to faults.
Fault: Represents faults within the system, which are conditions requiring attention.
FaultManager: Manages faults and symptoms, orchestrating detection and response.
The module supports a many-to-one mapping of symptoms to faults, allowing multiple symptom conditions to contribute to or influence the state of a single fault. This design enables a nuanced and responsive fault management system capable of handling complex scenarios and dependencies within the safety system architecture.

Primary functionalities include:

Initializing and tracking the states of faults and symptoms based on system configuration and runtime observations.
Dynamically updating fault states in response to changes in associated symptom conditions.
Executing defined recovery actions and notifications as part of the fault resolution process.
Generating a stable faulttag for each fault to identify and manage notifications and recovery actions associated with specific faults.
The faulttag feature is used across the system to create a stable identifier for each fault by hashing the fault name. This keeps multiple symptom contributions for the same fault correlated to one notification and recovery flow.

This module is integral to the safety system's ability to maintain operational integrity and respond effectively to detected issues, ensuring a high level of safety and reliability.

Note: This module is designed for internal use within the Home Assistant safety system and relies on configurations and interactions with other system components, including safety mechanisms and recovery action definitions.
"""

import hashlib
from typing import Any, Optional

import appdaemon.plugins.hass.hassapi as hass

from components.core.types_common import FaultState, SMState, Symptom, Fault
from components.core.event_bus import EventBus
from components.core.mqtt_entity_manager import MqttEntityManager
from components.core.fault_state_policy import FaultEvaluation, FaultEvaluationStatus


SYSTEM_STATE_BY_FAULT_LEVEL = {
    0: "no_faults",
    1: "emergency",
    2: "hazard",
    3: "warning",
    4: "information",
}


class FaultManager:
    """
    Manages the fault and symptom conditions within the safety management system.

    This includes initializing fault and symptom objects, enabling symptoms, setting and
    clearing fault states, and managing notifications and recovery actions associated with faults.

    Attributes:
        notify_man (NotificationManager): The manager responsible for handling notifications.
        recovery_man (RecoveryManager): The manager responsible for executing recovery actions.
        faults (dict[str, Fault]): A dictionary of fault objects managed by this manager.
        symptoms (dict[str, symptom]): A dictionary of symptom objects managed by this manager.
        sm_modules (dict): A dictionary mapping module names to module objects containing safety mechanisms.

    Args:
        notify_man (NotificationManager): An instance of the NotificationManager.
        recovery_man (RecoveryManager): An instance of the RecoveryManager.
        sm_modules (dict): A dictionary mapping module names to loaded module objects.
        symptom_dict (dict): A dictionary with symptom configurations.
        fault_dict (dict): A dictionary with fault configurations.
    """

    def __init__(
        self,
        hass: hass,
        sm_modules: dict,
        symptom_dict: dict,
        fault_dict: dict,
        event_bus: EventBus,
        mqtt_entities: MqttEntityManager,
    ) -> None:
        """
        Initialize the Fault Manager.

        :param config_path: Path to the YAML configuration file.
        """
        self.faults: dict[str, Fault] = fault_dict
        self.symptoms: dict[str, Symptom] = symptom_dict
        self.sm_modules: dict = sm_modules
        self.hass: hass.Hass = hass
        self.event_bus = event_bus
        self.mqtt_entities = mqtt_entities
        self._symptom_contexts: dict[str, dict[str, str]] = {}

    def get_fault_evaluation(self, fault_id: str) -> FaultEvaluation:
        """Return the authoritative fault-owned evaluation."""

        return self.faults[fault_id].evaluation

    def _publish_fault(self, fault: Fault, attributes: dict | None = None) -> None:
        """Publish evaluation status and independent activation/shadow axes."""

        entity_id = "sensor.fault_" + fault.name
        current_attributes = (
            attributes if attributes is not None else self._get_entity_attributes(entity_id)
        )
        payload = dict(current_attributes) if isinstance(current_attributes, dict) else {}
        payload.update(
            active=fault.evaluation.active,
            shadowed_by=sorted(fault.evaluation.shadowed_by),
            latched=fault.evaluation.latched,
        )
        self._set_internal_entity(entity_id, fault.evaluation.status.value, payload)

    def mark_evaluation_unavailable(self, symptom_id: str) -> None:
        """Record a failed or invalid evaluation without treating it as clear."""

        symptom = self.symptoms[symptom_id]
        fault = self.found_mapped_fault(symptom_id, symptom.sm_name)
        if fault is not None:
            fault.evaluation.mark_unavailable(symptom_id)
            self._publish_fault(fault)

    def handle_symptom_event(
        self,
        *,
        symptom_id: str,
        state: FaultState,
        additional_info: Optional[dict] = None,
        **_: Any,
    ) -> None:
        """Handle symptom events emitted by safety components."""
        if state == FaultState.SET:
            self.set_symptom(symptom_id, additional_info)
        elif state == FaultState.CLEARED:
            self.clear_symptom(symptom_id, additional_info or {})

    def init_safety_mechanisms(self) -> None:
        """
        Initializes safety mechanisms for each symptom condition.

        This function iterates over all symptoms defined in the system, initializing their respective
        safety mechanisms as specified by the safety mechanism's name (`sm_name`). It also sets the initial state
        of the symptoms to DISABLED if initialization is successful, or to ERROR otherwise.
        """
        for symptom_name, symptom_data in self.symptoms.items():
            result: bool = symptom_data.module.init_safety_mechanism(
                symptom_data.sm_name, symptom_name, symptom_data.parameters
            )
            if result:
                symptom_data.sm_state = SMState.DISABLED
            else:
                symptom_data.sm_state = SMState.ERROR

    def get_all_symptom(self) -> dict[str, Symptom]:
        """
        Function to return all register symptoms
        """
        return self.symptoms

    def enable_all_symptoms(self) -> None:
        """
        Enables all symptom safety mechanisms that are currently disabled.

        This method iterates through all symptoms stored in the system, and for each one that is in a DISABLED
        state, it attempts to enable the safety mechanism associated with it. The enabling function is dynamically
        invoked based on the `sm_name`. If the enabling operation is successful, the symptom state is updated
        to ENABLED, otherwise, it remains in ERROR.

        During the enabling process, the system also attempts to fetch and update the state of the safety mechanisms
        directly through the associated safety mechanism's function, updating the system's understanding of each
        symptom's current status.
        """
        for symptom_name, symptom_data in self.symptoms.items():
            if symptom_data.sm_state == SMState.DISABLED:
                self.enable_sm(sm_name=symptom_name, sm_state=SMState.ENABLED)

    def set_symptom(
        self, symptom_id: str, additional_info: Optional[dict] = None
    ) -> None:
        """
        Sets a symptom to its active state, indicating a potential fault condition.

        This method updates the symptom's state to SET, triggers any associated faults.

        Args:
            symptom_id (str): The identifier of the symptom to set.
            additional_info (dict | None, optional): Additional information or context for the symptom. Defaults to None.

        Raises:
            KeyError: If the specified symptom_id does not exist in the symptoms dictionary.
        """
        # Update symptom registry
        self.symptoms[symptom_id].state = FaultState.SET
        if additional_info:
            self._symptom_contexts[symptom_id] = {
                str(key): str(value) for key, value in additional_info.items()
            }

        # Call Related Fault
        self._set_fault(symptom_id, additional_info)

    def clear_symptom(self, symptom_id: str, additional_info: dict) -> None:
        """
        Clears a symptom state, indicating that the condition leading to a potential fault has been resolved.

        This method updates the specified symptom's state to CLEARED. It then attempts to clear any
        associated fault states if applicable. This is an important part of the fault management process,
        allowing the system to recover from potential issues and restore normal operation.

        The method also triggers notifications and recovery actions if specified for the cleared symptom,
        based on the provided additional information. This ensures that any necessary follow-up actions
        are taken to fully address and resolve the condition.

        Args:
            symptom_id (str): The identifier of the symptom to be cleared.
            additional_info (dict | None, optional): Additional information or context relevant to the symptom being cleared. Defaults to None.

        Raises:
            KeyError: If the specified symptom_id does not exist in the symptoms dictionary, indicating an attempt to clear an undefined symptom.
        """
        # Update symptom registry
        self.symptoms[symptom_id].state = FaultState.CLEARED
        self._symptom_contexts.pop(symptom_id, None)

        # Call Related Fault
        self._clear_fault(symptom_id, additional_info)

    def disable_symptom(self, symptom_id: str, additional_info: dict) -> None:
        """
        Retire evaluation evidence without asserting recovery of an active fault.
        """
        # Update symptom registry
        self.symptoms[symptom_id].state = FaultState.NOT_TESTED
        self._symptom_contexts.pop(symptom_id, None)

        self.mark_evaluation_unavailable(symptom_id)

    def check_symptom(self, symptom_id: str) -> FaultState:
        """
        Checks the current state of a specified symptom.

        This method returns the current state of the symptom identified by the given `symptom_id`.
        The state indicates whether the symptom is active (SET), has been cleared (CLEARED), or
        has not been tested (NOT_TESTED). This allows other parts of the system to query the status
        of symptoms and make decisions based on their current states.

        Args:
            symptom_id (str): The identifier of the symptom whose state is to be checked.

        Returns:
            FaultState: The current state of the specified symptom. Possible states are defined
                        in the FaultState Enum (NOT_TESTED, SET, CLEARED).

        Raises:
            KeyError: If the specified symptom_id does not exist in the symptoms dictionary, indicating
                    an attempt to check an undefined symptom.
        """
        return self.symptoms[symptom_id].state

    def _set_fault(self, symptom_id: str, additional_info: Optional[dict]) -> None:
        """
        Applies a qualified positive contribution to its owning fault.

        This private method is called when a symptom condition is detected (set) and aims to aggregate
        such symptom conditions to determine if a corresponding fault is active. It involves
        updating the fault's evaluation, triggering notifications, and executing any defined recovery actions
        specific to the symptom. The method aggregates several symptoms to evaluate the overall state of
        a related fault, ensuring comprehensive fault management.

        This process is central to the fault management system's ability to respond to potential issues
        proactively, allowing for the mitigation of faults through early detection and response.

        Args:
            symptom_id (str): The identifier of the symptom that triggered this fault setting process.
            additional_info (dict | None, optional): Additional information or context relevant to the fault being set. This information may be used in notifications and recovery actions. Defaults to None.

        Note:
            This method should only be called internally within the fault management system, as part of handling
            symptom conditions. It assumes that a mapping exists between symptoms and faults, allowing for
            appropriate fault state updates based on symptom triggers.
        """
        # Get sm name based on symptom_id
        sm_name: str = self.symptoms[symptom_id].sm_name

        # Collect all faults mapped from that symptom
        fault: Fault | None = self.found_mapped_fault(symptom_id, sm_name)
        if fault:
            fault.evaluation.observe(symptom_id, True)
            if not fault.evaluation.active:
                self._publish_fault(fault)
                return
            if self._is_fault_shadowed(fault.name):
                fault.evaluation.shadowed_by.update(
                    owner.name
                    for owner in self.faults.values()
                    if owner.evaluation.active and fault.name in owner.shadows
                )
                self._set_fault_shadowed(
                    fault, self.symptoms[symptom_id], additional_info
                )
                return

            # Generate a stable fault tag using the hash method
            fault_tag: str = self._generate_fault_tag(fault.name, additional_info)
            self.update_system_state_entity()  # Update the system state entity
            self.hass.log(f"Fault {fault.name} was set", level="DEBUG")

            # Determinate additional info
            info_to_send: dict | None
            if sm_name.startswith(("sm_ext_", "sm_entity_health_", "sm_iehm_")):
                info_to_send = self._aggregate_active_fault_info(fault)
            else:
                info_to_send = self._determinate_info(
                    "sensor.fault_" + fault.name,
                    additional_info,
                    FaultState.SET,
                )

            # Prepare the attributes for the state update
            attributes: dict = info_to_send if info_to_send else {}
            attributes["notification_tag"] = fault_tag

            # Set HA entity
            self._publish_fault(fault, attributes)

            self.event_bus.publish(
                "fault",
                fault_name=fault.name,
                fault_friendly_name=fault.friendly_name,
                level=fault.level,
                fault_state=FaultState.SET,
                additional_info=self._notification_info_from_merged(
                    additional_info, info_to_send
                ),
                fault_tag=fault_tag,
                symptom=self.symptoms[symptom_id],
                should_notify=True,
            )

            self._apply_shadowing(fault, self.symptoms[symptom_id], additional_info)

    def _aggregate_active_fault_info(self, fault: Fault) -> dict[str, str]:
        """Rebuild external-fault context from current active symptoms only."""

        values_by_key: dict[str, list[str]] = {}
        for symptom_id, symptom in self.symptoms.items():
            if symptom.state != FaultState.SET or not self._belongs_to_fault(
                fault, symptom_id, symptom.sm_name
            ):
                continue
            for key, value in self._symptom_contexts.get(symptom_id, {}).items():
                values = values_by_key.setdefault(key, [])
                if value not in values:
                    values.append(value)
        return {key: ", ".join(values) for key, values in values_by_key.items()}

    def _determinate_info(
            self, entity_id: str, additional_info: Optional[dict], fault_state: FaultState
        ) -> Optional[dict]:
            """
            Determine the information to send based on the current state and attributes of the entity,
            merging or clearing it with additional information provided based on the fault state.

            Args:
                entity_id (str): The Home Assistant entity ID to check.
                additional_info (Optional[dict]): Additional details to merge with or clear from the entity's current attributes.
                fault_state (FaultState): The state of the fault, either Set or Cleared.

            Returns:
                Optional[dict]: The updated information as a dictionary, or None if there is no additional info.
            """
            # If no additional info is provided, return None
            if not additional_info:
                return None

            # Retrieve the current state object for the entity
            current_attributes = self._get_entity_attributes(entity_id)
            if not current_attributes:
                return additional_info if fault_state == FaultState.SET else {}

            if fault_state == FaultState.SET:
                # Prepare the information to send by merging or updating current attributes with additional info
                info_to_send = current_attributes.copy()
                for key, value in additional_info.items():
                    if key in current_attributes and current_attributes[key] not in [
                        None,
                        "None",
                        "",
                    ]:
                        # If the current attribute exists and is not None, check if the value needs updating
                        current_value = current_attributes[key]
                        # If the current attribute is a comma-separated string, append new value if it's not already included
                        if isinstance(
                            current_value, str
                        ) and value not in current_value.split(", "):
                            current_value += ", " + value
                        info_to_send[key] = current_value
                    else:
                        # If the current attribute is None or does not exist, set it to the new value
                        info_to_send[key] = value
                return info_to_send
            elif fault_state == FaultState.CLEARED:
                # Clear specified keys from the current attributes by setting their values to empty strings
                info_to_send = current_attributes.copy()
                for key in additional_info.keys():
                    if key in info_to_send:
                        # Check if other values need to remain (if it was a list converted to string)
                        if ", " in info_to_send[key]:
                            # Remove only the specified value and leave others if any
                            new_values = [
                                val
                                for val in info_to_send[key].split(", ")
                                if val != additional_info[key]
                            ]
                            info_to_send[key] = ", ".join(new_values)
                        else:
                            # Set the key's value to an empty string instead of removing it
                            info_to_send[key] = ""
                    else:
                        # If the key does not exist, add it with an empty string value
                        info_to_send[key] = ""
                return info_to_send

            return None

    def _is_fault_shadowed(self, fault_name: str) -> bool:
        """
        Determines whether a fault is currently shadowed by another active fault.

        Args:
            fault_name (str): The fault name to check for shadowing.

        Returns:
            bool: True if any active fault shadows the provided fault name.
        """
        for active_fault in self.faults.values():
            if active_fault.evaluation.active and fault_name in active_fault.shadows:
                return True
        return False

    def _apply_shadowing(
        self,
        fault: Fault,
        symptom: Symptom,
        additional_info: Optional[dict],
    ) -> None:
        """
        Applies shadowing rules declared by the active fault.

        Args:
            fault (Fault): The active fault that may shadow others.
            symptom (Symptom): The symptom that triggered the fault.
            additional_info (dict | None): Additional info to use for notifications.
        """
        for shadowed_fault_name in fault.shadows:
            shadowed_fault = self.faults.get(shadowed_fault_name)
            if not shadowed_fault:
                self.hass.log(
                    f"Unknown shadowed fault '{shadowed_fault_name}' referenced by '{fault.name}'.",
                    level="WARNING",
                )
                continue
            was_shadowed = bool(shadowed_fault.evaluation.shadowed_by)
            shadowed_fault.evaluation.shadowed_by.add(fault.name)
            if shadowed_fault.evaluation.active and not was_shadowed:
                target_symptom = next(
                    (
                        candidate
                        for candidate in self.symptoms.values()
                        if candidate.name
                        in shadowed_fault.evaluation.active_contributors
                    ),
                    None,
                )
                if target_symptom is None:
                    continue
                self._set_fault_shadowed(
                    shadowed_fault,
                    target_symptom,
                    self._symptom_contexts.get(target_symptom.name),
                )
            elif shadowed_fault.evaluation.active:
                self._publish_fault(shadowed_fault)

    def _set_fault_shadowed(
        self,
        fault: Fault,
        symptom: Symptom,
        additional_info: Optional[dict],
    ) -> None:
        """
        Withdraws a shadowed fault's response without changing its evaluation.

        Args:
            fault (Fault): The fault to shadow.
            symptom (Symptom): The symptom that triggered the shadowing.
            additional_info (dict | None): Additional info to use for clearing notifications.
        """
        fault_tag: str = self._generate_fault_tag(fault.name, additional_info)
        self.update_system_state_entity()
        self.hass.log(f"Fault {fault.name} was shadowed", level="DEBUG")

        entity_id = "sensor.fault_" + fault.name
        info_to_send: Optional[dict] = None
        if additional_info:
            info_to_send = self._determinate_info(
                entity_id, additional_info, FaultState.CLEARED
            )
        if info_to_send is None:
            attributes = self._get_entity_attributes(entity_id)
        else:
            attributes = info_to_send

        self._publish_fault(fault, attributes)

        self.event_bus.publish(
            "fault",
            fault_name=fault.name,
            fault_friendly_name=fault.friendly_name,
            level=fault.level,
            fault_state=FaultState.SHADOWED,
            additional_info=additional_info,
            fault_tag=fault_tag,
            symptom=symptom,
            should_notify=True,
        )

    def _clear_fault(self, symptom_id: str, additional_info: dict) -> None:
        """
        Releases a fault after a triggering symptom has recovered.

        This private method is invoked when a symptom condition that previously contributed to setting a fault
        is resolved (cleared). It assesses the current state of related symptoms to determine whether the associated
        fault's activation can be released. This involves updating the evaluation and triggering appropriate
        notifications. The method ensures that faults are accurately reflected and managed based on the current status
        of their contributing symptom conditions.

        Clearing a fault involves potentially complex logic to ensure that all contributing factors are considered,
        making this method a critical component of the system's ability to recover and return to normal operation after
        a fault condition has been addressed.

        Args:
            symptom_id (str): The identifier of the symptom whose resolution triggers the clearing of the fault.
            additional_info (dict | None, optional): Additional information or context relevant to the fault being cleared. This information may be used to inform notifications. Defaults to None.

        Note:
            As with `_set_fault`, this method is designed for internal use within the fault management system. It assumes
            the existence of a logical mapping between symptoms and their corresponding faults, which allows the system
            to manage fault states dynamically based on the resolution of symptom conditions.
        """

        # Get sm name based on symptom_id
        sm_name: str = self.symptoms[symptom_id].sm_name

        # Collect all faults mapped from that symptom
        fault: Fault | None = self.found_mapped_fault(symptom_id, sm_name)

        if not fault:
            return

        evaluation = fault.evaluation
        was_active = evaluation.active
        was_shadowed = bool(evaluation.shadowed_by)
        evaluation.observe(symptom_id, False)

        entity_id = "sensor.fault_" + fault.name
        fault_tag: str = self._generate_fault_tag(fault.name, additional_info)
        has_active_related_symptoms = any(
            symptom.state == FaultState.SET
            for related_id, symptom in self.symptoms.items()
            if self._belongs_to_fault(fault, related_id, symptom.sm_name)
        )

        if has_active_related_symptoms:
            if sm_name.startswith(("sm_ext_", "sm_entity_health_")):
                info_to_send = self._aggregate_active_fault_info(fault)
            else:
                info_to_send = self._determinate_info(
                    entity_id, additional_info, FaultState.CLEARED
                )
            attributes = info_to_send if info_to_send else {}
            attributes["notification_tag"] = fault_tag

            self._publish_fault(fault, attributes)

            self.event_bus.publish(
                "fault",
                fault_name=fault.name,
                fault_friendly_name=fault.friendly_name,
                level=fault.level,
                fault_state=FaultState.SET,
                additional_info=self._notification_info_from_merged(
                    additional_info, info_to_send
                ),
                fault_tag=fault_tag,
                symptom=self.symptoms[symptom_id],
                should_notify=not evaluation.shadowed_by,
            )
            return

        if not has_active_related_symptoms and evaluation.active:
            # Another required contribution is unevaluable or recovery is pending.
            self._publish_fault(fault)
            return

        if not has_active_related_symptoms:
            self.hass.log(f"Fault {fault.name} was cleared", level="DEBUG")

            # Determinate additional info
            info_to_send = self._determinate_info(
                entity_id, additional_info, FaultState.CLEARED
            )

            # Prepare the attributes for the state update
            attributes = info_to_send if info_to_send else {}

            # Clear HA entity
            evaluation.shadowed_by.clear()
            self._publish_fault(fault, attributes)
            self.update_system_state_entity()  # Update the system state entity

            should_notify = was_active and not was_shadowed
            self.event_bus.publish(
                "fault",
                fault_name=fault.name,
                fault_friendly_name=fault.friendly_name,
                level=fault.level,
                fault_state=FaultState.CLEARED,
                additional_info=additional_info,
                fault_tag=fault_tag,
                symptom=self.symptoms[symptom_id],
                should_notify=should_notify,
            )
            self._restore_unshadowed_faults(fault.name)

    def _restore_unshadowed_faults(self, cleared_fault_name: str) -> None:
        """Re-present active evidence after the last shadow owner clears."""

        for candidate in self.faults.values():
            if cleared_fault_name not in candidate.evaluation.shadowed_by:
                continue
            candidate.evaluation.shadowed_by.discard(cleared_fault_name)
            self._publish_fault(candidate)
            if candidate.evaluation.shadowed_by or not candidate.evaluation.active:
                continue
            for symptom_id in sorted(candidate.evaluation.active_contributors):
                if (
                    symptom_id in self.symptoms
                    and self.symptoms[symptom_id].state == FaultState.SET
                ):
                    self._set_fault(
                        symptom_id, self._symptom_contexts.get(symptom_id)
                    )

    def check_fault(self, fault_id: str) -> FaultEvaluationStatus:
        """
        Checks the current evaluation status of a specified fault.

        This method returns the current evaluation status of the named fault.
        The status describes the most recent evaluation, while activation and
        shadowing remain separate fields on the fault-owned evaluation.

        Args:
            fault_id (str): The identifier of the fault whose state is to be checked.

        Returns:
            FaultEvaluationStatus: The current evaluation status.

        Raises:
            KeyError: If the specified fault_id does not exist in the faults dictionary,
                    indicating an attempt to check an undefined fault.
        """
        return self.faults[fault_id].evaluation.status

    def found_mapped_fault(self, symptom_id: str, sm_id: str) -> Optional[Fault]:
        """
        Finds the fault associated with a given symptom identifier.

        This private method searches through the registered faults to find the one that is
        mapped from the specified symptom. This mapping is crucial for the fault management
        system to correctly associate symptom conditions with their corresponding fault states.
        It ensures that faults are accurately updated based on the status of triggering symptoms.

        Note that this method assumes a many-to-one mapping between symptoms and faults. If multiple
        faults are found to be associated with a single symptom, this indicates a configuration or
        logical error within the fault management setup.

        Args:
            symptom_id (str): The identifier of the symptom for which the associated fault is sought.
            sm_id (str) : The identifier of the sm

        Returns:
            Optional[Fault]: The fault object associated with the specified symptom, if found. Returns
                            None if no associated fault is found or if multiple associated faults are detected,
                            indicating a configuration error.

        Note:
            This method is intended for internal use within the fault management system. It plays a critical
            role in linking symptom conditions to their corresponding faults, facilitating the automated
            management of fault states based on system observations and symptom activations.
        """

        # Collect all faults mapped from that symptom
        matching_objects: list[Fault] = [
            fault
            for fault in self.faults.values()
            if self._belongs_to_fault(fault, symptom_id, sm_id)
        ]

        # Validate there's exactly one occurrence
        if len(matching_objects) == 1:
            return matching_objects[0]

        elif len(matching_objects) > 1:
            self.hass.log(
                f"Error: Multiple faults found associated with symptom_id '{symptom_id}', indicating a configuration error.",
                level="ERROR",
            )
        else:
            self.hass.log(
                f"Error: No faults associated with symptom_id '{symptom_id}'. This may indicate a configuration error.",
                level="ERROR",
            )

        return None

    @staticmethod
    def _belongs_to_fault(fault: Fault, symptom_id: str, sm_id: str) -> bool:
        """Match a contributor by explicit identity or its unspecialized SM."""

        if fault.related_symptom_ids:
            return (
                symptom_id in fault.related_symptom_ids
                and sm_id in fault.related_symptoms
            )
        return sm_id in fault.related_symptoms

    def enable_sm(self, sm_name: str, sm_state: SMState) -> None:
        """
        Enables or disables a safety mechanism based on the provided state.

        This method is used to control the state of a specific safety mechanism identified by `sm_name`.
        It attempts to enable or disable the safety mechanism according to the provided `sm_state`.

        During the enabling process, the system also attempts to fetch and update the state of the safety mechanisms
        directly through the associated safety mechanism's function, updating the system's understanding of each
        symptom's current status.

        Args:
            sm_name (str): The identifier for the safety mechanism to be enabled or disabled.
            sm_state (SMState): The desired state for the safety mechanism. Must be a valid `SMState` enumeration value.

        Raises:
            ValueError: If `sm_state` is not a recognized value of the `SMState` enumeration.

        Note:
            Disabling invalidates this symptom's evidence without clearing an
            active fault.
        """
        symptom_data: Symptom = self.symptoms[sm_name]

        if sm_state == SMState.ENABLED:
            # Attempt to enable the safety mechanism
            result: bool = symptom_data.module.enable_safety_mechanism(
                sm_name, sm_state
            )

            if result:
                symptom_data.sm_state = SMState.ENABLED

                # Fetch and update the state of the safety mechanism directly
                sm_fcn = getattr(symptom_data.module, symptom_data.sm_name)
                try:
                    sm_fcn(symptom_data.module.safety_mechanisms[symptom_data.name])
                except Exception:
                    self.event_bus.publish("evaluation_exception", symptom_id=sm_name)
                    self.mark_evaluation_unavailable(sm_name)
                    recorder = getattr(symptom_data.module, "record_evaluation", None)
                    if callable(recorder):
                        recorder(success=False)
                    raise
                else:
                    self.event_bus.publish("evaluation_succeeded", symptom_id=sm_name)
                    recorder = getattr(symptom_data.module, "record_evaluation", None)
                    if callable(recorder):
                        recorder()
            else:
                symptom_data.sm_state = SMState.ERROR

        elif sm_state == SMState.DISABLED:
            # Disable the safety mechanism
            symptom_data.module.enable_safety_mechanism(sm_name, sm_state)
            symptom_data.sm_state = SMState.DISABLED
            # Invalidate evidence; disabling is not a fault recovery.
            self.disable_symptom(symptom_id=sm_name, additional_info={})

        else:
            # Handle an unexpected state
            self.hass.log(
                f"Error: Unknown SMState '{sm_state}' for safety mechanism '{sm_name}'.",
                level="ERROR",
            )

    def _generate_fault_tag(
        self, fault: str, additional_info: Optional[dict] = None
    ) -> str:
        """
        Generates a stable fault tag by hashing the fault name.

        Parameters:
            fault: The fault's name.
            additional_info: Kept for call compatibility; not used for tag identity.

        Returns:
            A stable fault tag as a string.
        """
        fault_str = fault
        fault_hash = hashlib.sha256(fault_str.encode()).hexdigest()
        return fault_hash

    @staticmethod
    def _notification_info_from_merged(
        additional_info: Optional[dict], merged_info: Optional[dict]
    ) -> Optional[dict]:
        """
        Build notification details from merged fault attributes.

        Only fields provided by the triggering symptom are sent to notifications,
        but values are taken from the merged fault state so descriptions reflect
        all active prefault contributors without leaking Home Assistant metadata.
        """
        if not additional_info:
            return None
        if not merged_info:
            return additional_info
        return {
            key: merged_info.get(key, value)
            for key, value in additional_info.items()
        }
    
    def get_system_fault_level(self) -> int:
        """
        Determines the highest severity level of active faults in the system.

        The severity level is based on the `level` attribute of faults.
        If no faults are active, the system's fault level is considered 0.

        Returns:
            int: The highest severity level of active faults, or 0 if no faults are active.
        """
        active_levels = [
            fault.level
            for fault in self.faults.values()
            if fault.evaluation.active
        ]
        return min(active_levels, default=0)
    
    def update_system_state_entity(self) -> None:
        """
        Updates the Home Assistant entity representing the overall system state.

        The state reflects the highest severity level of active faults.
        """
        highest_fault_level = self.get_system_fault_level()
        system_state = SYSTEM_STATE_BY_FAULT_LEVEL.get(
            highest_fault_level, "warning"
        )
        attributes = {
            "fault_count": len(
                [
                    fault
                    for fault in self.faults.values()
                    if fault.evaluation.active
                ]
            ),
            "highest_fault_level": highest_fault_level,
        }
        self._set_internal_entity(
            "sensor.safetysystem_state",
            system_state,
            attributes,
        )

    def _get_entity_attributes(self, entity_id: str) -> dict:
        """Return attributes cached for an internal MQTT entity."""
        return self.mqtt_entities.get_attributes(entity_id)

    def _set_internal_entity(
        self, entity_id: str, state: str, attributes: Optional[dict] = None
    ) -> None:
        """Publish an internal entity through MQTT."""
        self.mqtt_entities.publish_sensor_state(
            entity_id, state, attributes=attributes
        )
