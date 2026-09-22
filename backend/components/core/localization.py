"""Localize presentation metadata while preserving stable runtime contracts.

Internal entity IDs, MQTT states, fault names, and event payload codes stay in
English. Only user-facing entity names, ``state_label`` attributes, recovery
guidance, and notification text are translated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from pydantic import ConfigDict, Field, field_validator
import yaml

from components.core.pydantic_utils import StrictBaseModel


_LOCALES_DIR = Path(__file__).with_name("locales")


def _load_translations() -> dict[str, dict[str, str]]:
    """Load packaged backend translations from language files."""

    translations: dict[str, dict[str, str]] = {}
    for path in sorted(_LOCALES_DIR.glob("*.yml")):
        values = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(values, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in values.items()
        ):
            raise ValueError(f"Invalid localization file: {path}")
        translations[path.stem] = values
    if "en" not in translations:
        raise ValueError("English localization file is required")
    return translations


_TRANSLATIONS = _load_translations()


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
            "sensor.notification_delivery_health": "entity.notification_delivery_health",
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
        elif (
            normalized_id == "sensor.entity_monitor_summary"
            or normalized_id.startswith("sensor.entity_health_")
        ):
            prefix = "state.entity_health"
        elif normalized_id == "sensor.notification_delivery_health":
            prefix = "state.notification_delivery"
        else:
            return None
        key = f"{prefix}.{normalized_state}"
        return self._translations.get(key, _TRANSLATIONS["en"].get(key))
