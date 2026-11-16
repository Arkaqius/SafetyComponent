"""Monitor independent indoor smoke, gas, CO, and water-leak alarms."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import time
from typing import Any, Callable
from uuid import uuid4

import appdaemon.plugins.hass.hassapi as hass

from components.core.common_entities import CommonEntities
from components.core.event_bus import EventBus
from components.core.mqtt_entity_manager import MqttEntityManager
from components.core.sqlite_state_store import SqliteStateDatabase, state_database_path
from components.core.types_common import FaultState, OutcomeKind, RecoveryAction, SMState, Symptom
from components.recovery_manager.manual_actions import manual_action
from components.safetycomponents.core.safety_component import (
    SafetyComponent,
    SafetyMechanismResult,
    evaluation_entry,
    qualified_safety_mechanism_decorator,
    register_safety_component,
)
from components.safetycomponents.core.safety_mechanism import SafetyMechanism

from .schema import COMPONENT_NAME
from .observation import ClearAuthority, ClearCandidate, DetectorBinding, IndoorObservation, Provenance
from .state_store import (
    InMemoryInternalEnvironmentStateStore,
    InternalEnvironmentStateStore,
    IndoorStateOwner,
    MAX_BYTES,
)

_HAZARD_MECHANISMS = {
    "smoke": "sm_iehm_smoke",
    "flammable_gas": "sm_iehm_flammable_gas",
    "carbon_monoxide": "sm_iehm_carbon_monoxide",
    "water_leak": "sm_iehm_water_leak",
}
_HEALTH_MECHANISM = "sm_iehm_detector_health"
_HAZARD_LABELS = {
    "smoke": "smoke",
    "flammable_gas": "flammable gas",
    "carbon_monoxide": "carbon monoxide",
    "water_leak": "water leak",
}
_HAZARD_FAULTS = {
    "smoke": "InternalSmokeDetected",
    "flammable_gas": "InternalFlammableGasDetected",
    "carbon_monoxide": "InternalCarbonMonoxideDetected",
    "water_leak": "WaterLeakDetected",
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
    authority: ClearAuthority | None = None
    incident_id: str | None = None
    authority_scope_identity: tuple[Any, ...] | None = None
    record_id: str | None = None
    clear_pending: bool = False


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
        self._receiver_session = uuid4().hex
        self._monotonic: Callable[[], float] = time.monotonic
        self.own_event_listener("indoor:state_changed", self._source_event, "state_changed")
        self.own_event_listener("indoor:connected", self._source_session_changed, "plugin_started")
        self.own_event_listener("indoor:disconnected", self._source_session_changed, "plugin_stopped")

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
        database = getattr(self.hass_app, "state_database", None)
        if not isinstance(database, SqliteStateDatabase):
            database = SqliteStateDatabase(state_database_path(persistence["state_file"]))
        if persistence["enabled"]:
            self._state_store = database.store("internal_environment_state", persistence["state_file"], max_bytes=MAX_BYTES)
        else:
            self._state_store = InMemoryInternalEnvironmentStateStore()
        injected_owner = self.hass_app.__dict__.get("indoor_state_owner")
        self._owner = injected_owner if isinstance(injected_owner, IndoorStateOwner) else IndoorStateOwner(self._state_store)
        self._state_store = self._owner.store
        self._owner.begin()
        if injected_owner is None:
            self.own_interval("indoor:durability", self._drain_state, "now", 1)

        profiles = component_cfg["profiles"]
        symptoms: dict[str, Symptom] = {}
        recoveries: dict[str, RecoveryAction] = {}
        for detector_key, detector in component_cfg["detectors"].items():
            profile = dict(profiles[detector["profile"]])
            runtime = DetectorRuntime(
                key=detector_key,
                config=dict(detector),
                profile=profile,
                authority=ClearAuthority(DetectorBinding.from_config(detector_key, detector, profile), self._receiver_session),
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
                parameters: dict[str, Any] = {
                    "detector_key": detector_key,
                    "kind": kind,
                }
                if kind == "health":
                    parameters["detection_budget_seconds"] = 60
                symptoms[symptom_name] = Symptom(
                    module=modules[self.component_name],
                    name=symptom_name,
                    parameters=parameters,
                    sm_name=mechanism_name,
                )
                self._symptom_bindings[symptom_name] = (detector_key, kind)
                recoveries[symptom_name] = manual_action(
                    f"{'RespondTo' if kind == 'alarm' else 'Inspect'}{symptom_name}",
                    subject=str(detector["friendly_name"]),
                    instruction_key=(f"hazard.guidance.{hazard}" if kind == "alarm"
                                     else "recovery.inspect_detector"),
                    result_key=("recovery.result_hazard" if kind == "alarm"
                                else "recovery.result_detector"),
                    area_id=detector.get("area_id"),
                    area_name=detector.get("area_name"),
                    entity_id=str(detector["entity_id"]),
                    completion_condition="advisory" if kind == "alarm" else "owner_clear",
                    manual_report_allowed=kind == "health",
                    purpose="hazard_mitigation" if kind == "alarm" else "capability_repair",
                )

        self._restore_state()
        self.mqtt_entities.register_sensor(
            "sensor.internal_environment_summary",
            "Internal environment monitoring",
            state="degraded",
            attributes=self._summary_attributes(),
            icon="mdi:home-alert",
            entity_category="diagnostic",
        )
        return symptoms, recoveries

    def get_output_inhibitions(self) -> tuple[str, ...]:
        """Return persisted restrictions that must precede local output use."""

        if self._owner.gas_inhibited or any(
            runtime.gas_switching_inhibited
            for runtime in self._detectors.values()
        ):
            return ("active_or_unresolved_flammable_gas",)
        return ()

    def get_inactive_fault_names(self) -> set[str]:
        """Omit alarm faults for hazard channels not installed at this site."""

        configured_hazards = {
            str(runtime.config["hazard"]) for runtime in self._detectors.values()
        }
        configured_hazards.update(item.hazard for item in self._owner.records.values() if item.alarm_active and item.hazard is not None)
        if self._owner.history_unknown or any(item.alarm_active and item.hazard is None for item in self._owner.records.values()):
            return set()
        return {
            fault_name
            for hazard, fault_name in _HAZARD_FAULTS.items()
            if hazard not in configured_hazards
        }

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
            scope=self.scope.child(name),
            monitored_entities=[],
        )
        mechanism.sm_args.update(parameters)
        self.safety_mechanisms[name] = mechanism
        mechanism.on_invalidate = lambda: self._interrupt_channel(runtime, kind)
        mechanism.start()
        self.symptom_states[name] = FaultState.NOT_TESTED

        if runtime.listener_handle is None:
            runtime.listener_handle = self.own_state_listener(
                f"source:{runtime.config['entity_id']}",
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
            self.start()
            mechanism.start()
            mechanism.isEnabled = True
            return True
        if state == SMState.DISABLED:
            mechanism.isEnabled = False
            runtime = self._detectors[detector_key]
            self._cancel_timer(runtime, kind)
            if kind == "alarm" and runtime.authority is not None:
                self._cancel_pending_clear(runtime)
                runtime.authority.new_session(self._receiver_session)
                runtime.last_authoritative_clear_at = None
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

    def sm_iehm_water_leak(
        self,
        mechanism: SafetyMechanism,
        entities_changes: dict[str, str] | None = None,
    ) -> bool:
        """Evaluate one water-leak detector alarm channel without actuation."""

        return self._evaluate_mechanism(mechanism, entities_changes)

    def sm_iehm_detector_health(
        self,
        mechanism: SafetyMechanism,
        entities_changes: dict[str, str] | None = None,
    ) -> bool:
        """Evaluate availability without interpreting an alarm as unhealthy."""

        return self._evaluate_mechanism(mechanism, entities_changes)

    @qualified_safety_mechanism_decorator
    def _evaluate_mechanism(
        self,
        mechanism: SafetyMechanism,
        entities_changes: dict[str, str] | None = None,
    ) -> SafetyMechanismResult:
        if not mechanism.isEnabled:
            return SafetyMechanismResult(False, outcome_kind=OutcomeKind.DISABLED)
        detector_key, kind = self._symptom_bindings[mechanism.name]
        runtime = self._detectors[detector_key]
        entity_id = str(runtime.config["entity_id"])
        if entities_changes is not None:
            raw = entities_changes[entity_id] if entity_id in entities_changes else self._read_entity(entity_id)
            classification, _, _ = self._classify(runtime, raw)
            value = classification == "alarm" if kind == "alarm" else classification in {"unavailable", "unevaluable"}
            return SafetyMechanismResult(
                value, is_evaluable=kind == "health" or classification in {"alarm", "clear"},
                outcome_kind=OutcomeKind.INHIBITED if kind == "alarm" and classification == "test" else None,
                reason=classification,
            )

        raw = self._read_entity(entity_id)
        self._evaluate_runtime(runtime, raw, kinds={kind})
        return self._runtime_outcome(runtime, kind)

    def simulate(
        self, mechanism: SafetyMechanism, changes: dict[str, str], *, evaluator: Any = None,
    ) -> Any:
        """Use the typed shared detector kernel for every indoor public callback."""
        return super().simulate(mechanism, changes, evaluator=self._evaluate_mechanism)

    def _runtime_outcome(self, runtime: DetectorRuntime, kind: str) -> SafetyMechanismResult:
        """Separate alarm source authority from a valid detector-health failure."""
        alarm = kind == "alarm"
        active = runtime.alarm_active if alarm else runtime.health_active
        pending = runtime.alarm_timer if alarm else runtime.health_timer
        classification = runtime.last_classification
        return SafetyMechanismResult(
            active, is_evaluable=pending is None and (
                not alarm or classification in {"alarm", "clear"}
            ) and not (alarm and active and classification == "clear"),
            outcome_kind=OutcomeKind.INHIBITED if alarm and classification in {"test", "hush"} else None,
            reason="qualification_pending" if pending is not None else classification,
        )

    @evaluation_entry
    def _source_session_changed(self, event_name: str, _data: dict[str, Any], **_kwargs: Any) -> None:
        """Reconnect/initial sync destroys clear continuity, retaining danger."""
        self._receiver_session = uuid4().hex
        for runtime in self._detectors.values():
            self._cancel_timer(runtime, "alarm")
            self._cancel_pending_clear(runtime)
            runtime.last_authoritative_clear_at = None
            if runtime.authority is not None:
                runtime.authority.new_session(self._receiver_session, connected=event_name != "plugin_stopped")
            self._publish_diagnostics(runtime)

    @evaluation_entry
    def _source_event(self, _event_name: str, data: dict[str, Any], **_kwargs: Any) -> None:
        """Use the HASS event envelope for recovery; never synthesize source order."""
        for key in self._entity_to_detectors.get(str(data.get("entity_id")), []):
            runtime = self._detectors[key]
            if runtime.authority is None:
                continue
            observation = IndoorObservation.event(runtime.authority.binding, data,
                session=self._receiver_session, received=self._monotonic(), received_at=self._now())
            self._evaluate_runtime(runtime, data.get("new_state"), kinds={"alarm", "health"}, observation=observation)

    @evaluation_entry
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

    @evaluation_entry
    def _evaluate_runtime(
        self,
        runtime: DetectorRuntime,
        raw: Any,
        *,
        kinds: set[str],
        observation: IndoorObservation | None = None,
    ) -> None:
        classification, normalized, observed_at = self._classify(runtime, raw)
        runtime.last_classification = classification
        runtime.last_state = normalized
        runtime.last_observed_at = observed_at

        if "alarm" in kinds and self._kind_enabled(runtime.key, "alarm"):
            if runtime.authority is not None:
                identity = self._kind_mechanism(runtime, "alarm").scope._identity()
                if runtime.authority_scope_identity != identity:
                    self._cancel_timer(runtime, "alarm")
                    runtime.authority.new_session(self._receiver_session, connected=runtime.authority.connected)
                    runtime.authority_scope_identity = identity
                observation = observation or IndoorObservation.snapshot(runtime.authority.binding, raw,
                    provenance=Provenance.READBACK, session=self._receiver_session, received=self._monotonic(), received_at=self._now())
            self._evaluate_alarm(runtime, classification, observed_at, observation)
        if "health" in kinds and self._kind_enabled(runtime.key, "health"):
            self._evaluate_health(runtime, classification, observed_at)
        for kind in kinds:
            if self._kind_enabled(runtime.key, kind):
                self.observe_outcome(self._kind_mechanism(runtime, kind), self._runtime_outcome(runtime, kind))
        self._publish_diagnostics(runtime)
        self.record_evaluation()

    def _evaluate_alarm(
        self,
        runtime: DetectorRuntime,
        classification: str,
        observed_at: datetime,
        observation: IndoorObservation | None,
    ) -> None:
        if classification == "alarm" and not runtime.alarm_active:
            runtime.incident_id = uuid4().hex
        candidate = (runtime.authority.observe(observation, runtime.incident_id or "")
                     if runtime.authority is not None and observation is not None else None)
        if candidate is None:
            self._cancel_timer(runtime, "alarm")
            self._cancel_pending_clear(runtime)
            runtime.last_authoritative_clear_at = None
        if classification == "alarm":
            self._cancel_timer(runtime, "alarm")
            runtime.alarm_active = True
            if runtime.config["hazard"] == "flammable_gas":
                runtime.gas_switching_inhibited = True
            if runtime.authority is not None:
                try:
                    record = self._owner.set_alarm(runtime.authority.binding, {
                        "detector": str(runtime.config["friendly_name"])[:256],
                        "source_entity": str(runtime.config["entity_id"])[:255],
                    }, at=self._now())
                    runtime.record_id, runtime.incident_id = record.record_id, record.incident_id
                except (ValueError, TypeError):
                    self._owner.history_unknown = self._owner.gas_history_unknown = True
                    self._owner.persistence_error = "positive_identity_invalid"
                self._persistence_error = self._owner.persistence_error
            self._publish_symptom(runtime, "alarm", FaultState.SET)
            return

        if classification != "clear":
            self._cancel_timer(runtime, "alarm")
            if runtime.alarm_active:
                self._publish_symptom(runtime, "alarm", FaultState.SET)
            return

        if runtime.alarm_active:
            # Reassert restored state before beginning recovery qualification.
            self._publish_symptom(runtime, "alarm", FaultState.SET)
            if candidate is not None and not runtime.clear_pending:
                runtime.last_authoritative_clear_at = candidate.ha_clear_changed_at
                self._schedule_alarm_clear(runtime, candidate)
        else:
            self._publish_symptom(runtime, "alarm", FaultState.CLEARED)

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
        runtime.health_timer = self._kind_mechanism(runtime, "health").run_in(
            "qualification",
            self._health_timer_elapsed,
            delay,
            detector_key=runtime.key,
            target=target,
            observed_at=observed_at.isoformat(),
        )

    def _schedule_alarm_clear(
        self, runtime: DetectorRuntime, candidate: ClearCandidate
    ) -> None:
        if runtime.alarm_timer is not None:
            return
        runtime.alarm_callback_running = True
        try:
            runtime.alarm_timer = self._kind_mechanism(runtime, "alarm").run_in(
                "qualification",
                self._alarm_clear_elapsed,
                max(0.001, candidate.deadline_monotonic - self._monotonic()),
                detector_key=runtime.key,
                candidate_token=candidate.token,
            )
        finally:
            runtime.alarm_callback_running = False

    @evaluation_entry
    def _alarm_clear_elapsed(self, **kwargs: Any) -> None:
        runtime = self._detectors.get(str(kwargs["detector_key"]))
        if runtime is None:
            return
        authority = runtime.authority
        candidate = authority.candidate if authority is not None else None
        if authority is None or candidate is None or kwargs.get("candidate_token") != candidate.token:
            return
        mechanism = self._kind_mechanism(runtime, "alarm")
        identity = mechanism.scope._identity()
        if not mechanism.scope.eligible:
            return
        runtime.alarm_timer = None
        raw = self._read_entity(str(runtime.config["entity_id"]))
        if not mechanism.scope.eligible or mechanism.scope._identity() != identity:
            return
        classification, normalized, observed_at = self._classify(runtime, raw)
        runtime.last_classification = classification
        runtime.last_state = normalized
        runtime.last_observed_at = observed_at
        if classification != "clear":
            self._evaluate_runtime(runtime, raw, kinds={"alarm", "health"})
            return
        if self._monotonic() < candidate.deadline_monotonic:
            # The lightweight test/runtime fallback may invoke run_in callbacks
            # synchronously. Do not recurse; a real scheduler callback reschedules.
            if runtime.alarm_callback_running:
                return
            self._schedule_alarm_clear(runtime, candidate)
            return
        readback = IndoorObservation.snapshot(authority.binding, raw, provenance=Provenance.READBACK,
            session=self._receiver_session, received=self._monotonic(), received_at=self._now())
        if not authority.eligible(candidate, runtime.incident_id or "", self._monotonic(), readback):
            authority.candidate = None
            self._publish_diagnostics(runtime)
            return
        def eligible() -> bool:
            if not mechanism.scope.eligible or mechanism.scope._identity() != identity:
                return False
            latest = self._read_entity(str(runtime.config["entity_id"]))
            current = IndoorObservation.snapshot(authority.binding, latest, provenance=Provenance.READBACK,
                session=self._receiver_session, received=self._monotonic(), received_at=self._now())
            return bool(mechanism.scope.eligible and mechanism.scope._identity() == identity
                and authority.eligible(candidate, runtime.incident_id or "", self._monotonic(), current))
        if runtime.record_id is not None:
            runtime.clear_pending = self._owner.request_clear(runtime.record_id, candidate.token, eligible, candidate=candidate)
        self._persistence_error = self._owner.persistence_error
        self._publish_diagnostics(runtime)

    def _cancel_pending_clear(self, runtime: DetectorRuntime) -> None:
        if runtime.record_id is not None:
            self._owner.cancel_clear(runtime.record_id)
        runtime.clear_pending = False

    def _interrupt_channel(self, runtime: DetectorRuntime, kind: str) -> None:
        """Discard one child's timer and authority without cancelling shared ingress."""
        self._cancel_timer(runtime, kind)
        if kind == "alarm":
            self._cancel_pending_clear(runtime)
            if runtime.authority is not None:
                runtime.authority.new_session(self._receiver_session, connected=runtime.authority.connected)
            runtime.last_authoritative_clear_at = None

    def _drain_state(self, **_kwargs: Any) -> None:
        """Apply immutable successful write evidence on the evaluation owner only."""
        self.apply_durable_clears(self._owner.drain())

    @evaluation_entry
    def apply_durable_clears(self, record_ids: list[str]) -> None:
        """Emit HEAL only for a currently authorized exact durable CLEAR."""
        self._persistence_error = self._owner.persistence_error
        for runtime in self._detectors.values():
            if runtime.record_id in record_ids and runtime.clear_pending:
                runtime.alarm_active = False
                runtime.clear_pending = False
                if runtime.authority is not None:
                    runtime.authority.candidate = None
                self.observe_outcome(self._kind_mechanism(runtime, "alarm"), self._runtime_outcome(runtime, "alarm"))
                self._publish_symptom(runtime, "alarm", FaultState.CLEARED)
            self._publish_diagnostics(runtime)
        self.event_bus.publish("app_health_persistence", store="internal_environment_state",
            failed=self._persistence_error is not None, operation="save")

    @evaluation_entry
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
        self.observe_outcome(self._kind_mechanism(runtime, "health"), self._runtime_outcome(runtime, "health"))
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
            if (
                runtime.last_classification == "alarm" and state == FaultState.SET
            ) or (
                runtime.last_classification == "clear" and state == FaultState.CLEARED
            ):
                self.record_symptom_observation(symptom_name, state)
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
            "indoor_owner_generation": self._owner.revision,
            "indoor_incident_id": runtime.incident_id,
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
            "durable_clear_pending": runtime.clear_pending,
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
            "clear_authority": runtime.authority.reason if runtime.authority is not None else "unverified",
            "receiver_session": self._receiver_session,
        }

    def _summary_state(self) -> str:
        if any(runtime.alarm_active for runtime in self._detectors.values()) or any(item.alarm_active for item in self._owner.records.values()):
            return "active_hazard"
        if self._owner.history_unknown or self._owner.gas_history_unknown:
            return "degraded"
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
        localizer = getattr(self.hass_app, "localizer", None)
        return {
            **self._owner.projection({runtime.key: runtime.authority.binding.fingerprint
                for runtime in self._detectors.values() if runtime.authority is not None}, monitoring_enabled=self.scope.eligible,
                localize=localizer.text if localizer is not None else None),
            "monitored_detectors": len(self._detectors),
            "monitored_channels": {
                hazard: sum(
                    runtime.config["hazard"] == hazard
                    for runtime in self._detectors.values()
                )
                for hazard in hazards
            },
            "active_hazards": len({item.record_id for item in self._owner.records.values() if item.alarm_active}
                | {runtime.record_id or runtime.key for runtime in self._detectors.values() if runtime.alarm_active}),
            "unavailable_detectors": sum(
                runtime.health_active for runtime in self._detectors.values()
            ),
            "gas_switching_inhibited": self._owner.gas_inhibited or any(
                runtime.gas_switching_inhibited
                for runtime in self._detectors.values()
            ),
            "persistence_error": self._persistence_error,
            "retained_records_total": len(self._owner.records),
            "history_unknown": self._owner.history_unknown,
            "gas_inhibition_unknown": self._owner.gas_history_unknown,
        }

    def _restore_state(self) -> None:
        """Rehydrate only exact original binding, keeping all other owner records."""
        if self._owner.store is not self._state_store:
            self._owner = IndoorStateOwner(self._state_store)
            self._owner.begin()
        self._persistence_error = self._owner.persistence_error
        for runtime in self._detectors.values():
            record = self._owner.current_record(runtime.authority.binding) if runtime.authority is not None else None
            if record is not None:
                runtime.alarm_active = record.alarm_active
                runtime.health_active = record.health_active
                runtime.gas_switching_inhibited = record.gas_switching_inhibited
                runtime.incident_id, runtime.record_id = record.incident_id, record.record_id
            runtime.last_authoritative_clear_at = None
        self.event_bus.publish(
            "app_health_persistence", store="internal_environment_state",
            failed=self._persistence_error is not None, operation="load",
        )

    def _persist_state(self) -> None:
        """Queue the complete configuration-independent owner snapshot."""
        self._owner.store = self._state_store
        self._owner.persist()
        self._persistence_error = self._owner.persistence_error

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

    def _kind_mechanism(self, runtime: DetectorRuntime, kind: str) -> SafetyMechanism:
        """Resolve the child owning this detector's independent qualification."""
        name = self._symptom_name(
            str(runtime.config["hazard"]) if kind == "alarm" else "detector_health",
            runtime.key,
        )
        return self.safety_mechanisms[name]

    def stop(self) -> None:
        """Stop source ingress and qualifications while retaining danger and gas latch."""
        super().stop()
        self._receiver_session = uuid4().hex
        for runtime in self._detectors.values():
            self._cancel_pending_clear(runtime)
            runtime.alarm_timer = runtime.health_timer = runtime.listener_handle = None
            runtime.health_timer_target = None
            runtime.last_authoritative_clear_at = None
            if runtime.authority is not None:
                runtime.authority.new_session(self._receiver_session)

    def _cancel_timer(self, runtime: DetectorRuntime, kind: str) -> None:
        attribute = "alarm_timer" if kind == "alarm" else "health_timer"
        handle = getattr(runtime, attribute)
        if handle is None:
            return
        setattr(runtime, attribute, None)
        if kind == "health":
            runtime.health_timer_target = None
        self._kind_mechanism(runtime, kind).scope.cancel_handle(handle)

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
        if normalized in runtime.profile.get("hush_states", []):
            return "hush", normalized, observed_at
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
            "water_leak": (
                "Check the leak from a safe place and shut off water manually "
                "if it is safe to do so. Avoid wet electrical equipment."
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
            "water_leak": "mdi:water-alert",
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
