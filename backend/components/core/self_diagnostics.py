"""Route provider-adapter health into fault-owned diagnostic contributions.

The adapters continue to own polling, schemas, caches, and raw health. This
bridge owns only the Boolean fault contribution derived from each result.
"""

from __future__ import annotations

from typing import Any, Mapping

from components.core.event_bus import EventBus
from components.core.types_common import FaultState, SMState, Symptom
from components.external_apis.core.models import ApiResult, ProviderHealthState
from components.safetycomponents.core.safety_component import SafetyComponent
from components.safetycomponents.core.safety_mechanism import SafetyMechanism

PROVIDER_FAULTS: Mapping[str, str] = {
    "OpenMeteoWeatherApiComponent": "ExternalProviderUnavailableOpenMeteoWeather",
    "ImgwWarningsApiComponent": "ExternalProviderUnavailableImgwWarnings",
    "OpenMeteoAirQualityApiComponent": "ExternalProviderUnavailableOpenMeteoAirQuality",
}
PROVIDER_LABELS: Mapping[str, str] = {
    "OpenMeteoWeatherApiComponent": "Open-Meteo weather",
    "ImgwWarningsApiComponent": "IMGW warnings",
    "OpenMeteoAirQualityApiComponent": "Open-Meteo air quality",
}
APP_CAUSES = (
    "startup",
    "publication",
    "delivery",
    "local_output",
)
PERSISTENCE_STORES = (
    "notification_state", "recovery_state", "internal_environment_state",
    "periodic_test_state", "detector_test_state", "fault_evidence_state",
)


class SelfDiagnosticsComponent(SafetyComponent):
    """Convert provider and in-process App Health evidence into D faults."""

    component_name = "SelfDiagnosticsComponent"

    def __init__(
        self,
        hass_app: Any,
        common_entities: Any,
        event_bus: EventBus,
        mqtt_entities: Any,
        providers: Mapping[str, Any],
        *,
        persistence_stores: frozenset[str] = frozenset({
            "notification_state", "recovery_state"
        }),
        local_outputs_enabled: bool = True,
    ) -> None:
        super().__init__(hass_app, common_entities, event_bus, mqtt_entities)
        unknown = set(providers) - PROVIDER_FAULTS.keys()
        if unknown:
            raise ValueError(f"Provider diagnostics need explicit fault allocation: {sorted(unknown)}")
        self.providers = frozenset(providers)
        if not persistence_stores.issubset(PERSISTENCE_STORES):
            raise ValueError("Unknown App Health persistence store allocation")
        self.persistence_stores = persistence_stores
        self.enabled_app_causes = frozenset(
            cause for cause in APP_CAUSES
            if cause != "local_output" or local_outputs_enabled
        )
        self._fault_definitions: dict[str, dict[str, Any]] = {}
        self._observed: dict[str, bool | None] = {
            self._symptom_id(provider): None for provider in self.providers
        }
        self._observed.update({
            self._app_symptom_id(cause): None for cause in self.enabled_app_causes
        })
        self._observed.update({
            self._persistence_symptom_id(store): None for store in self.persistence_stores
        })
        self._app_contributions: dict[str, dict[str, bool | None]] = {
            cause: {} for cause in self.enabled_app_causes
        }
        self._persistence_operations: dict[str, dict[str, bool | None]] = {
            store: {} for store in self.persistence_stores
        }
        event_bus.subscribe("external_api_result", self.observe_provider, priority=-10)
        event_bus.subscribe("evaluation_exception", self.observe_evaluation_exception, priority=-10)
        event_bus.subscribe("evaluation_succeeded", self.observe_evaluation_success, priority=-10)
        event_bus.subscribe("app_health_persistence", self.observe_persistence, priority=-10)

    @staticmethod
    def _symptom_id(provider: str) -> str:
        return f"ProviderHealth{provider.removesuffix('ApiComponent')}"

    @staticmethod
    def _app_symptom_id(cause: str) -> str:
        return "AppHealth" + "".join(part.title() for part in cause.split("_"))

    @staticmethod
    def _persistence_symptom_id(store: str) -> str:
        return "AppHealthPersistence" + "".join(
            part.title() for part in store.split("_")
        )

    def get_symptoms_data(
        self, modules: dict[str, SafetyComponent], component_cfg: Any
    ) -> tuple[dict[str, Symptom], dict[str, Any]]:
        """Declare one installed D contributor and fault per enabled adapter."""

        symptoms: dict[str, Symptom] = {}
        localizer = getattr(self.hass_app, "localizer", None)
        for provider in sorted(self.providers):
            symptom_id = self._symptom_id(provider)
            fault_name = PROVIDER_FAULTS[provider]
            symptoms[symptom_id] = Symptom(
                symptom_id,
                "sm_provider_adapter_health",
                self,
                {"provider": provider},
            )
            self._fault_definitions[fault_name] = {
                "name": (
                    localizer.text(
                        "fault.external_provider_unavailable",
                        provider=PROVIDER_LABELS[provider],
                    )
                    if localizer is not None
                    else f"External provider unavailable: {PROVIDER_LABELS[provider]}"
                ),
                "related_sms": ["sm_provider_adapter_health"],
                "related_symptom_ids": [symptom_id],
                "level": 3,
                "category": "D",
            }
        app_ids = []
        for cause in APP_CAUSES:
            if cause not in self.enabled_app_causes:
                continue
            symptom_id = self._app_symptom_id(cause)
            symptoms[symptom_id] = Symptom(
                symptom_id,
                "sm_app_health",
                self,
                {"cause": cause},
            )
            app_ids.append(symptom_id)
        for store in sorted(self.persistence_stores):
            symptom_id = self._persistence_symptom_id(store)
            symptoms[symptom_id] = Symptom(
                symptom_id, "sm_app_health", self,
                {"cause": "persistence", "store": store},
            )
            app_ids.append(symptom_id)
        self._fault_definitions["SafetyAppHealth"] = {
            "name": (
                localizer.text("fault.safety_app_health")
                if localizer is not None
                else "Safety application health"
            ),
            "related_sms": ["sm_app_health"],
            "related_symptom_ids": app_ids,
            "level": 2,
            "category": "D",
        }
        return symptoms, {}

    def get_fault_definitions(self) -> dict[str, dict[str, Any]]:
        """Expose the exact installed provider fault catalog."""

        return dict(self._fault_definitions)

    def add_targeted_causes(
        self, evaluation_ids: set[str], recovery_ids: set[str]
    ) -> dict[str, Symptom]:
        """Allocate exact H evaluation and recovery contributors under App Health."""

        created: dict[str, Symptom] = {}
        app_fault = self._fault_definitions["SafetyAppHealth"]
        for cause, target_ids in (
            ("evaluation", evaluation_ids), ("recovery", recovery_ids)
        ):
            for target_id in sorted(target_ids):
                symptom_id = f"AppHealth{cause.title()}_{target_id}"
                created[symptom_id] = Symptom(
                    symptom_id, "sm_app_health", self,
                    {"cause": cause, "target_symptom_id": target_id},
                )
                self._observed[symptom_id] = None
                app_fault["related_symptom_ids"].append(symptom_id)
        return created

    def observe_evaluation_exception(self, *, symptom_id: str, **_: Any) -> None:
        """A thrown H predicate degrades only that evaluator."""

        self._observe_evaluation(symptom_id, True)

    def observe_evaluation_success(self, *, symptom_id: str, **_: Any) -> None:
        """A completed invocation clears its own technical failure only."""

        self._observe_evaluation(symptom_id, False)

    def _observe_evaluation(self, target_id: str, failed: bool) -> None:
        self._observe_targeted("evaluation", target_id, failed)

    def record_recovery(self, target_id: str, failed: bool) -> None:
        """Report the current shared recovery invocation status for one H owner."""

        self._observe_targeted("recovery", target_id, failed)

    def observe_persistence(
        self, *, store: str, failed: bool, operation: str = "io", **_: Any
    ) -> None:
        """Accept current storage evidence from a component-owned state store."""

        self.record_app_cause(
            "persistence", failed, detail=store, operation=operation
        )

    def _observe_targeted(self, cause: str, target_id: str, failed: bool) -> None:
        symptom_id = f"AppHealth{cause.title()}_{target_id}"
        if symptom_id not in self._observed or self._observed[symptom_id] is failed:
            return
        self._observed[symptom_id] = failed
        mechanism = self.safety_mechanisms.get(symptom_id)
        if mechanism is not None and mechanism.isEnabled:
            self._publish_state(symptom_id, failed, cause=cause, detail=target_id)

    def init_safety_mechanism(
        self, sm_name: str, name: str, parameters: dict[str, Any]
    ) -> bool:
        """Register an event-driven Boolean provider predicate."""

        if sm_name not in ("sm_provider_adapter_health", "sm_app_health") or name in self.safety_mechanisms:
            return False
        mechanism = SafetyMechanism(
            hass_app=self.hass_app,
            callback=lambda _: None,
            name=name,
            isEnabled=False,
            monitored_entities=[],
        )
        mechanism.sm_args.update(parameters)
        self.safety_mechanisms[name] = mechanism
        self.symptom_states[name] = FaultState.NOT_TESTED
        return True

    def enable_safety_mechanism(self, name: str, state: SMState) -> bool:
        """Enable future adapter observations without inventing a clear."""

        mechanism = self.safety_mechanisms.get(name)
        if mechanism is None or state not in (SMState.ENABLED, SMState.DISABLED):
            return False
        mechanism.isEnabled = state == SMState.ENABLED
        if mechanism.isEnabled and self._observed[name] is not None:
            self._publish_state(name, bool(self._observed[name]))
        return True

    def sm_provider_adapter_health(
        self, mechanism: SafetyMechanism,
        entities_changes: dict[str, str] | None = None,
    ) -> bool:
        """Return the last observed failure; an unseen adapter remains unknown."""

        del entities_changes
        return self._observed[mechanism.name] is True

    def sm_app_health(
        self, mechanism: SafetyMechanism,
        entities_changes: dict[str, str] | None = None,
    ) -> bool:
        """Return the last observed app failure without inferring unseen clears."""

        del entities_changes
        return self._observed[mechanism.name] is True

    def record_app_cause(
        self, cause: str, failed: bool | None, *, detail: str = "",
        operation: str = "io",
    ) -> None:
        """Record one current technical cause; historical counters do not qualify."""

        if cause == "persistence":
            if detail not in self.persistence_stores:
                raise ValueError(f"Unknown persistence store: {detail}")
            symptom_id = self._persistence_symptom_id(detail)
            self._persistence_operations[detail][operation] = failed
            values = self._persistence_operations[detail].values()
            aggregate = (
                True if any(value is True for value in values)
                else None if any(value is None for value in values)
                else False
            )
            if self._observed[symptom_id] is aggregate:
                return
            self._observed[symptom_id] = aggregate
            mechanism = self.safety_mechanisms.get(symptom_id)
            if mechanism is not None and mechanism.isEnabled:
                if aggregate is None:
                    self.event_bus.publish("evaluation_unavailable", symptom_id=symptom_id)
                else:
                    self._publish_state(symptom_id, aggregate, cause=cause, detail=detail)
            return
        if cause not in self.enabled_app_causes:
            raise ValueError(f"Unknown App Health cause: {cause}")
        symptom_id = self._app_symptom_id(cause)
        self._app_contributions[cause][detail or "default"] = failed
        values = self._app_contributions[cause].values()
        aggregate = (
            True if any(value is True for value in values)
            else None if any(value is None for value in values)
            else False
        )
        if self._observed[symptom_id] is aggregate:
            return
        self._observed[symptom_id] = aggregate
        mechanism = self.safety_mechanisms.get(symptom_id)
        if mechanism is None or not mechanism.isEnabled:
            return
        if aggregate is None:
            self.event_bus.publish("evaluation_unavailable", symptom_id=symptom_id)
            return
        self._publish_state(symptom_id, aggregate, cause=cause, detail=detail)

    def _publish_state(
        self, symptom_id: str, failed: bool, *, cause: str = "", detail: str = ""
    ) -> None:
        """Route one current observation through the established fault bus."""

        state = FaultState.SET if failed else FaultState.CLEARED
        self.symptom_states[symptom_id] = state
        self.event_bus.publish(
            "symptom",
            symptom_id=symptom_id,
            state=state,
            additional_info={"cause": cause, "detail": detail},
        )

    def observe_provider(self, *, result: ApiResult, **_: Any) -> None:
        """Publish only qualified state changes from one enabled adapter."""

        if result.provider not in self.providers:
            return
        symptom_id = self._symptom_id(result.provider)
        failed = result.health.state != ProviderHealthState.OK
        if self._observed[symptom_id] is failed:
            return
        self._observed[symptom_id] = failed
        mechanism = self.safety_mechanisms.get(symptom_id)
        if mechanism is None or not mechanism.isEnabled:
            return
        state = FaultState.SET if failed else FaultState.CLEARED
        self.symptom_states[symptom_id] = state
        self.event_bus.publish(
            "symptom",
            symptom_id=symptom_id,
            state=state,
            additional_info={
                "provider": result.provider,
                "provider_state": result.health.state.value,
                "detail_code": result.health.detail_code or "",
            },
        )
