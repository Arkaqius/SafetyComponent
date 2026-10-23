"""Resolve live HA labels for warnings and manual work, preserving identities."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from components.core.entity_names import friendly_entity_name
from components.core.event_bus import EventBus
from components.core.localization import Localizer
from components.recovery_manager.manual_actions import manual_action
from components.safetycomponents.safety_doors.safety_doors_component import SafetyDoorsComponent


@pytest.mark.parametrize("snapshot", [None, "unavailable", {}, {"attributes": None}, {"attributes": {"friendly_name": " "}}])
def test_missing_name_retains_context_without_assuming_entity_health(snapshot):
    app = Mock()
    app.get_state.return_value = snapshot
    assert friendly_entity_name(app, "binary_sensor.window", "Window") == "Window"
    app.get_state.side_effect = RuntimeError("read unavailable")
    assert friendly_entity_name(app, "binary_sensor.window", "Window") == "Window"
    assert friendly_entity_name(app, None, "Window") == "Window"


@pytest.mark.parametrize("language", ["pl", "en", "de"])
def test_manual_instruction_uses_current_ha_name_after_startup_and_rename(language):
    app = Mock()
    app.localizer = Localizer({"language": language})
    action = manual_action(
        "InspectInputExternalOpeningBedroomRightWindow",
        subject="ExternalOpeningBedroomRightWindow",
        instruction_key="recovery.inspect_input", result_key="recovery.result_input",
        entity_id="binary_sensor.window",
    )
    symptom = SimpleNamespace(parameters={"check_key": "availability"}, module=SimpleNamespace())
    for label in ("Okno sypialni - prawe", "Prawe okno po zmianie nazwy"):
        app.get_state.return_value = {"state": "unavailable", "attributes": {"friendly_name": label}}
        result = action.rec_fun(app, symptom, None, **action.params)
        assert label in result.instruction
        assert "ExternalOpeningBedroomRightWindow" not in result.instruction
        assert result.notifications == [result.instruction]
        assert not result.changed_actuators
    assert action.name == "InspectInputExternalOpeningBedroomRightWindow"
    assert action.params["entity_id"] == "binary_sensor.window"
    app.call_service.assert_not_called()


@pytest.mark.parametrize("key,label", [("GarageGate", "Brama garażowa"), ("ExternalGate", "Brama zewnętrzna")])
def test_gate_fault_uses_ha_friendly_name_and_keeps_stable_fault_identity(key, label):
    app = Mock()
    app.localizer = Localizer({"language": "pl"})
    app.get_state.return_value = {"state": "on", "attributes": {"friendly_name": label}}
    component = SafetyDoorsComponent(app, Mock(), EventBus(), Mock())
    symptoms, recoveries = component.get_symptoms_data(
        {component.component_name: component},
        [{key: {"entity_id": "binary_sensor.gate", "area_id": "outside"}}],
    )
    definitions = component.get_fault_definitions()
    fault_id = f"SafetyDoorOpenTimeout{key}"
    assert set(definitions) == {fault_id}
    assert label in definitions[fault_id]["name"]
    assert key not in definitions[fault_id]["name"]
    result = recoveries[fault_id].rec_fun(app, symptoms[fault_id], None, **recoveries[fault_id].params)
    assert label in result.instruction
    assert result.changed_sensors == {"binary_sensor.gate": "off"}
    assert not result.changed_actuators
    app.call_service.assert_not_called()
