"""
Door/window security component for monitoring open contacts with timeout enforcement.

This component raises symptoms when external doors stay open longer than the configured
timeout and when critical windows remain open while occupancy is in a gated state.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable, Dict, Optional

import appdaemon.plugins.hass.hassapi as hass  # type: ignore

from components.core.common_entities import CommonEntities
from components.core.types_common import (
    FaultState,
    RecoveryAction,
    RecoveryResult,
    SMState,
    Symptom,
)
from components.safetycomponents.core.safety_component import (
    DebounceState,
    SafetyComponent,
    SafetyMechanismResult,
    register_safety_component,
    safety_mechanism_decorator,
)
from components.safetycomponents.core.safety_mechanism import SafetyMechanism


@dataclass
class EntryTiming:
    """Track open/closed timing for a door/window entry."""

    opened_at: Optional[float] = None
    closed_at: Optional[float] = None


@register_safety_component
class DoorWindowSecurityComponent(SafetyComponent):
    """
    Monitor external doors and critical windows for open-timeout safety conditions.

    This component enforces closure of external doors within a timeout and requires
    critical windows to remain closed when occupancy is gated (e.g., unoccupied or minors).
    """

    component_name: str = "DoorWindowSecurityComponent"

    def __init__(
        self,
        hass_app: hass,
        common_entities: CommonEntities,
        event_bus: Any,
    ) -> None:  # type: ignore
        super().__init__(hass_app, common_entities, event_bus)
        self._entry_timing: dict[str, EntryTiming] = {}
        self._recheck_handles: dict[str, Any] = {}

    def get_symptoms_data(
        self, sm_modules: dict, component_cfg: list[dict[str, Any]]
    ) -> tuple[Dict[str, Symptom], Dict[str, RecoveryAction]]:
        """
        Build symptoms and recovery actions for door/window monitoring entries.

        Args:
            sm_modules (dict): Loaded safety component modules.
            component_cfg (list[dict[str, Any]]): Normalized door/window entries.

        Returns:
            tuple: symptom and recovery action dictionaries.
        """
        ret_val_pr: dict[str, Symptom] = {}
        ret_val_ra: dict[str, RecoveryAction] = {}

        for entry in component_cfg:
            for entry_name, data in entry.items():
                entry_type = data.get("entry_type")
                if entry_type == "door":
                    symptom_name = self._get_door_symptom_name(entry_name)
                    symptom = self._create_symptom(
                        sm_modules,
                        entry_name,
                        data,
                        symptom_name,
                        sm_name="sm_sec_door_timeout",
                    )
                    recovery_action = self._create_door_recovery_action(
                        entry_name, data, symptom_name
                    )
                    ret_val_pr[symptom_name] = symptom
                    if recovery_action is not None:
                        ret_val_ra[symptom_name] = recovery_action
                elif entry_type == "window":
                    symptom_name = self._get_window_symptom_name(entry_name)
                    symptom = self._create_symptom(
                        sm_modules,
                        entry_name,
                        data,
                        symptom_name,
                        sm_name="sm_sec_window_safety",
                    )
                    recovery_action = self._create_window_recovery_action(
                        entry_name, data, symptom_name
                    )
                    ret_val_pr[symptom_name] = symptom
                    if recovery_action is not None:
                        ret_val_ra[symptom_name] = recovery_action
                else:
                    self.hass_app.log(
                        f"Unknown entry type '{entry_type}' for {entry_name}",
                        level="ERROR",
                    )

        return ret_val_pr, ret_val_ra

    def init_safety_mechanism(self, sm_name: str, name: str, parameters: dict) -> bool:
        """
        Initialize door/window safety mechanisms based on the configuration.

        Args:
            sm_name (str): Name of the safety mechanism.
            name (str): Unique identifier for the mechanism instance.
            parameters (dict): Configuration parameters.

        Returns:
            bool: True if initialization succeeds.
        """
        if sm_name == "sm_sec_door_timeout":
            required_keys = [
                "door_sensor",
                "T_door_close_timeout",
                "T_stable",
                "entry_name",
            ]
            sm_method = self.sm_sec_door_timeout
        elif sm_name == "sm_sec_window_safety":
            required_keys = [
                "window_sensor",
                "occupancy_sensor",
                "T_window_close_timeout",
                "T_stable",
                "OccupancyGateStates",
                "entry_name",
            ]
            sm_method = self.sm_sec_window_safety
        else:
            self.hass_app.log(f"Unknown safety mechanism {sm_name}", level="ERROR")
            return False

        return self._init_sm(name, parameters, sm_method, required_keys)

    def enable_safety_mechanism(self, name: str, state: SMState) -> bool:
        """
        Enable or disable a door/window safety mechanism.

        Args:
            name (str): Safety mechanism instance name.
            state (SMState): Desired state.

        Returns:
            bool: True if the state change succeeds.
        """
        if name not in self.safety_mechanisms:
            self.hass_app.log(f"Safety mechanism {name} not found", level="ERROR")
            return False

        if state == SMState.ENABLED:
            self.safety_mechanisms[name].isEnabled = True
            return True
        if state == SMState.DISABLED:
            self.safety_mechanisms[name].isEnabled = False
            self._cancel_recheck(name)
            return True

        self.hass_app.log(
            f"Invalid state {state} for safety mechanism {name}", level="ERROR"
        )
        return False

    @safety_mechanism_decorator
    def sm_sec_door_timeout(
        self, sm: SafetyMechanism, entities_changes: dict[str, str] | None = None
    ) -> SafetyMechanismResult:
        """
        Detect external doors left open longer than the configured timeout.
        """
        settings = sm.sm_args["settings"]
        entry_name: str = settings["entry_name"]
        door_sensor: str = sm.sm_args["door_sensor"]
        timeout_seconds: int = settings["door_close_timeout"]
        stable_seconds: int = settings["stable_time"]

        door_open = self._is_contact_open(
            self._get_entity_state(door_sensor, entities_changes), door_sensor
        )

        return self._evaluate_entry(
            sm=sm,
            entry_name=entry_name,
            is_open=door_open,
            timeout_seconds=timeout_seconds,
            stable_seconds=stable_seconds,
            label_key="door",
        )

    @safety_mechanism_decorator
    def sm_sec_window_safety(
        self, sm: SafetyMechanism, entities_changes: dict[str, str] | None = None
    ) -> SafetyMechanismResult:
        """
        Detect critical windows open while occupancy is gated.
        """
        settings = sm.sm_args["settings"]
        entry_name: str = settings["entry_name"]
        window_sensor: str = sm.sm_args["window_sensor"]
        occupancy_sensor: str = sm.sm_args["occupancy_sensor"]
        timeout_seconds: int = settings["window_close_timeout"]
        stable_seconds: int = settings["stable_time"]
        gate_states: list[str] = settings["occupancy_gate_states"]

        occupancy_state = self._get_entity_state(
            occupancy_sensor, entities_changes
        )
        if occupancy_state is None:
            self.hass_app.log(
                f"Occupancy state missing for {occupancy_sensor}; treating as gated.",
                level="WARNING",
            )
            gated = True
        else:
            gated = occupancy_state in gate_states

        window_open = self._is_contact_open(
            self._get_entity_state(window_sensor, entities_changes), window_sensor
        )

        if not gated:
            self._cancel_recheck(sm.name)
            self._reset_debounce(sm.name)
            return SafetyMechanismResult(
                result=False,
                additional_info={
                    "window": entry_name,
                    "occupancy_state": occupancy_state or "Unknown",
                },
            )

        result = self._evaluate_entry(
            sm=sm,
            entry_name=entry_name,
            is_open=window_open,
            timeout_seconds=timeout_seconds,
            stable_seconds=stable_seconds,
            label_key="window",
        )
        if result.additional_info is None:
            result.additional_info = {}
        result.additional_info["occupancy_state"] = occupancy_state or "Unknown"
        return result

    def sm_recalled(self, **kwargs: dict) -> None:
        """Re-evaluate a scheduled safety mechanism."""
        sm_to_call: Any = getattr(self, kwargs["sm_method"], None)
        sm: SafetyMechanism = self.safety_mechanisms[kwargs["sm_name"]]
        entities_changes: dict = kwargs["entities_changes"]
        if sm_to_call is None:
            return
        sm_to_call(sm, entities_changes)

    def _evaluate_entry(
        self,
        *,
        sm: SafetyMechanism,
        entry_name: str,
        is_open: bool,
        timeout_seconds: int,
        stable_seconds: int,
        label_key: str,
    ) -> SafetyMechanismResult:
        """
        Evaluate timeout/clear logic for a single door/window entry.
        """
        now = time.monotonic()
        timing = self._entry_timing.setdefault(sm.name, EntryTiming())
        current_state = self.symptom_states.get(sm.name, FaultState.NOT_TESTED)
        additional_info = {label_key: entry_name}

        if is_open:
            if timing.opened_at is None:
                timing.opened_at = now
            timing.closed_at = None

            if current_state == FaultState.SET:
                self._cancel_recheck(sm.name)
                return SafetyMechanismResult(True, additional_info)

            open_duration = now - timing.opened_at
            if open_duration >= timeout_seconds:
                self._reset_debounce(sm.name)
                self._cancel_recheck(sm.name)
                return SafetyMechanismResult(True, additional_info)

            self._schedule_recheck(sm, timeout_seconds - open_duration)
            return SafetyMechanismResult(False, additional_info)

        if timing.closed_at is None:
            timing.closed_at = now
        timing.opened_at = None

        if current_state != FaultState.SET:
            self._cancel_recheck(sm.name)
            return SafetyMechanismResult(False, additional_info)

        closed_duration = now - timing.closed_at
        if closed_duration >= stable_seconds:
            self._reset_debounce(sm.name)
            self._cancel_recheck(sm.name)
            return SafetyMechanismResult(False, additional_info)

        self._schedule_recheck(sm, stable_seconds - closed_duration)
        return SafetyMechanismResult(True, additional_info)

    def _init_sm(
        self, name: str, parameters: dict, sm_method: Callable, required_keys: list
    ) -> bool:
        """
        Common method to initialize a safety mechanism.
        """
        if name in self.safety_mechanisms:
            self.hass_app.log(
                f"Doubled {sm_method.__name__} - Invalid Cfg", level="ERROR"
            )
            return False

        extracted_params = self._extract_params(parameters, required_keys)
        if not extracted_params:
            return False

        sm_instance: SafetyMechanism = self._create_safety_mechanism_instance(
            name, sm_method, extracted_params
        )
        self.safety_mechanisms[name] = sm_instance
        self.debounce_states[name] = DebounceState(debounce=0, force_sm=False)
        return True

    def _extract_params(self, parameters: dict, required_keys: list) -> dict:
        """
        Extract required parameters from the provided dictionary.
        """
        extracted_params: dict[str, Any] = {}
        try:
            for key in required_keys:
                extracted_params[key] = parameters[key]
        except KeyError as exc:
            self.hass_app.log(f"Key not found in sm_cfg: {exc}", level="ERROR")
            return {}

        for key in (
            "lock_actuator",
            "window_actuator",
            "T_escalate",
            "AutoLockEnabled",
            "AutoCloseWindowsEnabled",
        ):
            if key in parameters:
                extracted_params[key] = parameters[key]
        return extracted_params

    def _create_safety_mechanism_instance(
        self, name: str, sm_method: Callable, params: dict
    ) -> SafetyMechanism:
        """
        Create a SafetyMechanism instance.
        """
        sm_args: dict[str, Any] = {
            "hass_app": self.hass_app,
            "callback": sm_method,
            "name": name,
            "isEnabled": False,
            "debounce_limit": 1,
            "re_eval_delay_seconds": 0,
            "settings": {
                "entry_name": params["entry_name"],
                "door_close_timeout": params.get("T_door_close_timeout"),
                "window_close_timeout": params.get("T_window_close_timeout"),
                "stable_time": params["T_stable"],
                "occupancy_gate_states": params.get("OccupancyGateStates", []),
            },
        }

        if sm_method == self.sm_sec_door_timeout:
            sm_args["door_sensor"] = params["door_sensor"]
        else:
            sm_args["window_sensor"] = params["window_sensor"]
            sm_args["occupancy_sensor"] = params["occupancy_sensor"]

        return SafetyMechanism(**sm_args)

    def _get_door_symptom_name(self, entry_name: str) -> str:
        return f"DoorOpenTimeout{entry_name}"

    def _get_window_symptom_name(self, entry_name: str) -> str:
        return f"WindowOpenUnsafe{entry_name}"

    def _create_symptom(
        self, modules: dict, entry_name: str, data: dict, symptom_name: str, sm_name: str
    ) -> Symptom:
        """
        Helper to create a symptom object.
        """
        symptom_params = data.copy()
        symptom_params["entry_name"] = entry_name
        return Symptom(
            module=modules[self.__class__.__name__],
            name=symptom_name,
            parameters=symptom_params,
            sm_name=sm_name,
        )

    def _create_door_recovery_action(
        self, entry_name: str, data: dict, symptom_name: str
    ) -> RecoveryAction | None:
        """
        Create recovery action for a door entry if configured.
        """
        name = f"DoorSecure{entry_name}"
        params = {
            "entry_name": entry_name,
            "door_sensor": data.get("door_sensor"),
            "lock_actuator": data.get("lock_actuator"),
            "auto_lock_enabled": data.get("AutoLockEnabled"),
        }
        return RecoveryAction(name, params, self.door_open_recovery)

    def _create_window_recovery_action(
        self, entry_name: str, data: dict, symptom_name: str
    ) -> RecoveryAction | None:
        """
        Create recovery action for a window entry if configured.
        """
        name = f"WindowSecure{entry_name}"
        params = {
            "entry_name": entry_name,
            "window_sensor": data.get("window_sensor"),
            "window_actuator": data.get("window_actuator"),
            "auto_close_enabled": data.get("AutoCloseWindowsEnabled"),
        }
        return RecoveryAction(name, params, self.window_open_recovery)

    @staticmethod
    def door_open_recovery(
        hass_app: hass,
        symptom: Symptom,
        common_entities: CommonEntities,
        **kwargs: dict[str, Any],
    ) -> Optional[RecoveryResult]:
        """
        Attempt to lock doors or notify when a door is left open.
        """
        _ = common_entities
        door_sensor = kwargs.get("door_sensor")
        entry_name = kwargs.get("entry_name", "door")
        lock_actuator = kwargs.get("lock_actuator")
        auto_lock_enabled = bool(kwargs.get("auto_lock_enabled"))

        if door_sensor:
            state = hass_app.get_state(door_sensor)
            if state is not None and not DoorWindowSecurityComponent._is_open_state(
                str(state)
            ):
                return RecoveryResult({}, {}, [])

        if auto_lock_enabled and lock_actuator:
            return RecoveryResult({}, {lock_actuator: "locked"}, [])

        message = f"Please close/lock door {entry_name}."
        return RecoveryResult({}, {}, [message])

    @staticmethod
    def window_open_recovery(
        hass_app: hass,
        symptom: Symptom,
        common_entities: CommonEntities,
        **kwargs: dict[str, Any],
    ) -> Optional[RecoveryResult]:
        """
        Attempt to close windows or notify when a critical window is open.
        """
        _ = common_entities
        window_sensor = kwargs.get("window_sensor")
        entry_name = kwargs.get("entry_name", "window")
        window_actuator = kwargs.get("window_actuator")
        auto_close_enabled = bool(kwargs.get("auto_close_enabled"))

        if window_sensor:
            state = hass_app.get_state(window_sensor)
            if state is not None and not DoorWindowSecurityComponent._is_open_state(
                str(state)
            ):
                return RecoveryResult({}, {}, [])

        if auto_close_enabled and window_actuator:
            return RecoveryResult({}, {window_actuator: "closed"}, [])

        message = f"Please close critical window {entry_name}."
        return RecoveryResult({}, {}, [message])

    def _get_entity_state(
        self, entity_id: str, entities_changes: dict[str, str] | None
    ) -> str | None:
        """
        Get entity state, falling back to stubbed values when provided.
        """
        if entities_changes and entity_id in entities_changes:
            return str(entities_changes[entity_id])
        state = self.hass_app.get_state(entity_id)
        return str(state) if state is not None else None

    @staticmethod
    def _is_open_state(state: str) -> bool:
        normalized = state.strip().lower()
        if normalized in {"on", "open", "true", "1"}:
            return True
        if normalized in {"off", "closed", "false", "0"}:
            return False
        return True

    def _is_contact_open(self, state: str | None, entity_id: str) -> bool:
        if state is None:
            self.hass_app.log(
                f"State missing for {entity_id}; treating as open.",
                level="WARNING",
            )
            return True
        return self._is_open_state(state)

    def _schedule_recheck(self, sm: SafetyMechanism, delay_seconds: float) -> None:
        if delay_seconds <= 0:
            return
        self._cancel_recheck(sm.name)
        handle = self.hass_app.run_in(
            self.sm_recalled,
            delay_seconds,
            sm_method=sm.callback.__name__,
            sm_name=sm.name,
            entities_changes=None,
        )
        self._recheck_handles[sm.name] = handle

    def _cancel_recheck(self, sm_name: str) -> None:
        handle = self._recheck_handles.pop(sm_name, None)
        if handle is None:
            return
        try:
            self.hass_app.cancel_timer(handle)
        except Exception as exc:
            self.hass_app.log(
                f"Failed to cancel timer for {sm_name}: {exc}", level="WARNING"
            )

    def _reset_debounce(self, sm_name: str) -> None:
        if sm_name in self.debounce_states:
            self.debounce_states[sm_name] = DebounceState(
                debounce=0, force_sm=False
            )
