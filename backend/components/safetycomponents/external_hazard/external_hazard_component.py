"""Household policy and notification-only correlation for external hazards."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Mapping

import appdaemon.plugins.hass.hassapi as hass  # type: ignore

from components.core.common_entities import CommonEntities
from components.core.event_bus import EventBus
from components.core.mqtt_entity_manager import MqttEntityManager
from components.core.types_common import FaultState, RecoveryAction, RecoveryResult, SMState, Symptom
from components.external_apis.core.models import ApiResult, ExternalObservation, HazardType, ProviderHealthState
from components.recovery_manager.policy import RecoveryPolicyDecision
from components.safetycomponents.core.safety_component import SafetyComponent, register_safety_component
from components.safetycomponents.core.safety_mechanism import SafetyMechanism

from .policy import HazardAssessment, evaluate_observation

SM_WEATHER = "sm_ext_weather_exposure"
SM_AIR_QUALITY = "sm_ext_outdoor_air_quality_exposure"
SM_PROVIDER_UNAVAILABLE = "sm_ext_provider_unavailable"

OPEN_STATES = frozenset({"on", "open", "opening", "true", "1"})
CLOSED_STATES = frozenset({"off", "closed", "false", "0"})
MAX_DIAGNOSTIC_OBSERVATIONS = 64

_HAZARD_PROVIDER_GROUPS: dict[HazardType, tuple[str, ...]] = {
    HazardType.FROST: ("OpenMeteoWeatherApiComponent", "ImgwWarningsApiComponent"),
    HazardType.WIND: ("OpenMeteoWeatherApiComponent", "ImgwWarningsApiComponent"),
    HazardType.RAIN: ("OpenMeteoWeatherApiComponent", "ImgwWarningsApiComponent"),
    HazardType.STORM: ("OpenMeteoWeatherApiComponent", "ImgwWarningsApiComponent"),
    HazardType.OUTDOOR_AIR_POLLUTION: ("OpenMeteoAirQualityApiComponent",),
}

_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "WeatherPointModel": ("OpenMeteoWeatherApiComponent",),
    "OfficialWeatherWarnings": ("ImgwWarningsApiComponent",),
    "OutdoorAirQuality": ("OpenMeteoAirQualityApiComponent",),
}

_EXPECTED_PROVIDERS = frozenset(
    provider
    for providers in _CAPABILITIES.values()
    for provider in providers
)

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

        return [
            {
                "key": f"ExternalOpening{opening_name}",
                "entity_id": opening["entity_id"],
                "owner": cls.component_name,
                "purpose": f"External-hazard opening input for {opening_name}",
                "checks": {},
                "detection_budget_seconds": 30,
                "area_id": opening.get("area_id"),
                "area_name": opening.get("area_name"),
            }
            for opening_name, opening in component_cfg.get("openings", {}).items()
        ]

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
        self._health: dict[str, Any] = {}
        self._provider_seen: set[str] = set()
        self._provider_failure_since: dict[str, datetime] = {}
        self._listened_openings: set[str] = set()
        self._clear_handles: dict[str, Any] = {}
        self._last_context: dict[str, dict[str, str]] = {}
        self._provider_entity_ids: dict[str, str] = {}
        self.enabled_providers: set[str] = set(_EXPECTED_PROVIDERS)
        self._aggregate_entity_id: str | None = None
        self._inhibited_reasons: dict[str, dict[str, str]] = {}
        self.event_bus.subscribe("external_api_result", self.handle_external_api_result)

    def get_symptoms_data(
        self,
        modules: dict[str, SafetyComponent],
        component_cfg: dict[str, Any],
    ) -> tuple[dict[str, Symptom], dict[str, RecoveryAction]]:
        """Build stable per-opening and capability symptoms."""

        self.policy = dict(component_cfg["policy"])
        self.enabled_providers = set(
            component_cfg.get("enabled_providers", _EXPECTED_PROVIDERS)
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

        for capability, providers in _CAPABILITIES.items():
            if not self.enabled_providers.intersection(providers):
                continue
            symptom_id = f"ExternalHazardDataUnavailable{capability}"
            symptoms[symptom_id] = self._symptom(
                modules,
                symptom_id,
                SM_PROVIDER_UNAVAILABLE,
                capability=capability,
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
        monitored_entities: list[str] = []
        if isinstance(opening_name, str) and opening_name not in self._listened_openings:
            monitored_entities = [str(self.openings[opening_name]["entity_id"])]
            self._listened_openings.add(opening_name)
        mechanism = SafetyMechanism(
            hass_app=self.hass_app,
            callback=self._opening_changed,
            name=name,
            isEnabled=False,
            monitored_entities=monitored_entities,
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
        if provider not in self.enabled_providers:
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

    def _evaluate_all(self) -> None:
        for mechanism in self.safety_mechanisms.values():
            if not mechanism.isEnabled:
                continue
            getattr(self, self._sm_name_for(mechanism.name))(mechanism)
        self._publish_aggregate()

    def _sm_name_for(self, symptom_id: str) -> str:
        if symptom_id.startswith("ExternalWeatherExposure"):
            return SM_WEATHER
        if symptom_id.startswith("OutdoorAirQualityExposure"):
            return SM_AIR_QUALITY
        return SM_PROVIDER_UNAVAILABLE

    def _evaluate_exposure(
        self,
        mechanism: SafetyMechanism,
        entities_changes: dict[str, str] | None,
    ) -> bool:
        opening_name = str(mechanism.sm_args["opening_name"])
        hazard = HazardType(str(mechanism.sm_args["hazard"]))
        opening_entity = str(self.openings[opening_name]["entity_id"])
        if entities_changes is not None and opening_entity not in entities_changes:
            return False
        opening_state = self._opening_state(opening_name, entities_changes)
        if opening_state == "closed":
            status, context = "clear", self._opening_context(opening_name, hazard)
        elif opening_state == "unavailable":
            status, context = "unknown", self._opening_context(opening_name, hazard)
        else:
            status, context, _ = self._hazard_evidence(hazard)
            context = {**self._opening_context(opening_name, hazard), **context}
        if entities_changes is None and mechanism.isEnabled:
            self._apply_state(mechanism.name, status, context)
        return status == "active"

    def _hazard_evidence(
        self, hazard: HazardType
    ) -> tuple[str, dict[str, str], HazardAssessment | None]:
        now = self._now()
        applicable = [
            observation
            for provider_observations in self._observations.values()
            for observation in provider_observations.values()
            if observation.hazard_type == hazard and observation.valid_to >= now
        ]
        active: list[tuple[ExternalObservation, HazardAssessment]] = []
        for observation in applicable:
            try:
                assessment = evaluate_observation(observation, self.policy, now)
            except ValueError as exc:
                self.hass_app.log(
                    f"External hazard policy rejected {observation.provider}/{observation.observation_id}: {exc}",
                    level="WARNING",
                )
                continue
            if assessment.active:
                active.append((observation, assessment))
        if active:
            observation, assessment = max(
                active,
                key=lambda item: {"watch": 1, "warning": 2, "severe": 3}.get(item[1].severity, 0),
            )
            context = self._evidence_context(observation, assessment)
            if assessment.inhibits_opening_advice:
                self._inhibited_reasons[hazard.value] = {
                    "reason": hazard.value,
                    "valid_until": observation.valid_to.isoformat(),
                    "source": observation.provider,
                }
            return "active", context, assessment

        self._inhibited_reasons.pop(hazard.value, None)
        providers = tuple(
            provider
            for provider in _HAZARD_PROVIDER_GROUPS[hazard]
            if provider in self.enabled_providers
        )
        explicit_clear = all(
            provider in self._provider_seen
            and self._health.get(provider) is not None
            and self._health[provider].state == ProviderHealthState.OK
            for provider in providers
        )
        return ("clear" if explicit_clear else "unknown"), {}, None

    def _capability_health(self, capability: str) -> tuple[str, dict[str, str]]:
        providers = tuple(
            provider
            for provider in _CAPABILITIES[capability]
            if provider in self.enabled_providers
        )
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
        if all(
            provider in self._provider_seen
            and self._health.get(provider) is not None
            and self._health[provider].state == ProviderHealthState.OK
            for provider in providers
        ):
            return "clear", {"capability": capability, "providers": ", ".join(providers)}
        return "unknown", {}

    def _apply_state(
        self, symptom_id: str, status: str, context: dict[str, str]
    ) -> None:
        if status == "unknown":
            return
        current = self.symptom_states.get(symptom_id, FaultState.NOT_TESTED)
        if status == "active":
            self._cancel_clear(symptom_id)
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
                self._clear_handles[symptom_id] = self.hass_app.run_in(
                    self._finish_clear,
                    int(self.policy["clear_delay_seconds"]),
                    symptom_id=symptom_id,
                )
            return
        self._publish_clear(symptom_id, context)

    def _finish_clear(self, **kwargs: Any) -> None:
        symptom_id = str(kwargs["symptom_id"])
        self._clear_handles.pop(symptom_id, None)
        mechanism = self.safety_mechanisms.get(symptom_id)
        if mechanism is None or not mechanism.isEnabled:
            return
        if self._would_be_active(mechanism):
            return
        self._publish_clear(symptom_id, self._last_context.get(symptom_id, {}))
        self._publish_aggregate()

    def _would_be_active(self, mechanism: SafetyMechanism) -> bool:
        sm_name = self._sm_name_for(mechanism.name)
        if sm_name in {SM_WEATHER, SM_AIR_QUALITY}:
            return self._evaluate_exposure(mechanism, {})
        return self._capability_health(str(mechanism.sm_args["capability"]))[0] == "active"

    def _publish_clear(self, symptom_id: str, context: dict[str, str]) -> None:
        if self.symptom_states.get(symptom_id) == FaultState.CLEARED:
            return
        self.symptom_states[symptom_id] = FaultState.CLEARED
        clear_context = self._last_context.pop(symptom_id, context)
        self.event_bus.publish(
            "symptom",
            symptom_id=symptom_id,
            state=FaultState.CLEARED,
            additional_info=clear_context,
        )

    def _cancel_clear(self, symptom_id: str) -> None:
        handle = self._clear_handles.pop(symptom_id, None)
        if handle is None:
            return
        try:
            self.hass_app.cancel_timer(handle)
        except Exception as exc:
            self.hass_app.log(f"Unable to cancel external hazard clear timer: {exc}", level="WARNING")

    def _opening_state(
        self, opening_name: str, entities_changes: Mapping[str, str] | None
    ) -> str:
        entity_id = str(self.openings[opening_name]["entity_id"])
        raw = entities_changes.get(entity_id) if entities_changes and entity_id in entities_changes else self.hass_app.get_state(entity_id)
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
    ) -> dict[str, str]:
        context = {
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
        entity_id = self._provider_entity_ids.get(provider)
        if entity_id is None:
            slug = re.sub(r"(?<!^)(?=[A-Z])", "_", provider.replace("ApiComponent", "")).lower()
            entity_id = self.mqtt_entities.register_sensor(
                f"sensor.external_provider_{slug}",
                f"External provider: {provider}",
                icon="mdi:cloud-sync-outline",
                entity_category="diagnostic",
            )
            self._provider_entity_ids[provider] = entity_id
        health = result.health
        attributes: dict[str, Any] = {
            "provider": provider,
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
        if provider == "ImgwWarningsApiComponent":
            warnings = result.evidence.get("warnings", [])
            attributes["warnings"] = warnings if isinstance(warnings, list) else []
            attributes["warning_count"] = len(attributes["warnings"])
        self.mqtt_entities.publish_sensor_state(
            entity_id,
            health.state.value,
            attributes=attributes,
        )

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
        provider_data_incomplete = (
            not self.enabled_providers.issubset(self._provider_seen)
            or any(
                self._health.get(provider) is None
                or self._health[provider].state != ProviderHealthState.OK
                for provider in self.enabled_providers
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
                "active_hazards": sorted({context.get("hazard", "") for _, context in external_active if context.get("hazard")}),
                "affected_openings": sorted({context.get("openings", "") for _, context in external_active if context.get("openings")}),
                "providers": providers,
                "enabled_providers": sorted(self.enabled_providers),
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
        """Cancel component-owned clear timers during application shutdown."""

        for symptom_id in list(self._clear_handles):
            self._cancel_clear(symptom_id)

    def _label(self, key: str) -> str:
        language = getattr(getattr(self.hass_app, "localizer", None), "language", "en")
        return _LABELS.get(language, _LABELS["en"]).get(key, key)

    @staticmethod
    def _pascal(value: str) -> str:
        return "".join(part.capitalize() for part in value.split("_"))

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
