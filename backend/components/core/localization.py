"""Localize presentation metadata while preserving stable runtime contracts.

Internal entity IDs, MQTT states, fault names, and event payload codes stay in
English. Only user-facing entity names, ``state_label`` attributes, recovery
guidance, and notification text are translated.
"""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import ConfigDict, Field, field_validator

from components.core.pydantic_utils import StrictBaseModel


_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "entity.safety_app_health": "Safety app health",
        "entity.safety_system_state": "Safety system state",
        "entity.entity_monitor_summary": "Monitored entities",
        "entity.recovery_window": "Window recovery: {location}",
        "entity.temperature_low_threshold": "Low temperature limit: {location}",
        "entity.temperature_high_threshold": "High temperature limit: {location}",
        "state.health.init": "Starting",
        "state.health.running": "Running",
        "state.health.invalid_cfg": "Invalid configuration",
        "state.health.stopped": "Stopped",
        "state.system.no_faults": "No active faults",
        "state.system.emergency": "Emergency",
        "state.system.hazard": "Hazard",
        "state.system.warning": "Warning",
        "state.system.information": "Information",
        "state.system.stopped": "Stopped",
        "state.fault.set": "Active",
        "state.fault.shadowed": "Shadowed",
        "state.fault.cleared": "Cleared",
        "state.fault.not_tested": "Not tested",
        "state.recovery.to_perform": "Action needed",
        "state.recovery.do_not_perform": "No action needed",
        "state.entity_health.healthy": "Healthy",
        "state.entity_health.degraded": "Needs attention",
        "state.entity_health.stale": "Stale data",
        "state.entity_health.unavailable": "Unavailable",
        "fault.entity_health": "Entity problem: {entity}",
        "notification.title.1": "Immediate action needed",
        "notification.title.2": "Safety issue detected",
        "notification.title.3": "Please check your home",
        "notification.active": "{fault} needs your attention.",
        "notification.cleared": "Good news - {fault} is no longer active.",
        "notification.guidance": "What you can do:",
        "detail.location": "Location",
        "detail.hazard": "Hazard",
        "detail.openings": "Affected openings",
        "detail.observed_value": "Observed or forecast value",
        "detail.threshold": "Policy threshold",
        "detail.evidence_kind": "Evidence type",
        "detail.source": "Source",
        "detail.source_time": "Source time",
        "detail.valid_to": "Valid until",
        "detail.freshness": "Freshness",
        "detail.source_reference": "Authoritative reference",
        "detail.severity": "Severity",
        "detail.confirmation": "Confirmation",
        "detail.capability": "Capability",
        "detail.providers": "Providers",
        "detail.stations": "Stations",
        "detail.source_entity": "Opening sensor",
        "recovery.close_windows": "Please close the windows in {location}.",
        "recovery.open_windows": "Please open the windows in {location}.",
    },
    "pl": {
        "entity.safety_app_health": "Stan aplikacji bezpieczeństwa",
        "entity.safety_system_state": "Stan systemu bezpieczeństwa",
        "entity.entity_monitor_summary": "Monitorowane encje",
        "entity.recovery_window": "Działanie naprawcze: okna — {location}",
        "entity.temperature_low_threshold": "Dolny próg temperatury — {location}",
        "entity.temperature_high_threshold": "Górny próg temperatury — {location}",
        "state.health.init": "Uruchamianie",
        "state.health.running": "Działa",
        "state.health.invalid_cfg": "Błędna konfiguracja",
        "state.health.stopped": "Zatrzymana",
        "state.system.no_faults": "Brak aktywnych usterek",
        "state.system.emergency": "Alarm krytyczny",
        "state.system.hazard": "Zagrożenie",
        "state.system.warning": "Ostrzeżenie",
        "state.system.information": "Informacja",
        "state.system.stopped": "Zatrzymany",
        "state.fault.set": "Aktywna",
        "state.fault.shadowed": "Przesłonięta",
        "state.fault.cleared": "Usunięta",
        "state.fault.not_tested": "Nieprzetestowana",
        "state.recovery.to_perform": "Wymaga działania",
        "state.recovery.do_not_perform": "Nie wymaga działania",
        "state.entity_health.healthy": "Sprawna",
        "state.entity_health.degraded": "Wymaga uwagi",
        "state.entity_health.stale": "Dane nieaktualne",
        "state.entity_health.unavailable": "Niedostępna",
        "fault.entity_health": "Problem z encją: {entity}",
        "notification.title.1": "Wymagane natychmiastowe działanie",
        "notification.title.2": "Wykryto zagrożenie w domu",
        "notification.title.3": "Sprawdź, co dzieje się w domu",
        "notification.active": "Wymaga uwagi: {fault}.",
        "notification.cleared": "Dobra wiadomość - problem „{fault}” został rozwiązany.",
        "notification.guidance": "Co możesz zrobić:",
        "detail.location": "Lokalizacja",
        "detail.hazard": "Zagrożenie",
        "detail.openings": "Narażone okna lub drzwi",
        "detail.observed_value": "Wartość zmierzona lub prognozowana",
        "detail.threshold": "Próg bezpieczeństwa",
        "detail.evidence_kind": "Rodzaj danych",
        "detail.source": "Źródło",
        "detail.source_time": "Czas danych źródłowych",
        "detail.valid_to": "Ważne do",
        "detail.freshness": "Aktualność",
        "detail.source_reference": "Odnośnik urzędowy",
        "detail.severity": "Waga",
        "detail.confirmation": "Potwierdzenie",
        "detail.capability": "Zakres danych",
        "detail.providers": "Dostawcy danych",
        "detail.stations": "Stacje pomiarowe",
        "detail.source_entity": "Czujnik otwarcia",
        "recovery.close_windows": "Zamknij okna w lokalizacji: {location}.",
        "recovery.open_windows": "Otwórz okna w lokalizacji: {location}.",
    },
    "de": {
        "entity.safety_app_health": "Status der Sicherheitsanwendung",
        "entity.safety_system_state": "Status des Sicherheitssystems",
        "entity.entity_monitor_summary": "Überwachte Entitäten",
        "entity.recovery_window": "Fenstermaßnahme – {location}",
        "entity.temperature_low_threshold": "Untere Temperaturgrenze – {location}",
        "entity.temperature_high_threshold": "Obere Temperaturgrenze – {location}",
        "state.health.init": "Wird gestartet",
        "state.health.running": "Läuft",
        "state.health.invalid_cfg": "Ungültige Konfiguration",
        "state.health.stopped": "Angehalten",
        "state.system.no_faults": "Keine aktiven Fehler",
        "state.system.emergency": "Kritischer Alarm",
        "state.system.hazard": "Gefahr",
        "state.system.warning": "Warnung",
        "state.system.information": "Information",
        "state.system.stopped": "Angehalten",
        "state.fault.set": "Aktiv",
        "state.fault.shadowed": "Überlagert",
        "state.fault.cleared": "Behoben",
        "state.fault.not_tested": "Nicht getestet",
        "state.recovery.to_perform": "Maßnahme erforderlich",
        "state.recovery.do_not_perform": "Keine Maßnahme erforderlich",
        "state.entity_health.healthy": "Fehlerfrei",
        "state.entity_health.degraded": "Prüfung erforderlich",
        "state.entity_health.stale": "Veraltete Daten",
        "state.entity_health.unavailable": "Nicht verfügbar",
        "fault.entity_health": "Entitätsproblem: {entity}",
        "notification.title.1": "Sofortiges Handeln erforderlich",
        "notification.title.2": "Sicherheitsproblem erkannt",
        "notification.title.3": "Bitte prüfen Sie Ihr Zuhause",
        "notification.active": "{fault} erfordert Ihre Aufmerksamkeit.",
        "notification.cleared": "Gute Nachricht – {fault} ist nicht mehr aktiv.",
        "notification.guidance": "Das können Sie tun:",
        "detail.location": "Ort",
        "detail.hazard": "Gefahr",
        "detail.openings": "Betroffene Öffnungen",
        "detail.observed_value": "Mess- oder Prognosewert",
        "detail.threshold": "Sicherheitsschwelle",
        "detail.evidence_kind": "Datentyp",
        "detail.source": "Quelle",
        "detail.source_time": "Quellzeit",
        "detail.valid_to": "Gültig bis",
        "detail.freshness": "Aktualität",
        "detail.source_reference": "Behördliche Referenz",
        "detail.severity": "Schweregrad",
        "detail.confirmation": "Bestätigung",
        "detail.capability": "Datenbereich",
        "detail.providers": "Datenanbieter",
        "detail.stations": "Messstationen",
        "detail.source_entity": "Öffnungssensor",
        "recovery.close_windows": "Bitte schließen Sie die Fenster in {location}.",
        "recovery.open_windows": "Bitte öffnen Sie die Fenster in {location}.",
    },
}


class LocalizationSettings(StrictBaseModel):
    """Installation-specific localization settings."""

    model_config = ConfigDict(extra="allow")

    language: str = "en"
    entity_names: dict[str, str] = Field(default_factory=dict)

    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: str) -> str:
        language = value.strip().lower()
        if language not in _TRANSLATIONS:
            raise ValueError(
                f"Unsupported language {value!r}; supported={sorted(_TRANSLATIONS)}"
            )
        return language

    @field_validator("entity_names")
    @classmethod
    def _validate_entity_names(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for entity_id, name in value.items():
            normalized_id = entity_id.strip().lower()
            normalized_name = name.strip()
            if not normalized_id or not normalized_name:
                raise ValueError("entity_names keys and values must not be empty")
            normalized[normalized_id] = normalized_name
        return normalized


class Localizer:
    """Resolve localized text while keeping backend state codes stable."""

    def __init__(
        self,
        settings: LocalizationSettings | Mapping[str, Any] | None = None,
    ) -> None:
        if isinstance(settings, LocalizationSettings):
            self.settings = settings
        else:
            self.settings = LocalizationSettings.model_validate(dict(settings or {}))
        self._translations = _TRANSLATIONS[self.settings.language]

    @property
    def language(self) -> str:
        """Return the configured ISO language code."""
        return self.settings.language

    def text(self, key: str, **values: Any) -> str:
        """Return one translated string formatted with optional values."""
        template = self._translations.get(key, _TRANSLATIONS["en"].get(key, key))
        return template.format(**values)

    def entity_name(self, entity_id: str, fallback: str) -> str:
        """Return a configured or built-in localized entity name."""
        normalized_id = entity_id.strip().lower()
        configured = self.settings.entity_names.get(normalized_id)
        if configured:
            return configured
        built_in_keys = {
            "sensor.safety_app_health": "entity.safety_app_health",
            "sensor.safetysystem_state": "entity.safety_system_state",
            "sensor.entity_monitor_summary": "entity.entity_monitor_summary",
        }
        key = built_in_keys.get(normalized_id)
        return self.text(key) if key else fallback

    def detail_label(self, detail_name: str, fallback: str) -> str:
        """Return a localized label for one notification detail."""

        key = f"detail.{detail_name.strip().lower()}"
        return self._translations.get(key, _TRANSLATIONS["en"].get(key, fallback))

    def state_label(self, entity_id: str, state: Any) -> str | None:
        """Return localized display text for a stable backend state code."""
        normalized_id = entity_id.strip().lower()
        normalized_state = str(state).strip().lower()
        if normalized_id == "sensor.safety_app_health":
            prefix = "state.health"
        elif normalized_id == "sensor.safetysystem_state":
            prefix = "state.system"
        elif normalized_id.startswith("sensor.fault_"):
            prefix = "state.fault"
        elif normalized_id.startswith("sensor.recovery_"):
            prefix = "state.recovery"
        elif normalized_id == "sensor.entity_monitor_summary" or normalized_id.startswith(
            "sensor.entity_health_"
        ):
            prefix = "state.entity_health"
        else:
            return None
        key = f"{prefix}.{normalized_state}"
        return self._translations.get(key, _TRANSLATIONS["en"].get(key))
