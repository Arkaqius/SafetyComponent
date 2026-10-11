"""Regression contracts for consolidated diagnostics and source-report timing."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from SafetyFunctions import SafetyFunctions
from components.core.event_bus import EventBus
from components.core.fault_state_policy import FaultEvaluationStatus
from components.core.self_diagnostics import SelfDiagnosticsComponent
from components.core.types_common import Symptom
from components.faults_manager.cfg_parser import get_faults, validate_fault_routes
from components.faults_manager.fault_manager import FaultManager
from components.safetycomponents.entity_monitor.schema import validate_entity_monitor_config
from test_entity_monitor_component import _component, _config


def test_report_timeout_normalizes_without_renewing_source_or_mutating_configuration():
    raw = {"explicit_entities": {"Office": {
        "entity_id": "sensor.office_temperature",
        "description": "Office temperature",
        "report_timeout_seconds": 3600,
        "failure_debounce_seconds": 60,
        "checks": {"freshness": {"timestamp_source": "last_reported"}},
    }}}
    original = deepcopy(raw)
    runtime = validate_entity_monitor_config(raw)
    assert runtime["explicit_entities"][0]["checks"]["freshness"] == {
        "timestamp_source": "last_reported", "max_silence_seconds": 3600,
    }
    assert raw == original


@pytest.mark.parametrize("fields", [
    {"report_timeout_seconds": 0},
    {"report_timeout_seconds": 60},
    {"report_timeout_seconds": 60, "checks": None},
    {"report_timeout_seconds": 60, "checks": {"freshness": 42}},
    {"report_timeout_seconds": 60, "checks": {"freshness": {
        "timestamp_source": "", "max_silence_seconds": 60,
    }}},
    {"report_timeout_seconds": 60, "checks": {"freshness": {
        "timestamp_source": "last_reported", "max_silence_seconds": 120,
    }}},
])
def test_report_timeout_rejects_missing_untrusted_or_conflicting_contract(fields):
    with pytest.raises(ValueError):
        validate_entity_monitor_config({"explicit_entities": {"Office": {
            "entity_id": "sensor.office_temperature", "description": "Office", **fields,
        }}})


def test_component_timeout_override_inherits_source_and_internal_detection_allocation():
    dependency = _config()["component_entities"][0]
    dependency.update(failure_debounce_seconds=60, detection_budget_seconds=4020)
    dependency["checks"]["freshness"] = {
        "timestamp_source": "last_reported", "max_silence_seconds": 3600,
    }
    override = validate_entity_monitor_config({}, calibration={"component_overrides": {
        "TemperatureOffice": {"report_timeout_seconds": 7200, "failure_debounce_seconds": 30},
    }})["component_overrides"]
    calibrated = SafetyFunctions._calibrate_component_dependency(dependency, override, 15, 60)
    assert calibrated["checks"]["freshness"] == {
        "timestamp_source": "last_reported", "max_silence_seconds": 7200,
    }
    assert calibrated["detection_budget_seconds"] == 7590
    assert dependency["checks"]["freshness"]["max_silence_seconds"] == 3600


def test_component_timeout_cannot_enable_freshness_without_source_contract():
    dependency = _config()["component_entities"][0]
    dependency["checks"] = {}
    with pytest.raises(ValueError, match="trustworthy timestamp_source"):
        SafetyFunctions._calibrate_component_dependency(
            dependency, {"TemperatureOffice": {"report_timeout_seconds": 3600}}, 15, 60,
        )


@pytest.mark.parametrize("legacy", [
    "TemperatureMonitoringUnavailable", "SafetyDoorMonitoringUnavailable",
    "ExternalOpeningMonitoringUnavailable", "CommonInputUnavailable",
])
def test_legacy_input_fault_declarations_route_into_one_fault(mocked_hass_app_basic, legacy):
    app, _, component = _component(mocked_hass_app_basic)
    app.get_state = Mock(return_value=None)
    config = _config()
    config["component_entities"][0]["fault_name"] = legacy
    component.get_symptoms_data({component.component_name: component}, config)
    assert set(component.get_fault_definitions()) == {"InputMonitoringUnavailable"}


def test_slow_legacy_cadence_cannot_delay_short_freshness_or_qualification(mocked_hass_app_basic):
    app, _, component = _component(mocked_hass_app_basic)
    app.get_state = Mock(return_value=None)
    config = _config()
    config["evaluation_interval_seconds"] = 3600
    dependency = config["component_entities"][0]
    dependency["checks"]["freshness"]["max_silence_seconds"] = 3600
    dependency["failure_debounce_seconds"] = 15
    component.get_symptoms_data({component.component_name: component}, config)
    assert component._policy["evaluation_interval_seconds"] == 15
    dependency["checks"]["freshness"]["max_silence_seconds"] = 30
    component.get_symptoms_data({component.component_name: component}, config)
    assert component._has_short_budget(component._entities["TemperatureOffice"].dependency)


def test_unrelated_diagnostic_families_share_source_but_retain_fault_ownership(mocked_hass_app_basic):
    app, _, component = _component(mocked_hass_app_basic)
    app.get_state = Mock(return_value=None)
    config = _config()
    config["component_entities"].append({
        **config["component_entities"][0], "key": "ExternalRecoveryOffice",
        "fault_name": "ExternalRecoveryUnavailable",
    })
    config["component_entities"][0].update(failure_debounce_seconds=60, detection_budget_seconds=4020)
    config["component_entities"][0]["checks"]["freshness"]["max_silence_seconds"] = 3600
    config["component_entities"][1].update(checks={}, detection_budget_seconds=30)
    component.state_reader = SimpleNamespace(register=Mock(), report=Mock(return_value=None))
    symptoms, _ = component.get_symptoms_data({component.component_name: component}, config)
    assert set(component.get_fault_definitions()) == {
        "InputMonitoringUnavailable", "ExternalRecoveryUnavailable",
    }
    assert set(component._entities) == {"TemperatureOffice", "ExternalRecoveryOffice"}
    component.state_reader.register.assert_called_once_with(
        "EntityMonitorComponent:5", {"sensor.office_temperature"}, 5,
    )
    for symptom in symptoms.values():
        component.init_safety_mechanism(symptom.sm_name, symptom.name, symptom.parameters)
    app.listen_state.assert_called_once_with(component._entity_changed, "sensor.office_temperature")
    app.cancel_listen_state = Mock()
    component.stop()
    app.cancel_listen_state.assert_called_once()


def test_external_fault_keeps_provider_and_capability_failures_independent():
    app = Mock(localizer=None)
    mqtt = Mock()
    mqtt.get_attributes.return_value = {}
    bus = EventBus()
    diagnostics = SelfDiagnosticsComponent(app, Mock(), bus, mqtt, {
        "OpenMeteoWeatherApiComponent": Mock(), "ImgwWarningsApiComponent": Mock(),
    })
    symptoms, _ = diagnostics.get_symptoms_data({}, {})
    capability = "ExternalHazardDataUnavailableWeatherPointModel"
    symptoms[capability] = Symptom(capability, "sm_ext_provider_unavailable", Mock(), {})
    faults = get_faults(diagnostics.get_fault_definitions())
    validate_fault_routes(symptoms, faults)
    manager = FaultManager(app, {}, symptoms, faults, bus, mqtt)
    fault = faults["ExternalDataUnavailable"]
    weather = "ProviderHealthOpenMeteoWeather"
    warnings = "ProviderHealthImgwWarnings"
    manager.set_symptom(weather, {"provider": "weather"})
    manager.set_symptom(capability, {"capability": "WeatherPointModel"})
    manager.clear_symptom(warnings, {})
    manager.clear_symptom(weather, {})
    assert fault.evaluation.active is True
    assert fault.evaluation.active_contributors == {capability}
    manager.mark_evaluation_unavailable(capability)
    assert fault.evaluation.active is True
    manager.clear_symptom(capability, {})
    assert fault.evaluation.status == FaultEvaluationStatus.PASS
