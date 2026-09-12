"""Monitor internal binary smoke, flammable-gas, and CO detector alarms."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any, Callable

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

from .schema import COMPONENT_NAME
from .state_store import (
    InMemoryInternalEnvironmentStateStore,
    InternalEnvironmentStateStore,
    JsonInternalEnvironmentStateStore,
)

_STATE_VERSION = 1
_HAZARD_MECHANISMS = {
    "smoke": "sm_iehm_smoke",
    "flammable_gas": "sm_iehm_flammable_gas",
    "carbon_monoxide": "sm_iehm_carbon_monoxide",
}
_HEALTH_MECHANISM = "sm_iehm_detector_health"
_HAZARD_LABELS = {
    "smoke": "smoke",
    "flammable_gas": "flammable gas",
    "carbon_monoxide": "carbon monoxide",
}


@dataclass
class DetectorRuntime:
    """Mutable latches and timers for one configured detector channel."""

    key: str
    config: dict[str, Any]
    profile: dict[str, Any]
    alarm_active: bool = False
    health_active: bool = False
    alarm_timer: Any | None = None
    alarm_callback_running: bool = False
    health_timer: Any | None = None
    health_timer_target: str | None = None
    listener_handle: Any | None = None
    diagnostic_entity_id: str | None = None
    last_classification: str = "unevaluable"
    last_state: str | None = None
    last_observed_at: datetime | None = None
    last_authoritative_clear_at: datetime | None = None
    gas_switching_inhibited: bool = False


@register_safety_component
class InternalEnvironmentalHazardMonitorComponent(SafetyComponent):
    """Propagate each valid detector alarm independently without actuation."""

    component_name = COMPONENT_NAME

    @classmethod
    def get_entity_dependencies(
        cls, component_cfg: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Declare Group B inputs for shared entity-health diagnostics."""

        dependencies: list[dict[str, Any]] = []
        for detector_key, detector in component_cfg.get("detectors", {}).items():
            dependencies.append(
                {
                    "key": f"InternalEnvironment{detector_key}",
                    "entity_id": detector["entity_id"],
                    "owner": cls.component_name,
                    "purpose": (
                        f"{detector['hazard']} alarm input for {detector_key}"
                    ),
                    "checks": {},
                    # The component owns the stable R06 fault. EntityMonitor still
                    # publishes the individual Group B health record.
                    "fault_owner": "none",
                    "detection_budget_seconds": 60,
                    "area_id": detector.get("area_id"),
                    "area_name": detector.get("area_name"),
                }
            )
        return dependencies

    def __init__(
        self,
        hass_app: hass.Hass,
        common_entities: CommonEntities,
        event_bus: EventBus,
        mqtt_entities: MqttEntityManager,
    ) -> None:
        super().__init__(hass_app, common_entities, event_bus, mqtt_entities)
        self._detectors: dict[str, DetectorRuntime] = {}
        self._symptom_bindings: dict[str, tuple[str, str]] = {}
        self._entity_to_detectors: dict[str, list[str]] = {}
        self._state_store: InternalEnvironmentStateStore = (
            InMemoryInternalEnvironmentStateStore()
        )
        self._persistence_error: str | None = None
        self._health_failure_seconds = 5
        self._health_recovery_seconds = 60

    def get_symptoms_data(
        self,
        modules: dict[str, SafetyComponent],
        component_cfg: dict[str, Any],
    ) -> tuple[dict[str, Symptom], dict[str, RecoveryAction]]:
        """Build independent hazard and health symptoms for every detector."""

        self._health_failure_seconds = int(
            component_cfg["health_failure_debounce_seconds"]
        )
        self._health_recovery_seconds = int(
            component_cfg["health_recovery_debounce_seconds"]
        )
        persistence = component_cfg["persistence"]
        self._state_store = (
            JsonInternalEnvironmentStateStore(str(persistence["state_file"]))
            if persistence["enabled"]
            else InMemoryInternalEnvironmentStateStore()
        )

        profiles = component_cfg["profiles"]
        symptoms: dict[str, Symptom] = {}
        for detector_key, detector in component_cfg["detectors"].items():
            profile = dict(profiles[detector["profile"]])
            runtime = DetectorRuntime(
                key=detector_key,
                config=dict(detector),
                profile=profile,
            )
            self._detectors[detector_key] = runtime
            self._entity_to_detectors.setdefault(
                str(detector["entity_id"]), []
            ).append(detector_key)

            hazard = str(detector["hazard"])
            hazard_symptom = self._symptom_name(hazard, detector_key)
            health_symptom = self._symptom_name("detector_health", detector_key)
            for symptom_name, mechanism_name, kind in (
                (hazard_symptom, _HAZARD_MECHANISMS[hazard], "alarm"),
                (health_symptom, _HEALTH_MECHANISM, "health"),
            ):
                parameters = {
                    "detector_key": detector_key,
                    "kind": kind,
                }
                symptoms[symptom_name] = Symptom(
                    module=modules[self.component_name],
                    name=symptom_name,
                    parameters=parameters,
                    sm_name=mechanism_name,
                )
                self._symptom_bindings[symptom_name] = (detector_key, kind)

        self._restore_state()
        self.mqtt_entities.register_sensor(
            "sensor.internal_environment_summary",
            "Internal environment monitoring",
            state="degraded",
            attributes=self._summary_attributes(),
            icon="mdi:home-alert",
            entity_category="diagnostic",
        )
        return symptoms, {}

    def get_output_inhibitions(self) -> tuple[str, ...]:
        """Return persisted restrictions that must precede local output use."""

        if any(
            runtime.gas_switching_inhibited
            for runtime in self._detectors.values()
        ):
            return ("active_or_unresolved_flammable_gas",)
        return ()

    def init_safety_mechanism(
        self, sm_name: str, name: str, parameters: dict[str, Any]
    ) -> bool:
        """Initialize one hazard or detector-health symptom."""

        binding = self._symptom_bindings.get(name)
        if binding is None or name in self.safety_mechanisms:
            self.hass_app.log(f"Invalid internal hazard symptom {name}", level="ERROR")
            return False
        detector_key, kind = binding
        runtime = self._detectors[detector_key]
        expected = (
            _HAZARD_MECHANISMS[str(runtime.config["hazard"])]
            if kind == "alarm"
            else _HEALTH_MECHANISM
        )
        if sm_name != expected:
            self.hass_app.log(
                f"Invalid internal hazard mechanism {sm_name} for {name}",
                level="ERROR",
            )
            return False

        callback: Callable[..., bool] = getattr(self, sm_name)
        mechanism = SafetyMechanism(
            hass_app=self.hass_app,
            callback=callback,
            name=name,
            isEnabled=False,
            monitored_entities=[],
        )
        mechanism.sm_args.update(parameters)
        self.safety_mechanisms[name] = mechanism
        self.symptom_states[name] = FaultState.NOT_TESTED

        if runtime.listener_handle is None:
            runtime.listener_handle = self.hass_app.listen_state(
                self._entity_changed,
                str(runtime.config["entity_id"]),
                attribute="all",
            )
        if runtime.diagnostic_entity_id is None:
            runtime.diagnostic_entity_id = self.mqtt_entities.register_sensor(
                f"sensor.internal_environment_{self._slug(detector_key)}",
                str(runtime.config["friendly_name"]),
                state="degraded",
                attributes=self._diagnostic_attributes(runtime),
                icon=self._icon(str(runtime.config["hazard"])),
                entity_category="diagnostic",
            )
        return True

    def enable_safety_mechanism(self, name: str, state: SMState) -> bool:
        """Enable or disable one independent symptom evaluator."""

        mechanism = self.safety_mechanisms.get(name)
        binding = self._symptom_bindings.get(name)
        if mechanism is None or binding is None:
            return False
        detector_key, kind = binding
        if state == SMState.ENABLED:
            mechanism.isEnabled = True
            return True
        if state == SMState.DISABLED:
            mechanism.isEnabled = False
            self._cancel_timer(self._detectors[detector_key], kind)
            return True
        return False

    def sm_iehm_smoke(
        self,
        mechanism: SafetyMechanism,
        entities_changes: dict[str, str] | None = None,
    ) -> bool:
        """Evaluate one smoke detector alarm channel."""

        return self._evaluate_mechanism(mechanism, entities_changes)

    def sm_iehm_flammable_gas(
        self,
        mechanism: SafetyMechanism,
        entities_changes: dict[str, str] | None = None,
    ) -> bool:
        """Evaluate one flammable-gas detector alarm channel."""

        return self._evaluate_mechanism(mechanism, entities_changes)

    def sm_iehm_carbon_monoxide(
        self,
        mechanism: SafetyMechanism,
        entities_changes: dict[str, str] | None = None,
    ) -> bool:
        """Evaluate one carbon-monoxide detector alarm channel."""

        return self._evaluate_mechanism(mechanism, entities_changes)

    def sm_iehm_detector_health(
        self,
        mechanism: SafetyMechanism,
        entities_changes: dict[str, str] | None = None,
    ) -> bool:
        """Evaluate availability without interpreting an alarm as unhealthy."""

        return self._evaluate_mechanism(mechanism, entities_changes)

    def _evaluate_mechanism(
        self,
        mechanism: SafetyMechanism,
        entities_changes: dict[str, str] | None = None,
    ) -> bool:
        if not mechanism.isEnabled:
            return False
        detector_key, kind = self._symptom_bindings[mechanism.name]
        runtime = self._detectors[detector_key]
        entity_id = str(runtime.config["entity_id"])
        if entities_changes is not None:
            raw = entities_changes.get(entity_id, self._read_entity(entity_id))
            classification, _, _ = self._classify(runtime, raw)
            return (
                classification == "alarm"
                if kind == "alarm"
                else classification in {"unavailable", "unevaluable"}
            )

        raw = self._read_entity(entity_id)
        self._evaluate_runtime(runtime, raw, kinds={kind})
        return runtime.alarm_active if kind == "alarm" else runtime.health_active

    def _entity_changed(
        self,
        entity: str,
        _attribute: str,
        _old: Any,
        new: Any,
        **_kwargs: Any,
    ) -> None:
        """Latch the delivered assertion edge before any later state is read."""

        for detector_key in self._entity_to_detectors.get(entity, []):
            self._evaluate_runtime(
                self._detectors[detector_key], new, kinds={"alarm", "health"}
            )

    def _evaluate_runtime(
        self,
        runtime: DetectorRuntime,
        raw: Any,
        *,
        kinds: set[str],
    ) -> None:
        classification, normalized, observed_at = self._classify(runtime, raw)
        runtime.last_classification = classification
        runtime.last_state = normalized
        runtime.last_observed_at = observed_at

        if "alarm" in kinds and self._kind_enabled(runtime.key, "alarm"):
            self._evaluate_alarm(runtime, classification, observed_at)
        if "health" in kinds and self._kind_enabled(runtime.key, "health"):
            self._evaluate_health(runtime, classification, observed_at)
        self._publish_diagnostics(runtime)

    def _evaluate_alarm(
        self,
        runtime: DetectorRuntime,
        classification: str,
        observed_at: datetime,
    ) -> None:
        if classification == "alarm":
            self._cancel_timer(runtime, "alarm")
            runtime.alarm_active = True
            if runtime.config["hazard"] == "flammable_gas":
                runtime.gas_switching_inhibited = True
            self._publish_symptom(runtime, "alarm", FaultState.SET)
            self._persist_state()
            return

        if classification != "clear":
            self._cancel_timer(runtime, "alarm")
            if runtime.alarm_active:
                self._publish_symptom(runtime, "alarm", FaultState.SET)
            return

        runtime.last_authoritative_clear_at = observed_at
        if runtime.alarm_active:
            # Reassert restored state before beginning recovery qualification.
            self._publish_symptom(runtime, "alarm", FaultState.SET)
        self._schedule_alarm_clear(runtime, observed_at)

    def _evaluate_health(
        self,
        runtime: DetectorRuntime,
        classification: str,
        observed_at: datetime,
    ) -> None:
        unavailable = classification in {"unavailable", "unevaluable"}
        target = "set" if unavailable else "clear"
        delay = (
            self._health_failure_seconds
            if unavailable
            else self._health_recovery_seconds
        )
        desired_active = unavailable
        if runtime.health_active == desired_active:
            self._cancel_timer(runtime, "health")
            self._publish_symptom(
                runtime,
                "health",
                FaultState.SET if desired_active else FaultState.CLEARED,
            )
            return
        if delay == 0:
            self._apply_health_target(runtime, target)
            return
        if runtime.health_timer is not None and runtime.health_timer_target == target:
            return
        self._cancel_timer(runtime, "health")
        runtime.health_timer_target = target
        runtime.health_timer = self.hass_app.run_in(
            self._health_timer_elapsed,
            delay,
            detector_key=runtime.key,
            target=target,
            observed_at=observed_at.isoformat(),
        )

    def _schedule_alarm_clear(
        self, runtime: DetectorRuntime, observed_at: datetime
    ) -> None:
        if runtime.alarm_timer is not None:
            return
        duration = int(runtime.profile["clear_duration_seconds"])
        elapsed = max(0, int((self._now() - observed_at).total_seconds()))
        runtime.alarm_callback_running = True
        try:
            runtime.alarm_timer = self.hass_app.run_in(
                self._alarm_clear_elapsed,
                max(1, duration - elapsed),
                detector_key=runtime.key,
            )
        finally:
            runtime.alarm_callback_running = False

    def _alarm_clear_elapsed(self, **kwargs: Any) -> None:
        runtime = self._detectors.get(str(kwargs["detector_key"]))
        if runtime is None:
            return
        runtime.alarm_timer = None
        raw = self._read_entity(str(runtime.config["entity_id"]))
        classification, normalized, observed_at = self._classify(runtime, raw)
        runtime.last_classification = classification
        runtime.last_state = normalized
        runtime.last_observed_at = observed_at
        if classification != "clear":
            self._evaluate_runtime(runtime, raw, kinds={"alarm", "health"})
            return
        clear_since = runtime.last_authoritative_clear_at or observed_at
        duration = int(runtime.profile["clear_duration_seconds"])
        if self._now() - clear_since < timedelta(seconds=duration):
            # The lightweight test/runtime fallback may invoke run_in callbacks
            # synchronously. Do not recurse; a real scheduler callback reschedules.
            if runtime.alarm_callback_running:
                return
            self._schedule_alarm_clear(runtime, clear_since)
            return
        runtime.alarm_active = False
        self._publish_symptom(runtime, "alarm", FaultState.CLEARED)
        self._persist_state()
        self._publish_diagnostics(runtime)

    def _health_timer_elapsed(self, **kwargs: Any) -> None:
        runtime = self._detectors.get(str(kwargs["detector_key"]))
        if runtime is None:
            return
        target = str(kwargs["target"])
        runtime.health_timer = None
        runtime.health_timer_target = None
        raw = self._read_entity(str(runtime.config["entity_id"]))
        classification, normalized, observed_at = self._classify(runtime, raw)
        runtime.last_classification = classification
        runtime.last_state = normalized
        runtime.last_observed_at = observed_at
        currently_unavailable = classification in {"unavailable", "unevaluable"}
        if (target == "set") != currently_unavailable:
            self._evaluate_health(runtime, classification, observed_at)
            self._publish_diagnostics(runtime)
            return
        self._apply_health_target(runtime, target)
        self._publish_diagnostics(runtime)

    def _apply_health_target(self, runtime: DetectorRuntime, target: str) -> None:
        runtime.health_active = target == "set"
        self._publish_symptom(
            runtime,
            "health",
            FaultState.SET if runtime.health_active else FaultState.CLEARED,
        )
        self._persist_state()

    def _publish_symptom(
        self, runtime: DetectorRuntime, kind: str, state: FaultState
    ) -> None:
        hazard = str(runtime.config["hazard"])
        symptom_name = self._symptom_name(
            hazard if kind == "alarm" else "detector_health", runtime.key
        )
        if self.symptom_states.get(symptom_name) == state:
            return
        self.symptom_states[symptom_name] = state
        info = {
            "location": str(runtime.config.get("area_name", runtime.config["area_id"])),
            "detector": str(runtime.config["friendly_name"]),
            "detector_key": runtime.key,
            "source_entity": str(runtime.config["entity_id"]),
            "hazard": self._hazard_label(hazard),
            "detector_state": str(runtime.last_state or "unknown"),
            "assertion_status": (
                "confirmed" if state == FaultState.SET else "authoritative_clear"
            ),
        }
        if hazard == "flammable_gas":
            info["gas_identity"] = str(runtime.config["gas_identity"])
            info["switching_inhibited"] = str(
                runtime.gas_switching_inhibited
            ).lower()
        if kind == "alarm" and state == FaultState.SET:
            info["recommendation"] = self._guidance(hazard)
        if kind == "health":
            info["health_reason"] = runtime.last_classification
        self.event_bus.publish(
            "symptom",
            symptom_id=symptom_name,
            state=state,
            additional_info=info,
        )

    def _publish_diagnostics(self, runtime: DetectorRuntime) -> None:
        if runtime.diagnostic_entity_id is not None:
            state = "unavailable" if runtime.health_active else (
                "degraded"
                if runtime.last_classification in {"unavailable", "unevaluable"}
                else "healthy"
            )
            self.mqtt_entities.publish_sensor_state(
                runtime.diagnostic_entity_id,
                state,
                attributes=self._diagnostic_attributes(runtime),
            )
        self.mqtt_entities.publish_sensor_state(
            "sensor.internal_environment_summary",
            self._summary_state(),
            attributes=self._summary_attributes(),
        )

    def _diagnostic_attributes(self, runtime: DetectorRuntime) -> dict[str, Any]:
        return {
            "detector_key": runtime.key,
            "friendly_name": runtime.config["friendly_name"],
            "area_id": runtime.config["area_id"],
            "area_name": runtime.config.get("area_name"),
            "source_entity_id": runtime.config["entity_id"],
            "hazard": runtime.config["hazard"],
            "gas_identity": runtime.config.get("gas_identity"),
            "profile": runtime.config["profile"],
            "profile_version": runtime.profile["version"],
            "profile_provenance": runtime.profile["provenance"],
            "current_state": runtime.last_state,
            "classification": runtime.last_classification,
            "alarm_active": runtime.alarm_active,
            "health_fault_active": runtime.health_active,
            "pending_alarm_clear": runtime.alarm_timer is not None,
            "pending_health_transition": runtime.health_timer_target,
            "last_observed_at": (
                runtime.last_observed_at.isoformat()
                if runtime.last_observed_at is not None
                else None
            ),
            "last_authoritative_clear_at": (
                runtime.last_authoritative_clear_at.isoformat()
                if runtime.last_authoritative_clear_at is not None
                else None
            ),
            "gas_switching_inhibited": runtime.gas_switching_inhibited,
        }

    def _summary_state(self) -> str:
        if any(runtime.alarm_active for runtime in self._detectors.values()):
            return "active_hazard"
        if any(runtime.health_active for runtime in self._detectors.values()):
            return "unavailable"
        if any(
            runtime.last_classification in {"unavailable", "unevaluable"}
            for runtime in self._detectors.values()
        ):
            return "degraded"
        return "healthy"

    def _summary_attributes(self) -> dict[str, Any]:
        hazards = tuple(_HAZARD_MECHANISMS)
        return {
            "monitored_detectors": len(self._detectors),
            "monitored_channels": {
                hazard: sum(
                    runtime.config["hazard"] == hazard
                    for runtime in self._detectors.values()
                )
                for hazard in hazards
            },
            "active_hazards": sum(
                runtime.alarm_active for runtime in self._detectors.values()
            ),
            "unavailable_detectors": sum(
                runtime.health_active for runtime in self._detectors.values()
            ),
            "gas_switching_inhibited": any(
                runtime.gas_switching_inhibited
                for runtime in self._detectors.values()
            ),
            "persistence_error": self._persistence_error,
        }

    def _restore_state(self) -> None:
        try:
            snapshot = self._state_store.load()
            if not snapshot:
                return
            if int(snapshot.get("version", -1)) != _STATE_VERSION:
                raise ValueError("unsupported internal environment state version")
            stored = snapshot.get("detectors", {})
            if not isinstance(stored, dict):
                raise ValueError("detectors state must be an object")
            for key, runtime in self._detectors.items():
                item = stored.get(key)
                if not isinstance(item, dict):
                    continue
                runtime.alarm_active = bool(item.get("alarm_active", False))
                runtime.health_active = bool(item.get("health_active", False))
                runtime.gas_switching_inhibited = bool(
                    item.get("gas_switching_inhibited", False)
                )
                runtime.last_authoritative_clear_at = self._parse_datetime(
                    item.get("last_authoritative_clear_at")
                )
        except Exception as exc:
            self._persistence_error = str(exc)
            self.hass_app.log(
                f"Unable to restore internal environment state: {exc}",
                level="ERROR",
            )

    def _persist_state(self) -> None:
        snapshot = {
            "version": _STATE_VERSION,
            "updated_at": self._now().isoformat(),
            "detectors": {
                key: {
                    "alarm_active": runtime.alarm_active,
                    "health_active": runtime.health_active,
                    "gas_switching_inhibited": runtime.gas_switching_inhibited,
                    "last_authoritative_clear_at": (
                        runtime.last_authoritative_clear_at.isoformat()
                        if runtime.last_authoritative_clear_at is not None
                        else None
                    ),
                }
                for key, runtime in self._detectors.items()
            },
        }
        try:
            self._state_store.save(snapshot)
            self._persistence_error = None
        except Exception as exc:
            self._persistence_error = str(exc)
            self.hass_app.log(
                f"Unable to persist internal environment state: {exc}",
                level="ERROR",
            )

    def _kind_enabled(self, detector_key: str, kind: str) -> bool:
        symptom_name = self._symptom_name(
            (
                str(self._detectors[detector_key].config["hazard"])
                if kind == "alarm"
                else "detector_health"
            ),
            detector_key,
        )
        mechanism = self.safety_mechanisms.get(symptom_name)
        return bool(mechanism and mechanism.isEnabled)

    def _cancel_timer(self, runtime: DetectorRuntime, kind: str) -> None:
        attribute = "alarm_timer" if kind == "alarm" else "health_timer"
        handle = getattr(runtime, attribute)
        if handle is None:
            return
        setattr(runtime, attribute, None)
        if kind == "health":
            runtime.health_timer_target = None
        try:
            self.hass_app.cancel_timer(handle)
        except Exception as exc:
            self.hass_app.log(
                f"Unable to cancel internal hazard timer for {runtime.key}: {exc}",
                level="WARNING",
            )

    def _classify(
        self, runtime: DetectorRuntime, raw: Any
    ) -> tuple[str, str, datetime]:
        observed_at = self._now()
        state = raw
        if isinstance(raw, dict):
            state = raw.get("state")
            observed_at = (
                self._parse_datetime(raw.get("last_changed"))
                or self._parse_datetime(raw.get("last_updated"))
                or observed_at
            )
        normalized = str(state or "").strip().lower()
        if normalized in runtime.profile["alarm_states"]:
            return "alarm", normalized, observed_at
        if normalized in runtime.profile["clear_states"]:
            return "clear", normalized, observed_at
        if normalized in runtime.profile["test_states"]:
            return "test", normalized, observed_at
        if normalized in runtime.profile["unavailable_states"] or not normalized:
            return "unavailable", normalized or "unavailable", observed_at
        return "unevaluable", normalized, observed_at

    def _read_entity(self, entity_id: str) -> Any:
        try:
            return self.hass_app.get_state(entity_id, attribute="all")
        except Exception as exc:
            self.hass_app.log(
                f"Unable to read internal detector {entity_id}: {exc}",
                level="WARNING",
            )
            return None

    def _guidance(self, hazard: str) -> str:
        localizer = getattr(self.hass_app, "localizer", None)
        if localizer is not None:
            return str(localizer.text(f"hazard.guidance.{hazard}"))
        return {
            "smoke": "Leave the affected area and call emergency services.",
            "flammable_gas": (
                "Leave the affected area, avoid electrical switches, and call "
                "emergency services from a safe place."
            ),
            "carbon_monoxide": (
                "Leave the affected area immediately and call emergency services."
            ),
        }[hazard]

    def _hazard_label(self, hazard: str) -> str:
        localizer = getattr(self.hass_app, "localizer", None)
        if localizer is not None:
            return str(localizer.text(f"hazard.label.{hazard}"))
        return _HAZARD_LABELS[hazard]

    @staticmethod
    def _symptom_name(rule: str, detector_key: str) -> str:
        return f"InternalEnv_{rule}_{detector_key}"

    @staticmethod
    def _slug(value: str) -> str:
        separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
        return "_".join(
            part.lower() for part in re.findall(r"[A-Za-z0-9]+", separated)
        )

    @staticmethod
    def _icon(hazard: str) -> str:
        return {
            "smoke": "mdi:smoke-detector-alert",
            "flammable_gas": "mdi:gas-cylinder",
            "carbon_monoxide": "mdi:molecule-co",
        }[hazard]

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
