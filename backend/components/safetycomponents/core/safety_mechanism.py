"""
This module defines the SafetyMechanism class for integrating safety-related features into Home Assistant applications.
It provides a framework for monitoring changes in entity states and executing custom callback functions in response to those changes.
This enables the creation and management of dynamic safety mechanisms tailored to specific needs within a smart home environment.

The SafetyMechanism class within this module serves as a foundational component for developing safety mechanisms.
By monitoring specified entities within the Home Assistant environment, it allows for the implementation of custom logic to respond to state changes,
facilitating automated safety responses and alerts. This mechanism supports a wide range of use cases, from simple notifications to complex safety procedures
involving multiple entities and conditions.

Key Features:
- Dynamic monitoring of entity states within the Home Assistant environment.
- Execution of custom callback functions in response to monitored state changes, allowing for the implementation of bespoke safety logic.
- Flexible configuration of monitored entities and additional parameters passed to callback functions, supporting a broad array of safety mechanism designs.

This module is designed to be utilized by developers looking to enhance the safety features of their Home Assistant setups,
offering both ease of use for common use cases and the flexibility to support complex safety scenarios.
"""

from typing import Callable, List, Any
import appdaemon.plugins.hass.hassapi as hass  # type: ignore


class SafetyMechanism:
    """
    A class designed to define and manage safety mechanisms within a Home Assistant environment,
    allowing for dynamic monitoring and response to changes in entity states.

    Safety mechanisms are defined by a set of entities to monitor and a callback function
    that is executed when the state of any monitored entity changes. This enables the implementation
    of custom logic to respond to various events and conditions within a smart home setup.

    Attributes:
        hass_app: A reference to the Home Assistant application instance, used to interact with the Home Assistant API.
        entities: A list of entity IDs that this safety mechanism monitors.
        callback: The callback function that is called when a monitored entity's state changes.
        name: A user-friendly name for this safety mechanism, used for logging and reference.
        sm_args: Additional keyword arguments that are passed to the callback function upon execution.

    Methods:
        setup_listeners: Initializes state change listeners for all monitored entities.
        entity_changed: A callback method triggered by state changes in monitored entities.
        extract_entities: Utility method to extract entity IDs from keyword arguments.
    """

    def __init__(
        self,
        hass_app: hass,
        callback: Callable[..., Any],
        name: str,
        isEnabled: bool,
        **kwargs: Any,
    ) -> None:
        """
        Initializes a new instance of the SafetyMechanism class.

        Args:
            hass_app: The Home Assistant application instance, providing context for entity monitoring and callbacks.
            callback: The callback function to be executed when the state of a monitored entity changes.
                      The function is expected to accept a single argument: an instance of `SafetyMechanism`.
            name: A descriptive name for this safety mechanism.
            isEnabled: A flag that indicate if logic shall be executed
            **kwargs: Additional keyword arguments representing entities to monitor and other parameters
                      relevant to the specific safety mechanism being implemented. These arguments are
                      passed through to the callback function.
        """
        self.hass_app: Any = hass_app
        self.entities: List[str] = self.extract_entities(kwargs)
        self.callback: Callable = callback
        self.name: str = name
        self.isEnabled: bool = isEnabled
        self.sm_args: dict[str, Any] = kwargs
        self.setup_listeners()

    def setup_listeners(self) -> None:
        """
        Configures the Home Assistant listeners for state changes on all entities this safety mechanism is monitoring.

        This method iterates over the `entities` list and registers a callback (`entity_changed`) to be invoked
        whenever the state of any such entity changes, allowing the safety mechanism to respond to relevant events.
        """
        for entity in self.entities:
            self.hass_app.log(f"Setting up listener for entity: {entity}")
            self.hass_app.listen_state(self.entity_changed, entity)

    def entity_changed(
        self, entity: str, _: str, __: Any, ___: Any, **kwargs: dict
    ) -> None:
        """
        Invoked when a state change is detected for any of the monitored entities, triggering the safety mechanism's callback.

        Args:
            entity: The ID of the entity that experienced a state change.
            attribute: The specific attribute of the entity that changed (not used in this implementation).
            old: The previous state of the entity before the change (not used in this implementation).
            new: The new state of the entity after the change (not used in this implementation).
            kwargs: A dictionary of additional keyword arguments provided by the listener (not used in this implementation).

        This method logs the state change and then calls the configured callback function, passing itself (`self`) as the argument,
        allowing the callback to access the safety mechanism's properties and respond appropriately.
        """
        self.hass_app.log(f"Entity changed detected for {entity}, calling callback.")
        self.callback(self)

    def extract_entities(self, kwargs: dict) -> List[str]:
        """
        Extracts a list of entity IDs from the keyword arguments passed to the constructor.

        This method supports the flexible specification of entities, allowing for both individual entity IDs and lists of IDs.

        Args:
            kwargs: A dictionary of keyword arguments passed to the safety mechanism's constructor.

        Returns:
            A list of entity IDs that are to be monitored by this safety mechanism.
        """
        entities = []
        for _, value in kwargs.items():
            if isinstance(value, list):
                entities.extend(value)
            elif isinstance(value, str):
                entities.append(value)
        return entities
    
    def disable_sm(self, sm_name : str):
        
        self.isEnabled = False
