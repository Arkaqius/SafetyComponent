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
Generating a unique faulttag for each fault instance to uniquely identify and manage notifications and recovery actions associated with specific faults.
The faulttag feature is used across the system to create a unique identifier for each fault by hashing the fault name and additional context information. This allows consistent tracking and correlation of notifications, fault states, and recovery actions, ensuring accurate fault management.

This module is integral to the safety system's ability to maintain operational integrity and respond effectively to detected issues, ensuring a high level of safety and reliability.

Note: This module is designed for internal use within the Home Assistant safety system and relies on configurations and interactions with other system components, including safety mechanisms and recovery action definitions.
"""

from typing import Optional, Callable
from shared.types_common import FaultState, SMState, Symptom, Fault
import appdaemon.plugins.hass.hassapi as hass
import hashlib


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
    ) -> None:
        """
        Initialize the Fault Manager.

        :param config_path: Path to the YAML configuration file.
        """
        self.notify_interface: (
            Callable[[str, int, FaultState, dict | None], None] | None
        ) = None
        self.recovery_interface: Callable[[Symptom], None] | None = None
        self.faults: dict[str, Fault] = fault_dict
        self.symptoms: dict[str, Symptom] = symptom_dict
        self.sm_modules: dict = sm_modules
        self.hass: hass.Hass = hass

    def register_callbacks(
        self,
        recovery_interface: Callable[[Symptom], None],
        notify_interface: Callable[[str, int, FaultState, dict | None], None],
    ) -> None:
        self.recovery_interface = recovery_interface
        self.notify_interface = notify_interface

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

        # Call Related Fault
        self._clear_fault(symptom_id, additional_info)

    def disable_symptom(self, symptom_id: str, additional_info: dict) -> None:
        """
        TODO
        """
        # Update symptom registry
        self.symptoms[symptom_id].state = FaultState.NOT_TESTED

        # Call Related Fault
        self._clear_fault(symptom_id, additional_info)

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
        Sets the state of a fault based on a triggered symptom condition.

        This private method is called when a symptom condition is detected (set) and aims to aggregate
        such symptom conditions to determine if a corresponding fault state should also be set. It involves
        updating the fault's state to SET, triggering notifications, and executing any defined recovery actions
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
            # Generate a unique fault tag using the hash method
            fault_tag: str = self._generate_fault_tag(fault.name, additional_info)
            # Save previous value
            fault.previous_val = fault.state
            # Set Fault
            fault.state = FaultState.SET
            self.update_system_state_entity()  # Update the system state entity
            self.hass.log(f"Fault {fault.name} was set", level="DEBUG")

            # Determinate additional info
            info_to_send: dict | None = self._determinate_info(
                "sensor.fault_" + fault.name, additional_info, FaultState.SET
            )

            # Prepare the attributes for the state update
            attributes: dict = info_to_send if info_to_send else {}

            # Set HA entity
            self.hass.set_state(
                "sensor.fault_" + fault.name, state="Set", attributes=attributes
            )

            # Call notifications
            if self.notify_interface:
                self.notify_interface(
                    fault.name,
                    fault.level,
                    FaultState.SET,
                    additional_info,
                    fault_tag,
                )
            else:
                self.hass.log("No notification interface", level="WARNING")

            # Call recovery actions (specific for symptom)
            if self.recovery_interface:
                self.recovery_interface(self.symptoms[symptom_id], fault_tag)
            else:
                self.hass.log("No recovery interface", level="WARNING")

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
            state = self.hass.get_state(entity_id, attribute="all")
            # If the entity does not exist, simply return the additional info if the fault is being set
            if not state:
                return additional_info if fault_state == FaultState.SET else {}

            # Get the current attributes of the entity; if none exist, initialize to an empty dict
            current_attributes = state.get("attributes", {})
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

    def _clear_fault(self, symptom_id: str, additional_info: dict) -> None:
        """
        Clears the state of a fault based on the resolution of a triggering symptom condition.

        This private method is invoked when a symptom condition that previously contributed to setting a fault
        is resolved (cleared). It assesses the current state of related symptoms to determine whether the associated
        fault's state can also be cleared. This involves updating the fault's state to CLEARED and triggering appropriate
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

        if fault and not any(
            symptom.state == FaultState.SET
            for symptom in self.symptoms.values()
            if symptom.sm_name == sm_name
        ):  # If Fault was found and if other fault related symptoms are not raised
            # Generate a unique fault tag using the hash method
            fault_tag: str = self._generate_fault_tag(fault.name, additional_info)
            # Save previous value
            fault.previous_val = fault.state
            # Clear Fault
            fault.state = FaultState.CLEARED
            self.hass.log(f"Fault {fault.name} was cleared", level="DEBUG")

            # Determinate additional info
            info_to_send = self._determinate_info(
                "sensor.fault_" + fault.name, additional_info, FaultState.CLEARED
            )

            # Prepare the attributes for the state update
            attributes = info_to_send if info_to_send else {}

            # Clear HA entity
            self.hass.set_state(
                "sensor.fault_" + fault.name, state="Cleared", attributes=attributes
            )
            self.update_system_state_entity()  # Update the system state entity

            if fault.previous_val == FaultState.SET:
                # Call notifications
                if self.notify_interface:
                    self.notify_interface(
                        fault.name,
                        fault.level,
                        FaultState.CLEARED,
                        additional_info,
                        fault_tag,
                    )
                else:
                    self.hass.log("No notification interface", level="WARNING")

            # Call recovery actions (specific for symptom)
            if self.recovery_interface:
                self.recovery_interface(self.symptoms[symptom_id], fault_tag)
            else:
                self.hass.log("No recovery interface", level="WARNING")

    def check_fault(self, fault_id: str) -> FaultState:
        """
        Checks the current state of a specified fault.

        This method returns the current state of the fault identified by the given `fault_id`.
        The state indicates whether the fault is active (SET), has been resolved (CLEARED),
        or has not yet been tested (NOT_TESTED). This functionality allows other components
        of the system to query the status of faults and adjust their behavior accordingly.

        Args:
            fault_id (str): The identifier of the fault whose state is to be checked.

        Returns:
            FaultState: The current state of the specified fault, indicating whether it is
                        NOT_TESTED, SET, or CLEARED.

        Raises:
            KeyError: If the specified fault_id does not exist in the faults dictionary,
                    indicating an attempt to check an undefined fault.
        """
        return self.faults[fault_id].state

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
            fault for fault in self.faults.values() if sm_id in fault.related_symptoms
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
            This method also clears all pre-existing fault states associated with the specified safety mechanism
            when disabling it, setting them to `NOT_TESTED`.
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
                sm_fcn(symptom_data.module.safety_mechanisms[symptom_data.name])
            else:
                symptom_data.sm_state = SMState.ERROR

        elif sm_state == SMState.DISABLED:
            # Disable the safety mechanism
            symptom_data.module.enable_safety_mechanism(sm_name, sm_state)
            symptom_data.sm_state = SMState.DISABLED
            # Clear all related faults to NOT_TESTED state when disabling the safety mechanism
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
        Generates a unique fault tag by hashing the fault name and additional information.

        Parameters:
            fault: The fault's name.
            additional_info: Additional information about the fault, such as location.

        Returns:
            A unique fault tag as a string.
        """
        # Combine fault name and additional info into a single string
        fault_str = fault
        if additional_info:
            # Sort the dictionary items to ensure consistent hash generation
            sorted_info = sorted(additional_info.items())
            for key, value in sorted_info:
                fault_str += f"|{key}:{value}"

        # Generate a hash of the combined string
        fault_hash = hashlib.sha256(fault_str.encode()).hexdigest()
        return fault_hash
    
    def get_system_fault_level(self) -> int:
        """
        Determines the highest severity level of active faults in the system.

        The severity level is based on the `level` attribute of faults.
        If no faults are active, the system's fault level is considered 0.

        Returns:
            int: The highest severity level of active faults, or 0 if no faults are active.
        """
        highest_level = 0
        for fault in self.faults.values():
            if fault.state == FaultState.SET:
                highest_level = max(highest_level, fault.level)
        return highest_level
    
    def update_system_state_entity(self) -> None:
        """
        Updates the Home Assistant entity representing the overall system state.

        The state reflects the highest severity level of active faults.
        """
        highest_fault_level = self.get_system_fault_level()
        attributes = {
            "fault_count": len(
                [fault for fault in self.faults.values() if fault.state == FaultState.SET]
            ),
            "highest_fault_level": highest_fault_level,
        }
        self.hass.set_state(
            "sensor.system_state",
            state=str(highest_fault_level),  # Use the fault level as the state
            attributes=attributes,
        )
