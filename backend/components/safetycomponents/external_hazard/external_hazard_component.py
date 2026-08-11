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
SM_RADIATION = "sm_ext_ionizing_radiation_alert"
SM_RADIATION_ANOMALY = "sm_ext_radiation_data_anomaly"
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
    HazardType.IONIZING_RADIATION: ("PaaRadiationApiComponent",),
    HazardType.RADIATION_ANOMALY: ("PaaRadiationApiComponent",),
}

_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "WeatherPointModel": ("OpenMeteoWeatherApiComponent",),
    "OfficialWeatherWarnings": ("ImgwWarningsApiComponent",),
    "OutdoorAirQuality": ("OpenMeteoAirQualityApiComponent",),
    "IonizingRadiation": ("PaaRadiationApiComponent",),
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
        "ionizing_radiation": "ionizing-radiation alert",
        "radiation_anomaly": "unconfirmed radiation-data anomaly",
        "close": "Close the affected external openings.",
        "radiation": "Follow the current instructions published by PAA.",
        "verify": "Verify the relevant authoritative source directly.",
        "external_data": "External data",
        "home": "Home",
        "none_open": "none observed open",
        "official_confirmation": "official PAA message",
        "unconfirmed": "unconfirmed raw-data anomaly",
    },
    "pl": {
        "frost": "mróz",
        "wind": "niebezpieczny wiatr",
        "rain": "intensywny deszcz",
        "storm": "burza",
        "outdoor_air_pollution": "zanieczyszczenie powietrza na zewnątrz",
        "ionizing_radiation": "oficjalne ostrzeżenie o promieniowaniu jonizującym",
        "radiation_anomaly": "niepotwierdzona anomalia danych radiacyjnych",
        "close": "Zamknij wskazane okna lub drzwi zewnętrzne.",
        "radiation": "Postępuj zgodnie z aktualnymi komunikatami Państwowej Agencji Atomistyki.",
        "verify": "Sprawdź właściwe źródło urzędowe bezpośrednio.",
        "external_data": "Dane zewnętrzne",
        "home": "Dom",
        "none_open": "nie wykryto otwartych",
        "official_confirmation": "oficjalny komunikat PAA",
        "unconfirmed": "niepotwierdzona anomalia danych pomiarowych",
    },
    "de": {
        "frost": "Frost",
        "wind": "gefährlicher Wind",
        "rain": "Starkregen",
        "storm": "Gewitter",
        "outdoor_air_pollution": "Außenluftverschmutzung",
        "ionizing_radiation": "amtliche Warnung vor ionisierender Strahlung",
        "radiation_anomaly": "unbestätigte Strahlungsdatenanomalie",
        "close": "Schließen Sie die betroffenen Außenöffnungen.",
        "radiation": "Befolgen Sie die aktuellen Anweisungen der polnischen Atomenergiebehörde PAA.",
        "verify": "Prüfen Sie die zuständige behördliche Quelle direkt.",
        "external_data": "Externe Daten",
        "home": "Haus",
        "none_open": "keine offene Öffnung erkannt",
        "official_confirmation": "amtliche PAA-Mitteilung",
        "unconfirmed": "unbestätigte Messdatenanomalie",
    },
}


@register_safety_component
class ExternalHazardComponent(SafetyComponent):
    """Correlate normalized provider evidence with external openings."""

    component_name = "ExternalHazardComponent"

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
        """Build stable per-opening, authority, and capability symptoms."""

        self.policy = dict(component_cfg["policy"])
        self.enabled_providers = set(
            component_cfg.get("enabled_providers", _EXPECTED_PROVIDERS)
        )
        self.openings = {
            name: dict(config) for name, config in component_cfg["openings"].items()
        }
        symptoms: dict[str, Symptom] = {}
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
            if "outdoor_air_pollution" in opening["hazards"]:
                symptom_id = f"OutdoorAirQualityExposure{opening_name}"
                symptoms[symptom_id] = self._symptom(
                    modules,
                    symptom_id,
                    SM_AIR_QUALITY,
                    opening_name=opening_name,
                    hazard="outdoor_air_pollution",
                )

        if "PaaRadiationApiComponent" in self.enabled_providers:
            symptoms["IonizingRadiationAlertPaa"] = self._symptom(
                modules,
                "IonizingRadiationAlertPaa",
                SM_RADIATION,
                hazard="ionizing_radiation",
            )
            symptoms["RadiationDataAnomalyPaaStations"] = self._symptom(
                modules,
                "RadiationDataAnomalyPaaStations",
                SM_RADIATION_ANOMALY,
                hazard="radiation_anomaly",
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
        return symptoms, {}

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

    def sm_ext_ionizing_radiation_alert(
        self,
        mechanism: SafetyMechanism,
        entities_changes: dict[str, str] | None = None,
    ) -> bool:
        dry_run = entities_changes is not None
        if dry_run:
            return False
        status, context, _ = self._hazard_evidence(HazardType.IONIZING_RADIATION)
        if mechanism.isEnabled and not dry_run:
            self._apply_state(mechanism.name, status, context)
        return status == "active"

    def sm_ext_radiation_data_anomaly(
        self,
        mechanism: SafetyMechanism,
        entities_changes: dict[str, str] | None = None,
    ) -> bool:
        dry_run = entities_changes is not None
        if dry_run:
            return False
        status, context = self._radiation_anomaly_evidence()
        if mechanism.isEnabled and not dry_run:
            self._apply_state(mechanism.name, status, context)
        return status == "active"

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
        if symptom_id.startswith("IonizingRadiationAlert"):
            return SM_RADIATION
        if symptom_id.startswith("RadiationDataAnomaly"):
            return SM_RADIATION_ANOMALY
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

    def _radiation_anomaly_evidence(self) -> tuple[str, dict[str, str]]:
        radiation_policy = self.policy["radiation"]
        if not radiation_policy.get("raw_anomaly_enabled", False):
            return "clear", {}
        threshold = radiation_policy.get("raw_anomaly_usv_h")
        if threshold is None:
            return "unknown", {}
        now = self._now()
        anomalous: list[ExternalObservation] = []
        for observation in self._observations.get("PaaRadiationApiComponent", {}).values():
            if observation.hazard_type != HazardType.RADIATION_ANOMALY or observation.valid_to < now:
                continue
            dose = observation.values.get("dose_rate")
            try:
                if float(getattr(dose, "value")) >= float(threshold):
                    anomalous.append(observation)
            except (TypeError, ValueError, AttributeError):
                continue
        required = int(radiation_policy.get("raw_anomaly_min_stations", 2))
        if len(anomalous) >= required:
            stations = ", ".join(str(item.values["station_id"].value) for item in anomalous)
            return "active", {
                "hazard": self._label("radiation_anomaly"),
                "source": "PAA monitoring measurements",
                "observed_value": f"{len(anomalous)} stations ≥ {threshold} µSv/h",
                "threshold": f"≥ {required} corroborating stations",
                "confirmation": self._label("unconfirmed"),
                "stations": stations,
                "recommendation": self._label("radiation"),
            }
        health = self._health.get("PaaRadiationApiComponent")
        if health is not None and health.state == ProviderHealthState.OK:
            return "clear", {}
        return "unknown", {}

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
        if sm_name == SM_RADIATION:
            return self._hazard_evidence(HazardType.IONIZING_RADIATION)[0] == "active"
        if sm_name == SM_RADIATION_ANOMALY:
            return self._radiation_anomaly_evidence()[0] == "active"
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
        if observation.hazard_type == HazardType.IONIZING_RADIATION:
            context["confirmation"] = self._label("official_confirmation")
            context["recommendation"] = self._label("radiation")
            open_names = self._currently_open_names()
            context["openings"] = ", ".join(open_names) if open_names else self._label("none_open")
            context["location"] = self._label("home")
        return context

    def _currently_open_names(self) -> list[str]:
        names = []
        for opening_name, opening in self.openings.items():
            if self._opening_state(opening_name, None) == "open":
                names.append(str(opening["friendly_name"]))
        return names

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
                "notification_only": True,
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
