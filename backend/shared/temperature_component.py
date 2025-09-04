"""
This module defines the TemperatureComponent class, part of a Home Assistant-based safety system designed to monitor and respond to temperature-related risks. TemperatureComponent is responsible for managing safety mechanisms that trigger based on direct temperature readings and forecasted temperature changes, providing a dynamic response to potential temperature hazards within a monitored environment.

The component utilizes Home Assistant's infrastructure to monitor temperature sensors and execute predefined safety mechanisms when certain temperature thresholds are reached or forecasted. This system is designed to be configurable, allowing users to define safety mechanisms through external configuration, making it adaptable to various scenarios and requirements.

Classes:
- DebounceState: A NamedTuple that represents the state of a debounce process.
- TemperatureComponent: Manages temperature-related safety mechanisms within Home Assistant.

Key Features:
- Direct temperature monitoring with immediate response mechanisms.
- Forecasted temperature monitoring for proactive safety measures.
- Configurable thresholds and response actions to accommodate different monitoring needs and scenarios.
- Integration with Home Assistant for accessing sensor data and executing actions.

Usage:
The TemperatureComponent class is intended to be used within a Home Assistant automation setup. Users can define safety mechanisms and their configurations in external YAML files, which the component will read and use to initialize the necessary monitoring and response logic.

Note:
This module is part of a larger system designed for enhancing safety through Home Assistant. It should be integrated with the appropriate Home Assistant setup and configured according to the specific needs and safety requirements of the environment being monitored.
"""

import math
from typing import Dict, Any, Callable, Optional
from shared.safety_component import (
    SafetyComponent,
    safety_mechanism_decorator,
    DebounceState,
    SafetyMechanismResult,
)
from shared.safety_mechanism import SafetyMechanism
from shared.types_common import Symptom, RecoveryAction, SMState, RecoveryResult
from shared.common_entities import CommonEntities
import appdaemon.plugins.hass.hassapi as hass  # type: ignore

# CONFIG
DEBOUNCE_INIT = 0
SM_TC_2_DEBOUNCE_LIMIT = 0
FORECAST_SAMPLING_TIME = 15  # minutes, but deviratives are ALWAYS in minutes


class TemperatureComponent(SafetyComponent):
    """
    Manages and orchestrates temperature-related safety mechanisms within the Home Assistant framework.
    This component is responsible for initializing temperature monitoring mechanisms, processing
    temperature data, and executing appropriate actions based on configurable thresholds and forecasted conditions.

    It leverages Home Assistant's sensor data to proactively manage temperature risks, employing debouncing strategies
    to ensure reliable detection and response to temperature fluctuations. The component supports multiple safety mechanisms,
    each designed to monitor specific conditions and execute defined actions, such as sending alerts or triggering automations.
    """

    component_name: str = "TemperatureComponent"

    # region Init and enables
    def __init__(self, hass_app: hass, common_entities: CommonEntities) -> None:  # type: ignore
        """
        Initializes the TemperatureComponent instance with the Home Assistant application context, setting up the foundation
        for temperature-related safety management within the smart home environment.

        Args:
            hass_app (hass.Hass): The Home Assistant application instance through which sensor data is accessed and actions are executed.
            common_entities (CommonEntities): A shared object providing access to common entities used across different safety mechanisms.
        """
        super().__init__(hass_app, common_entities)

    def get_symptoms_data(
        self, sm_modules: dict, component_cfg: list[dict[str, Any]]
    ) -> tuple[Dict[str, Symptom], Dict[str, RecoveryAction]]:
        """
        Retrieve symptom configurations from the component configuration and generate corresponding symptom objects.

        Args:
            sm_modules (dict): A dictionary of system modules.
            component_cfg (list[dict[str, Any]]): A list of dictionaries where each dictionary
                contains a single location as the key and a dictionary of configuration data for that location.

        Returns:
            Tuple[Dict[str, symptom], Dict[str, RecoveryAction]]: Two dictionaries, one for symptoms and one for RecoveryActions.
        """
        ret_val_pr: dict[str, Symptom] = {}
        ret_val_ra: dict[str, RecoveryAction] = {}

        for location_dict in component_cfg:
            for location, data in location_dict.items():
                self.hass_app.log(
                    f"Processing symptoms for location: {location}, data: {data}"
                )
                self._process_symptoms_for_location(
                    sm_modules, location, data, ret_val_pr, ret_val_ra
                )

        return (ret_val_pr, ret_val_ra)

    def init_safety_mechanism(self, sm_name: str, name: str, parameters: dict) -> bool:
        """
        Initializes a safety mechanism based on the provided safety mechanism name.

        Args:
            sm_name (str): The name of the safety mechanism (e.g., "sm_tc_1" or "sm_tc_2").
            name (str): The unique name identifying this safety mechanism.
            parameters (dict): Configuration parameters for the safety mechanism.

        Returns:
            bool: True if the initialization is successful, False otherwise.
        """
        if sm_name == "sm_tc_1":
            required_keys: list[str] = [
                "temperature_sensor",
                "CAL_LOW_TEMP_THRESHOLD",
                "location",
            ]
            sm_method = self.sm_tc_1
        elif sm_name == "sm_tc_2":
            required_keys = [
                "temperature_sensor",
                "CAL_LOW_TEMP_THRESHOLD",
                "CAL_FORECAST_TIMESPAN",
                "location",
            ]
            sm_method = self.sm_tc_2
        else:
            self.hass_app.log(f"Unknown safety mechanism {sm_name}", level="ERROR")
            return False

        return self._init_sm(name, parameters, sm_method, required_keys)

    def enable_safety_mechanism(self, name: str, state: SMState) -> bool:
        """
        Enables or disables a safety mechanism based on the provided state.

        Args:
            name (str): The unique name identifying this safety mechanism.
            state (SMState): The state to set for the safety mechanism (ENABLED or DISABLED).

        Returns:
            bool: True if the state change is successful, False otherwise.
        """
        if name not in self.safety_mechanisms:
            self.hass_app.log(f"Safety mechanism {name} not found", level="ERROR")
            return False

        if state == SMState.ENABLED:
            self.safety_mechanisms[name].isEnabled = True
            return True
        elif state == SMState.DISABLED:
            self.safety_mechanisms[name].isEnabled = False
            return True
        else:
            self.hass_app.log(
                f"Invalid state {state} for safety mechanism {name}", level="ERROR"
            )
            return False

    # endregion
    # region Safety mechanisms
    @safety_mechanism_decorator
    def sm_tc_1(
        self, sm: SafetyMechanism, entities_changes: dict[str, str] | None = None
    ) -> SafetyMechanismResult:
        """
        The core logic for a direct temperature threshold safety mechanism. It reads current temperature
        data, compares it against defined thresholds, and, if a risk condition is detected, executes configured
        actions to mitigate the risk.

        Args:
            sm (SafetyMechanism): The instance of the safety mechanism being processed.
            **kwargs: Additional keyword arguments, primarily for future extensions and compatibility.

        Operations:
            - Retrieves current temperature from the configured sensor.
            - Applies debouncing to stabilize detection over time.
            - Triggers configured actions if the temperature crosses the defined threshold.

        Note:
            This method is wrapped with a decorator to log its execution and handle any exceptions gracefully.
        """
        temperature_sensor: str = sm.sm_args["temperature_sensor"]
        cold_threshold: float = sm.sm_args["cold_thr"]
        location: str = sm.sm_args["location"]

        # Fetch temperature value, using stubbed value if provided
        temperature: float | None = self._get_temperature_value(
            temperature_sensor, entities_changes
        )
        if temperature is None:
            return SafetyMechanismResult(False, None)

        sm_result: bool = temperature < cold_threshold
        additional_info: dict[str, str] = {"location": location}

        return SafetyMechanismResult(result=sm_result, additional_info=additional_info)

    @safety_mechanism_decorator
    def sm_tc_2(
        self, sm: SafetyMechanism, entities_changes: dict[str, str] | None = None
    ) -> tuple[bool, dict[str, Any] | None]:
        """
        Implements logic for a forecast-based temperature change safety mechanism. This method analyzes
        temperature trends and forecasts future conditions to proactively address potential risks based
        on predicted temperature changes.

        Args:
            sm (SafetyMechanism): The safety mechanism instance being evaluated.
            **kwargs: Arbitrary keyword arguments, allowing for future flexibility in method signatures.

        Operations:
            - Calculates forecasted temperature using current data and rate of change.
            - Employs debouncing for reliable forecasting over specified intervals.
            - Executes preventive actions if forecasted conditions indicate a potential risk.

        Note:
            Enhanced with a decorator for execution logging and error management, ensuring robust operation.
        """
        temperature_sensor: str = sm.sm_args["temperature_sensor"]
        cold_threshold: float = sm.sm_args["cold_thr"]
        location: str = sm.sm_args["location"]
        forecast_span: float = sm.sm_args["forecast_timespan"]

        # Fetch temperature value, using stubbed value if provided
        temperature: float | None = self._get_temperature_value(
            temperature_sensor, entities_changes
        )

        # Fetch temperature value, using stubbed value if provided
        temperature_rate: float | None = self._get_temperature_value(
            f"{temperature_sensor}_rate", entities_changes
        )

        if temperature is None or temperature_rate is None:
            return SafetyMechanismResult(False, None)

        forecasted_temperature = self.forecast_temperature(
            temperature, temperature_rate, forecast_span
        )

        sm_result: bool = forecasted_temperature < cold_threshold
        additional_info: dict[str, str] = {"location": location}

        return SafetyMechanismResult(result=sm_result, additional_info=additional_info)

    def forecast_temperature(
        self,
        initial_temperature: float,
        dT: float,
        forecast_timespan_hours: float,
    ) -> float:
        """
        Forecast the temperature using an exponential decay model.

        Parameters:
        - initial_temperature (float): The initial temperature in degrees Celsius (T_0).
        - dT (float): The temperature drop per 15 minute (initial rate).
        - forecast_timespan_hours (float): The timespan for the forecast in hours.

        Returns:
        - float: The forecasted temperature after the given timespan.
        """
        # Convert forecast timespan from hours to minutes
        forecast_timespan_in_minutes = forecast_timespan_hours * 60

        # Calculate decay constant k based on the initial rate of temperature change
        k: float = -math.log(
            (initial_temperature + dT/FORECAST_SAMPLING_TIME) / initial_temperature
        )

        # Calculate forecasted temperature for the specified timespan using exponential decay
        forecasted_temperature: float = initial_temperature * math.exp(
            -k * forecast_timespan_in_minutes
        )

        return forecasted_temperature

    def sm_recalled(self, **kwargs: dict) -> None:
        """
        The sm_recalled function is designed to handle the re-execution of safety mechanisms that require multiple evaluations over time.
        This function is typically invoked by a scheduler after a delay, allowing for periodic reassessment of safety conditions.
        It ensures that the safety mechanism is called again with the correct context, enabling continued monitoring and decision-making based on updated data.

        Arguments:
            kwargs: A dictionary containing key parameters needed to re-invoke the safety mechanism:
            sm_method: The name of the safety mechanism method to be called (as a string).
            sm_name: The unique name of the safety mechanism instance.
            entities_changes: A dictionary containing any changes in entity states that should be considered during the re-evaluation.

        Functionality:
        Retrieves the method to be invoked based on the sm_method string.
        Fetches the corresponding SafetyMechanism instance using the sm_name.
        Calls the safety mechanism method, passing in the relevant safety mechanism instance and any entity changes.
        The function handles the continued monitoring and evaluation of safety conditions, ensuring that appropriate actions are taken based on the latest data.
        This function is a critical component in scenarios where the safety mechanism needs to be evaluated multiple times in succession.
        By using a scheduler, it avoids overwhelming the system with constant checks while still providing timely responses to changing conditions.
        """

        # Prepare args and functions
        sm_to_call: Any = getattr(self, kwargs["sm_method"], None)
        sm: SafetyMechanism = self.safety_mechanisms[kwargs["sm_name"]]
        entities_changes: dict = kwargs["entities_changes"]

        # Call SM
        print(f'self:{self} sm:{sm} entities_changes"{entities_changes}')
        sm_to_call(sm, entities_changes)

    # endregion
    # region Private functions
    def _process_symptoms_for_location(
        self,
        sm_modules: dict,
        location: str,
        data: dict,
        ret_val_pr: dict,
        ret_val_ra: dict,
    ) -> None:
        """
        Process symptoms for a given location and update the provided dictionaries.

        Args:
            sm_modules (dict): A dictionary of system modules.
            location (str): The location identifier.
            data (dict): Configuration data specific to the location.
            ret_val_pr (dict): Dictionary to store generated symptom objects.
            ret_val_ra (dict): Dictionary to store generated RecoveryAction objects.
        """
        # Process SM TC 1
        self._process_sm_tc(sm_modules, location, data, ret_val_pr, ret_val_ra, tc_number=1)  # type: ignore[misc]

        # Process SM TC 2
        self._process_sm_tc(sm_modules, location, data, ret_val_pr, ret_val_ra, tc_number=2)  # type: ignore[misc]

    def _process_sm_tc(
        self,
        sm_modules: dict,
        location: str,
        data: dict,
        ret_val_pr: dict,
        ret_val_ra: dict,
        tc_number: int,
    ) -> None:
        """
        Process a specific SM TC (Safety Mechanism Temperature Condition) and update the provided dictionaries.

        Args:
            sm_modules (dict): A dictionary of system modules.
            location (str): The location identifier.
            data (dict): Configuration data specific to the location.
            ret_val_pr (dict): Dictionary to store generated symptom objects.
            ret_val_ra (dict): Dictionary to store generated RecoveryAction objects.
            tc_number (int): The TC number to process (e.g., 1 or 2).
        """
        symptom_name_func = getattr(self, f"_get_sm_tc_{tc_number}_pr_name")
        symptom_func = getattr(self, f"_get_sm_tc_{tc_number}_symptom")
        recovery_action_func = getattr(self, f"_get_sm_tc_{tc_number}_recovery_action")

        symptom_name = symptom_name_func(location)
        symptom = symptom_func(sm_modules, location, data, symptom_name)
        recovery_action = recovery_action_func(sm_modules, location, data, symptom_name)

        ret_val_pr[symptom_name] = symptom
        ret_val_ra[symptom_name] = recovery_action

    def _create_symptom(
        self, modules: dict, location: str, data: dict, symptom_name: str, sm_name: str
    ) -> Symptom:
        """
        Helper function to create a symptom object.

        Args:
            modules (dict): A dictionary of system modules.
            location (str): The location identifier.
            data (dict): Configuration data specific to the symptom.
            symptom_name (str): The symptom's name.
            sm_name (str): The safety mechanism name.

        Returns:
            symptom: The created symptom object.
        """
        symptom_params = data.copy()
        symptom_params["location"] = location

        return Symptom(
            module=modules[self.__class__.__name__],
            name=symptom_name,
            parameters=symptom_params,
            sm_name=sm_name,
        )

    def _create_recovery_action(
        self, location: str, data: dict, action_name: str, default_name: str
    ) -> RecoveryAction:
        """
        Helper function to create a RecoveryAction object.

        Args:
            location (str): The location identifier.
            data (dict): Configuration data specific to the recovery action.
            action_name (str): The recovery action function name.
            default_name (str): The default name for the recovery action.

        Returns:
            RecoveryAction: The created RecoveryAction object.
        """
        name: str = f"{default_name}{location}"
        params = {
            "location": location,
            "actuator": data.get("actuator"),
            "window_sensor": data["window_sensor"],
        }
        recovery_func = getattr(self, action_name)

        return RecoveryAction(name, params, recovery_func)

    def _get_sm_tc_1_pr_name(self, location: str) -> str:
        return f"RiskyTemperature{location}"

    def _get_sm_tc_1_symptom(
        self, modules: dict, location: str, data: dict, symptom_name: str
    ) -> Symptom:
        return self._create_symptom(
            modules, location, data, symptom_name, sm_name="sm_tc_1"
        )

    def _get_sm_tc_1_recovery_action(
        self, _: dict, location: str, data: dict, ___: str
    ) -> RecoveryAction:
        return self._create_recovery_action(
            location,
            data,
            action_name="RiskyTemperature_recovery",
            default_name="ManipulateWindow",
        )

    def _get_sm_tc_2_pr_name(self, location: str) -> str:
        return f"RiskyTemperature{location}ForeCast"

    def _get_sm_tc_2_symptom(
        self, modules: dict, location: str, data: dict, symptom_name: str
    ) -> Symptom:
        return self._create_symptom(
            modules, location, data, symptom_name, sm_name="sm_tc_2"
        )

    def _get_sm_tc_2_recovery_action(
        self, _: dict, location: str, data: dict, ___: str
    ) -> RecoveryAction:
        return self._create_recovery_action(
            location,
            data,
            action_name="RiskyTemperature_recovery",
            default_name="ManipulateWindow",
        )

    def _init_sm(
        self, name: str, parameters: dict, sm_method: Callable, required_keys: list
    ) -> bool:
        """
        Common method to initialize a safety mechanism.

        Args:
            name (str): The unique name identifying this safety mechanism.
            parameters (dict): Configuration parameters for the safety mechanism.
            sm_method (callable): The method to be called for this safety mechanism.
            required_keys (list): List of keys required in the parameters.

        Returns:
            bool: True if the initialization is successful, False otherwise.
        """
        if name in self.safety_mechanisms:
            self.hass_app.log(
                f"Doubled {sm_method.__name__} - Invalid Cfg", level="ERROR"
            )
            return False

        extracted_params = self._extract_params(parameters, required_keys)

        # Store the SafetyMechanism instance in the dictionary using the unique name as the key
        sm_instance: SafetyMechanism = self._create_safety_mechanism_instance(
            name, sm_method, extracted_params
        )
        self.safety_mechanisms[name] = sm_instance

        # Initialize the debounce state for this mechanism
        self.debounce_states[name] = DebounceState(
            debounce=DEBOUNCE_INIT, force_sm=False
        )

        # Additional setup for SM TC 2
        if sm_method == self.sm_tc_2:
            self.derivative_monitor.register_entity(
                extracted_params["temperature_sensor"], 60*FORECAST_SAMPLING_TIME, -2, 2
            )

        return True

    def _extract_params(self, parameters: dict, required_keys: list) -> dict:
        """
        Extracts parameters from the provided dictionary.

        Args:
            parameters (dict): The parameters to extract.
            required_keys (list): The required keys for extraction.

        Returns:
            dict: The extracted parameters.
        """
        extracted_params = {}
        try:
            for key in required_keys:
                extracted_params[key] = parameters[key]
            extracted_params["actuator"] = parameters.get("actuator")
        except KeyError as e:
            self.hass_app.log(f"Key not found in sm_cfg: {e}", level="ERROR")
            return {}

        return extracted_params

    def _create_safety_mechanism_instance(
        self, name: str, sm_method: Callable, params: dict
    ) -> SafetyMechanism:
        """
        Creates a SafetyMechanism instance.

        Args:
            name (str): The unique name of the safety mechanism.
            sm_method (callable): The method to be called for this safety mechanism.
            params (dict): The parameters for the safety mechanism.

        Returns:
            SafetyMechanism: The created SafetyMechanism instance.
        """
        sm_args = {
            "hass_app": self.hass_app,
            "callback": sm_method,
            "name": name,
            "isEnabled": False,
            "temperature_sensor": params["temperature_sensor"],
            "cold_thr": params["CAL_LOW_TEMP_THRESHOLD"],
            "location": params["location"],
            "actuator": params["actuator"],
        }

        if sm_method == self.sm_tc_2:
            sm_args.update(
                {
                    "forecast_timespan": params["CAL_FORECAST_TIMESPAN"],
                }
            )

        return SafetyMechanism(**sm_args)

    def _get_temperature_value(
        self, sensor_id: str, entities_changes: dict[str, str] | None
    ) -> float | None:
        """
        Fetch and convert temperature from a sensor, using stubbed values if provided.

        Args:
            sensor_id (str): The ID of the temperature sensor.
            entities_changes (dict | None): Optional dictionary containing stubbed values for testing.

        Returns:
            float | None: The temperature value, or None if there was an error.
        """
        if entities_changes and sensor_id in entities_changes:
            try:
                temperature = float(entities_changes[sensor_id])
                return temperature
            except (ValueError, TypeError) as e:
                self.hass_app.log(
                    f"Error handling stubbed temperature: {e}", level="ERROR"
                )
                return None
        else:
            return self.get_num_sensor_val(self.hass_app, sensor_id)

    # endregion
    @staticmethod
    def RiskyTemperature_recovery(
        hass_app: hass,
        symptom: Symptom,
        common_entities: CommonEntities,
        **kwargs: dict[str, str],
    ) -> Optional[RecoveryResult]:
        """
        Recovery action for handling risky temperature conditions.

        This method is called when a risky temperature condition is detected. It determines the appropriate
        recovery actions, such as closing or opening windows, and generates notifications if manual actions are needed.

        Args:
            hass_app (hass.Hass): The Home Assistant application instance.
            symptom (symptom): The symptom instance containing the fault parameters.
            common_entities (CommonEntities): Shared object providing access to common entities.
            **kwargs (dict): Additional keyword arguments, such as location, actuator, and window sensors.

        Returns:
            Optional[RecoveryResult]: A NamedTuple containing the changed entities and notifications,
            or None if an error occurred.
        """
        changed_sensors: dict[str, str] = {}
        changed_actuators: dict[str, str] = {}
        notifications: list[str] = []
        location: str = kwargs["location"]  # type: ignore
        actuator: str = kwargs["actuator"]  # type: ignore
        window_sensors: list[str] = kwargs["window_sensor"]  # type: ignore

        # Get room temperature
        meas_room_temp: float | None = SafetyComponent.get_num_sensor_val(
            hass_app, symptom.parameters["temperature_sensor"]
        )
        if meas_room_temp is None:
            return None

        # Get outside temperature
        outside_temp_raw: str | None = common_entities.get_outisde_temperature()
        if not outside_temp_raw:
            return RecoveryResult(changed_sensors, changed_actuators, notifications)

        outside_temp = float(outside_temp_raw)

        if outside_temp < meas_room_temp:
            window_sensors_state = "off"
            actuator_sensors_state = "off"
            notification: str = f"Please close windows in {location} as recovery action"
        else:
            window_sensors_state = "on"
            actuator_sensors_state = "on"
            notification: str = f"Please open windows in {location} as recovery action"

        # Close windows if outside temperature is lower
        changed_sensors = SafetyComponent.change_all_entities_state(
            window_sensors, window_sensors_state
        )
        if actuator:
            changed_actuators[actuator] = actuator_sensors_state
        else:
            notifications.append(notification)

        return RecoveryResult(changed_sensors, changed_actuators, notifications)
