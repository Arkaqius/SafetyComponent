"""Recovered evidence must reach faults without bypassing qualification."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from components.core.common_entities import CommonEntities
from components.core.event_bus import EventBus
from components.core.fault_state_policy import FaultEvaluationStatus as Status
from components.core.startup_grace import StartupGrace
from components.core.types_common import Fault, FaultState, Symptom
from components.faults_manager.fault_manager import FaultManager
from components.safetycomponents.core.safety_component import (
    DebounceState,
    SafetyMechanismResult,
    safety_mechanism_decorator,
)
from test_safety_component_core import DummyComponent


class EvaluatedComponent(DummyComponent):
    """Exercise the production wrapper with controlled predicate evidence."""

    @safety_mechanism_decorator
    def evaluate(self, sm, entities_changes=None):
        result = self.results[sm.name]
        if isinstance(result, Exception):
            raise result
        return result


def monitored_fault(*, grace_seconds=0):
    """Wire a component through startup qualification to the real FaultManager."""
    hass = Mock()
    hass.get_state.return_value = None
    mqtt = Mock()
    mqtt.get_attributes.return_value = {}
    bus = EventBus()
    component = EvaluatedComponent(
        hass, CommonEntities(hass, {"outside_temp": "sensor.outside"}), bus, mqtt
    )
    component.results = {}
    mechanisms = {
        name: SimpleNamespace(
            name=name,
            isEnabled=True,
            sm_args={"debounce_limit": 2, "re_eval_delay_seconds": 30},
        )
        for name in ("first", "second")
    }
    symptoms = {name: Symptom(name, "sm_test", component, {}) for name in mechanisms}
    fault = Fault("TestFault", ["sm_test"], 3)
    for name in mechanisms:
        component.debounce_states[name] = DebounceState(0, False)
        component.results[name] = SafetyMechanismResult(False, {})
        fault.evaluation.bind(name)
    manager = FaultManager(hass, {}, symptoms, {fault.name: fault}, bus, mqtt)
    now = [0.0]
    grace = StartupGrace(bus, set(mechanisms), grace_seconds, clock=lambda: now[0])
    bus.subscribe("qualified_symptom", manager.handle_symptom_event)
    bus.subscribe(
        "qualified_evaluation_unavailable", manager.mark_evaluation_unavailable
    )
    fault_events = []
    bus.subscribe("fault", lambda **payload: fault_events.append(payload))
    return component, mechanisms, manager, fault, fault_events, now, grace


def qualify(component, mechanism):
    """Supply enough consecutive evaluations for the configured debounce."""
    for _ in range(4):
        component.evaluate(mechanism)


@pytest.mark.parametrize("violation", [False, True])
@pytest.mark.parametrize("failure", ["unavailable", "malformed", "exception"])
def test_same_result_requalifies_after_invalid_or_failed_evaluation(violation, failure):
    component, mechanisms, manager, fault, events, _, _ = monitored_fault()
    qualify(component, mechanisms["second"])
    component.results["first"] = SafetyMechanismResult(violation, {})
    qualify(component, mechanisms["first"])
    expected = Status.FAIL if violation else Status.PASS
    assert fault.evaluation.status is expected
    events.clear()

    if failure == "unavailable":
        component.results["first"] = SafetyMechanismResult(False, {}, False)
        component.evaluate(mechanisms["first"])
    else:
        component.results["first"] = (
            SafetyMechanismResult("invalid", {})
            if failure == "malformed"
            else ValueError("failed read")
        )
        with pytest.raises((TypeError, ValueError)):
            component.evaluate(mechanisms["first"])
    assert fault.evaluation.status is Status.UNEVALUABLE
    assert fault.evaluation.active is violation
    assert events == []
    # FaultManager retains the last qualified condition while evidence is unknown.
    assert manager.check_symptom("first") is (
        FaultState.SET if violation else FaultState.CLEARED
    )

    component.results["first"] = SafetyMechanismResult(violation, {})
    component.evaluate(mechanisms["first"])
    assert fault.evaluation.status is Status.UNEVALUABLE
    assert events == []
    component.evaluate(mechanisms["first"])
    assert fault.evaluation.status is expected
    assert fault.evaluation.active is violation
    assert len(events) == 1
    qualify(component, mechanisms["first"])
    assert len(events) == 1  # Stable valid evidence does not repeat lifecycle events.


def test_active_fault_waits_for_recovered_negative_evidence_from_every_contributor():
    component, mechanisms, _, fault, events, _, _ = monitored_fault()
    qualify(component, mechanisms["first"])
    component.results["second"] = SafetyMechanismResult(True, {})
    qualify(component, mechanisms["second"])
    assert fault.evaluation.active
    component.results["first"] = SafetyMechanismResult(False, {}, False)
    component.evaluate(mechanisms["first"])
    component.results["second"] = SafetyMechanismResult(False, {})
    qualify(component, mechanisms["second"])
    assert fault.evaluation.status is Status.UNEVALUABLE
    assert fault.evaluation.active
    events.clear()

    component.results["first"] = SafetyMechanismResult(False, {})
    component.evaluate(mechanisms["first"])
    assert fault.evaluation.active
    assert events == []
    component.evaluate(mechanisms["first"])
    assert fault.evaluation.status is Status.PASS
    assert not fault.evaluation.active
    assert [event["fault_state"] for event in events] == [FaultState.CLEARED]
    assert events[0]["should_notify"] is True


def test_another_data_gap_discards_partial_requalification():
    component, mechanisms, _, fault, _, _, _ = monitored_fault()
    qualify(component, mechanisms["second"])
    component.results["first"] = SafetyMechanismResult(True, {})
    qualify(component, mechanisms["first"])
    for _ in range(2):
        component.results["first"] = SafetyMechanismResult(False, {}, False)
        component.evaluate(mechanisms["first"])
        component.results["first"] = SafetyMechanismResult(False, {})
        component.evaluate(mechanisms["first"])
        assert fault.evaluation.status is Status.UNEVALUABLE
        assert fault.evaluation.active
    component.evaluate(mechanisms["first"])
    assert fault.evaluation.status is Status.PASS


def test_requalification_after_invalidated_startup_evidence_obeys_grace():
    component, mechanisms, _, fault, events, now, grace = monitored_fault(
        grace_seconds=600
    )
    for mechanism in mechanisms.values():
        qualify(component, mechanism)
    component.results["first"] = SafetyMechanismResult(False, {}, False)
    component.evaluate(mechanisms["first"])
    now[0] = 600
    grace.finish()
    assert fault.evaluation.status is Status.UNEVALUABLE
    assert not fault.evaluation.active
    events.clear()
    component.results["first"] = SafetyMechanismResult(False, {})
    component.evaluate(mechanisms["first"])
    assert fault.evaluation.status is Status.UNEVALUABLE
    component.evaluate(mechanisms["first"])
    assert fault.evaluation.status is Status.PASS
    assert events[0]["should_notify"] is False


@pytest.mark.parametrize("active", [False, True])
def test_temperature_forecast_requalifies_unchanged_safe_room_after_rate_returns(
    mocked_hass_app_with_temp_component,
    active: bool,
):
    """Use actual forecast predicates and application routing across a data gap."""
    app, *_ = mocked_hass_app_with_temp_component
    app.initialize()
    component = app.sm_modules["TemperatureComponent"]
    mechanisms = [
        sm
        for sm in component.safety_mechanisms.values()
        if sm.name.endswith("ForeCast")
    ]
    states = {}
    for sm in mechanisms:
        sm.sm_args.update(
            cold_thr=18, hot_thr=26, forecast_timespan=2, debounce_limit=2
        )
        sensor = sm.sm_args["temperature_sensor"]
        states[sensor] = "22"
        states[f"{sensor}_rate"] = "0"
    app.get_state.side_effect = lambda entity_id, **kwargs: states.get(entity_id)
    for sm in mechanisms:
        for _ in range(4):
            sm.callback(sm)
    fault = app.fm.faults["RiskyTemperatureForecast"]
    assert fault.evaluation.status is Status.PASS

    if active:
        states["sensor.kitchen_temperature_rate"] = "-0.04"
        for _ in range(4):
            sm = component.safety_mechanisms["RiskyTemperatureKitchenForeCast"]
            sm.callback(sm)
        assert fault.evaluation.active

    office = [sm for sm in mechanisms if "Office" in sm.name]
    states["sensor.office_temperature_rate"] = "unavailable"
    for sm in office:
        sm.callback(sm)
    states["sensor.kitchen_temperature_rate"] = "0"
    for sm in mechanisms:
        if sm not in office:
            for _ in range(4):
                sm.callback(sm)
    assert fault.evaluation.status is Status.UNEVALUABLE
    assert fault.evaluation.active is active

    states["sensor.office_temperature_rate"] = "0"
    for sm in office:
        sm.callback(sm)
    assert fault.evaluation.status is Status.UNEVALUABLE
    assert fault.evaluation.active is active
    for sm in office:
        sm.callback(sm)
    assert fault.evaluation.status is Status.PASS
    assert not fault.evaluation.active


@pytest.mark.parametrize("changes", [{}, {"sensor.source": "unavailable"}])
@pytest.mark.parametrize("violation", [False, True])
@pytest.mark.parametrize(
    "result",
    [
        SafetyMechanismResult(False, {}),
        SafetyMechanismResult(True, {}),
        SafetyMechanismResult(False, {}, False),
        SafetyMechanismResult("invalid", {}),
        ValueError("failed simulated read"),
    ],
)
def test_simulation_cannot_mutate_live_assessment_or_evaluation_telemetry(
    changes,
    violation,
    result,
):
    component, mechanisms, manager, fault, events, _, _ = monitored_fault()
    component.results["first"] = SafetyMechanismResult(violation, {})
    for mechanism in mechanisms.values():
        qualify(component, mechanism)
    telemetry = []
    for event_name in (
        "evaluation_succeeded",
        "evaluation_exception",
        "evaluation_unavailable",
    ):
        component.event_bus.subscribe(event_name, lambda **data: telemetry.append(data))
    before = dict(component.debounce_states)
    component.hass_app.reset_mock()
    events.clear()
    component.results["first"] = result
    if isinstance(result, Exception) or not isinstance(result.result, bool):
        with pytest.raises((TypeError, ValueError)):
            component.evaluate(mechanisms["first"], changes)
    else:
        component.evaluate(mechanisms["first"], changes)
    assert fault.evaluation.status is (Status.FAIL if violation else Status.PASS)
    assert fault.evaluation.active is violation
    expected = FaultState.SET if violation else FaultState.CLEARED
    assert manager.check_symptom("first") is expected
    assert component.symptom_states["first"] is expected
    assert component.debounce_states == before
    assert events == []
    assert telemetry == []
    component.hass_app.run_in.assert_not_called()
    component.hass_app.record_safety_evaluation.assert_not_called()
