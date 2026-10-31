"""Publish read-only heating supervision, qualified faults and coverage evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import json
import math
import time
from typing import Any
from uuid import UUID, uuid4

from components.core.localization import Localizer
from components.core.entity_names import friendly_entity_name
from components.core.sqlite_state_store import SqliteStateDatabase
from components.core.types_common import FaultState, RecoveryAction, SMState, Symptom
from components.recovery_manager.manual_actions import manual_action
from components.safetycomponents.core.safety_component import (
    SafetyComponent,
    register_safety_component,
)
from components.safetycomponents.core.safety_mechanism import SafetyMechanism

from .engine import RULES, HeatingResult, observed_phase, supervise_inputs
from .inputs import HeatingInputReader, HeatingObservation
from .rules import HeatingRuleEngine
from .schema import COMPONENT_NAME, HeatingConfig, HeatingInput, TEMPERATURE_ROLES
from .state import compatible_contract, fingerprint, legacy_fingerprint


@dataclass
class HeatingLatch:
    """Keep activation independent of current evaluability and pending recovery."""

    active: bool = False
    pending_kind: str | None = None
    pending_since: float | None = None
    pending_observed_seconds: float | None = None
    status: str = "NOT_EVALUATED"
    reason: str = "collecting_samples"
    published: bool | None = None
    restore_pending: bool = False


@register_safety_component
class HeatingSystemMonitorComponent(SafetyComponent):
    """Consume generic configured signals; never issue heating device commands."""

    component_name = COMPONENT_NAME

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._config = HeatingConfig()
        self._reader = HeatingInputReader(self._read_state)
        self._bindings: dict[str, tuple[str, str, str]] = {}
        self._latches: dict[str, HeatingLatch] = {}
        self._fault_definitions: dict[str, dict[str, Any]] = {}
        self._incidents: dict[str, str] = {}
        self._incident_owners: dict[str, str] = {}
        self._sensor_ids: dict[str, str] = {}
        self._store: Any = None
        self._fingerprint = ""
        self._semantic_config: dict[str, Any] = {}
        self._engines: dict[str, HeatingRuleEngine] = {}
        self._quality_pending: dict[str, dict[str, float]] = {}
        self._restore_error: str | None = None
        self._save_error: str | None = None
        self._last_tick: float | None = None
        self._last_snapshot: dict[str, Any] | None = None
        self._evidence: dict[str, dict[str, Any]] = {}
        self._timer: Any = None
        self._sampling = False
        self._flushing_publications = False
        self._queued_publications: list[tuple[str, bool, dict[str, Any]]] = []
        self._queued_sensors: list[tuple[str, str, dict[str, Any]]] = []

    @classmethod
    def get_entity_dependencies(
        cls, component_cfg: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Declare component-owned sources without duplicating shared C-TEMP faults."""
        config = HeatingConfig.model_validate(component_cfg)
        dependencies = []
        for key, system in config.systems.items():
            bindings: list[tuple[str, HeatingInput]] = [
                (role, binding) for role, binding in system.inputs.items()
            ]
            bindings += [
                (f"{room_key}{role}", binding)
                for room_key, room in system.rooms.items()
                for role, binding in room.inputs.items()
            ]
            for role, binding in bindings:
                if binding.shared_temperature:
                    continue
                for suffix, entity_id in (
                    ("", binding.entity_id),
                    ("Time", binding.observed_at_entity_id),
                ):
                    if entity_id:
                        dependencies.append(
                            {
                                "key": f"Heating{key}{role.replace('_', '')}{suffix}",
                                "entity_id": entity_id,
                                "owner": cls.component_name,
                                "purpose": f"Heating input {role}",
                                "checks": {},
                                "fault_owner": "none",
                            }
                        )
        return dependencies

    def get_symptoms_data(
        self, modules: dict, component_cfg: dict[str, Any] | list[dict[str, Any]]
    ) -> tuple[dict[str, Symptom], dict[str, RecoveryAction]]:
        """Bind only selected installations and profile-enabled mechanisms."""
        self._config = HeatingConfig.model_validate(component_cfg)
        semantic_config = self._config.model_dump()
        for system in semantic_config["systems"].values():
            system.pop("friendly_name", None)
            for room in system["rooms"].values():
                room.pop("friendly_name", None)
        self._semantic_config = semantic_config
        self._fingerprint = fingerprint(semantic_config)
        database = getattr(self.hass_app, "state_database", None)
        if not isinstance(database, SqliteStateDatabase):
            raise ValueError(
                "Heating monitoring requires the shared durable state database"
            )
        self._store = database.store(
            "heating_monitor_state", self._config.state_file, max_bytes=1048576
        )
        symptoms: dict[str, Symptom] = {}
        recoveries: dict[str, RecoveryAction] = {}
        for key, system in self._config.systems.items():
            profile = self._config.profiles[system.profile]
            self._engines[key] = HeatingRuleEngine(
                profile,
                self._config.evaluation_interval_seconds,
                self._config.maximum_clock_drift_seconds,
            )
            for rule in profile.enabled_rules:
                room_keys = (
                    list(system.rooms)
                    if rule in {"R03", "R09"} and system.rooms
                    else [""]
                )
                for room_key in room_keys:
                    mechanism, fault, level = RULES[rule]
                    symptom_id = (
                        f"Heating_{mechanism.removeprefix('sm_hsm_')}_{key}"
                        + (f"_{room_key}" if room_key else "")
                    )
                    self._bindings[symptom_id] = (key, rule, room_key)
                    self._latches[symptom_id] = HeatingLatch()
                    symptoms[symptom_id] = Symptom(
                        module=modules[self.component_name],
                        name=symptom_id,
                        sm_name=mechanism,
                        parameters={
                            "installation_key": key,
                            "rule_key": rule,
                            "room_key": room_key,
                        },
                    )
                    definition = self._fault_definitions.setdefault(
                        fault,
                        {
                            "name": self._text(f"heating.fault.{fault}"),
                            "level": level,
                            "category": "D" if rule in {"R01", "R12", "R13"} else "H",
                            "related_sms": [],
                            "related_symptom_ids": [],
                            "shadows": [],
                        },
                    )
                    if mechanism not in definition["related_sms"]:
                        definition["related_sms"].append(mechanism)
                    definition["related_symptom_ids"].append(symptom_id)
                    recoveries[symptom_id] = manual_action(
                        f"Inspect{symptom_id}",
                        subject=system.friendly_name,
                        instruction_key="heating.guidance",
                        result_key="heating.recovery_result",
                        completion_condition="owner_clear",
                        manual_report_allowed=False,
                    )
            self._sensor_ids[key] = self.mqtt_entities.register_sensor(
                f"sensor.heating_system_{key.lower()}",
                system.friendly_name,
                state="degraded",
                attributes={"coverage": "partial", "phase": "unknown"},
                icon="mdi:radiator",
                entity_category="diagnostic",
            )
        self._restore()
        self._last_tick = self._monotonic()
        if self._config.systems:
            self._timer = self.hass_app.run_every(
                self._tick,
                self._now()
                + timedelta(seconds=self._config.evaluation_interval_seconds),
                self._config.evaluation_interval_seconds,
            )
        return symptoms, recoveries

    def get_fault_definitions(self) -> dict[str, dict[str, Any]]:
        """Return stable fault groups with explicitly bound symptom contributors."""
        return self._fault_definitions

    def init_safety_mechanism(self, sm_name: str, name: str, parameters: dict) -> bool:
        """Register a predicate callback without actuator or source listeners."""
        if name not in self._bindings or sm_name != RULES[self._bindings[name][1]][0]:
            return False
        self.safety_mechanisms[name] = SafetyMechanism(
            self.hass_app, self._evaluate_mechanism, name, False, monitored_entities=[]
        )
        self.symptom_states[name] = FaultState.NOT_TESTED
        return True

    def enable_safety_mechanism(self, name: str, state: SMState) -> bool:
        """Control evaluation eligibility while retaining active latches."""
        if name not in self.safety_mechanisms or state not in {
            SMState.ENABLED,
            SMState.DISABLED,
        }:
            return False
        self.safety_mechanisms[name].isEnabled = state == SMState.ENABLED
        return True

    def _evaluate_mechanism(
        self, mechanism: SafetyMechanism, entities_changes: dict | None = None
    ) -> bool:
        if entities_changes is not None:
            # Hypothetical recovery simulation must never fabricate a live result.
            return False
        self._tick()
        return mechanism.isEnabled

    def _tick(self, **_: Any) -> None:
        """Commit one coherent evaluation before publishing aggregate transitions."""
        previous = {name: replace(latch) for name, latch in self._latches.items()}
        incidents, owners = dict(self._incidents), dict(self._incident_owners)
        self._queued_publications = []
        self._queued_sensors = []
        self._sampling = True
        try:
            self._sample_tick()
        except Exception:
            self._latches, self._incidents, self._incident_owners = (
                previous,
                incidents,
                owners,
            )
            raise
        finally:
            self._sampling = False
        self._persist()
        if self._save_error:
            for name, latch in self._latches.items():
                if previous[name].active and not latch.active:
                    latch.active = True
                    latch.status = "UNEVALUABLE"
                    latch.reason = "storage_unavailable"
                self.event_bus.publish("evaluation_unavailable", symptom_id=name)
        # Pending/unavailable contributors have already invalidated their old
        # results. Publish current failures before any qualified group clears.
        self._flushing_publications = True
        try:
            for name, active, extra in sorted(
                self._queued_publications, key=lambda item: not item[1]
            ):
                if active or not self._save_error:
                    self._publish(name, active, extra)
        finally:
            self._flushing_publications = False
        for fault in list(self._incidents):
            if self._fault_positively_clear(fault):
                self._retire_incident(fault)
        for key, state, attributes in self._queued_sensors:
            attributes["persistence_error"] = bool(
                self._restore_error or self._save_error
            )
            selected = {
                name: latch
                for name, latch in self._latches.items()
                if self._bindings[name][0] == key
            }
            attributes["active_faults"] = list(
                dict.fromkeys(
                    RULES[self._bindings[name][1]][1]
                    for name, latch in selected.items()
                    if latch.active
                )
            )
            for row in attributes["rules"]:
                contributors = [
                    latch
                    for name, latch in selected.items()
                    if self._bindings[name][1] == row["key"]
                ]
                row["active"] = any(latch.active for latch in contributors)
                row["status"] = self._aggregate_status(contributors)
                if self._save_error and any(
                    latch.reason == "storage_unavailable" for latch in contributors
                ):
                    row["reasons"] = [self._text("heating.reason.storage_unavailable")]
            self.mqtt_entities.publish_sensor_state(
                self._sensor_ids[key], state=state, attributes=attributes
            )
        self.record_evaluation(
            success=not bool(self._restore_error or self._save_error)
        )

    def _sample_tick(self) -> None:
        now = self._now().timestamp()
        mono = self._monotonic()
        gap = self._last_tick is not None and (
            mono < self._last_tick
            or mono - self._last_tick > self._config.evaluation_interval_seconds * 2
        )
        self._last_tick = mono
        if self._restore_error:
            self.event_bus.publish(
                "app_health_persistence",
                store="heating_monitor_state",
                failed=True,
                operation="load",
            )
        for key, system in self._config.systems.items():
            engine = self._engines[key]
            engine.advance(now, mono)
            quality_causes: dict[str, str] = {}
            inputs: dict[str, HeatingObservation] = {
                role: self._reader.read(role, binding, now)
                for role, binding in system.inputs.items()
            }
            room_inputs: dict[str, dict[str, HeatingObservation]] = {
                room_key: {
                    role: self._reader.read(role, binding, now)
                    for role, binding in room.inputs.items()
                }
                for room_key, room in system.rooms.items()
            }
            all_inputs = {
                **inputs,
                **{
                    f"{room}.{role}": value
                    for room, values in room_inputs.items()
                    for role, value in values.items()
                },
            }
            # Evaluate specific rules before their quality supervisor.
            for symptom_id, (system_key, rule, room_key) in sorted(
                self._bindings.items(), key=lambda item: item[1][1] == "R01"
            ):
                if system_key != key:
                    continue
                mechanism = self.safety_mechanisms.get(symptom_id)
                if mechanism is None or not mechanism.isEnabled:
                    continue
                latch = self._latches[symptom_id]
                if gap:
                    latch.pending_since = None
                    latch.pending_kind = None
                    self._quality_pending.pop(symptom_id, None)
                if latch.restore_pending:
                    self._publish(symptom_id, True, {"restored": True})
                    latch.restore_pending = False
                evidence = {**inputs, **room_inputs.get(room_key, {})}
                if rule == "R01":
                    owned: set[str] = {
                        role
                        for role, binding in system.inputs.items()
                        if not binding.shared_temperature
                    }
                    owned.update(
                        f"{room}.{role}"
                        for room, values in system.rooms.items()
                        for role, binding in values.inputs.items()
                        if not binding.shared_temperature
                    )
                    evidence = {
                        role: item
                        for role, item in all_inputs.items()
                        if role in owned
                        or item.quality
                        in {"stale", "invalid_timestamp", "future", "replayed"}
                    }
                self._evidence[symptom_id] = {
                    "observed_inputs": {
                        role: {
                            "value": item.value,
                            "quality": item.quality,
                            "observed_at": item.observed_at,
                            "entity_id": item.entity_id,
                        }
                        for role, item in evidence.items()
                    },
                    "evaluated_at": now,
                    "profile": system.profile,
                }
                if rule == "R01":
                    outcome = self._supervision_outcome(
                        symptom_id,
                        evidence,
                        all_inputs,
                        owned,
                        quality_causes,
                        engine.clock_uncertain,
                        mono,
                    )
                else:
                    outcome = engine.evaluate(
                        rule, evidence, now, mono, key=symptom_id, active=latch.active
                    )
                    if outcome.quality_cause:
                        quality_causes[symptom_id] = outcome.quality_cause
                self._evidence[symptom_id]["need_budget"] = {
                    "onset_utc": outcome.onset_utc,
                    "elapsed_seconds": outcome.elapsed_seconds,
                    "remaining_seconds": outcome.remaining_seconds,
                    "reference_target": outcome.reference_target,
                }
                self._evidence[symptom_id]["output_window"] = dict(
                    outcome.window_evidence
                )
                if (
                    rule != "R01"
                    and (self._restore_error or self._save_error)
                    and not (rule in {"R10", "R11"} and outcome.violation is True)
                ):
                    outcome = HeatingResult(
                        rule == "R01" or None, "storage_unavailable"
                    )
                self._qualify(symptom_id, outcome, mono)
            selected = {
                symptom: latch
                for symptom, latch in self._latches.items()
                if self._bindings[symptom][0] == key
            }
            rules = []
            for rule in RULES:
                contributors = [
                    latch
                    for symptom, latch in selected.items()
                    if self._bindings[symptom][1] == rule
                ]
                rules.append(
                    {
                        "key": rule,
                        "level": RULES[rule][2],
                        "label": self._text(f"heating.rule.{rule}"),
                        "admission": "diagnostic_only"
                        if rule == "R01" and contributors
                        else "selected"
                        if contributors
                        else "excluded",
                        "status": self._aggregate_status(contributors),
                        "active": any(item.active for item in contributors),
                        "reasons": list(
                            dict.fromkeys(
                                (
                                    system.rooms[self._bindings[name][2]].friendly_name
                                    + ": "
                                    if self._bindings[name][2]
                                    else ""
                                )
                                + self._text(f"heating.reason.{item.reason}")
                                for name, item in selected.items()
                                if self._bindings[name][1] == rule
                            )
                        )
                        or [self._text("heating.reason.excluded")],
                    }
                )
            state = (
                "unavailable"
                if all(
                    item.quality not in {"valid", "availability_only"}
                    for item in all_inputs.values()
                )
                else "degraded"
            )
            self._queued_sensors.append(
                (
                    key,
                    state,
                    {
                        "state_label": self._text(f"heating.state.{state}"),
                        "phase": observed_phase(inputs),
                        "phase_label": self._text(
                            f"heating.phase.{observed_phase(inputs)}"
                        ),
                        "coverage": "partial",
                        "coverage_label": self._text("heating.coverage.partial"),
                        "rules": rules,
                        "active_faults": list(
                            dict.fromkeys(
                                RULES[self._bindings[symptom][1]][1]
                                for symptom, latch in selected.items()
                                if latch.active
                            )
                        ),
                        "inputs": [
                            {
                                "role": role,
                                "label": self._text(
                                    f"heating.input.{role.split('.')[-1]}"
                                ),
                                "entity_id": item.entity_id,
                                "source_name": friendly_entity_name(
                                    self.hass_app,
                                    item.entity_id,
                                    self._text(f"heating.input.{role.split('.')[-1]}"),
                                ),
                                "value_label": self._value_label(
                                    item.value, role.split(".")[-1]
                                ),
                                "value": item.value,
                                "quality": item.quality,
                                "quality_label": self._text(
                                    f"heating.quality.{item.quality}"
                                ),
                                "observed_at": datetime.fromtimestamp(
                                    item.observed_at, timezone.utc
                                ).isoformat()
                                if item.observed_at is not None
                                else None,
                            }
                            for role, item in all_inputs.items()
                        ],
                        "persistence_error": bool(
                            self._restore_error or self._save_error
                        ),
                    },
                )
            )

    def _qualify(self, symptom_id: str, outcome: HeatingResult, now: float) -> None:
        latch = self._latches[symptom_id]
        key, rule, _room = self._bindings[symptom_id]
        profile = self._config.profiles[self._config.systems[key].profile]
        policy = profile.rule_policy(rule) or profile
        latch.reason = outcome.reason
        latch.pending_observed_seconds = outcome.observed_qualification_seconds
        if outcome.violation is None:
            latch.pending_since = None
            latch.pending_kind = None
            latch.status = (
                "NOT_APPLICABLE"
                if outcome.reason == "not_applicable"
                else "INHIBITED"
                if outcome.reason
                in {
                    "request_allowance",
                    "starting_allowance",
                    "bounded_inhibition",
                    "target_changed",
                    "output_hysteresis",
                }
                else "UNEVALUABLE"
            )
            latch.published = None
            self.event_bus.publish("evaluation_unavailable", symptom_id=symptom_id)
            return
        violation = outcome.violation
        group_recovery_pending = (
            not violation
            and RULES[rule][1] in self._incidents
            and outcome.observed_qualification_seconds is not None
            and outcome.observed_qualification_seconds < policy.recovery_seconds
        )
        if violation == latch.active and not group_recovery_pending:
            latch.pending_since = None
            latch.pending_kind = None
            latch.status = "FAIL" if violation else "PASS"
            self._publish(symptom_id, violation, {})
            return
        kind = "failure" if violation else "recovery"
        if latch.pending_kind != kind or latch.pending_since is None:
            latch.pending_kind, latch.pending_since = kind, now
        delay = policy.failure_seconds if violation else policy.recovery_seconds
        elapsed = (
            outcome.observed_qualification_seconds
            if outcome.observed_qualification_seconds is not None
            else now - latch.pending_since
        )
        if elapsed >= delay:
            latch.active = violation
            latch.pending_since = None
            latch.pending_kind = None
            latch.status = "FAIL" if violation else "PASS"
            if violation:
                self._incidents.setdefault(
                    RULES[self._bindings[symptom_id][1]][1], str(uuid4())
                )
                self._incident_owners.setdefault(RULES[rule][1], symptom_id)
            self._persist()
            if not violation and self._save_error:
                latch.active = True
                latch.status = "UNEVALUABLE"
                self.event_bus.publish("evaluation_unavailable", symptom_id=symptom_id)
                return
            self._publish(symptom_id, violation, {})
        else:
            latch.status = "PENDING_FAILURE" if violation else "PENDING_RECOVERY"
            latch.published = None
            self.event_bus.publish(
                "evaluation_pending", symptom_id=symptom_id, violation=violation
            )

    def _supervision_outcome(
        self,
        symptom_id: str,
        evidence: dict[str, HeatingObservation],
        all_inputs: dict[str, HeatingObservation],
        owned: set[str],
        quality_causes: dict[str, str],
        clock_uncertain: bool,
        mono: float,
    ) -> HeatingResult:
        """Qualify each source independently; missing shared evidence cannot HEAL."""
        outcome = supervise_inputs(evidence)
        causes = {
            f"input:{role}"
            for role, item in evidence.items()
            if item.quality not in {"valid", "availability_only"}
            or role == "source_health"
            and item.value is False
        }
        causes.update(f"rule:{name}" for name in quality_causes)
        if clock_uncertain:
            causes.add("clock")
        if self._restore_error or self._save_error:
            causes.add("persistence")
        pending = self._quality_pending.setdefault(symptom_id, {})
        for cause in list(pending):
            if cause not in causes:
                pending.pop(cause)
        for cause in causes:
            pending.setdefault(cause, mono)
        latch = self._latches[symptom_id]
        if causes and not latch.active:
            latch.pending_kind = "failure"
            latch.pending_since = min(pending.values())
        if self._restore_error or self._save_error:
            return HeatingResult(True, "storage_unavailable")
        if clock_uncertain or quality_causes:
            return HeatingResult(
                True,
                "clock_uncertain"
                if clock_uncertain
                else next(iter(quality_causes.values())),
            )
        if (
            outcome.violation is False
            and latch.active
            and any(
                role not in owned and item.quality not in {"valid", "availability_only"}
                for role, item in all_inputs.items()
            )
        ):
            return HeatingResult(None, "unqualified_input")
        return outcome

    def _restore_quality_pending(self, pending: Any, expected: set[str]) -> None:
        """Restore valid observed duration, excluding unevaluated downtime."""
        if not isinstance(pending, dict) or set(pending) - expected:
            raise ValueError("invalid heating cause qualification")
        for name, causes in pending.items():
            if (
                self._bindings[name][1] != "R01"
                or not isinstance(causes, dict)
                or len(causes) > 2048
            ):
                raise ValueError("invalid heating cause registry")
            for cause, elapsed in causes.items():
                if (
                    not isinstance(cause, str)
                    or len(cause) > 200
                    or isinstance(elapsed, bool)
                    or not isinstance(elapsed, (int, float))
                    or not math.isfinite(elapsed)
                    or not 0 <= elapsed <= 1800
                ):
                    raise ValueError("invalid heating cause duration")
            self._quality_pending[name] = {
                cause: self._monotonic() - elapsed for cause, elapsed in causes.items()
            }
            for cause in causes:
                if cause.startswith("rule:"):
                    symptom = cause.removeprefix("rule:")
                    if symptom in self._bindings:
                        owner, rule, _ = self._bindings[symptom]
                        if rule in {"R05", "R06"}:
                            self._engines[owner].output.lost.add(symptom)
                        if rule in {"R08", "R09"}:
                            self._engines[owner].distribution.lost.add(symptom)

    def _publish(self, symptom_id: str, active: bool, extra: dict[str, Any]) -> None:
        if self._sampling:
            self._queued_publications.append((symptom_id, active, extra))
            return
        latch = self._latches[symptom_id]
        key, rule, room = self._bindings[symptom_id]
        fault = RULES[rule][1]
        if active:
            self._incidents.setdefault(
                fault,
                "" if extra.get("restored") and self._restore_error else str(uuid4()),
            )
            self._incident_owners.setdefault(fault, symptom_id)
        state = FaultState.SET if active else FaultState.CLEARED
        details = {
            "installation": self._config.systems[key].friendly_name,
            "rule_key": rule,
            "room_key": room,
            "room": self._config.systems[key].rooms[room].friendly_name if room else "",
            "incident_id": self._incidents.get(fault, ""),
            "recommendation": self._text("heating.guidance"),
            "reason": self._text(f"heating.reason.{latch.reason}"),
            **extra,
        }
        if latch.published == active:
            self.record_symptom_observation(symptom_id, state, details)
        else:
            self.event_bus.publish(
                "symptom",
                symptom_id=symptom_id,
                state=state,
                additional_info=details,
                diagnostic_evidence={
                    "heating": {**details, **self._evidence.get(symptom_id, {})},
                    "evaluation_status": latch.status,
                },
            )
        latch.published = active
        self.symptom_states[symptom_id] = state
        if not self._flushing_publications and self._fault_positively_clear(fault):
            self._retire_incident(fault)

    def _retire_incident(self, fault: str) -> None:
        """Discard recovery references only after the whole incident is clear."""
        self._incidents.pop(fault, None)
        self._incident_owners.pop(fault, None)
        for name, (owner, rule, _) in self._bindings.items():
            if RULES[rule][1] != fault:
                continue
            if rule in {"R10", "R11"}:
                self._engines[owner].episodes.pop(name, None)
            if rule == "R12":
                self._engines[owner].cycling.active_modes.pop(name, None)

    def _fault_positively_clear(self, fault: str) -> bool:
        """Keep the aggregate incident open until every contributor is positive."""
        return all(
            not item.active and item.status == "PASS"
            for name, item in self._latches.items()
            if RULES[self._bindings[name][1]][1] == fault
        )

    def _restore(self) -> None:
        try:
            with self._store.database.connect() as connection:
                existed = (
                    connection.execute(
                        "SELECT 1 FROM stores WHERE name=?", ("heating_monitor_state",)
                    ).fetchone()
                    is not None
                )
            snapshot = self._store.load()
            if existed and not snapshot:
                raise ValueError("previous heating state is missing")
            if snapshot:
                if snapshot.get("version") not in {1, 2} or not isinstance(
                    snapshot.get("latches"), dict
                ):
                    raise ValueError("unsupported heating state")
                # Restore known active conditions even when calibration changed;
                # a mismatch then blocks recovery until state is reconciled.
                for name, item in snapshot["latches"].items():
                    if isinstance(item, dict) and isinstance(item.get("active"), bool):
                        if name not in self._latches:
                            raise ValueError("removed heating contract requires review")
                        latch = self._latches[name]
                        latch.active = item["active"]
                        latch.restore_pending = latch.active
                        elapsed = item.get("pending_failure_seconds", 0)
                        if (
                            isinstance(elapsed, bool)
                            or not isinstance(elapsed, (int, float))
                            or not math.isfinite(elapsed)
                            or not 0 <= elapsed <= 1800
                        ):
                            raise ValueError("invalid heating qualification state")
                        if elapsed and self._bindings[name][1] not in {
                            "R05",
                            "R06",
                            "R08",
                            "R09",
                            "R12",
                        }:
                            latch.pending_kind = "failure"
                            latch.pending_since = self._monotonic() - elapsed
                    else:
                        raise ValueError("unrecognized heating latch")
                incidents = snapshot.get("incidents", {})
                if not isinstance(incidents, dict) or any(
                    not isinstance(value, str) for value in incidents.values()
                ):
                    raise ValueError("invalid heating incident state")
                self._incidents = incidents
                if snapshot["version"] == 1 and set(snapshot["latches"]) != set(
                    self._latches
                ):
                    raise ValueError("missing expected heating latches")
                for name, latch in self._latches.items():
                    if latch.active:
                        incident = self._incidents.get(
                            RULES[self._bindings[name][1]][1]
                        )
                        if (
                            not isinstance(incident, str)
                            or str(UUID(incident)) != incident
                        ):
                            raise ValueError(
                                "missing or invalid active heating incident"
                            )
                if snapshot["version"] == 1:
                    compatible = snapshot.get("fingerprint") in {
                        self._fingerprint,
                        legacy_fingerprint(self._semantic_config),
                    }
                    # V1 did not identify the failed constituent; its aggregate
                    # pending duration cannot qualify a different source.
                    for latch in self._latches.values():
                        latch.pending_since = None
                        latch.pending_kind = None
                else:
                    contract = snapshot.get("contract")
                    compatible = (
                        isinstance(contract, dict)
                        and snapshot.get("fingerprint") == fingerprint(contract)
                        and compatible_contract(contract, self._semantic_config)
                    )
                    engines = snapshot.get("engines")
                    if (
                        not isinstance(contract, dict)
                        or not isinstance(engines, dict)
                        or set(engines) != set(contract.get("systems", {}))
                    ):
                        raise ValueError("invalid heating budget registry")
                    for key, state in engines.items():
                        if key not in self._engines:
                            raise ValueError("removed heating budget owner")
                        allowed = {
                            name
                            for name, (owner, rule, _) in self._bindings.items()
                            if owner == key
                            and rule
                            in {
                                "R03",
                                "R04",
                                "R05",
                                "R06",
                                "R07",
                                "R08",
                                "R09",
                                "R10",
                                "R11",
                            }
                        }
                        cycling_keys = {
                            name
                            for name, (owner, rule, _) in self._bindings.items()
                            if owner == key and rule == "R12"
                        }
                        self._engines[key].restore(state, allowed, cycling_keys)
                        for name in cycling_keys:
                            if self._latches[name].active and not self._engines[
                                key
                            ].cycling.active_modes.get(name):
                                raise ValueError(
                                    "missing active heating cycling causes"
                                )
                    expected_old = self._contract_latches(contract)
                    if set(snapshot["latches"]) != expected_old:
                        raise ValueError("missing expected heating latches")
                    self._restore_quality_pending(
                        snapshot.get("quality_pending"), expected_old
                    )
                if not compatible:
                    raise ValueError(
                        "heating configuration changed; persisted evidence requires review"
                    )
                active_faults = {
                    RULES[self._bindings[name][1]][1]
                    for name, latch in self._latches.items()
                    if latch.active
                }
                owners = (
                    snapshot.get("incident_owners")
                    if snapshot["version"] == 2
                    else None
                )
                if owners is None:
                    self._incidents = {
                        key: value
                        for key, value in self._incidents.items()
                        if key in active_faults
                    }
                    self._incident_owners = {
                        fault: next(
                            name
                            for name, latch in self._latches.items()
                            if latch.active
                            and RULES[self._bindings[name][1]][1] == fault
                        )
                        for fault in self._incidents
                    }
                else:
                    if not isinstance(owners, dict) or set(owners) != set(
                        self._incidents
                    ):
                        raise ValueError("invalid heating aggregate owners")
                    for fault, owner in owners.items():
                        if (
                            owner not in self._latches
                            or RULES[self._bindings[owner][1]][1] != fault
                            or str(UUID(self._incidents[fault]))
                            != self._incidents[fault]
                        ):
                            raise ValueError("invalid heating aggregate identity")
                        if fault not in active_faults:
                            # FaultManager retained this incident while another
                            # contributor lacked positive clear evidence.
                            self._latches[owner].active = True
                            self._latches[owner].restore_pending = True
                    self._incident_owners = owners
                for name, (owner, rule, _) in self._bindings.items():
                    if RULES[rule][1] not in self._incidents:
                        if rule in {"R10", "R11"}:
                            self._engines[owner].episodes.pop(name, None)
                        if rule == "R12":
                            self._engines[owner].cycling.active_modes.pop(name, None)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self._restore_error = str(exc)
        self.event_bus.publish(
            "app_health_persistence",
            store="heating_monitor_state",
            failed=bool(self._restore_error),
            operation="load",
        )

    def _persist(self) -> None:
        if self._sampling or self._store is None or self._restore_error:
            return
        snapshot = {
            "version": 2,
            "fingerprint": self._fingerprint,
            "contract": self._semantic_config,
            "engines": {
                key: engine.snapshot() for key, engine in self._engines.items()
            },
            "quality_pending": {
                name: {
                    cause: max(
                        0,
                        min(
                            1800,
                            (
                                self._last_tick
                                if self._last_tick is not None
                                else self._monotonic()
                            )
                            - since,
                        ),
                    )
                    for cause, since in causes.items()
                }
                for name, causes in self._quality_pending.items()
            },
            "latches": {
                name: {
                    "active": item.active,
                    "pending_failure_seconds": max(
                        0,
                        min(
                            1800,
                            item.pending_observed_seconds
                            if item.pending_observed_seconds is not None
                            else (
                                self._last_tick
                                if self._last_tick is not None
                                else self._monotonic()
                            )
                            - item.pending_since,
                        ),
                    )
                    if item.pending_kind == "failure" and item.pending_since is not None
                    else 0,
                }
                for name, item in self._latches.items()
            },
            "incidents": {
                key: value
                for key, value in self._incidents.items()
                if not self._fault_positively_clear(key)
            },
            "incident_owners": {
                key: value
                for key, value in self._incident_owners.items()
                if key in self._incidents and not self._fault_positively_clear(key)
            },
        }
        if snapshot == self._last_snapshot and not self._save_error:
            return
        try:
            self._store.save(snapshot)
            self._last_snapshot = json.loads(json.dumps(snapshot))
            self._save_error = None
        except (OSError, ValueError) as exc:
            self._save_error = str(exc)
        self.event_bus.publish(
            "app_health_persistence",
            store="heating_monitor_state",
            failed=bool(self._save_error),
            operation="save",
        )

    def _text(self, key: str) -> str:
        localizer = getattr(self.hass_app, "localizer", None)
        return (localizer if isinstance(localizer, Localizer) else Localizer()).text(
            key
        )

    def _read_state(self, entity_id: str) -> Any:
        return self.hass_app.get_state(entity_id, attribute="all")

    def sm_hsm_supervision_loss(
        self, mechanism: SafetyMechanism, entities_changes: dict | None = None
    ) -> bool:
        """Evaluate admitted input diagnostics without implying thermal coverage."""
        return self._evaluate_mechanism(mechanism, entities_changes)

    def sm_hsm_device_fault(
        self, mechanism: SafetyMechanism, entities_changes: dict | None = None
    ) -> bool:
        """Evaluate a freshly classified current device fault."""
        return self._evaluate_mechanism(mechanism, entities_changes)

    def sm_hsm_missing_demand(
        self, mechanism: SafetyMechanism, entities_changes: dict | None = None
    ) -> bool:
        """Evaluate independent permitted room need without a heating request."""
        return self._evaluate_mechanism(mechanism, entities_changes)

    def sm_hsm_no_response(
        self, mechanism: SafetyMechanism, entities_changes: dict | None = None
    ) -> bool:
        """Evaluate commissioned CH response and its bounded allowances."""
        return self._evaluate_mechanism(mechanism, entities_changes)

    def sm_hsm_maintenance(
        self, mechanism: SafetyMechanism, entities_changes: dict | None = None
    ) -> bool:
        """Evaluate informational maintenance without restricting hazard checks."""
        return self._evaluate_mechanism(mechanism, entities_changes)

    def sm_hsm_no_flow_rise(
        self, mechanism: SafetyMechanism, entities_changes: dict | None = None
    ) -> bool:
        """Evaluate physical CH flow rise from qualified observation windows."""
        return self._evaluate_mechanism(mechanism, entities_changes)

    def sm_hsm_flow_tracking(
        self, mechanism: SafetyMechanism, entities_changes: dict | None = None
    ) -> bool:
        """Evaluate physical CH target deficit from qualified observation windows."""
        return self._evaluate_mechanism(mechanism, entities_changes)

    def sm_hsm_pump_mismatch(
        self, mechanism: SafetyMechanism, entities_changes: dict | None = None
    ) -> bool:
        """Evaluate the commissioned physical CH pump relationship."""
        return self._evaluate_mechanism(mechanism, entities_changes)

    def sm_hsm_flow_return(
        self, mechanism: SafetyMechanism, entities_changes: dict | None = None
    ) -> bool:
        """Evaluate loaded flow/return differential windows."""
        return self._evaluate_mechanism(mechanism, entities_changes)

    def sm_hsm_room_delivery(
        self, mechanism: SafetyMechanism, entities_changes: dict | None = None
    ) -> bool:
        """Evaluate physical delivery and the observed room response."""
        return self._evaluate_mechanism(mechanism, entities_changes)

    def sm_hsm_mode_overtemperature(
        self, mechanism: SafetyMechanism, entities_changes: dict | None = None
    ) -> bool:
        """Evaluate the reviewed physical envelope of the observed phase."""
        return self._evaluate_mechanism(mechanism, entities_changes)

    def sm_hsm_absolute_overtemperature(
        self, mechanism: SafetyMechanism, entities_changes: dict | None = None
    ) -> bool:
        """Evaluate the independent absolute physical temperature limit."""
        return self._evaluate_mechanism(mechanism, entities_changes)

    def sm_hsm_short_cycling(
        self, mechanism: SafetyMechanism, entities_changes: dict | None = None
    ) -> bool:
        """Evaluate informational CH/DHW cycling from covered observations."""
        return self._evaluate_mechanism(mechanism, entities_changes)

    def _value_label(self, value: Any, role: str) -> str:
        if isinstance(value, bool):
            return self._text("heating.value.on" if value else "heating.value.off")
        if isinstance(value, str):
            if role == "inhibition_reason":
                return self._text(f"heating.inhibition.{value}")
            if value in {"clear", "fault", "maintenance"}:
                return self._text(f"heating.value.{value}")
            return self._text(f"heating.phase.{value}")
        if isinstance(value, float):
            suffix = (
                " °C"
                if role in TEMPERATURE_ROLES
                else " %"
                if role == "power_percent"
                else " W"
                if role == "power_w"
                else ""
            )
            return f"{value:g}{suffix}"
        return (
            str(value)
            if value is not None
            else self._text("heating.quality.unavailable")
        )

    def stop(self) -> None:
        """Release the sampling timer and commit remaining durable state."""
        if self._timer is not None:
            self.hass_app.cancel_timer(self._timer)
            self._timer = None
        self._persist()

    @staticmethod
    def _aggregate_status(contributors: list[HeatingLatch]) -> str:
        for status in (
            "FAIL",
            "UNEVALUABLE",
            "PENDING_FAILURE",
            "PENDING_RECOVERY",
            "NOT_EVALUATED",
            "INHIBITED",
            "NOT_APPLICABLE",
            "PASS",
        ):
            if any(item.status == status for item in contributors):
                return status
        return "DISABLED"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _monotonic() -> float:
        return time.monotonic()

    @staticmethod
    def _contract_latches(contract: dict[str, Any]) -> set[str]:
        """Derive the old complete registry without trusting a saved latch list."""
        result = set()
        for key, system in contract["systems"].items():
            for rule in contract["profiles"][system["profile"]]["enabled_rules"]:
                rooms = (
                    list(system["rooms"])
                    if rule in {"R03", "R09"} and system["rooms"]
                    else [""]
                )
                for room in rooms:
                    result.add(
                        f"Heating_{RULES[rule][0].removeprefix('sm_hsm_')}_{key}"
                        + (f"_{room}" if room else "")
                    )
        return result
