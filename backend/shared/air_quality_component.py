"""
AirQualityComponent monitors the Air Quality Index (AQI) within the Home Assistant
environment and exposes safety mechanisms for reacting to degraded air conditions.

The component provides a single safety mechanism (``sm_aq_1``) which evaluates the
current AQI against a configurable threshold. When the measured AQI rises above the
threshold, the mechanism reports the condition and can trigger a recovery action to
advise ventilation of the affected area.

This module is intentionally lightweight and serves as an example of how additional
safety components can be integrated into the SafetyFunctions framework.
"""
from __future__ import annotations

from typing import Dict, Any
import appdaemon.plugins.hass.hassapi as hass  # type: ignore

from shared.safety_component import (
    SafetyComponent,
    safety_mechanism_decorator,
    DebounceState,
    SafetyMechanismResult,
)
from shared.safety_mechanism import SafetyMechanism
from shared.types_common import Symptom, RecoveryAction, SMState, RecoveryResult
from shared.common_entities import CommonEntities


class AirQualityComponent(SafetyComponent):
    """Component responsible for monitoring air quality levels."""

    component_name: str = "AirQualityComponent"

    def __init__(self, hass_app: hass, common_entities: CommonEntities) -> None:
        super().__init__(hass_app, common_entities)

    # ------------------------------------------------------------------
    # Initialization helpers
    def get_symptoms_data(
        self, sm_modules: dict, component_cfg: list[dict[str, Any]]
    ) -> tuple[Dict[str, Symptom], Dict[str, RecoveryAction]]:
        ret_val_pr: Dict[str, Symptom] = {}
        ret_val_ra: Dict[str, RecoveryAction] = {}
        for location_dict in component_cfg:
            for location, data in location_dict.items():
                symptom_name = self._get_sm_aq_1_pr_name(location)
                symptom = self._get_sm_aq_1_symptom(
                    sm_modules, location, data, symptom_name
                )
                recovery = self._get_sm_aq_1_recovery_action(
                    sm_modules, location, data, symptom_name
                )
                ret_val_pr[symptom_name] = symptom
                ret_val_ra[symptom_name] = recovery
        return (ret_val_pr, ret_val_ra)

    def init_safety_mechanism(self, sm_name: str, name: str, parameters: dict) -> bool:
        if sm_name != "sm_aq_1":
            self.hass_app.log(f"Unknown safety mechanism {sm_name}", level="ERROR")
            return False

        required = ["aqi_sensor", "CAL_AQI_THRESHOLD", "location"]
        for key in required:
            if key not in parameters:
                self.hass_app.log(f"Key not found in sm_cfg: {key}", level="ERROR")
                return False

        sm_instance = SafetyMechanism(
            self.hass_app,
            self.sm_aq_1,
            name,
            True,
            aqi_sensor=parameters["aqi_sensor"],
            CAL_AQI_THRESHOLD=parameters["CAL_AQI_THRESHOLD"],
            location=parameters["location"],
            actuator=parameters.get("actuator"),
        )
        self.safety_mechanisms[name] = sm_instance
        self.debounce_states[name] = DebounceState(debounce=0, force_sm=False)
        return True

    def enable_safety_mechanism(self, name: str, state: SMState) -> bool:
        if name not in self.safety_mechanisms:
            self.hass_app.log(f"Safety mechanism {name} not found", level="ERROR")
            return False
        if state == SMState.ENABLED:
            self.safety_mechanisms[name].isEnabled = True
            return True
        if state == SMState.DISABLED:
            self.safety_mechanisms[name].isEnabled = False
            return True
        self.hass_app.log(
            f"Invalid state {state} for safety mechanism {name}", level="ERROR"
        )
        return False

    # ------------------------------------------------------------------
    # Safety mechanism
    @safety_mechanism_decorator
    def sm_aq_1(
        self, sm: SafetyMechanism, entities_changes: dict[str, str] | None = None
    ) -> SafetyMechanismResult:
        aqi_sensor: str = sm.sm_args["aqi_sensor"]
        threshold: float = sm.sm_args["CAL_AQI_THRESHOLD"]
        location: str = sm.sm_args["location"]

        aqi_value = self._get_aqi_value(aqi_sensor, entities_changes)
        if aqi_value is None:
            return SafetyMechanismResult(False, None)

        result = aqi_value > threshold
        additional_info = {"location": location, "aqi": aqi_value}
        return SafetyMechanismResult(result=result, additional_info=additional_info)

    # ------------------------------------------------------------------
    # Recovery action
    def PoorAirQuality_recovery(
        self,
        hass_app: hass,
        symptom: Symptom,
        common_entities: CommonEntities,
        **kwargs: dict[str, str],
    ) -> RecoveryResult | None:
        location: str = kwargs.get("location", "")
        notification = f"Air quality poor at {location}. Please ventilate."
        return RecoveryResult({}, {}, [notification])

    # ------------------------------------------------------------------
    # Helper methods
    def _get_aqi_value(
        self, sensor: str, entities_changes: dict[str, str] | None
    ) -> float | None:
        if entities_changes and sensor in entities_changes:
            return self._to_float(entities_changes[sensor])
        value = self.hass_app.get_state(sensor)
        return self._to_float(value)

    @staticmethod
    def _to_float(value: str | None) -> float | None:
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None

    def _create_symptom(
        self, modules: dict, location: str, data: dict, symptom_name: str, sm_name: str
    ) -> Symptom:
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
        name = f"{default_name}{location}"
        params = {"location": location, "actuator": data.get("actuator")}
        recovery_func = getattr(self, action_name)
        return RecoveryAction(name, params, recovery_func)

    def _get_sm_aq_1_pr_name(self, location: str) -> str:
        return f"PoorAirQuality{location}"

    def _get_sm_aq_1_symptom(
        self, modules: dict, location: str, data: dict, symptom_name: str
    ) -> Symptom:
        return self._create_symptom(modules, location, data, symptom_name, "sm_aq_1")

    def _get_sm_aq_1_recovery_action(
        self, _: dict, location: str, data: dict, ___: str
    ) -> RecoveryAction:
        return self._create_recovery_action(
            location, data, action_name="PoorAirQuality_recovery", default_name="Ventilate"
        )
