"""Monitor Home Assistant entity dependencies and publish per-entity faults."""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
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

from .models import (
    CheckRuntime,
    EntityDependency,
    EntityHealthState,
    EntityRuntime,
    EntitySource,
    FaultOwner,
)

COMPONENT_NAME = "EntityMonitorComponent"
UNAVAILABLE_STATES = frozenset({"", "none", "unknown", "unavailable"})
CHECK_SUFFIXES = {
    "availability": "Availability",
    "freshness": "Freshness",
    "required_value": "RequiredValue",
    "allowed_values": "AllowedValues",
    "finite_number": "FiniteNumber",
    "numeric_range": "NumericRange",
    "rate_of_change": "RateOfChange",
}
HEALTH_SEVERITY = {
    EntityHealthState.HEALTHY: 0,
    EntityHealthState.DEGRADED: 1,
    EntityHealthState.STALE: 2,
    EntityHealthState.UNAVAILABLE: 3,
}


@register_safety_component
class EntityMonitorComponent(SafetyComponent):
    """Evaluate Group A/B entities without commanding Home Assistant."""

    component_name = COMPONENT_NAME

    def __init__(
        self,
        hass_app: hass.Hass,
        common_entities: CommonEntities,
        event_bus: EventBus,
        mqtt_entities: MqttEntityManager,
    ) -> None:
        super().__init__(hass_app, common_entities, event_bus, mqtt_entities)
        self._entities: dict[str, EntityRuntime] = {}
        self._symptom_to_check: dict[str, tuple[str, str]] = {}
        self._fault_definitions: dict[str, dict[str, Any]] = {}
        self._timer_handle: Any | None = None
        self._startup_at = self._now()
        self._policy: dict[str, Any] = {}

    def __getattr__(self, name: str) -> Callable[[SafetyMechanism], bool]:
        """Resolve deterministic per-entity safety-mechanism callbacks."""

        if name.startswith("sm_entity_health_"):
            return self._evaluate_mechanism
        raise AttributeError(name)

    def get_symptoms_data(
        self,
        modules: dict[str, SafetyComponent],
        component_cfg: dict[str, Any],
    ) -> tuple[dict[str, Symptom], dict[str, RecoveryAction]]:
        """Build one symptom per enabled check and one fault per owned entity."""

        self._policy = dict(component_cfg)
        self._startup_at = self._now()
        dependencies = self._merge_dependencies(
            [
                *component_cfg.get("explicit_entities", []),
                *component_cfg.get("component_entities", []),
            ]
        )
        symptoms: dict[str, Symptom] = {}

        self.mqtt_entities.register_sensor(
            "sensor.entity_monitor_summary",
            "Monitorowane encje",
            state="degraded" if dependencies else "healthy",
            attributes={
                "total": len(dependencies),
                "healthy": 0,
                "degraded": len(dependencies),
                "stale": 0,
                "unavailable": 0,
                "source_counts": {
                    "explicit": sum(
                        EntitySource.EXPLICIT in dependency.sources
                        for dependency in dependencies
                    ),
                    "component": sum(
                        EntitySource.COMPONENT in dependency.sources
                        for dependency in dependencies
                    ),
                    "mixed": sum(
                        len(dependency.sources) > 1 for dependency in dependencies
                    ),
                },
                "unhealthy_entities": [],
            },
            icon="mdi:database-eye",
            entity_category="diagnostic",
        )

        for dependency in dependencies:
            runtime = EntityRuntime(dependency=dependency)
            runtime.snapshot = self._read_snapshot(dependency.entity_id)
            runtime.diagnostic_entity_id = self.mqtt_entities.register_sensor(
                f"sensor.entity_health_{self._slug(dependency.key)}",
                self._friendly_name(runtime.snapshot, dependency),
                state="healthy",
                attributes=self._diagnostic_attributes(runtime),
                icon="mdi:database-check",
                entity_category="diagnostic",
            )
            self._entities[dependency.key] = runtime

            check_names = ["availability", *dependency.checks]
            mechanism_name = self._mechanism_name(dependency.key)
            related_symptoms: list[str] = []
            for check_name in check_names:
                symptom_name = self._symptom_name(dependency.key, check_name)
                related_symptoms.append(symptom_name)
                runtime.checks[check_name] = CheckRuntime()
                self._symptom_to_check[symptom_name] = (dependency.key, check_name)
                symptoms[symptom_name] = Symptom(
                    module=modules[self.component_name],
                    name=symptom_name,
                    parameters={
                        "entity_key": dependency.key,
                        "check_key": check_name,
                    },
                    sm_name=mechanism_name,
                )

            if dependency.fault_owner == FaultOwner.ENTITY_MONITOR:
                fault_name = self._fault_name(dependency.key)
                entity_name = self._friendly_name(runtime.snapshot, dependency)
                localizer = getattr(self.hass_app, "localizer", None)
                self._fault_definitions[fault_name] = {
                    "name": (
                        localizer.text("fault.entity_health", entity=entity_name)
                        if localizer is not None
                        else f"Entity problem: {entity_name}"
                    ),
                    "level": 3,
                    "related_sms": [mechanism_name],
                    "shadows": [],
                }

        self._publish_summary()
        return symptoms, {}

    def get_fault_definitions(self) -> dict[str, dict[str, Any]]:
        """Return deterministic dynamic fault definitions for FaultManager."""

        return dict(self._fault_definitions)

    def init_safety_mechanism(
        self, sm_name: str, name: str, parameters: dict[str, Any]
    ) -> bool:
        """Initialize one check mechanism and one listener per entity."""

        mapping = self._symptom_to_check.get(name)
        if mapping is None or sm_name != self._mechanism_name(mapping[0]):
            self.hass_app.log(f"Invalid Entity Monitor symptom {name}", level="ERROR")
            return False
        if name in self.safety_mechanisms:
            return False

        entity_key, _ = mapping
        runtime = self._entities[entity_key]
        self.safety_mechanisms[name] = SafetyMechanism(
            hass_app=self.hass_app,
            callback=self._evaluate_mechanism,
            name=name,
            isEnabled=False,
            monitored_entities=[],
        )
        self.safety_mechanisms[name].sm_args.update(parameters)
        self.symptom_states[name] = FaultState.NOT_TESTED

        if runtime.listener_handle is None:
            runtime.listener_handle = self.hass_app.listen_state(
                self._entity_changed, runtime.dependency.entity_id
            )
        if self._timer_handle is None:
            self._timer_handle = self.hass_app.run_every(
                self._tick,
                "now",
                int(self._policy["evaluation_interval_seconds"]),
            )
        return True

    def enable_safety_mechanism(self, name: str, state: SMState) -> bool:
        """Enable or disable one entity check."""

        mechanism = self.safety_mechanisms.get(name)
        if mechanism is None:
            return False
        if state == SMState.ENABLED:
            mechanism.isEnabled = True
            return True
        if state == SMState.DISABLED:
            mechanism.isEnabled = False
            return True
        return False

    def stop(self) -> None:
        """Cancel listeners and the periodic evaluation timer."""

        for runtime in self._entities.values():
            if runtime.listener_handle is not None:
                try:
                    self.hass_app.cancel_listen_state(runtime.listener_handle)
                except Exception:
                    pass
        if self._timer_handle is not None:
            try:
                self.hass_app.cancel_timer(self._timer_handle)
            except Exception:
                pass

    def _entity_changed(self, entity: str, *_: Any, **__: Any) -> None:
        """Evaluate the record associated with a changed Home Assistant entity."""

        for key, runtime in self._entities.items():
            if runtime.dependency.entity_id == entity:
                self._evaluate_entity(key)

    def _tick(self, **_: Any) -> None:
        """Evaluate elapsed freshness and debounce deadlines."""

        for key in self._entities:
            self._evaluate_entity(key)

    def _evaluate_mechanism(self, mechanism: SafetyMechanism) -> bool:
        """Evaluate the entity containing the enabled check mechanism."""

        if not mechanism.isEnabled:
            return False
        entity_key = str(mechanism.sm_args["entity_key"])
        self._evaluate_entity(entity_key)
        check_key = str(mechanism.sm_args["check_key"])
        return self._entities[entity_key].checks[check_key].active

    def _evaluate_entity(self, entity_key: str) -> None:
        runtime = self._entities[entity_key]
        runtime.snapshot = self._read_snapshot(runtime.dependency.entity_id)
        now = self._now()
        results: dict[str, tuple[bool | None, str, Any]] = {}
        availability = self._check_availability(runtime.snapshot)
        results["availability"] = availability

        for check_name, check_cfg in runtime.dependency.checks.items():
            results[check_name] = self._evaluate_check(
                check_name,
                check_cfg,
                runtime,
                now,
                available=availability[0] is False,
            )

        if results and all(result[0] is False for result in results.values()):
            runtime.last_valid_value = (runtime.snapshot or {}).get("state")
            runtime.last_valid_at = now

        for check_name, result in results.items():
            symptom_name = self._symptom_name(entity_key, check_name)
            mechanism = self.safety_mechanisms.get(symptom_name)
            if mechanism is None or not mechanism.isEnabled:
                continue
            self._apply_result(runtime, check_name, result, now)

        self._publish_entity(runtime)
        self._publish_summary()

    def _apply_result(
        self,
        runtime: EntityRuntime,
        check_name: str,
        result: tuple[bool | None, str, Any],
        now: datetime,
    ) -> None:
        failing, reason, observed = result
        state = runtime.checks[check_name]
        state.reason = reason
        state.observed_value = observed
        state.evaluated_at = now
        if failing is None:
            state.result = "unevaluable"
            return

        symptom_name = self._symptom_name(runtime.dependency.key, check_name)
        if failing:
            state.pending_recovery_since = None
            if state.active:
                state.result = "failed"
                return
            if state.pending_failure_since is None:
                state.pending_failure_since = now
            elapsed = (now - state.pending_failure_since).total_seconds()
            state.result = "pending_failure"
            if elapsed >= runtime.dependency.failure_debounce_seconds:
                state.active = True
                state.result = "failed"
                self.symptom_states[symptom_name] = FaultState.SET
                self.event_bus.publish(
                    "symptom",
                    symptom_id=symptom_name,
                    state=FaultState.SET,
                    additional_info=self._symptom_context(runtime, check_name, state),
                )
            return

        state.pending_failure_since = None
        if not state.active and self.symptom_states.get(symptom_name) == FaultState.CLEARED:
            state.result = "passed"
            return
        if state.pending_recovery_since is None:
            state.pending_recovery_since = now
        elapsed = (now - state.pending_recovery_since).total_seconds()
        state.result = "pending_recovery"
        if elapsed >= runtime.dependency.recovery_debounce_seconds:
            state.active = False
            state.result = "passed"
            self.symptom_states[symptom_name] = FaultState.CLEARED
            self.event_bus.publish(
                "symptom",
                symptom_id=symptom_name,
                state=FaultState.CLEARED,
                additional_info=self._symptom_context(runtime, check_name, state),
            )

    def _evaluate_check(
        self,
        check_name: str,
        config: dict[str, Any],
        runtime: EntityRuntime,
        now: datetime,
        *,
        available: bool,
    ) -> tuple[bool | None, str, Any]:
        if not available:
            return None, "entity_unavailable", None
        snapshot = runtime.snapshot or {}
        if check_name == "freshness":
            startup_grace = int(self._policy.get("startup_grace_seconds", 0))
            if (now - self._startup_at).total_seconds() < startup_grace:
                return None, "startup_grace", None
            source = str(config["timestamp_source"])
            timestamp = self._timestamp_value(snapshot, source)
            if timestamp is None:
                return None, "timestamp_unavailable", None
            age = max(0.0, (now - timestamp).total_seconds())
            maximum = float(config["max_silence_seconds"])
            return age > maximum, "freshness_expired" if age > maximum else "fresh", round(age, 3)

        target = str(config.get("target", "state"))
        value, present = self._target_value(snapshot, target)
        if check_name == "required_value":
            missing = not present or value is None or (isinstance(value, str) and not value.strip())
            return missing, "required_value_missing" if missing else "required_value_present", value
        if not present or value is None or (isinstance(value, str) and not value.strip()):
            return None, "target_unavailable", value
        if check_name == "allowed_values":
            normalized = str(value).strip().lower()
            allowed = set(config["values"])
            return normalized not in allowed, "value_not_allowed" if normalized not in allowed else "value_allowed", value
        number = self._finite_number(value)
        if check_name == "finite_number":
            return number is None, "not_finite_number" if number is None else "finite_number", value
        if number is None:
            return None, "not_finite_number", value
        if check_name == "numeric_range":
            below = config.get("minimum") is not None and number < float(config["minimum"])
            above = config.get("maximum") is not None and number > float(config["maximum"])
            return below or above, "outside_numeric_range" if below or above else "inside_numeric_range", number
        if check_name == "rate_of_change":
            return self._evaluate_rate(runtime, target, number, config, snapshot, now)
        return None, "unsupported_check", value

    def _evaluate_rate(
        self,
        runtime: EntityRuntime,
        target: str,
        number: float,
        config: dict[str, Any],
        snapshot: dict[str, Any],
        now: datetime,
    ) -> tuple[bool | None, str, Any]:
        observed_at = self._timestamp_value(snapshot, "last_updated") or now
        samples = runtime.samples.setdefault(target, [])
        if not samples or samples[-1][0] != observed_at:
            samples.append((observed_at, number))
        cutoff = now - timedelta(seconds=int(config["window_seconds"]))
        samples[:] = [sample for sample in samples if sample[0] >= cutoff]
        if len(samples) < int(config.get("min_samples", 2)):
            return None, "insufficient_samples", None
        elapsed = (samples[-1][0] - samples[0][0]).total_seconds()
        if elapsed <= 0:
            return None, "insufficient_elapsed_time", None
        rate = (samples[-1][1] - samples[0][1]) / elapsed * 60.0
        rising = config.get("maximum_rise_per_minute") is not None and rate > float(config["maximum_rise_per_minute"])
        falling = config.get("maximum_fall_per_minute") is not None and rate < -float(config["maximum_fall_per_minute"])
        return rising or falling, "rate_outside_bounds" if rising or falling else "rate_inside_bounds", round(rate, 6)

    def _publish_entity(self, runtime: EntityRuntime) -> None:
        if runtime.diagnostic_entity_id is None:
            return
        health = self._health(runtime)
        self.mqtt_entities.publish_sensor_state(
            runtime.diagnostic_entity_id,
            health.value,
            attributes=self._diagnostic_attributes(runtime),
        )

    def _publish_summary(self) -> None:
        counts = {state.value: 0 for state in EntityHealthState}
        unhealthy: list[dict[str, Any]] = []
        for runtime in self._entities.values():
            health = self._health(runtime)
            counts[health.value] += 1
            if health != EntityHealthState.HEALTHY:
                unhealthy.append(
                    {
                        "entity_id": runtime.dependency.entity_id,
                        "entity_key": runtime.dependency.key,
                        "friendly_name": self._friendly_name(runtime.snapshot, runtime.dependency),
                        "health": health.value,
                        "failed_checks": [
                            name
                            for name, check in runtime.checks.items()
                            if check.active
                            or check.result in {"pending_failure", "failed"}
                        ],
                    }
                )
        summary_health = max(
            (self._health(runtime) for runtime in self._entities.values()),
            key=lambda item: HEALTH_SEVERITY[item],
            default=EntityHealthState.HEALTHY,
        )
        limit = int(self._policy.get("unhealthy_summary_limit", 32))
        source_counts = {
            "explicit": sum(
                EntitySource.EXPLICIT in runtime.dependency.sources
                for runtime in self._entities.values()
            ),
            "component": sum(
                EntitySource.COMPONENT in runtime.dependency.sources
                for runtime in self._entities.values()
            ),
            "mixed": sum(
                len(runtime.dependency.sources) > 1
                for runtime in self._entities.values()
            ),
        }
        source_health_counts = {
            source.value: {
                health.value: sum(
                    source in runtime.dependency.sources
                    and self._health(runtime) == health
                    for runtime in self._entities.values()
                )
                for health in EntityHealthState
            }
            for source in EntitySource
        }
        self.mqtt_entities.publish_sensor_state(
            "sensor.entity_monitor_summary",
            summary_health.value,
            attributes={
                "total": len(self._entities),
                **counts,
                "source_counts": source_counts,
                "source_health_counts": source_health_counts,
                "unhealthy_entities": unhealthy[:limit],
                "unhealthy_truncated": len(unhealthy) > limit,
            },
        )

    def _diagnostic_attributes(self, runtime: EntityRuntime) -> dict[str, Any]:
        snapshot = runtime.snapshot or {}
        dependency = runtime.dependency
        return {
            # Home Assistant removes the reserved ``entity_id`` attribute from
            # MQTT JSON attributes, so publish a non-reserved source reference.
            "source_entity_id": dependency.entity_id,
            "entity_id": dependency.entity_id,
            "entity_key": dependency.key,
            "friendly_name": self._friendly_name(snapshot, dependency),
            "source_groups": [source.value for source in sorted(dependency.sources, key=lambda item: item.value)],
            "owners": list(dependency.owners),
            "purposes": list(dependency.purposes),
            "fault_owner": dependency.fault_owner.value,
            "fault_name": self._fault_name(dependency.key) if dependency.fault_owner == FaultOwner.ENTITY_MONITOR else None,
            "area_id": dependency.area_id,
            "area_name": dependency.area_name,
            "device_id": (snapshot.get("attributes") or {}).get("device_id"),
            "current_state": snapshot.get("state"),
            "last_valid_value": runtime.last_valid_value,
            "last_valid_at": (
                runtime.last_valid_at.isoformat() if runtime.last_valid_at else None
            ),
            "last_changed": snapshot.get("last_changed"),
            "last_updated": snapshot.get("last_updated"),
            "failure_debounce_seconds": dependency.failure_debounce_seconds,
            "recovery_debounce_seconds": dependency.recovery_debounce_seconds,
            "detection_budget_seconds": dependency.detection_budget_seconds,
            "checks": [
                {
                    "check": name,
                    "result": state.result,
                    "reason": state.reason,
                    "observed_value": state.observed_value,
                    "evaluated_at": state.evaluated_at.isoformat() if state.evaluated_at else None,
                    "calibration": dependency.checks.get(name, {}),
                }
                for name, state in runtime.checks.items()
            ],
        }

    def _health(self, runtime: EntityRuntime) -> EntityHealthState:
        availability = runtime.checks.get("availability")
        if availability and (
            availability.active
            or availability.result in {"pending_failure", "failed"}
        ):
            return EntityHealthState.UNAVAILABLE
        freshness = runtime.checks.get("freshness")
        if freshness and (
            freshness.active or freshness.result in {"pending_failure", "failed"}
        ):
            return EntityHealthState.STALE
        if any(
            check.active or check.result in {"pending_failure", "failed"}
            for check in runtime.checks.values()
        ):
            return EntityHealthState.DEGRADED
        if any(check.result != "passed" for check in runtime.checks.values()):
            return EntityHealthState.DEGRADED
        return EntityHealthState.HEALTHY

    def _symptom_context(
        self, runtime: EntityRuntime, check_name: str, state: CheckRuntime
    ) -> dict[str, Any]:
        return {
            "entity_id": runtime.dependency.entity_id,
            "entity_key": runtime.dependency.key,
            "friendly_name": self._friendly_name(runtime.snapshot, runtime.dependency),
            "area_name": runtime.dependency.area_name or "",
            "failed_check": check_name,
            "reason": state.reason,
            "observed_value": state.observed_value,
            "current_value": (runtime.snapshot or {}).get("state"),
            "last_valid_value": runtime.last_valid_value,
            "last_valid_at": (
                runtime.last_valid_at.isoformat() if runtime.last_valid_at else ""
            ),
            "failure_started_at": (
                state.pending_failure_since.isoformat()
                if state.pending_failure_since
                else ""
            ),
            "evaluated_at": state.evaluated_at.isoformat() if state.evaluated_at else "",
        }

    def _merge_dependencies(self, raw_dependencies: list[dict[str, Any]]) -> list[EntityDependency]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in raw_dependencies:
            entity_id = str(item["entity_id"])
            grouped.setdefault(entity_id, []).append(item)
        merged: list[EntityDependency] = []
        for entity_id, items in grouped.items():
            explicit = [item for item in items if item.get("source") == "explicit"]
            primary = explicit[0] if explicit else items[0]
            checks: dict[str, dict[str, Any]] = {}
            for item in items:
                for name, config in item.get("checks", {}).items():
                    if name in checks and checks[name] != config:
                        raise ValueError(f"Conflicting {name} checks for {entity_id}")
                    checks[name] = dict(config)
            owners = tuple(dict.fromkeys(str(item["owner"]) for item in items))
            purposes = tuple(dict.fromkeys(str(item["purpose"]) for item in items))
            fault_owners = {FaultOwner(str(item.get("fault_owner", "entity_monitor"))) for item in items}
            if len(fault_owners) != 1:
                raise ValueError(f"Conflicting fault owners for {entity_id}")
            merged.append(
                EntityDependency(
                    key=str(primary["key"]),
                    entity_id=entity_id,
                    sources=frozenset(EntitySource(str(item["source"])) for item in items),
                    owners=owners,
                    purposes=purposes,
                    fault_owner=next(iter(fault_owners)),
                    checks=checks,
                    failure_debounce_seconds=min(int(item["failure_debounce_seconds"]) for item in items),
                    recovery_debounce_seconds=max(int(item["recovery_debounce_seconds"]) for item in items),
                    detection_budget_seconds=min(
                        (
                            int(item["detection_budget_seconds"])
                            for item in items
                            if item.get("detection_budget_seconds") is not None
                        ),
                        default=None,
                    ),
                    area_id=next((str(item["area_id"]) for item in items if item.get("area_id")), None),
                    area_name=next((str(item["area_name"]) for item in items if item.get("area_name")), None),
                )
            )
        return sorted(merged, key=lambda item: item.key.lower())

    def _read_snapshot(self, entity_id: str) -> dict[str, Any] | None:
        try:
            raw = self.hass_app.get_state(entity_id, attribute="all")
        except Exception:
            return None
        if raw is None:
            return None
        if isinstance(raw, dict):
            return {
                "state": raw.get("state"),
                "attributes": raw.get("attributes") if isinstance(raw.get("attributes"), dict) else {},
                "last_changed": raw.get("last_changed"),
                "last_updated": raw.get("last_updated"),
            }
        return {"state": raw, "attributes": {}, "last_changed": None, "last_updated": None}

    @staticmethod
    def _check_availability(snapshot: dict[str, Any] | None) -> tuple[bool, str, Any]:
        if snapshot is None:
            return True, "entity_missing", None
        state = snapshot.get("state")
        normalized = str(state).strip().lower() if state is not None else "none"
        failing = normalized in UNAVAILABLE_STATES
        return failing, "entity_unavailable" if failing else "entity_available", state

    @staticmethod
    def _target_value(snapshot: dict[str, Any], target: str) -> tuple[Any, bool]:
        if target == "state":
            return snapshot.get("state"), "state" in snapshot
        attributes = snapshot.get("attributes") or {}
        return attributes.get(target), target in attributes

    @classmethod
    def _timestamp_value(cls, snapshot: dict[str, Any], source: str) -> datetime | None:
        value = snapshot.get(source) if source in {"last_changed", "last_updated"} else (snapshot.get("attributes") or {}).get(source)
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
    def _finite_number(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _friendly_name(snapshot: dict[str, Any] | None, dependency: EntityDependency) -> str:
        if snapshot:
            friendly = (snapshot.get("attributes") or {}).get("friendly_name")
            if friendly:
                return str(friendly)
        return dependency.key

    @staticmethod
    def _pascal(value: str) -> str:
        return "".join(part[:1].upper() + part[1:] for part in re.findall(r"[A-Za-z0-9]+", value))

    @staticmethod
    def _slug(value: str) -> str:
        separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
        return "_".join(
            part.lower() for part in re.findall(r"[A-Za-z0-9]+", separated)
        )

    @classmethod
    def _mechanism_name(cls, entity_key: str) -> str:
        return f"sm_entity_health_{cls._slug(entity_key)}"

    @classmethod
    def _symptom_name(cls, entity_key: str, check_name: str) -> str:
        return f"EntityHealthFailure{cls._pascal(entity_key)}{CHECK_SUFFIXES[check_name]}"

    @classmethod
    def _fault_name(cls, entity_key: str) -> str:
        return f"EntityHealth{cls._pascal(entity_key)}"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
