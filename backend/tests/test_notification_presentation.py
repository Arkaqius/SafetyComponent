"""Operator copy stays concise, localized and independent of raw evidence."""

import string
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from components.core.localization import Localizer
from components.core.types_common import FaultState
from components.notification_manager.notification_manager import NotificationManager


def manager(language="pl"):
    app = Mock()
    app.get_state.return_value = {
        "state": "unavailable",
        "attributes": {"friendly_name": "Okno sypialni — prawe"},
    }
    app.call_service.return_value = {"success": True}
    clock = Mock(return_value=1000.0)
    return NotificationManager(app, {}, localizer=Localizer({"language": language}), clock=clock), app, clock


@pytest.mark.parametrize("language,prefix,action", [
    ("pl", "Brak odczytu:", "Sprawdź zasilanie i łączność czujnika."),
    ("en", "No reading:", "Check sensor power and connectivity."),
    ("de", "Kein Messwert:", "Prüfen Sie Stromversorgung und Verbindung des Sensors."),
])
def test_unavailable_input_has_specific_title_short_action_and_raw_diagnostics(language, prefix, action):
    subject, app, _ = manager(language)
    info = {
        "entity_id": "binary_sensor.bedroom_window", "failed_check": "availability",
        "observed_value": "unavailable", "source_reference": "TECHNICAL_METADATA",
    }
    subject.notify("InputMonitoringUnavailable", 3, FaultState.SET, info, "window")
    sent = app.call_service.call_args.kwargs
    assert sent["title"] == prefix + " Okno sypialni — prawe"
    assert sent["message"] == action
    assert "unavailable" not in sent["title"] + sent["message"]
    assert "TECHNICAL_METADATA" not in sent["message"]
    assert len(sent["title"]) < 90 and len(sent["message"]) < 90
    assert subject.active_notification["window"]["_details"]["observed_value"] == "unavailable"
    assert subject.notification_history[-1]["message"] == sent["message"]


@pytest.mark.parametrize("language", ["pl", "en", "de"])
@pytest.mark.parametrize("value", ["unavailable", "unknown", "none"])
def test_raw_absent_reading_is_localized_without_leaking_source_metadata(language, value):
    subject, app, _ = manager(language)
    subject.notify("TechnicalFaultKey", 3, FaultState.SET, {"observed_value": value}, "tag")
    sent = app.call_service.call_args.kwargs
    assert sent["message"] == subject.localizer.text(f"notification.observation.{value}")
    if language != "en":
        assert value not in sent["message"]
    assert "TechnicalFaultKey" not in sent["title"]


def test_l2_guidance_is_short_without_losing_the_full_saved_list_or_explicit_count():
    subject, app, clock = manager()
    subject.notify("Fault", 2, FaultState.SET, None, "tag", friendly_name="Problem z temperaturą")
    for key, text in [("a", "Zamknij okno biura."), ("b", "Zamknij okno kuchni."), ("duplicate", "Zamknij okno biura."), ("c", "Sprawdź termostat.")]:
        subject.upsert_recovery_guidance(key, text, "tag")
    clock.return_value += 1
    subject.tick()
    body = app.call_service.call_args.kwargs["message"]
    assert body == "• Zamknij okno biura.\n• Zamknij okno kuchni.\nPozostałe zalecenia: 1. Otwórz Safety Home."
    assert len(subject.active_notification["tag"]["_recovery_messages"]) == 4
    subject.remove_recovery_guidance("a", "tag")
    subject.remove_recovery_guidance("duplicate", "tag")
    clock.return_value += 1
    subject.tick()
    assert "Sprawdź termostat." in app.call_service.call_args.kwargs["message"]
    assert "Zamknij okno biura." not in app.call_service.call_args.kwargs["message"]


def test_l1_keeps_complete_owner_instructions_and_urgent_title():
    subject, app, clock = manager()
    evacuation = "Opuść zagrożone miejsce, nie używaj przełączników elektrycznych i wezwij służby z bezpiecznego miejsca."
    subject.notify("Gas", 1, FaultState.SET, {"recommendation": evacuation}, "gas", friendly_name="Wykryto gaz")
    assert app.call_service.call_args.kwargs["title"] == "PILNE: Wykryto gaz"
    assert app.call_service.call_args.kwargs["message"] == evacuation
    instructions = ["Instrukcja " + str(index) + "!" * 900 for index in range(3)]
    for index, instruction in enumerate(instructions):
        subject.upsert_recovery_guidance(str(index), instruction, "gas")
    clock.return_value += 1
    subject.tick()
    body = app.call_service.call_args.kwargs["message"]
    assert evacuation in body
    assert all(instruction in body for instruction in instructions)
    assert len(body) > 2048  # The journal limit must never truncate the actual alert.


def test_recovery_uses_subject_without_retaining_active_failure_wording():
    subject, app, _ = manager()
    info = {"entity_id": "binary_sensor.window", "failed_check": "availability", "observed_value": "unavailable"}
    subject.notify("InputMonitoringUnavailable", 3, FaultState.SET, info, "window")
    subject.notify("InputMonitoringUnavailable", 3, FaultState.CLEARED, info, "window")
    sent = app.call_service.call_args.kwargs
    assert sent["title"] == "Problem ustąpił"
    assert sent["message"] == "Okno sypialni — prawe."
    assert "Brak odczytu" not in sent["message"]
    assert subject.notification_history[-1]["kind"] == "resolved"


def test_missing_friendly_name_uses_localized_subject_and_never_technical_binding():
    subject, app, _ = manager()
    app.get_state.return_value = None
    subject.notify("InternalInputKey", 3, FaultState.SET, {
        "entity_id": "binary_sensor.technical", "entity_key": "ExternalOpeningBedroomRightWindow",
        "failed_check": "availability",
    }, "tag")
    assert app.call_service.call_args.kwargs["title"] == "Brak odczytu: Monitorowany czujnik"


def test_presentation_keys_have_nonempty_translations_and_identical_placeholders():
    base = Path(__file__).parents[1] / "components/core/locales"
    translations = {language: yaml.safe_load((base / f"{language}.yml").read_text(encoding="utf-8")) for language in ["en", "pl", "de"]}
    keys = {key for key in translations["en"] if key.startswith("notification.")}
    for key in keys:
        placeholders = []
        for values in translations.values():
            assert isinstance(values.get(key), str) and values[key].strip(), key
            placeholders.append({name for _, name, _, _ in string.Formatter().parse(values[key]) if name})
        assert placeholders[0] == placeholders[1] == placeholders[2], key
