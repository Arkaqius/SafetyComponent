"""Contracts for manual recovery across the installed component families."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from components.core.event_bus import EventBus
from components.core.localization import Localizer
from components.core.self_diagnostics import SelfDiagnosticsComponent
from components.core.types_common import FaultState
from components.safetycomponents.internal_environmental_hazard.internal_environmental_hazard_monitor_component import (
    InternalEnvironmentalHazardMonitorComponent,
)
from components.safetycomponents.temperature.temperature_component import TemperatureComponent
from tests.test_functional_safety_monitor import make_monitor
from tests.test_internal_environmental_hazard_component import _configuration
from tests.test_external_hazard_component import _component


@pytest.mark.parametrize("language", ["en", "pl", "de"])
def test_internal_hazards_are_advisory_and_detector_repairs_require_owner_evidence(language):
    app = MagicMock()
    app.localizer = Localizer({"language": language})
    component = InternalEnvironmentalHazardMonitorComponent(app, MagicMock(), EventBus(), MagicMock())
    symptoms, actions = component.get_symptoms_data(
        {component.component_name: component}, _configuration(include_leak=True)
    )
    assert set(actions) == set(symptoms)
    for name, action in actions.items():
        symptom = symptoms[name]
        symptom.state = FaultState.SET
        result = action.rec_fun(app, symptom, None, **action.params)
        assert result.execution_policy == "manual"
        assert not result.changed_actuators
        assert not result.changed_sensors
        assert action.params["subject"] in result.instruction
        assert result.expected_result
        if symptom.parameters["kind"] == "alarm":
            assert result.completion_condition == "advisory"
            assert not result.manual_report_allowed
        else:
            assert result.completion_condition == "owner_clear"
            assert result.manual_report_allowed
        assert symptom.state == FaultState.SET
    app.call_service.assert_not_called()


def test_platform_and_maintenance_faults_all_have_manual_owner_qualified_repair():
    monitor, bus, _ = make_monitor({})
    symptoms, actions = monitor.get_symptoms_data({monitor.component_name: monitor}, {})
    assert set(actions) == set(symptoms)
    for name, action in actions.items():
        result = action.rec_fun(monitor.hass_app, symptoms[name], None, **action.params)
        assert result.execution_policy == "manual"
        assert result.completion_condition == "owner_clear"
        assert result.manual_report_allowed
        assert not result.changed_actuators
        assert not result.changed_sensors
        assert result.instruction
    assert not bus.events


def test_provider_and_each_app_health_path_keep_independent_repair_proposals():
    app = MagicMock()
    app.localizer = Localizer()
    diagnostics = SelfDiagnosticsComponent(
        app, MagicMock(), EventBus(), MagicMock(),
        {"OpenMeteoWeatherApiComponent": object(), "ImgwWarningsApiComponent": object()},
    )
    symptoms, _ = diagnostics.get_symptoms_data({}, {})
    symptoms.update(diagnostics.add_targeted_causes({"SmokePath", "LeakPath"}, {"WindowPath"}))
    actions = diagnostics.get_recovery_actions()
    assert set(actions) == set(symptoms)
    for name, action in actions.items():
        result = action.rec_fun(app, symptoms[name], None, **action.params)
        assert result.completion_condition == "owner_clear"
        assert result.manual_report_allowed
        assert not result.changed_actuators
        assert result.instruction
    assert "SmokePath" in actions["AppHealthEvaluation_SmokePath"].params["subject"]
    assert "LeakPath" not in actions["AppHealthEvaluation_SmokePath"].params["subject"]
    app.call_service.assert_not_called()


@pytest.mark.parametrize("method", ["_get_sm_tc_3_recovery_action", "_get_sm_tc_4_recovery_action"])
def test_high_temperature_inspection_can_be_reported_without_window_or_climate_action(method):
    app = MagicMock()
    app.localizer = Localizer({"language": "pl"})
    component = TemperatureComponent(app, MagicMock(), EventBus(), MagicMock())
    action = getattr(component, method)({}, "Office", {"area_id": "office", "area_name": "Biuro"}, "High")
    symptom = SimpleNamespace(parameters={}, module=component, state=FaultState.SET)
    result = action.rec_fun(app, symptom, None, **action.params)
    assert result.completion_condition == "operator_report"
    assert result.manual_report_allowed
    assert "Biuro" in result.instruction
    assert not result.changed_actuators
    assert not result.changed_sensors
    assert symptom.state == FaultState.SET
    app.call_service.assert_not_called()


@pytest.mark.parametrize("outside", [None, "unavailable", "unknown", "nan", "inf"])
def test_unavailable_outside_evidence_keeps_temperature_inspection_without_window_advice(outside):
    app = MagicMock()
    app.localizer = Localizer()
    app.get_state.return_value = "17"
    common = MagicMock()
    common.get_outisde_temperature.return_value = outside
    symptom = SimpleNamespace(parameters={"temperature_sensor": "sensor.room"}, module=object())
    result = TemperatureComponent.RiskyTemperature_recovery(
        app, symptom, common, location="Room", actuator="switch.window", window_sensor="binary_sensor.window",
    )
    assert result.execution_policy == "manual"
    assert result.completion_condition == "operator_report"
    assert not result.changed_actuators
    assert not result.changed_sensors
    app.call_service.assert_not_called()


def test_external_missing_capability_has_manual_repair_without_fake_contact_dependency():
    component, app, _, _ = _component()
    symptoms, actions = component.get_symptoms_data(
        {component.component_name: component}, {"policy": component.policy, "openings": component.openings},
    )
    names = [name for name in symptoms if name.startswith("ExternalHazardDataUnavailable")]
    assert len(names) == 3
    for name in names:
        action = actions[name]
        result = action.rec_fun(app, symptoms[name], None, **action.params)
        assert result.completion_condition == "owner_clear"
        assert result.manual_report_allowed
        assert not result.changed_sensors
        assert not result.changed_actuators
        assert symptoms[name].parameters["capability"] in result.instruction
    assert not app.service_calls


def test_app_repair_names_failed_delivery_channel_and_persistence_operation():
    app = MagicMock()
    app.localizer = Localizer()
    diagnostics = SelfDiagnosticsComponent(app, MagicMock(), EventBus(), MagicMock(), {})
    symptoms, actions = diagnostics.get_symptoms_data({}, {})
    diagnostics.record_app_cause("delivery", True, detail="notify.caregiver")
    diagnostics.record_app_cause("delivery", False, detail="notify.other")
    diagnostics.record_app_cause("persistence", True, detail="recovery_state", operation="restore")
    for name, included, excluded in (
        ("AppHealthDelivery", "notify.caregiver", "notify.other"),
        ("AppHealthPersistenceRecoveryState", "restore", "notification_state"),
    ):
        action = actions[name]
        result = action.rec_fun(app, symptoms[name], None, **action.params)
        assert included in result.instruction
        assert excluded not in result.instruction
        assert not result.changed_actuators
    app.call_service.assert_not_called()


def test_temperature_with_unavailable_actuator_keeps_observed_manual_window_work():
    app = MagicMock()
    app.localizer = Localizer()
    states = {"sensor.room": "17", "switch.window": "unavailable", "binary_sensor.window": "on"}
    app.get_state.side_effect = states.get
    common = MagicMock()
    common.get_outisde_temperature.return_value = "10"
    symptom = SimpleNamespace(parameters={"temperature_sensor": "sensor.room"}, module=object())
    result = TemperatureComponent.RiskyTemperature_recovery(
        app, symptom, common, location="Room", actuator="switch.window", window_sensor="binary_sensor.window",
    )
    assert result.execution_policy == "manual"
    assert result.changed_sensors == {"binary_sensor.window": "off"}
    assert not result.changed_actuators
    app.call_service.assert_not_called()


@pytest.mark.parametrize("invalid_room", ["nan", "inf", "unknown"])
def test_invalid_room_temperature_cannot_authorize_window_work(invalid_room):
    app = MagicMock()
    app.localizer = Localizer()
    app.get_state.return_value = invalid_room
    common = MagicMock()
    common.get_outisde_temperature.return_value = "10"
    symptom = SimpleNamespace(parameters={"temperature_sensor": "sensor.room"}, module=object())
    result = TemperatureComponent.RiskyTemperature_recovery(
        app, symptom, common, location="Room", actuator="switch.window", window_sensor="binary_sensor.window",
    )
    assert result.completion_condition == "operator_report"
    assert not result.changed_actuators
    assert not result.changed_sensors
    app.call_service.assert_not_called()
