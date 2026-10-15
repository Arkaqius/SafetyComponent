"""Verify device contact keeps an unchanged, valid temperature usable."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from SafetyFunctions import SafetyFunctions
from components.core.types_common import SMState
from components.safetycomponents.temperature.temperature_component import TemperatureComponent
from test_entity_monitor_component import _component, _config, _snapshot


def _temperature_dependency() -> dict:
    dependencies = TemperatureComponent.get_entity_dependencies([
        {"Office": {
            "temperature_sensor": "sensor.office_temperature",
            "SM_TC_MIN_VALID_TEMPERATURE_C": -40,
            "SM_TC_MAX_VALID_TEMPERATURE_C": 80,
            "SM_TC_2_DERIVATIVE_SAMPLE_MINUTES": 15,
        }}
    ])
    return next(item for item in dependencies if item["key"] == "TemperatureOffice")


def _contact_monitor(mocked_hass_app_basic, state: str = "21.5"):
    app, _, component = _component(mocked_hass_app_basic)
    clock = [datetime(2026, 10, 14, 22, tzinfo=timezone.utc)]
    old = _snapshot(state, clock[0] - timedelta(hours=3))
    report = {
        **old,
        "last_reported": old["last_updated"],
        "last_contact_at": (clock[0] - timedelta(seconds=20)).isoformat(),
        "last_contact_source_entity": "sensor.office_last_seen",
    }
    current = {"report": report}
    app.get_state = MagicMock(return_value=old)
    component._now = lambda: clock[0]
    component.state_reader = SimpleNamespace(
        register=MagicMock(), report=lambda *_: current["report"],
    )
    config = _config()
    config["component_entities"][0].update(_temperature_dependency())
    symptoms, _ = component.get_symptoms_data({component.component_name: component}, config)
    for symptom in symptoms.values():
        component.init_safety_mechanism(symptom.sm_name, symptom.name, symptom.parameters)
        component.enable_safety_mechanism(symptom.name, SMState.ENABLED)
    return app, component, clock, current


def test_recent_contact_accepts_unchanged_temperature_and_retains_real_report_times(
    mocked_hass_app_basic,
):
    _, component, clock, current = _contact_monitor(mocked_hass_app_basic)
    component._evaluate_entity("TemperatureOffice")
    runtime = component._entities["TemperatureOffice"]
    assert runtime.checks["freshness"].reason == "fresh"
    assert runtime.checks["freshness"].observed_value == 20
    assert runtime.last_valid_at == clock[0] - timedelta(seconds=20)
    attributes = component._diagnostic_attributes(runtime)
    assert attributes["last_reported"] == current["report"]["last_reported"]
    assert attributes["last_contact_at"] == current["report"]["last_contact_at"]


def test_new_temperature_write_cannot_replace_expired_device_contact(mocked_hass_app_basic):
    _, component, clock, current = _contact_monitor(mocked_hass_app_basic)
    current["report"]["last_reported"] = clock[0].isoformat()
    current["report"]["last_contact_at"] = (clock[0] - timedelta(seconds=3601)).isoformat()
    component._evaluate_entity("TemperatureOffice")
    runtime = component._entities["TemperatureOffice"]
    assert runtime.checks["freshness"].reason == "freshness_expired"
    assert not runtime.checks["freshness"].active
    clock[0] += timedelta(seconds=60)
    component._evaluate_entity("TemperatureOffice")
    assert runtime.checks["freshness"].active


@pytest.mark.parametrize("contact", [None, "invalid", "2026-10-14T22:00:01+00:00"])
def test_missing_invalid_or_future_contact_cannot_clear_an_active_fault(
    mocked_hass_app_basic, contact,
):
    _, component, clock, current = _contact_monitor(mocked_hass_app_basic)
    component._evaluate_entity("TemperatureOffice")
    runtime = component._entities["TemperatureOffice"]
    runtime.checks["freshness"].active = True
    current["report"]["last_contact_at"] = contact
    current["report"]["last_reported"] = clock[0].isoformat()
    component._evaluate_entity("TemperatureOffice")
    assert runtime.checks["freshness"].active
    assert runtime.checks["freshness"].result == "unevaluable"
    assert runtime.checks["freshness"].pending_recovery_since is None
    current["report"]["last_contact_at"] = clock[0].isoformat()
    component._evaluate_entity("TemperatureOffice")
    assert runtime.checks["freshness"].active
    clock[0] += timedelta(seconds=10)
    component._evaluate_entity("TemperatureOffice")
    assert not runtime.checks["freshness"].active


@pytest.mark.parametrize("state,failed_check", [
    ("unknown", "availability"), ("unavailable", "availability"),
    ("NaN", "finite_number"), ("100", "numeric_range"),
])
def test_contact_does_not_override_an_unusable_or_out_of_range_temperature(
    mocked_hass_app_basic, state, failed_check,
):
    _, component, _, _ = _contact_monitor(mocked_hass_app_basic, state)
    component._evaluate_entity("TemperatureOffice")
    runtime = component._entities["TemperatureOffice"]
    assert runtime.checks[failed_check].result == "pending_failure"
    assert runtime.last_valid_value is None


def test_new_cache_state_keeps_contact_from_authoritative_report(mocked_hass_app_basic):
    app, component, clock, current = _contact_monitor(mocked_hass_app_basic)
    app.get_state.return_value = _snapshot("22.0", clock[0])
    component._evaluate_entity("TemperatureOffice")
    runtime = component._entities["TemperatureOffice"]
    assert runtime.snapshot["state"] == "22.0"
    assert runtime.snapshot["last_contact_at"] == current["report"]["last_contact_at"]
    assert runtime.checks["freshness"].reason == "fresh"
    current["report"] = None
    component._evaluate_entity("TemperatureOffice")
    assert runtime.checks["availability"].reason == "source_report_unavailable"
    assert runtime.checks["freshness"].result == "unevaluable"


def test_explicit_thermostat_override_retains_its_integration_timestamp():
    dependency = _temperature_dependency()
    calibrated = SafetyFunctions._calibrate_component_dependency(
        dependency,
        {"TemperatureOffice": {
            "failure_debounce_seconds": 15,
            "detection_budget_seconds": 14415,
            "checks": {"freshness": {
                "timestamp_source": "last_updated", "max_silence_seconds": 14400,
            }},
        }},
        default_failure_debounce=15, default_recovery_debounce=60,
    )
    assert calibrated["checks"]["freshness"] == {
        "timestamp_source": "last_updated", "max_silence_seconds": 14400,
    }
    assert dependency["checks"]["freshness"]["timestamp_source"] == "last_contact_at"
