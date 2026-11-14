"""Household policy and notification-only correlation for external hazards."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from math import ceil
from time import monotonic
from typing import Any, Callable, Mapping

import appdaemon.plugins.hass.hassapi as hass  # type: ignore

from components.core.common_entities import CommonEntities
from components.core.event_bus import EventBus
from components.core.localization import Localizer
from components.core.mqtt_entity_manager import MqttEntityManager
from components.core.types_common import FaultState, RecoveryAction, RecoveryResult, SMState, Symptom
from components.external_apis import get_registered_api_components
from components.external_apis.core.models import ApiResult, ExternalObservation, HazardType, ProviderCapability, ProviderHealth, ProviderHealthState
from components.recovery_manager.policy import RecoveryPolicyDecision
from components.recovery_manager.manual_actions import manual_action
from components.safetycomponents.core.safety_component import SafetyComponent, register_safety_component
from components.safetycomponents.core.safety_mechanism import SafetyMechanism

from .policy import HazardAssessment, evaluate_observation

SM_WEATHER = "sm_ext_weather_exposure"
SM_AIR_QUALITY = "sm_ext_outdoor_air_quality_exposure"
SM_PROVIDER_UNAVAILABLE = "sm_ext_provider_unavailable"

OPEN_STATES = frozenset({"on", "open", "opening", "true", "1"})
CLOSED_STATES = frozenset({"off", "closed", "false", "0"})
MAX_DIAGNOSTIC_OBSERVATIONS = 64
DOOR_OPEN_QUALIFICATION_SECONDS = 60
DEBOUNCED_OPENING_KINDS = frozenset({"door", "garage_door", "gate"})

HazardContext = dict[str, Any]
HazardEvidence = tuple[str, HazardContext, HazardAssessment | None]
ModelKey = tuple[str, HazardType]

_WEATHER_CAPABILITIES = (ProviderCapability.WEATHER_MODEL, ProviderCapability.OFFICIAL_WARNINGS)
_HAZARD_CAPABILITIES = {
    hazard: (ProviderCapability.AIR_QUALITY,) if hazard == HazardType.OUTDOOR_AIR_POLLUTION else _WEATHER_CAPABILITIES
    for hazard in HazardType
}

_LABELS = {
    "en": {
        "frost": "frost",
        "wind": "damaging wind",
        "rain": "heavy rain",
        "storm": "storm",
        "outdoor_air_pollution": "outdoor air pollution",
        "close": "Close the affected external openings.",
        "verify": "Verify the relevant authoritative source directly.",
        "external_data": "External data",
        "home": "Home",
        "none_open": "none observed open",
    },
    "pl": {
        "frost": "mróz",
        "wind": "niebezpieczny wiatr",
        "rain": "intensywny deszcz",
        "storm": "burza",
        "outdoor_air_pollution": "zanieczyszczenie powietrza na zewnątrz",
        "close": "Zamknij wskazane okna lub drzwi zewnętrzne.",
        "verify": "Sprawdź właściwe źródło urzędowe bezpośrednio.",
        "external_data": "Dane zewnętrzne",
        "home": "Dom",
        "none_open": "nie wykryto otwartych",
    },
    "de": {
        "frost": "Frost",
        "wind": "gefährlicher Wind",
        "rain": "Starkregen",
        "storm": "Gewitter",
        "outdoor_air_pollution": "Außenluftverschmutzung",
        "close": "Schließen Sie die betroffenen Außenöffnungen.",
        "verify": "Prüfen Sie die zuständige behördliche Quelle direkt.",
        "external_data": "Externe Daten",
        "home": "Haus",
        "none_open": "keine offene Öffnung erkannt",
    },
}


@register_safety_component
class ExternalHazardComponent(SafetyComponent):
    """Correlate normalized provider evidence with external openings."""

    component_name = "ExternalHazardComponent"

    @classmethod
    def get_entity_dependencies(
        cls, component_cfg: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Declare opening contacts used by external-hazard correlation."""

        dependencies: list[dict[str, Any]] = []
        for opening_name, opening in component_cfg.get("openings", {}).items():
            hazard_symptoms = [
                f"ExternalWeatherExposure{cls._pascal(hazard)}{opening_name}"
                for hazard in ("frost", "wind", "rain", "storm")
                if hazard in opening.get("hazards", ())
            ]
            if "outdoor_air_pollution" in opening.get("hazards", ()):
                hazard_symptoms.append(f"OutdoorAirQualityExposure{opening_name}")
            dependencies.append({
                "key": f"ExternalOpening{opening_name}",
                "entity_id": opening["entity_id"],
                "owner": cls.component_name,
                "fault_owner": "component",
                "fault_name": "InputMonitoringUnavailable",
                "purpose": f"External-hazard opening input for {opening_name}",
                "degradation_targets": tuple(
                    (symptom_id, "external_exposure", opening_name, "evaluation")
                    for symptom_id in hazard_symptoms
                ),
                "checks": {},
                "detection_budget_seconds": 30,
                "area_id": opening.get("area_id"),
                "area_name": opening.get("area_name"),
            })
            actuator = opening.get("actuator_entity_id")
            if opening.get("execution_policy") == "user_confirmed" and actuator:
                dependencies.append({
                    "key": f"ExternalRecovery{opening_name}",
                    "entity_id": actuator,
                    "owner": cls.component_name,
                    "fault_owner": "component",
                    "fault_name": "ExternalRecoveryUnavailable",
                    "purpose": f"Confirmed recovery actuator for {opening_name}",
                    "recovery_command": True,
                    "degradation_targets": tuple(
                        (symptom_id, "external_recovery", opening_name, "recovery")
                        for symptom_id in hazard_symptoms
                    ),
                    "checks": {},
                    "detection_budget_seconds": 30,
                    "area_id": opening.get("area_id"),
                    "area_name": opening.get("area_name"),
                })
        return dependencies

    def __init__(
        self,
        hass_app: hass.Hass,
        common_entities: CommonEntities,
        event_bus: EventBus,
        mqtt_entities: MqttEntityManager,
    ) -> None:
        super().__init__(hass_app, common_entities, event_bus, mqtt_entities)
        self.policy: dict[str, Any] = {}
        self.openings: dict[str, dict[str, Any]] = {}
        self._observations: dict[str, dict[str, ExternalObservation]] = {}
        self._health: dict[str, ProviderHealth] = {}
        self._provider_seen: set[str] = set()
        self._provider_failure_since: dict[str, datetime] = {}
        self._listened_openings: set[str] = set()
        self._opening_listeners: dict[str, Any] = {}
        self._opened_since: dict[str, float] = {}
        self._opening_timers: dict[str, tuple[object, Any]] = {}
        self._model_assertions: dict[ModelKey, tuple[float, datetime]] = {}
        self._model_timers: dict[ModelKey, tuple[object, Any]] = {}
        self._clear_handles: dict[str, tuple[object, Any]] = {}
        self._stopped = False
        self._last_context: dict[str, HazardContext] = {}
        self._provider_entity_ids: dict[str, str] = {}
        self._provider_plugins = get_registered_api_components()
        self._test_provider_plugins: dict[str, Any] = {}
        self._runtime_selections: dict[str, str | None] = {}
        self.runtime_id = str(getattr(hass_app, "runtime_id", ""))
        self.assertion_observer: Callable[[str, bool, HazardContext], bool] | None = None
        self._test_entity_id: str | None = None
        self.enabled_providers: set[str] = set(self._provider_plugins)
        self._aggregate_entity_id: str | None = None
        self._inhibited_reasons: dict[str, dict[str, str]] = {}
        self.event_bus.subscribe("external_api_result", self.handle_external_api_result)
        self.event_bus.subscribe("external_api_test_result", self.handle_external_api_test_result)

    def configure_runtime(self, *, runtime_id: str, selections: Mapping[str, str | None]) -> None:
        """Bind this start's applied choices without activating synthetic policy."""
        if not runtime_id or len(runtime_id) > 128 or not runtime_id.isascii():
            raise ValueError("Invalid external-hazard runtime_id")
        if set(selections) != {capability.value for capability in ProviderCapability}:
            raise ValueError("External source selection must contain all capabilities")
        plugins = get_registered_api_components()
        selected = {name for name in selections.values() if name is not None}
        if not selected.issubset(plugins):
            raise ValueError("Unknown external source selection")
        self.runtime_id = runtime_id
        self._runtime_selections = dict(selections)
        self._provider_plugins = {
            name: plugin for name, plugin in plugins.items()
            if name in selected and plugin.data_kind == "live"
        }
        self._test_provider_plugins = {
            name: plugin for name, plugin in plugins.items()
            if name in selected and plugin.data_kind == "synthetic"
        }
        self.enabled_providers = set(self._provider_plugins)
        if self._test_provider_plugins:
            provider = next(iter(self._test_provider_plugins))
            self._publish_test_preview(provider, None)

    def restore_assertions(self, records: Mapping[str, HazardContext]) -> None:
        """Retain confirmed real danger without replaying qualification or actions."""
        for symptom_id, context in records.items():
            if not symptom_id.startswith(("ExternalWeatherExposure", "OutdoorAirQualityExposure")):
                continue
            self.symptom_states[symptom_id] = FaultState.SET
            self._last_context[symptom_id] = {**dict(context), "retained": True, "freshness": "unevaluable"}

    def _record_assertion(self, symptom_id: str, active: bool, context: HazardContext) -> bool:
        """Persist real assertion changes before they are published to consumers."""
        if self.assertion_observer is None or symptom_id.startswith("ExternalHazardDataUnavailable"):
            return True
        try:
            return self.assertion_observer(symptom_id, active, context)
        except Exception as exc:
            self.hass_app.log(f"External assertion persistence failed: {exc}", level="ERROR")
            return False

    def handle_external_api_test_result(self, *, result: ApiResult, **_: Any) -> None:
        """Publish trusted synthetic previews without evaluating real safety policy."""
        if self._stopped or result.provider not in self._test_provider_plugins:
            return
        if result.health.provider != result.provider:
            return
        plugin = self._test_provider_plugins[result.provider]
        if any(observation.provider != result.provider or observation.authority_confirmed
               or observation.hazard_type not in plugin.hazards
               for observation in result.observations):
            return
        self._publish_test_preview(result.provider, result)

    def _publish_test_preview(self, provider: str, result: ApiResult | None) -> None:
        if self._test_entity_id is None:
            self._test_entity_id = self.mqtt_entities.register_sensor(
                "sensor.external_hazard_test_state", self._presentation_text("entity.external_hazard_test"),
                icon="mdi:flask-outline", entity_category="diagnostic",
            )
        observations = result.observations[:MAX_DIAGNOSTIC_OBSERVATIONS] if result is not None else ()
        plugin = self._test_provider_plugins[provider]
        self.mqtt_entities.publish_sensor_state(
            self._test_entity_id, result.health.state.value if result else "awaiting_evidence",
            attributes={
                "schema_version": 1, "runtime_id": self.runtime_id, "provider": provider,
                "provider_name": self._provider_display_name(provider), "data_kind": "synthetic",
                "scenario": result.evidence.get("scenario") if result else None,
                "health": result.health.state.value if result else "awaiting_evidence",
                "capability": plugin.capability.value,
                "hazards": sorted(hazard.value for hazard in plugin.hazards),
                "count": len(observations),
                "observations": [self._observation_summary(item) for item in observations],
                "warnings": [self._warning_summary(item) for item in observations],
                "last_success_at": result.health.last_success_at.isoformat() if result and result.health.last_success_at else None,
                "last_attempt_at": result.health.last_attempt_at.isoformat() if result and result.health.last_attempt_at else None,
                "stale_after_seconds": result.health.stale_after_seconds if result else 180,
                "detail_code": result.health.detail_code if result else None,
                "test_label": self._presentation_text("provider.synthetic.label"),
            },
        )

    def get_symptoms_data(
        self,
        modules: dict[str, SafetyComponent],
        component_cfg: dict[str, Any],
    ) -> tuple[dict[str, Symptom], dict[str, RecoveryAction]]:
        """Build stable per-opening and capability symptoms."""

        self.policy = dict(component_cfg["policy"])
        self.enabled_providers = set(
            component_cfg.get("enabled_providers", self._provider_plugins)
        )
        self.enabled_providers.intersection_update(
            name for name, plugin in self._provider_plugins.items()
            if getattr(plugin, "data_kind", None) == "live"
        )
        self.openings = {
            name: dict(config) for name, config in component_cfg["openings"].items()
        }
        symptoms: dict[str, Symptom] = {}
        recoveries: dict[str, RecoveryAction] = {}
        weather_hazards = ("frost", "wind", "rain", "storm")
        for opening_name, opening in self.openings.items():
            for hazard in weather_hazards:
                if hazard not in opening["hazards"]:
                    continue
                symptom_id = f"ExternalWeatherExposure{self._pascal(hazard)}{opening_name}"
                symptoms[symptom_id] = self._symptom(
                    modules,
                    symptom_id,
                    SM_WEATHER,
                    opening_name=opening_name,
                    hazard=hazard,
                )
                recoveries[symptom_id] = self._opening_recovery(
                    symptom_id, opening_name, opening
                )
            if "outdoor_air_pollution" in opening["hazards"]:
                symptom_id = f"OutdoorAirQualityExposure{opening_name}"
                symptoms[symptom_id] = self._symptom(
                    modules,
                    symptom_id,
                    SM_AIR_QUALITY,
                    opening_name=opening_name,
                    hazard="outdoor_air_pollution",
                )
                recoveries[symptom_id] = self._opening_recovery(
                    symptom_id, opening_name, opening
                )

        for capability in ProviderCapability:
            providers = self._providers_for((capability,))
            if not providers:
                continue
            symptom_id = f"ExternalHazardDataUnavailable{capability.value}"
            symptoms[symptom_id] = self._symptom(
                modules,
                symptom_id,
                SM_PROVIDER_UNAVAILABLE,
                capability=capability.value,
            )
            recoveries[symptom_id] = manual_action(
                f"InspectExternalData{capability.value}",
                subject=f"{capability.value}: {', '.join(providers)}",
                instruction_key="recovery.inspect_external_data",
                result_key="recovery.result_external_data",
                manual_report_allowed=True,
            )
        return symptoms, recoveries

    def _opening_recovery(
        self,
        symptom_id: str,
        opening_name: str,
        opening: dict[str, Any],
    ) -> RecoveryAction:
        """Build one close-opening proposal for an exposure symptom."""

        localizer = getattr(self.hass_app, "localizer", None)
        friendly_name = (
            localizer.text(
                "recovery.close_opening", opening=opening["friendly_name"]
            )
            if localizer is not None
            else f"Close {opening['friendly_name']}"
        )
        return RecoveryAction(
            f"CloseExternalOpening{opening_name}",
            {
                "opening_name": opening_name,
                "friendly_name": friendly_name,
                "location": opening.get("area_name", opening["area_id"]),
                "area_id": opening["area_id"],
            },
            self._close_opening_recovery,
        )

    def _close_opening_recovery(
        self,
        _hass_app: hass.Hass,
        symptom: Symptom,
        _common_entities: CommonEntities,
        **_: Any,
    ) -> RecoveryResult:
        """Return a non-actuating proposal or a confirmation-gated cover command."""

        opening_name = str(symptom.parameters["opening_name"])
        opening = self.openings[opening_name]
        friendly_name = str(opening["friendly_name"])
        context = self._last_context.get(symptom.name, {})
        execution_policy = str(opening.get("execution_policy", "manual"))
        actuator = opening.get("actuator_entity_id")
        changed_actuators = (
            {str(actuator): "closed"}
            if execution_policy == "user_confirmed" and actuator
            else {}
        )
        localizer = getattr(self.hass_app, "localizer", None)
        if localizer is not None:
            instruction = localizer.text(
                "recovery.close_opening", opening=friendly_name
            )
        else:
            instruction = f"Close {friendly_name}."
        if execution_policy == "user_confirmed":
            if localizer is not None:
                instruction = localizer.text(
                    "recovery.confirm_close_opening", opening=friendly_name
                )
            else:
                instruction = (
                    f"Confirm closing {friendly_name}. SafetyComponent will act "
                    "only after your confirmation."
                )
        return RecoveryResult(
            changed_sensors={str(opening["entity_id"]): "off"},
            changed_actuators=changed_actuators,
            notifications=[instruction],
            instruction=instruction,
            execution_policy=execution_policy,
            reason=str(context.get("hazard", symptom.parameters.get("hazard", ""))),
            source=str(context.get("source", "SafetyComponent")),
            valid_until=str(context.get("valid_to", "")),
            confirmation_timeout_seconds=int(
                opening.get("confirmation_timeout_seconds", 120)
            ),
            completion_condition="opening_closed" if execution_policy == "manual" else "entity_state",
            expected_result=(localizer.text("recovery.result_closed", subject=friendly_name)
                             if localizer is not None else f"Current contact confirms {friendly_name} is closed."),
            purpose="hazard_mitigation",
        )

    def _symptom(
        self,
        modules: dict[str, SafetyComponent],
        name: str,
        sm_name: str,
        **parameters: Any,
    ) -> Symptom:
        return Symptom(
            name=name,
            sm_name=sm_name,
            module=modules[self.component_name],
            parameters=parameters,
        )

    def init_safety_mechanism(
        self, sm_name: str, name: str, parameters: dict[str, Any]
    ) -> bool:
        """Initialize one policy mechanism and a single listener per opening."""

        callback = getattr(self, sm_name, None)
        if callback is None or name in self.safety_mechanisms:
            return False
        opening_name = parameters.get("opening_name")
        if isinstance(opening_name, str) and opening_name not in self._listened_openings:
            entity_id = str(self.openings[opening_name]["entity_id"])
            self._opening_listeners[opening_name] = self.hass_app.listen_state(
                self._opening_contact_changed, entity_id, opening_name=opening_name
            )
            self._listened_openings.add(opening_name)
        mechanism = SafetyMechanism(
            hass_app=self.hass_app,
            callback=self._opening_changed,
            name=name,
            isEnabled=False,
        )
        mechanism.sm_args.update(parameters)
        self.safety_mechanisms[name] = mechanism
        self.symptom_states[name] = FaultState.NOT_TESTED
        self._ensure_aggregate_entity()
        return True

    def enable_safety_mechanism(self, name: str, state: SMState) -> bool:
        mechanism = self.safety_mechanisms.get(name)
        if mechanism is None:
            return False
        if state == SMState.ENABLED:
            mechanism.isEnabled = True
            return True
        if state == SMState.DISABLED:
            mechanism.isEnabled = False
            self._cancel_clear(name)
            return True
        return False

    def sm_ext_weather_exposure(
        self,
        mechanism: SafetyMechanism,
        entities_changes: dict[str, str] | None = None,
    ) -> bool:
        return self._evaluate_exposure(mechanism, entities_changes)

    def sm_ext_outdoor_air_quality_exposure(
        self,
        mechanism: SafetyMechanism,
        entities_changes: dict[str, str] | None = None,
    ) -> bool:
        return self._evaluate_exposure(mechanism, entities_changes)

    def sm_ext_provider_unavailable(
        self,
        mechanism: SafetyMechanism,
        entities_changes: dict[str, str] | None = None,
    ) -> bool:
        dry_run = entities_changes is not None
        if dry_run:
            return False
        status, context = self._capability_health(str(mechanism.sm_args["capability"]))
        if mechanism.isEnabled and not dry_run:
            self._apply_state(mechanism.name, status, context)
        return status == "active"

    def handle_external_api_result(self, *, result: ApiResult, **_: Any) -> None:
        """Accept one complete provider snapshot and re-evaluate policy."""

        provider = result.provider
        plugin = self._provider_plugins.get(provider)
        if (
            self._stopped or provider not in self.enabled_providers or plugin is None
            or getattr(plugin, "data_kind", None) != "live"
            or result.health.provider != provider
        ):
            return
        official = plugin.capability == ProviderCapability.OFFICIAL_WARNINGS
        if any(
            observation.provider != provider
            or observation.hazard_type not in plugin.hazards
            or observation.authority_confirmed != official
            for observation in result.observations
        ):
            return
        self._provider_seen.add(provider)
        self._health[provider] = result.health
        if result.health.state == ProviderHealthState.OK:
            self._observations[provider] = {
                observation.observation_id: observation
                for observation in result.observations
            }
            self._provider_failure_since.pop(provider, None)
        else:
            self._provider_failure_since.setdefault(provider, self._now())
        self._publish_provider_health(result)
        self._evaluate_all()

    def _opening_changed(self, _: SafetyMechanism) -> None:
        self._evaluate_all()

    def _opening_contact_changed(
        self, _entity: str, _attribute: str, old: Any, new: Any, **kwargs: Any
    ) -> None:
        opening_name = str(kwargs["opening_name"])
        # Consume the edge even if a close/reopen burst has already changed readback.
        old_state = self._normalize_opening(old)
        new_state = self._normalize_opening(new)
        if old_state != "open" or new_state != "open":
            self._reset_opening_qualification(opening_name)
        if old_state != new_state and new_state != "closed":
            for mechanism in self.safety_mechanisms.values():
                if mechanism.sm_args.get("opening_name") == opening_name:
                    self._cancel_clear(mechanism.name)
        self._evaluate_all()

    def _evaluate_all(self) -> None:
        if self._stopped:
            return
        evidence: dict[HazardType, HazardEvidence] = {}
        for mechanism in self.safety_mechanisms.values():
            if not mechanism.isEnabled:
                continue
            hazard = mechanism.sm_args.get("hazard")
            if hazard is None:
                self.sm_ext_provider_unavailable(mechanism)
                continue
            hazard = HazardType(hazard)
            if hazard not in evidence:
                evidence[hazard] = self._hazard_evidence(hazard)
            self._evaluate_exposure(mechanism, None, evidence[hazard])
        self._publish_aggregate()
        self.record_evaluation()

    def _evaluate_exposure(
        self,
        mechanism: SafetyMechanism,
        entities_changes: dict[str, str] | None,
        evidence: HazardEvidence | None = None,
    ) -> bool:
        opening_name = str(mechanism.sm_args["opening_name"])
        hazard = HazardType(str(mechanism.sm_args["hazard"]))
        opening_entity = str(self.openings[opening_name]["entity_id"])
        if entities_changes is not None and opening_entity not in entities_changes:
            return False
        opening_state = self._opening_state(opening_name, entities_changes)
        status, context, assessment = self._exposure_evidence(
            opening_name, hazard, opening_state, evidence, track=entities_changes is None
        )
        if entities_changes is None and mechanism.isEnabled:
            qualified = self._opening_qualified(opening_name, opening_state)
            if (
                status == "active"
                and not qualified
                and self.symptom_states.get(mechanism.name) != FaultState.SET
                and not (assessment and assessment.immediate_exposure)
            ):
                return False
            self._apply_state(mechanism.name, status, context)
        return status == "active"

    def _exposure_evidence(
        self, opening_name: str, hazard: HazardType, opening_state: str,
        evidence: HazardEvidence | None = None, *, track: bool = True,
    ) -> HazardEvidence:
        context = self._opening_context(opening_name, hazard)
        if opening_state == "closed":
            return "clear", context, None
        if opening_state == "unavailable":
            return "unknown", context, None
        status, hazard_context, assessment = evidence or self._hazard_evidence(hazard, track=track)
        return status, {**context, **hazard_context}, assessment

    def _opening_qualified(self, opening_name: str, opening_state: str) -> bool:
        if self.openings[opening_name]["kind"] not in DEBOUNCED_OPENING_KINDS:
            return True
        if opening_state != "open":
            self._reset_opening_qualification(opening_name)
            return False
        now = monotonic()
        started = self._opened_since.setdefault(opening_name, now)
        remaining = DOOR_OPEN_QUALIFICATION_SECONDS - (now - started)
        if remaining <= 0:
            return True
        if opening_name not in self._opening_timers:
            token = object()
            handle = self.hass_app.run_in(
                self._finish_opening_qualification,
                ceil(remaining),
                opening_name=opening_name,
                token=token,
            )
            self._opening_timers[opening_name] = (token, handle)
        return False

    def _finish_opening_qualification(self, **kwargs: Any) -> None:
        opening_name = str(kwargs["opening_name"])
        timer = self._opening_timers.get(opening_name)
        if timer is None or timer[0] is not kwargs["token"]:
            return
        self._opening_timers.pop(opening_name)
        self._evaluate_all()

    def _reset_opening_qualification(self, opening_name: str) -> None:
        self._opened_since.pop(opening_name, None)
        timer = self._opening_timers.pop(opening_name, None)
        if timer is not None:
            self._cancel_timer(timer[1])

    def _hazard_evidence(self, hazard: HazardType, *, track: bool = True) -> HazardEvidence:
        now = self._now()
        elapsed = monotonic()
        persistence = int(self.policy["weather"].get("persistence_seconds", 120))
        providers = self._providers_for(_HAZARD_CAPABILITIES[hazard], hazard=hazard)
        active: list[tuple[ExternalObservation, HazardAssessment]] = []
        reevaluated_sources: list[str] = []
        inhibition: ExternalObservation | None = None
        asserted_sources = {
            context.get("source")
            for symptom_id, context in self._last_context.items()
            if self.symptom_states.get(symptom_id) == FaultState.SET
            and symptom_id in self.safety_mechanisms
            and self.safety_mechanisms[symptom_id].sm_args.get("hazard") == hazard.value
        }
        unusable = False
        pending = False
        for provider in providers:
            official_warning = self._provider_plugins[provider].capability == ProviderCapability.OFFICIAL_WARNINGS
            health = self._health.get(provider)
            fresh = self._provider_snapshot_is_fresh(provider, now)
            key = (provider, hazard)
            started, valid_until = self._model_assertions.get(key, (elapsed, now))
            if valid_until < now:
                started = elapsed
                if track:
                    self._cancel_model_timer(key)
            previously_active = provider in asserted_sources or (
                key in self._model_assertions
                and valid_until >= now
                and elapsed - started >= persistence
            )
            provider_active: list[tuple[ExternalObservation, HazardAssessment]] = []
            provider_usable = False
            invalid = False
            for observation in self._observations.get(provider, {}).values():
                if observation.hazard_type != hazard or observation.valid_from > now:
                    continue
                if observation.provider != provider or observation.authority_confirmed != official_warning:
                    invalid = True
                    continue
                if observation.valid_to < now or (not official_warning and not fresh):
                    continue
                try:
                    assessment = evaluate_observation(
                        observation, self.policy, now, previously_active=previously_active
                    )
                except ValueError as exc:
                    invalid = True
                    self.hass_app.log(
                        f"External hazard policy rejected {provider}/{observation.observation_id}: {exc}",
                        level="WARNING",
                    )
                    continue
                provider_usable = True
                if assessment.active:
                    provider_active.append((observation, assessment))
                    if assessment.inhibits_opening_advice and (
                        inhibition is None or observation.valid_to > inhibition.valid_to
                    ):
                        inhibition = observation
            unusable |= invalid
            source_ready = (
                provider in self._provider_seen
                and health is not None
                and health.state == ProviderHealthState.OK
                and fresh
                and not invalid
            )
            if official_warning:
                if source_ready:
                    reevaluated_sources.append(provider)
                active.extend(provider_active)
                continue
            if invalid or not provider_usable or health is None or health.state != ProviderHealthState.OK:
                unusable = True
                provider_active.clear()
            if not track:
                active.extend(provider_active)
                continue
            if not provider_active:
                if source_ready and provider_usable:
                    reevaluated_sources.append(provider)
                self._model_assertions.pop(key, None)
                self._cancel_model_timer(key)
                continue
            deadline = max(observation.valid_to for observation, _ in provider_active)
            if health is not None and health.last_success_at is not None and health.stale_after_seconds > 0:
                deadline = min(deadline, health.last_success_at + timedelta(seconds=health.stale_after_seconds))
            remaining = persistence - (elapsed - started)
            self._model_assertions[key] = (started, deadline)
            if remaining <= 0:
                if source_ready and provider_usable:
                    reevaluated_sources.append(provider)
                self._cancel_model_timer(key)
                active.extend(provider_active)
            else:
                pending = True
                self._schedule_model_qualification(key, remaining)

        if track:
            if inhibition is None:
                self._inhibited_reasons.pop(hazard.value, None)
            else:
                self._inhibited_reasons[hazard.value] = {
                    "reason": hazard.value,
                    "valid_until": inhibition.valid_to.isoformat(),
                    "source": inhibition.provider,
                }
        if active:
            observation, assessment = max(
                active,
                key=lambda item: (
                    item[1].immediate_exposure,
                    {"watch": 1, "warning": 2, "severe": 3}.get(item[1].severity, 0),
                ),
            )
            context = self._evidence_context(observation, assessment)
            context["reevaluated_sources"] = reevaluated_sources
            return "active", context, assessment

        explicit_clear = bool(providers) and not unusable and not pending and all(
            provider in self._provider_seen
            and self._health.get(provider) is not None
            and self._health[provider].state == ProviderHealthState.OK
            and self._provider_snapshot_is_fresh(provider, now)
            for provider in providers
        )
        context = {"reevaluated_sources": reevaluated_sources} if explicit_clear else {}
        return ("clear" if explicit_clear else "unknown"), context, None

    def _schedule_model_qualification(self, key: ModelKey, remaining: float) -> None:
        if key in self._model_timers:
            return
        token = object()
        handle = self.hass_app.run_in(
            self._finish_model_qualification, ceil(remaining), key=key, token=token
        )
        self._model_timers[key] = (token, handle)

    def _finish_model_qualification(self, **kwargs: Any) -> None:
        key = kwargs["key"]
        timer = self._model_timers.get(key)
        if timer is None or timer[0] is not kwargs["token"]:
            return
        self._model_timers.pop(key)
        self._evaluate_all()

    def _cancel_model_timer(self, key: ModelKey) -> None:
        timer = self._model_timers.pop(key, None)
        if timer is not None:
            self._cancel_timer(timer[1])

    def _providers_for(
        self,
        capabilities: tuple[ProviderCapability, ...],
        *,
        hazard: HazardType | None = None,
    ) -> tuple[str, ...]:
        """Select installed evidence paths within their declared hazard coverage."""

        return tuple(sorted(
            name for name, plugin in self._provider_plugins.items()
            if name in self.enabled_providers and plugin.capability in capabilities
            and getattr(plugin, "data_kind", None) == "live"
            and (hazard is None or hazard in plugin.hazards)
        ))

    def _provider_snapshot_is_fresh(self, provider: str, now: datetime) -> bool:
        health = self._health.get(provider)
        if health is None or health.last_success_at is None:
            return False
        age = (now - health.last_success_at).total_seconds()
        return age >= 0 and (health.stale_after_seconds <= 0 or age <= health.stale_after_seconds)

    def _capability_health(self, capability: str) -> tuple[str, dict[str, str]]:
        providers = self._providers_for((ProviderCapability(capability),))
        if not providers:
            return "unknown", {}
        now = self._now()
        degraded: list[str] = []
        for provider in providers:
            health = self._health.get(provider)
            failed_since = self._provider_failure_since.get(provider)
            if health is None or failed_since is None:
                continue
            if health.state != ProviderHealthState.OK and (
                now - failed_since
            ).total_seconds() >= int(health.stale_after_seconds):
                degraded.append(provider)
        if len(degraded) == len(providers):
            return "active", {
                "location": self._label("external_data"),
                "capability": capability,
                "providers": ", ".join(degraded),
                "freshness": "stale or unavailable",
                "recommendation": self._label("verify"),
            }
        if any(
            provider in self._provider_seen
            and self._health.get(provider) is not None
            and self._health[provider].state == ProviderHealthState.OK
            and self._provider_snapshot_is_fresh(provider, now)
            for provider in providers
        ):
            return "clear", {"capability": capability, "providers": ", ".join(providers)}
        return "unknown", {}

    def _coverage_details(self) -> list[dict[str, Any]]:
        """Project configured capability/hazard coverage independently of raw health."""

        now = self._now()
        hazards = sorted({
            HazardType(hazard)
            for opening in self.openings.values()
            for hazard in opening["hazards"]
        }, key=lambda hazard: hazard.value)
        details: list[dict[str, Any]] = []
        for hazard in hazards:
            for capability in _HAZARD_CAPABILITIES[hazard]:
                capability_providers = self._providers_for((capability,))
                providers = self._providers_for((capability,), hazard=hazard)
                status = self._coverage_status(
                    capability, hazard, providers, capability_providers, now
                )
                details.append({
                    "capability": capability.value,
                    "hazard": hazard.value,
                    "providers": list(providers),
                    "status": status,
                    "status_label": self._presentation_text(f"provider.coverage.{status}"),
                })
        return details

    def _coverage_status(
        self,
        capability: ProviderCapability,
        hazard: HazardType,
        providers: tuple[str, ...],
        capability_providers: tuple[str, ...],
        now: datetime,
    ) -> str:
        """Describe completeness without granting safe evidence to uncovered paths."""

        if not capability_providers:
            return "not_configured"
        if not providers:
            return "unsupported"
        if any(
            health is not None and (
                health.state != ProviderHealthState.OK
                or not self._provider_snapshot_is_fresh(provider, now)
            )
            for provider in providers
            for health in (self._health.get(provider),)
        ):
            return "unavailable"
        if any(
            provider not in self._provider_seen or self._health.get(provider) is None
            for provider in providers
        ):
            return "awaiting_evidence"
        observations = [
            observation
            for provider in providers
            for observation in self._observations.get(provider, {}).values()
            if observation.provider == provider
            and observation.hazard_type == hazard
            and observation.valid_from <= now <= observation.valid_to
        ]
        if capability == ProviderCapability.OFFICIAL_WARNINGS:
            return "available" if observations else "no_current_warnings"
        for provider in providers:
            usable = False
            for observation in observations:
                if observation.provider != provider or observation.authority_confirmed:
                    continue
                try:
                    evaluate_observation(observation, self.policy, now)
                except ValueError:
                    continue
                usable = True
                break
            if not usable:
                return "unavailable"
        return "available"

    def _apply_state(
        self, symptom_id: str, status: str, context: HazardContext
    ) -> None:
        if status == "unknown":
            self._cancel_clear(symptom_id)
            return
        current = self.symptom_states.get(symptom_id, FaultState.NOT_TESTED)
        if status == "active":
            self._cancel_clear(symptom_id)
            self._record_assertion(symptom_id, True, context)
            if current == FaultState.SET:
                self.record_symptom_observation(symptom_id, FaultState.SET, context)
            if current != FaultState.SET or self._last_context.get(symptom_id) != context:
                self.symptom_states[symptom_id] = FaultState.SET
                self._last_context[symptom_id] = context
                self.event_bus.publish(
                    "symptom",
                    symptom_id=symptom_id,
                    state=FaultState.SET,
                    additional_info=context,
                )
            return
        if current == FaultState.SET and int(self.policy.get("clear_delay_seconds", 0)) > 0:
            if symptom_id not in self._clear_handles:
                token = object()
                handle = self.hass_app.run_in(
                    self._finish_clear,
                    int(self.policy["clear_delay_seconds"]),
                    symptom_id=symptom_id,
                    token=token,
                )
                self._clear_handles[symptom_id] = (token, handle)
            return
        self._publish_clear(symptom_id, context)

    def _finish_clear(self, **kwargs: Any) -> None:
        symptom_id = str(kwargs["symptom_id"])
        timer = self._clear_handles.get(symptom_id)
        if timer is None or timer[0] is not kwargs["token"]:
            return
        self._clear_handles.pop(symptom_id)
        mechanism = self.safety_mechanisms.get(symptom_id)
        if self._stopped or mechanism is None or not mechanism.isEnabled:
            return
        opening_name = mechanism.sm_args.get("opening_name")
        if isinstance(opening_name, str):
            status, context, _ = self._exposure_evidence(
                opening_name,
                HazardType(str(mechanism.sm_args["hazard"])),
                self._opening_state(opening_name, None),
            )
        else:
            status, context = self._capability_health(str(mechanism.sm_args["capability"]))
        if status == "clear":
            self._publish_clear(symptom_id, context)
            self._publish_aggregate()

    def _publish_clear(self, symptom_id: str, context: HazardContext) -> None:
        if not self._record_assertion(symptom_id, False, context):
            return
        if self.symptom_states.get(symptom_id) == FaultState.CLEARED:
            self.record_symptom_observation(symptom_id, FaultState.CLEARED, context)
            return
        self.symptom_states[symptom_id] = FaultState.CLEARED
        clear_context = dict(self._last_context.pop(symptom_id, context))
        clear_context.pop("reevaluated_sources", None)
        if "reevaluated_sources" in context:
            clear_context["reevaluated_sources"] = context["reevaluated_sources"]
        self.event_bus.publish(
            "symptom",
            symptom_id=symptom_id,
            state=FaultState.CLEARED,
            additional_info=clear_context,
        )

    def _cancel_clear(self, symptom_id: str) -> None:
        timer = self._clear_handles.pop(symptom_id, None)
        if timer is not None:
            self._cancel_timer(timer[1])

    def _cancel_timer(self, handle: Any) -> None:
        try:
            self.hass_app.cancel_timer(handle)
        except Exception as exc:
            self.hass_app.log(f"Unable to cancel external hazard timer: {exc}", level="WARNING")

    def _opening_state(
        self, opening_name: str, entities_changes: Mapping[str, str] | None
    ) -> str:
        entity_id = str(self.openings[opening_name]["entity_id"])
        raw = entities_changes.get(entity_id) if entities_changes and entity_id in entities_changes else self.hass_app.get_state(entity_id)
        return self._normalize_opening(raw)

    @staticmethod
    def _normalize_opening(raw: Any) -> str:
        normalized = str(raw or "").strip().lower()
        if normalized in OPEN_STATES:
            return "open"
        if normalized in CLOSED_STATES:
            return "closed"
        return "unavailable"

    def _opening_context(self, opening_name: str, hazard: HazardType) -> dict[str, str]:
        opening = self.openings[opening_name]
        return {
            "location": str(opening.get("area_name", opening["area_id"])),
            "hazard": self._label(hazard.value),
            "openings": str(opening["friendly_name"]),
            "source_entity": str(opening["entity_id"]),
            "recommendation": self._label("close"),
        }

    def _evidence_context(
        self, observation: ExternalObservation, assessment: HazardAssessment
    ) -> HazardContext:
        context: HazardContext = {
            "hazard": self._label(observation.hazard_type.value),
            "severity": assessment.severity,
            "observed_value": assessment.observed_value,
            "threshold": assessment.threshold,
            "evidence_kind": assessment.evidence_kind,
            "source": observation.provider,
            "source_time": (observation.observed_at or observation.retrieved_at).isoformat(),
            "valid_to": observation.valid_to.isoformat(),
            "freshness": "fresh",
            "source_reference": observation.source_reference,
        }
        return context

    def _publish_provider_health(self, result: ApiResult) -> None:
        provider = result.provider
        provider_name = self._provider_display_name(provider)
        entity_id = self._provider_entity_ids.get(provider)
        if entity_id is None:
            slug = re.sub(r"(?<!^)(?=[A-Z])", "_", provider.replace("ApiComponent", "")).lower()
            entity_id = self.mqtt_entities.register_sensor(
                f"sensor.external_provider_{slug}",
                self._presentation_text("entity.external_provider", provider=provider_name),
                icon="mdi:cloud-sync-outline",
                entity_category="diagnostic",
            )
            self._provider_entity_ids[provider] = entity_id
        health = result.health
        attributes: dict[str, Any] = {
            "runtime_id": self.runtime_id,
            "data_kind": "live",
            "provider": provider,
            "provider_name": provider_name,
            "state_label": self._presentation_text(f"provider.health.{health.state.value}"),
            "capability": self._provider_plugins[provider].capability.value,
            "hazards": sorted(hazard.value for hazard in self._provider_plugins[provider].hazards),
            "last_attempt_at": health.last_attempt_at.isoformat() if health.last_attempt_at else None,
            "last_success_at": health.last_success_at.isoformat() if health.last_success_at else None,
            "consecutive_failures": health.consecutive_failures,
            "detail_code": health.detail_code,
            "stale_after_seconds": health.stale_after_seconds,
            "observation_count": len(result.observations),
            "observations": [
                self._observation_summary(observation)
                for observation in result.observations[
                    :MAX_DIAGNOSTIC_OBSERVATIONS
                ]
            ],
        }
        if self._provider_plugins[provider].capability == ProviderCapability.OFFICIAL_WARNINGS:
            warnings = result.evidence.get("warnings")
            if not isinstance(warnings, list):
                warnings = [
                    self._warning_summary(observation)
                    for observation in result.observations
                    if observation.provider == provider and observation.authority_confirmed
                ]
            attributes["warnings"] = warnings[:MAX_DIAGNOSTIC_OBSERVATIONS]
            attributes["warning_count"] = len(attributes["warnings"])
        self.mqtt_entities.publish_sensor_state(
            entity_id,
            health.state.value,
            attributes=attributes,
        )

    def _warning_summary(self, observation: ExternalObservation) -> dict[str, Any]:
        """Present a normalized official alert without provider-specific fields."""
        title = observation.values.get("event_name")
        return {
            "id": observation.observation_id,
            "event_name": str(title.value)[:200] if title is not None else self._label(observation.hazard_type.value),
            "degree": observation.provider_level,
            "valid_from": observation.valid_from.isoformat(),
            "valid_to": observation.valid_to.isoformat(),
            "locally_applicable": True,
        }

    @staticmethod
    def _observation_summary(observation: ExternalObservation) -> dict[str, Any]:
        """Return bounded provider evidence suitable for operator presentation."""

        display_value: float | int | str | bool | None = None
        display_unit: str | None = None
        for key in ("polish_index_name", "current_european_aqi"):
            measurement = observation.values.get(key)
            if measurement is not None:
                display_value = measurement.value
                display_unit = measurement.unit
                break
        return {
            "id": observation.observation_id,
            "hazard_type": observation.hazard_type.value,
            "provider_level": observation.provider_level,
            "observed_at": (
                observation.observed_at.isoformat()
                if observation.observed_at is not None
                else None
            ),
            "valid_to": observation.valid_to.isoformat(),
            "display_value": display_value,
            "display_unit": display_unit,
        }

    def _ensure_aggregate_entity(self) -> None:
        if self._aggregate_entity_id is not None:
            return
        self._aggregate_entity_id = self.mqtt_entities.register_sensor(
            "sensor.external_hazard_state",
            "External hazard state",
            state="unavailable",
            icon="mdi:home-alert-outline",
            entity_category="diagnostic",
        )

    def _publish_aggregate(self) -> None:
        self._ensure_aggregate_entity()
        active = [
            (name, self._last_context.get(name, {}))
            for name, state in self.symptom_states.items()
            if state == FaultState.SET
        ]
        external_active = [item for item in active if not item[0].startswith("ExternalHazardDataUnavailable")]
        unavailable_active = [item for item in active if item[0].startswith("ExternalHazardDataUnavailable")]
        now = self._now()
        provider_data_incomplete = (
            not self.enabled_providers
            or not self.enabled_providers.issubset(self._provider_seen)
            or any(
                self._health.get(provider) is None
                or self._health[provider].state != ProviderHealthState.OK
                or not self._provider_snapshot_is_fresh(provider, now)
                for provider in self.enabled_providers
            )
            or any(
                self._hazard_evidence(HazardType(hazard), track=False)[0] == "unknown"
                for opening in self.openings.values()
                for hazard in opening["hazards"]
            )
        )
        severities = []
        for _, context in external_active:
            severities.append(context.get("severity", "warning"))
        if "severe" in severities:
            state = "severe"
        elif "warning" in severities:
            state = "warning"
        elif "watch" in severities:
            state = "watch"
        elif unavailable_active or provider_data_incomplete:
            state = "unavailable"
        elif self._provider_seen:
            state = "clear"
        else:
            state = "unavailable"
        providers = {
            provider: health.state.value for provider, health in self._health.items()
        }
        self.mqtt_entities.publish_sensor_state(
            self._aggregate_entity_id,
            state,
            attributes={
                "runtime_id": self.runtime_id,
                "retained_assertions": [
                    {"symptom_id": name, **context}
                    for name, context in external_active if context.get("retained")
                ],
                "active_hazards": sorted({context.get("hazard", "") for _, context in external_active if context.get("hazard")}),
                "affected_openings": sorted({context.get("openings", "") for _, context in external_active if context.get("openings")}),
                "providers": providers,
                "enabled_providers": sorted(self.enabled_providers),
                "official_warnings_configured": bool(self._providers_for((ProviderCapability.OFFICIAL_WARNINGS,))),
                "coverage_details": self._coverage_details(),
                "advice_inhibition": list(self._inhibited_reasons.values()),
                "last_evaluated_at": self._now().isoformat(),
                "actuation_mode": self.policy.get(
                    "actuation_mode", "manual_and_user_confirmed"
                ),
                "active_symptom_count": len(external_active),
            },
        )

    def evaluate_recovery_policy(
        self, recovery_result: RecoveryResult
    ) -> RecoveryPolicyDecision:
        """Block contradictory proposals to open external apertures."""

        if not self._inhibited_reasons:
            return RecoveryPolicyDecision(True)
        configured_entities = {
            str(opening["entity_id"]) for opening in self.openings.values()
        }
        opening_requested = any(
            str(value).strip().lower() in OPEN_STATES and entity in configured_entities
            for entity, value in recovery_result.changed_sensors.items()
        ) or any(
            str(value).strip().lower() in OPEN_STATES
            and (entity in configured_entities or entity.startswith("cover."))
            for entity, value in recovery_result.changed_actuators.items()
        )
        if not opening_requested:
            return RecoveryPolicyDecision(True)
        reasons = ", ".join(sorted(self._inhibited_reasons))
        return RecoveryPolicyDecision(False, f"open_external_opening inhibited by {reasons}")

    def stop(self) -> None:
        """Discard pending opening qualification and cancel component timers."""

        self._stopped = True
        for key in list(self._model_timers):
            self._cancel_model_timer(key)
        self._model_assertions.clear()
        for symptom_id in list(self._clear_handles):
            self._cancel_clear(symptom_id)
        for opening_name in list(self._opened_since):
            self._reset_opening_qualification(opening_name)
        for handle in self._opening_listeners.values():
            try:
                self.hass_app.cancel_listen_state(handle)
            except Exception as exc:
                self.hass_app.log(f"Unable to cancel external opening listener: {exc}", level="WARNING")
        self._opening_listeners.clear()

    def _label(self, key: str) -> str:
        language = getattr(getattr(self.hass_app, "localizer", None), "language", "en")
        return _LABELS.get(language, _LABELS["en"]).get(key, key)

    def _presentation_text(self, key: str, **values: str) -> str:
        """Translate operator metadata without altering technical state contracts."""
        localizer = getattr(self.hass_app, "localizer", None) or Localizer()
        return str(localizer.text(key, **values))

    def _provider_display_name(self, provider: str) -> str:
        """Use packaged branding or a new plugin's own friendly metadata."""
        key = f"provider.{provider}.name"
        translated = self._presentation_text(key)
        if translated != key:
            return translated
        plugin = self._provider_plugins.get(provider) or self._test_provider_plugins.get(provider)
        return str(getattr(plugin, "display_name", "") or provider)

    @staticmethod
    def _pascal(value: str) -> str:
        return "".join(part.capitalize() for part in value.split("_"))

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
