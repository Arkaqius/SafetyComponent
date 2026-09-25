"""Observe host and maintenance evidence without controlling household devices."""

from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from time import monotonic
from typing import Any, Mapping

from components.core.memory_pressure import MemoryPressureRule
from components.core.types_common import FaultState, SMState, Symptom

UPDATE_PRODUCTS = (
    "home_assistant_core",
    "home_assistant_os",
    "home_assistant_supervisor",
    "safety_component",
)
UPDATE_PRODUCT_NAMES = {
    "home_assistant_core": "Home Assistant Core",
    "home_assistant_os": "Home Assistant OS",
    "home_assistant_supervisor": "Home Assistant Supervisor",
    "safety_component": "SafetyComponent App",
}


class FunctionalSafetyMonitor:
    """Own L2 memory, L3 WAN, and L4 update/battery policy faults."""

    component_name = "FunctionalSafetyMonitor"
    summary_entity = "sensor.functional_safety_sources"

    def __init__(
        self,
        hass_app: Any,
        event_bus: Any,
        mqtt_entities: Any,
        bindings: Mapping[str, Any],
        policy: Mapping[str, Any],
        *,
        wan_entity: str | None,
        detector_names: Mapping[str, str] | None = None,
    ) -> None:
        self.hass_app = hass_app
        self.event_bus = event_bus
        self.mqtt_entities = mqtt_entities
        self.bindings = dict(bindings)
        self.policy = dict(policy)
        self.wan_entity = wan_entity
        self.detector_names = dict(detector_names or {})
        self.safety_mechanisms: dict[str, None] = {}
        self.symptom_states: dict[str, FaultState] = {}
        self._enabled: set[str] = set()
        self._fault_definitions: dict[str, dict[str, Any]] = {}
        self._timer_handle: Any = None
        self._wan_down_since: float | None = None
        self._wan_up_since: float | None = None
        self._wan_fault_active = False
        self._cpu_high_since: float | None = None
        self._cpu_recovery_since: float | None = None
        self._cpu_fault_active = False
        self._memory = MemoryPressureRule(
            low_available_mib=float(policy["memory_low_available_mib"]),
            recovery_available_mib=float(policy["memory_recovery_available_mib"]),
            high_psi_percent=float(policy["memory_high_psi_percent"]),
            recovery_psi_percent=float(policy["memory_recovery_psi_percent"]),
            qualification_seconds=float(policy["memory_qualification_seconds"]),
            recovery_seconds=float(policy["memory_recovery_seconds"]),
        )

    def get_symptoms_data(self, modules: Mapping[str, Any], _: Any) -> tuple[dict[str, Symptom], dict[str, Any]]:
        """Create stable policy symptoms only for configured sources."""

        localizer = getattr(self.hass_app, "localizer", None)
        def label(key: str, **values: str) -> str:
            return localizer.text(key, **values) if localizer else key

        fault_sources: list[tuple[str, int, str]] = []
        if self.bindings.get("host_memory"):
            fault_sources.append(("HostMemoryPressure", int(self.policy["memory_fault_level"]), label("fault.host_memory_pressure")))
        if self.bindings.get("host_cpu_entity"):
            fault_sources.append(("HostCpuPressure", int(self.policy["cpu_fault_level"]), label("fault.host_cpu_pressure")))
        if self.wan_entity:
            fault_sources.append(("WanUnavailable", int(self.policy["wan_fault_level"]), label("fault.wan_unavailable")))
        for product, entity in self.bindings.get("updates", {}).items():
            if entity:
                fault_sources.append((f"UpdateAvailable{self._pascal(product)}", int(self.policy["maintenance_fault_level"]), label("fault.update_available", product=UPDATE_PRODUCT_NAMES[product])))
        for device, binding in self.bindings.get("remote_batteries", {}).items():
            if binding.get("enabled", True):
                fault_sources.append((f"RemoteBatteryLow{device}", int(self.policy["maintenance_fault_level"]), label("fault.remote_battery_low", device=binding["friendly_name"])))
        for detector, friendly_name in self.detector_names.items():
            fault_sources.append((f"DetectorTestDue{detector}", int(self.policy["maintenance_fault_level"]), label("fault.detector_test_due", detector=friendly_name)))
        symptoms: dict[str, Symptom] = {}
        for fault, level, name in fault_sources:
            symptom_id = f"fsm_{fault}"
            mechanism = f"sm_fsm_{fault}"
            symptoms[symptom_id] = Symptom(
                name=symptom_id,
                sm_name=mechanism,
                module=modules[self.component_name],
                parameters={},
            )
            self._fault_definitions[fault] = {
                "name": name,
                "level": level,
                "related_sms": [mechanism],
                "shadows": [],
            }
        self.mqtt_entities.register_sensor(
            self.summary_entity,
            "Functional Safety Sources",
            state="unknown",
            icon="mdi:heart-pulse",
            entity_category="diagnostic",
        )
        return symptoms, {}

    def get_fault_definitions(self) -> dict[str, dict[str, Any]]:
        """Return dynamic fault definitions for configured policy sources."""

        return dict(self._fault_definitions)

    def get_inactive_fault_names(self) -> set[str]:
        """Keep every configured policy fault active in the catalog."""

        return set()

    def init_safety_mechanism(self, sm_name: str, name: str, parameters: dict[str, Any]) -> bool:
        """Register a policy symptom and start one sampling timer."""

        del parameters
        if sm_name != f"sm_{name}" or name not in {f"fsm_{fault}" for fault in self._fault_definitions}:
            return False
        self.safety_mechanisms[name] = None
        self.symptom_states[name] = FaultState.NOT_TESTED
        return True

    def start(self) -> None:
        """Begin periodic sampling after FaultManager enables symptoms."""

        self._timer_handle = self.hass_app.run_every(
            self.evaluate, "now", int(self.policy["evaluation_interval_seconds"])
        )
        self.evaluate()

    def enable_safety_mechanism(self, name: str, state: SMState) -> bool:
        """Enable or disable one diagnostic symptom."""

        if name not in self.safety_mechanisms:
            return False
        if state == SMState.ENABLED:
            self._enabled.add(name)
        else:
            self._enabled.discard(name)
        return True

    def __getattr__(self, name: str) -> Any:
        if name.startswith("sm_fsm_"):
            return self.evaluate
        raise AttributeError(name)

    def record_evaluation(self, *, success: bool = True) -> None:
        """Report completed policy evaluation independently of other components."""

        reporter = getattr(self.hass_app, "record_safety_evaluation", None)
        if callable(reporter):
            reporter(self.component_name, success=success)

    def observe_detector_test(self, detector: str, status: str) -> None:
        """Bridge durable test status into a maintenance fault without control."""

        if detector not in self.detector_names:
            return
        if status in {"due", "overdue", "failed"}:
            self._emit(f"DetectorTestDue{detector}", True)
        elif status == "current":
            self._emit(f"DetectorTestDue{detector}", False)

    def evaluate(self, _: Any = None, **__: Any) -> None:
        """Sample configured sources; unknown readings never heal active faults."""

        diagnostics: dict[str, Any] = {}
        host = self.bindings.get("host_memory")
        if host:
            available, available_reason = self._number(host["available_entity"], {"MiB": 1, "GiB": 1024, "MB": 0.953674, "GB": 953.674}, "memory")
            psi, psi_reason = self._number(host["psi_entity"], {"%": 1}, "psi")
            result = self._memory.observe(available, psi)
            diagnostics["memory"] = {
                "status": result.status,
                "available_mib": available,
                "psi_percent": psi,
                "reason": available_reason or psi_reason,
                "source_entities": [host["available_entity"], host["psi_entity"]],
                "scope": "installation_declared_host",
            }
            if result.evidence_valid:
                self._emit("HostMemoryPressure", result.fault_active)
        else:
            diagnostics["memory"] = {"status": "unknown", "reason": "not_configured"}

        diagnostics["cpu"] = self._evaluate_cpu()

        diagnostics["wan"] = self._evaluate_wan()
        diagnostics["updates"] = self._evaluate_updates()
        diagnostics["remote_batteries"] = self._evaluate_batteries()
        statuses = [diagnostics["memory"]["status"], diagnostics["cpu"]["status"], diagnostics["wan"]["status"]]
        statuses += [item["status"] for item in diagnostics["updates"].values()]
        statuses += [item["status"] for item in diagnostics["remote_batteries"].values()]
        overall = "attention" if any(status in {"active", "high", "low", "available", "offline"} for status in statuses) else "unknown" if "unknown" in statuses else "observed"
        self.mqtt_entities.publish_sensor_state(
            self.summary_entity,
            overall,
            attributes={"observed_at": datetime.now(timezone.utc).isoformat(), **diagnostics},
        )
        self.record_evaluation()

    def stop(self) -> None:
        """Cancel the sampling timer on clean shutdown."""

        if self._timer_handle is not None:
            cancel = getattr(self.hass_app, "cancel_timer", None)
            if callable(cancel):
                cancel(self._timer_handle)
            self._timer_handle = None

    def _evaluate_cpu(self) -> dict[str, Any]:
        entity = self.bindings.get("host_cpu_entity")
        if not entity:
            return {"status": "unknown", "reason": "not_configured"}
        percent, reason = self._number(entity, {"%": 1}, "cpu")
        if percent is None or percent > 100:
            self._cpu_high_since = None
            self._cpu_recovery_since = None
            return {"status": "unknown", "reason": reason or "invalid_value", "source_entity": entity}
        now = monotonic()
        if not self._cpu_fault_active:
            if percent >= self.policy["cpu_high_percent"]:
                self._cpu_high_since = self._cpu_high_since or now
                if now - self._cpu_high_since >= self.policy["cpu_qualification_seconds"]:
                    self._cpu_fault_active = True
                    self._emit("HostCpuPressure", True)
            else:
                self._cpu_high_since = None
        elif percent <= self.policy["cpu_recovery_percent"]:
            self._cpu_recovery_since = self._cpu_recovery_since or now
            if now - self._cpu_recovery_since >= self.policy["cpu_recovery_seconds"]:
                self._cpu_fault_active = False
                self._cpu_high_since = None
                self._cpu_recovery_since = None
                self._emit("HostCpuPressure", False)
        else:
            self._cpu_recovery_since = None
        status = "high" if self._cpu_fault_active else "qualifying" if self._cpu_high_since is not None else "normal"
        return {"status": status, "percent": percent, "source_entity": entity, "scope": "installation_declared_host"}

    def _evaluate_wan(self) -> dict[str, Any]:
        if not self.wan_entity:
            return {"status": "unknown", "reason": "not_configured"}
        snapshot = self._snapshot(self.wan_entity)
        state = str(snapshot.get("state", "")).lower()
        valid_state = state in {"on", "online", "connected", "off", "offline", "disconnected"}
        fresh = self._fresh(snapshot, "last_reported", "wan_stale_after_seconds", fallback="last_updated")
        if not valid_state or not fresh:
            self._wan_down_since = None
            self._wan_up_since = None
            return {"status": "unknown", "reason": "stale" if valid_state else "unavailable", "source_entity": self.wan_entity}
        now = monotonic()
        online = state in {"on", "online", "connected"}
        if online:
            self._wan_down_since = None
            if self._wan_fault_active:
                self._wan_up_since = self._wan_up_since or now
                if now - self._wan_up_since >= self.policy["wan_recovery_seconds"]:
                    self._wan_fault_active = False
                    self._emit("WanUnavailable", False)
            status = "recovering" if self._wan_fault_active else "online"
        else:
            self._wan_up_since = None
            if not self._wan_fault_active:
                self._wan_down_since = self._wan_down_since or now
                if now - self._wan_down_since >= self.policy["wan_qualification_seconds"]:
                    self._wan_fault_active = True
                    self._emit("WanUnavailable", True)
            status = "offline" if self._wan_fault_active else "qualifying"
        return {"status": status, "source_entity": self.wan_entity}

    def _evaluate_updates(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for product in UPDATE_PRODUCTS:
            entity = self.bindings.get("updates", {}).get(product)
            if not entity:
                results[product] = {"status": "unknown", "reason": "not_configured"}
                continue
            snapshot = self._snapshot(entity)
            state = str(snapshot.get("state", "")).lower()
            attrs = snapshot.get("attributes") or {}
            # last_updated can remain old while an update entity is polled;
            # only an explicit source refresh timestamp may establish freshness.
            fresh = self._fresh(snapshot, "last_reported", "update_stale_after_seconds")
            valid = state in {"on", "off"} and fresh
            status = "available" if valid and state == "on" else "current" if valid else "unknown"
            results[product] = {
                "status": status,
                "source_entity": entity,
                "installed_version": attrs.get("installed_version"),
                "latest_version": attrs.get("latest_version"),
                "observed_at": snapshot.get("last_reported"),
            }
            if valid:
                self._emit(f"UpdateAvailable{self._pascal(product)}", state == "on")
        return results

    def _evaluate_batteries(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for device, binding in self.bindings.get("remote_batteries", {}).items():
            if not binding.get("enabled", True):
                continue
            readings: list[bool | None] = []
            percentage = None
            if entity := binding.get("percentage_entity"):
                percentage, _ = self._number(entity, {"%": 1}, "battery")
                readings.append(None if percentage is None or percentage > 100 else percentage <= self.policy["battery_low_percent"])
            if entity := binding.get("low_entity"):
                snapshot = self._snapshot(entity)
                attrs = snapshot.get("attributes") or {}
                state = str(snapshot.get("state", "")).lower()
                readings.append(state == "on" if attrs.get("device_class") == "battery" and state in {"on", "off"} and self._fresh(snapshot, "last_reported", "battery_stale_after_seconds", fallback="last_updated") else None)
            status = "low" if True in readings else "unknown" if None in readings else "current"
            results[device] = {
                "status": status,
                "friendly_name": binding["friendly_name"],
                "percentage": percentage,
                "source_entities": [binding[key] for key in ("percentage_entity", "low_entity") if binding.get(key)],
            }
            if status != "unknown":
                self._emit(f"RemoteBatteryLow{device}", status == "low")
        return results

    def _emit(self, fault: str, active: bool) -> None:
        symptom_id = f"fsm_{fault}"
        if symptom_id not in self._enabled:
            return
        next_state = FaultState.SET if active else FaultState.CLEARED
        if self.symptom_states.get(symptom_id) == next_state:
            return
        self.symptom_states[symptom_id] = next_state
        self.event_bus.publish("symptom", symptom_id=symptom_id, state=next_state)

    def _snapshot(self, entity: str) -> dict[str, Any]:
        raw = self.hass_app.get_state(entity, attribute="all")
        return raw if isinstance(raw, dict) else {"state": raw, "attributes": {}}

    def _number(self, entity: str, units: Mapping[str, float], device_class: str) -> tuple[float | None, str | None]:
        snapshot = self._snapshot(entity)
        attrs = snapshot.get("attributes", {})
        allowed_classes = {"memory": {None, "data_size"}, "psi": {None}, "cpu": {None}, "battery": {"battery"}}
        if not isinstance(attrs, dict) or attrs.get("device_class") not in allowed_classes[device_class]:
            return None, "wrong_device_class"
        factor = units.get(str(attrs.get("unit_of_measurement", "")))
        if factor is None:
            return None, "wrong_unit"
        try:
            value = float(snapshot.get("state"))
        except (ValueError, TypeError):
            return None, "invalid_value"
        if not isfinite(value) or value < 0:
            return None, "invalid_value"
        freshness_key = "battery_stale_after_seconds" if device_class == "battery" else "resource_stale_after_seconds"
        if not self._fresh(snapshot, "last_reported", freshness_key, fallback="last_updated"):
            return None, "stale"
        return value * factor, None

    def _fresh(self, snapshot: Mapping[str, Any], field: str, policy_key: str, *, fallback: str | None = None) -> bool:
        timestamp = snapshot.get(field) or (snapshot.get(fallback) if fallback else None)
        if isinstance(timestamp, datetime):
            observed = timestamp
        elif isinstance(timestamp, str):
            try:
                observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                return False
        else:
            return False
        if observed.tzinfo is None:
            return False
        age = (datetime.now(timezone.utc) - observed).total_seconds()
        return 0 <= age <= self.policy[policy_key]

    @staticmethod
    def _pascal(value: str) -> str:
        return "".join(word.capitalize() for word in value.split("_"))
