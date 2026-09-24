"""Tests for localized presentation metadata and stable backend contracts."""

import pytest
from pydantic import ValidationError

from components.core.localization import Localizer, LocalizationSettings, _TRANSLATIONS


def test_all_languages_implement_the_same_translation_contract() -> None:
    assert set(_TRANSLATIONS) == {"en", "pl", "de"}
    assert set(_TRANSLATIONS["pl"]) == set(_TRANSLATIONS["en"])
    assert set(_TRANSLATIONS["de"]) == set(_TRANSLATIONS["en"])


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "No active faults"),
        ("pl", "Brak aktywnych usterek"),
        ("de", "Keine aktiven Fehler"),
    ],
)
def test_system_state_labels_are_available_in_every_language(
    language: str, expected: str
) -> None:
    localizer = Localizer({"language": language})

    assert localizer.language == language
    assert (
        localizer.state_label("sensor.safetysystem_state", "no_faults")
        == expected
    )


def test_german_localization_covers_notifications_and_dynamic_entities() -> None:
    localizer = Localizer({"language": "de"})

    assert localizer.text("notification.active", fault="Übertemperatur") == (
        "Übertemperatur erfordert Ihre Aufmerksamkeit."
    )
    assert localizer.text(
        "entity.temperature_low_threshold", location="Büro"
    ) == "Untere Temperaturgrenze – Büro"
    assert localizer.text("recovery.close_windows", location="Büro") == (
        "Bitte schließen Sie die Fenster in Büro."
    )


def test_entity_monitor_presentation_is_localized() -> None:
    localizer = Localizer({"language": "de"})

    assert localizer.entity_name(
        "sensor.entity_monitor_summary", "fallback"
    ) == "Überwachte Entitäten"
    assert (
        localizer.state_label("sensor.entity_health_office", "stale")
        == "Veraltete Daten"
    )
    assert localizer.text("fault.entity_health", entity="Büro") == (
        "Entitätsproblem: Büro"
    )


@pytest.mark.parametrize(
    ("language", "entity_name", "queued_label", "ack_label"),
    [
        ("en", "Notification delivery health", "Queued", "Acknowledge"),
        (
            "pl",
            "Stan dostarczania powiadomie\u0144",
            "Oczekuje w kolejce",
            "Potwierd\u017a",
        ),
        (
            "de",
            "Status der Benachrichtigungszustellung",
            "In Warteschlange",
            "Best\u00e4tigen",
        ),
    ],
)
def test_notification_delivery_presentation_is_localized(
    language: str, entity_name: str, queued_label: str, ack_label: str
) -> None:
    localizer = Localizer({"language": language})

    assert (
        localizer.entity_name("sensor.notification_delivery_health", "fallback")
        == entity_name
    )
    assert (
        localizer.state_label("sensor.notification_delivery_health", "queued")
        == queued_label
    )
    assert localizer.text("notification.action.ack") == ack_label


def test_unknown_text_key_falls_back_to_key() -> None:
    assert Localizer({"language": "de"}).text("missing.key") == "missing.key"


def test_private_entity_names_override_packaged_names_without_changing_ids(tmp_path) -> None:
    (tmp_path / "pl.yml").write_text(
        "entity_name.sensor.safety_app_health: Prywatna nazwa\n",
        encoding="utf-8",
    )
    localizer = Localizer({"language": "pl"}, private_locales_dir=tmp_path)

    assert localizer.entity_name("sensor.safety_app_health", "fallback") == "Prywatna nazwa"
    assert localizer.entity_name("sensor.safetysystem_state", "fallback") == "Stan systemu bezpieczeństwa"


@pytest.mark.parametrize("source", ["wrong: Name\n", "entity_name.sensor.test: ''\n", "- invalid\n"])
def test_private_locale_rejects_unknown_or_empty_entries(tmp_path, source: str) -> None:
    (tmp_path / "pl.yml").write_text(source, encoding="utf-8")
    with pytest.raises(ValueError, match="private"):
        Localizer({"language": "pl"}, private_locales_dir=tmp_path)


@pytest.mark.parametrize(
    "settings",
    [
        {"language": "fr"},
        {"entity_names": {"": "Name"}},
        {"entity_names": {"sensor.test": "  "}},
    ],
)
def test_invalid_localization_settings_are_rejected(settings: dict) -> None:
    with pytest.raises(ValidationError):
        LocalizationSettings.model_validate(settings)
