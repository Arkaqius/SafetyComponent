from typing import List
from unittest.mock import Mock

import pytest

from components.core.common_entities import CommonEntities
from components.core.event_bus import EventBus
from components.core.types_common import FaultState, SMState
from components.safetycomponents.core.safety_component import (
    SafetyComponent,
    clear_registered_components,
    get_registered_components,
    register_safety_component,
)


class DummyComponent(SafetyComponent):
    component_name = "DummyComponent"

    def get_symptoms_data(self, modules, component_cfg):
        return {}, {}

    def init_safety_mechanism(self, sm_name: str, name: str, parameters: dict) -> bool:
        return True

    def enable_safety_mechanism(self, name: str, state: SMState) -> bool:
        return True


def _make_component():
    hass_app = Mock()
    hass_app.log = Mock()
    common_entities = CommonEntities(hass_app, {"outside_temp": "sensor.outside"})
    event_bus = EventBus()
    return DummyComponent(hass_app, common_entities, event_bus)


def test_register_safety_component_errors_on_unknown_name():
    class BadComponent(SafetyComponent):
        component_name = "UNKNOWN"

        def get_symptoms_data(self, modules, component_cfg):
            return {}, {}

        def init_safety_mechanism(self, sm_name: str, name: str, parameters: dict) -> bool:
            return True

        def enable_safety_mechanism(self, name: str, state: SMState) -> bool:
            return True

    with pytest.raises(ValueError):
        register_safety_component(BadComponent)


def test_register_safety_component_duplicate_raises():
    original = get_registered_components()
    try:
        with pytest.raises(ValueError):
            register_safety_component(original["TemperatureComponent"])
    finally:
        clear_registered_components()
        for cls in original.values():
            register_safety_component(cls)


def test_validate_entities_reports_missing_and_type_errors():
    component = _make_component()
    component.hass_app.log = Mock()

    assert component.validate_entities({}, {"temp": float}) is False

    sm_args = {"temps": [1, 2]}
    assert component.validate_entities(sm_args, {"temps": List[str]}) is False


def test_process_symptom_emits_event():
    component = _make_component()
    events = []

    component.event_bus.subscribe("symptom", lambda **payload: events.append(payload))
    counter, force = component.process_symptom(
        "symptom", 0, True, {}, debounce_limit=1
    )

    assert counter == 1
    assert force is False
    assert events[0]["symptom_id"] == "symptom"
    assert events[0]["state"] == FaultState.SET


def test_sm_recalled_raises_not_implemented():
    component = _make_component()
    with pytest.raises(NotImplementedError):
        component.sm_recalled()
