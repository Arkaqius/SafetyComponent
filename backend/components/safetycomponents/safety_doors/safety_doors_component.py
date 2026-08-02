"""Monitor configured doors and report sustained open states through MQTT."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import appdaemon.plugins.hass.hassapi as hass  # type: ignore

from components.core.common_entities import CommonEntities
from components.core.event_bus import EventBus
from components.core.mqtt_entity_manager import MqttEntityManager
from components.core.types_common import FaultState, RecoveryAction, SMState, Symptom
from components.safetycomponents.core.safety_component import (
    SafetyComponent,
    register_safety_component,
)
from components.safetycomponents.core.safety_mechanism import SafetyMechanism

SAFETY_MECHANISM_NAME = "sm_safety_door_open_timeout"
OPEN_STATES = frozenset({"on", "open", "opening", "closing", "true", "1"})
CLOSED_STATES = frozenset({"off", "closed", "false", "0"})
UNAVAILABLE_STATES = frozenset({"", "none", "unknown", "unavailable"})


@dataclass
class DoorRuntime:
    """Mutable timing state for one configured door."""

    opened_at: datetime | None = None
    timer_handle: Any | None = None
    active: bool = False


@register_safety_component
class SafetyDoorsComponent(SafetyComponent):
    """Report a safety condition when a configured door exceeds its timeout."""

    component_name = "SafetyDoorsComponent"

    def __init__(
        self,
        hass_app: hass.Hass,
        common_entities: CommonEntities,
        event_bus: EventBus,
        mqtt_entities: MqttEntityManager,
    ) -> None:
        super().__init__(hass_app, common_entities, event_bus, mqtt_entities)
        self._door_runtime: dict[str, DoorRuntime] = {}
        self._mqtt_entity_ids: dict[str, str] = {}

    def get_symptoms_data(
        self,
        modules: dict[str, SafetyComponent],
        component_cfg: list[dict[str, Any]],
    ) -> tuple[dict[str, Symptom], dict[str, RecoveryAction]]:
        """Create one timeout symptom for every configured safety door."""
        symptoms: dict[str, Symptom] = {}

        for entry in component_cfg:
            for door_name, parameters in entry.items():
                symptom_name = self._symptom_name(door_name)
                runtime_parameters = dict(parameters)
                runtime_parameters["door_name"] = door_name
                symptoms[symptom_name] = Symptom(
                    module=modules[self.component_name],
                    name=symptom_name,
                    parameters=runtime_parameters,
                    sm_name=SAFETY_MECHANISM_NAME,
                )

        return symptoms, {}

    def init_safety_mechanism(
        self, sm_name: str, name: str, parameters: dict[str, Any]
    ) -> bool:
        """Initialize state listening and MQTT discovery for one door."""
        if sm_name != SAFETY_MECHANISM_NAME:
            self.hass_app.log(
                f"Unknown safety mechanism {sm_name}", level="ERROR"
            )
            return False
        if name in self.safety_mechanisms:
            self.hass_app.log(
                f"Safety mechanism {name} is already initialized", level="ERROR"
            )
            return False

        try:
            door_name = str(parameters["door_name"])
            area_id = str(parameters["area_id"])
            area_name = str(parameters["area_name"])
            entity_id = str(parameters["entity_id"])
            timeout_seconds = int(parameters["timeout_seconds"])
            condition = self._normalize_condition(parameters.get("condition"))
        except (KeyError, TypeError, ValueError) as exc:
            self.hass_app.log(
                f"Invalid Safety Doors configuration for {name}: {exc}",
                level="ERROR",
            )
            return False

        monitored_entities = [entity_id]
        if condition is not None:
            monitored_entities.append(condition["entity_id"])

        mechanism = SafetyMechanism(
            hass_app=self.hass_app,
            callback=self.sm_safety_door_open_timeout,
            name=name,
            isEnabled=False,
            monitored_entities=list(dict.fromkeys(monitored_entities)),
        )
        mechanism.sm_args.update(
            {
                "door_name": door_name,
                "area_id": area_id,
                "area_name": area_name,
                "entity_id": entity_id,
                "timeout_seconds": timeout_seconds,
                "condition": condition,
            }
        )
        self.safety_mechanisms[name] = mechanism
        self.symptom_states[name] = FaultState.NOT_TESTED
        self._door_runtime[name] = DoorRuntime()

        mqtt_entity_id = self.mqtt_entities.register_sensor(
            f"sensor.safety_door_{door_name}",
            f"Safety Door: {door_name}",
            icon="mdi:door",
            entity_category="diagnostic",
        )
        self._mqtt_entity_ids[name] = mqtt_entity_id
        return True

    def enable_safety_mechanism(self, name: str, state: SMState) -> bool:
        """Enable or disable monitoring for a configured door."""
        mechanism = self.safety_mechanisms.get(name)
        if mechanism is None:
            self.hass_app.log(
                f"Safety mechanism {name} not found", level="ERROR"
            )
            return False
        if state == SMState.ENABLED:
            mechanism.isEnabled = True
            return True
        if state == SMState.DISABLED:
            mechanism.isEnabled = False
            self._cancel_timer(name)
            return True

        self.hass_app.log(
            f"Invalid state {state} for safety mechanism {name}", level="ERROR"
        )
        return False

    def sm_safety_door_open_timeout(self, sm: SafetyMechanism) -> bool:
        """Evaluate whether one door has remained open beyond its timeout."""
        if not sm.isEnabled:
            return False

        runtime = self._door_runtime[sm.name]
        now = self._now()
        timeout_seconds = int(sm.sm_args["timeout_seconds"])
        condition_result, condition_state, condition_last_changed = (
            self._read_condition_state(sm)
        )
        door_state, door_last_changed = self._read_door_state(
            sm.sm_args["entity_id"]
        )

        if condition_result == "blocked":
            self._cancel_timer(sm.name)
            runtime.opened_at = None
            runtime.active = False
            self._publish_symptom(
                sm,
                FaultState.CLEARED,
                elapsed_seconds=0,
                condition_state=condition_state,
            )
            self._publish_door_state(
                sm,
                state="blocked",
                door_state=door_state,
                condition_result=condition_result,
                condition_state=condition_state,
                now=now,
            )
            return False

        if condition_result == "unavailable":
            self._cancel_timer(sm.name)
            runtime.opened_at = None
            self._publish_door_state(
                sm,
                state="unavailable",
                door_state=door_state,
                condition_result=condition_result,
                condition_state=condition_state,
                now=now,
            )
            return runtime.active

        if door_state == "unavailable":
            self._cancel_timer(sm.name)
            self._publish_door_state(
                sm,
                state="unavailable",
                door_state=door_state,
                condition_result=condition_result,
                condition_state=condition_state,
                now=now,
            )
            return runtime.active

        if door_state == "closed":
            self._cancel_timer(sm.name)
            runtime.opened_at = None
            runtime.active = False
            self._publish_symptom(
                sm,
                FaultState.CLEARED,
                elapsed_seconds=0,
                condition_state=condition_state,
            )
            self._publish_door_state(
                sm,
                state="inactive",
                door_state=door_state,
                condition_result=condition_result,
                condition_state=condition_state,
                now=now,
            )
            return False

        if runtime.opened_at is None:
            active_since_candidates = [
                changed_at
                for changed_at in (door_last_changed, condition_last_changed)
                if changed_at is not None
            ]
            runtime.opened_at = (
                max(active_since_candidates) if active_since_candidates else now
            )
        elapsed_seconds = max(
            0, int((now - runtime.opened_at).total_seconds())
        )

        if elapsed_seconds >= timeout_seconds:
            self._cancel_timer(sm.name)
            runtime.active = True
            self._publish_symptom(
                sm,
                FaultState.SET,
                elapsed_seconds=elapsed_seconds,
                condition_state=condition_state,
            )
            self._publish_door_state(
                sm,
                state="active",
                door_state=door_state,
                condition_result=condition_result,
                condition_state=condition_state,
                now=now,
            )
            return True

        runtime.active = False
        self._publish_symptom(
            sm,
            FaultState.CLEARED,
            elapsed_seconds=elapsed_seconds,
            condition_state=condition_state,
        )
        self._schedule_timeout(sm, timeout_seconds - elapsed_seconds)
        self._publish_door_state(
            sm,
            state="inactive",
            door_state=door_state,
            condition_result=condition_result,
            condition_state=condition_state,
            now=now,
        )
        return False

    def _timeout_reached(self, **kwargs: Any) -> None:
        """Re-evaluate a door when its configured open timeout expires."""
        sm_name = str(kwargs["sm_name"])
        mechanism = self.safety_mechanisms.get(sm_name)
        if mechanism is None:
            return
        self._door_runtime[sm_name].timer_handle = None
        self.sm_safety_door_open_timeout(mechanism)

    def _schedule_timeout(
        self, mechanism: SafetyMechanism, delay_seconds: int
    ) -> None:
        self._cancel_timer(mechanism.name)
        self._door_runtime[mechanism.name].timer_handle = self.hass_app.run_in(
            self._timeout_reached,
            max(1, delay_seconds),
            sm_name=mechanism.name,
        )

    def _cancel_timer(self, sm_name: str) -> None:
        runtime = self._door_runtime.get(sm_name)
        if runtime is None or runtime.timer_handle is None:
            return
        handle = runtime.timer_handle
        runtime.timer_handle = None
        try:
            self.hass_app.cancel_timer(handle)
        except Exception as exc:
            self.hass_app.log(
                f"Unable to cancel Safety Doors timer {sm_name}: {exc}",
                level="WARNING",
            )

    def _publish_symptom(
        self,
        mechanism: SafetyMechanism,
        state: FaultState,
        *,
        elapsed_seconds: int,
        condition_state: str | None,
    ) -> None:
        if self.symptom_states.get(mechanism.name) == state:
            return
        self.symptom_states[mechanism.name] = state
        additional_info = {
            "location": str(mechanism.sm_args["area_name"]),
            "doors": str(mechanism.sm_args["door_name"]),
            "source_entity": str(mechanism.sm_args["entity_id"]),
            "open_duration_seconds": str(elapsed_seconds),
        }
        condition = mechanism.sm_args.get("condition")
        if isinstance(condition, dict):
            additional_info["condition_entity"] = str(condition["entity_id"])
            additional_info["condition_state"] = str(condition_state or "")
        self.event_bus.publish(
            "symptom",
            symptom_id=mechanism.name,
            state=state,
            additional_info=additional_info,
        )

    def _publish_door_state(
        self,
        mechanism: SafetyMechanism,
        *,
        state: str,
        door_state: str,
        condition_result: str,
        condition_state: str | None,
        now: datetime,
    ) -> None:
        runtime = self._door_runtime[mechanism.name]
        opened_at = runtime.opened_at
        elapsed_seconds = (
            max(0, int((now - opened_at).total_seconds()))
            if opened_at is not None
            else 0
        )
        timeout_seconds = int(mechanism.sm_args["timeout_seconds"])
        condition = mechanism.sm_args.get("condition")
        condition_attributes = {
            "condition_entity": None,
            "condition_state": None,
            "condition_result": "not_configured",
            "condition_pass_states": [],
            "condition_blocked_states": [],
        }
        if isinstance(condition, dict):
            condition_attributes = {
                "condition_entity": condition["entity_id"],
                "condition_state": condition_state,
                "condition_result": condition_result,
                "condition_pass_states": condition["pass_states"],
                "condition_blocked_states": condition["blocked_states"],
            }
        self.mqtt_entities.publish_sensor_state(
            self._mqtt_entity_ids[mechanism.name],
            state,
            attributes={
                "attribution": "Managed by SafetyFunction",
                "description": "Configured door open-timeout monitor.",
                "door_name": mechanism.sm_args["door_name"],
                "area_id": mechanism.sm_args["area_id"],
                "area_name": mechanism.sm_args["area_name"],
                "door_state": door_state,
                "source_entity": mechanism.sm_args["entity_id"],
                "timeout_seconds": timeout_seconds,
                "open_duration_seconds": elapsed_seconds,
                "remaining_seconds": max(0, timeout_seconds - elapsed_seconds),
                "opened_at": opened_at.isoformat() if opened_at else None,
                **condition_attributes,
            },
        )

    def _read_condition_state(
        self, mechanism: SafetyMechanism
    ) -> tuple[str, str | None, datetime | None]:
        condition = mechanism.sm_args.get("condition")
        if not isinstance(condition, dict):
            return "pass", None, None

        entity_id = str(condition["entity_id"])
        try:
            raw_state = self.hass_app.get_state(entity_id, attribute="all")
        except Exception as exc:
            self.hass_app.log(
                f"Unable to read Safety Doors condition {entity_id}: {exc}",
                level="WARNING",
            )
            return "unavailable", "unavailable", None

        last_changed: datetime | None = None
        if isinstance(raw_state, dict):
            state = raw_state.get("state")
            last_changed = self._parse_datetime(raw_state.get("last_changed"))
        else:
            state = raw_state

        normalized = str(state or "").strip().lower()
        if normalized in condition["pass_states"]:
            return "pass", normalized, last_changed
        if normalized in condition["blocked_states"]:
            return "blocked", normalized, last_changed

        if normalized not in UNAVAILABLE_STATES:
            self.hass_app.log(
                f"Unsupported Safety Doors condition state '{state}' "
                f"for {entity_id}",
                level="WARNING",
            )
        return "unavailable", normalized or "unavailable", last_changed

    def _read_door_state(
        self, entity_id: str
    ) -> tuple[str, datetime | None]:
        raw_state = self.hass_app.get_state(entity_id, attribute="all")
        last_changed: datetime | None = None
        if isinstance(raw_state, dict):
            state = raw_state.get("state")
            last_changed = self._parse_datetime(raw_state.get("last_changed"))
        else:
            state = raw_state

        normalized = str(state or "").strip().lower()
        if normalized in OPEN_STATES:
            return "open", last_changed
        if normalized in CLOSED_STATES:
            return "closed", last_changed
        if normalized not in UNAVAILABLE_STATES:
            self.hass_app.log(
                f"Unsupported door state '{state}' for {entity_id}",
                level="WARNING",
            )
        return "unavailable", last_changed

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _normalize_condition(value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("condition must be a mapping")

        entity_id_value = value["entity_id"]
        pass_states_value = value["pass_states"]
        blocked_states_value = value["blocked_states"]
        if not isinstance(entity_id_value, str):
            raise ValueError("condition entity_id must be a string")
        if not isinstance(pass_states_value, list) or not isinstance(
            blocked_states_value, list
        ):
            raise ValueError(
                "condition pass_states and blocked_states must be lists"
            )

        entity_id = entity_id_value.strip()
        pass_states = [
            str(state).strip().lower() for state in pass_states_value
        ]
        blocked_states = [
            str(state).strip().lower() for state in blocked_states_value
        ]
        if not entity_id or not pass_states or not blocked_states:
            raise ValueError(
                "condition requires entity_id, pass_states and blocked_states"
            )
        if any(not state for state in pass_states + blocked_states):
            raise ValueError("condition states must not be empty")
        if set(pass_states) & set(blocked_states):
            raise ValueError(
                "condition pass_states and blocked_states must be disjoint"
            )
        return {
            "entity_id": entity_id,
            "pass_states": pass_states,
            "blocked_states": blocked_states,
        }

    @staticmethod
    def _symptom_name(door_name: str) -> str:
        return f"SafetyDoorOpenTimeout{door_name}"
