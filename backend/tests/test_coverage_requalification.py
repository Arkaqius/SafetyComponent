"""Fresh unchanged observations repair coverage without fault lifecycle replay."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from SafetyFunctions import SafetyFunctions
from components.core.types_common import FaultState, SMState
from components.core.startup_grace import StartupGrace
from components.core.self_diagnostics import SelfDiagnosticsComponent
from components.core.degradation import (
    DegradationRegistry, DegradationTarget, DiagnosticBinding, RestrictionEffect,
)
from components.core.fault_state_policy import FaultCategory
from components.core.types_common import Fault
from components.safetycomponents.core.safety_component import (
    SafetyMechanismResult,
    safety_mechanism_decorator,
)

from .test_external_hazard_component import _component
from .test_degradation import _registry
from .test_internal_environmental_hazard_component import (
    CO_ENTITY, GAS_ENTITY, _build_component as indoor_component, _snapshot,
)
from .test_safety_component_core import _make_component
from .test_safety_doors_component import _build_component as door_component


def test_external_unchanged_clear_keeps_source_and_unknown_does_not_observe():
    component, _, _, events = _component()
    observations = []
    component.event_bus.subscribe("symptom_observed", lambda **data: observations.append(data))
    symptom = "ExternalWeatherExposureWindOfficeWindow"
    context = {"source": "OpenMeteoWeatherApiComponent"}
    component._apply_state(symptom, "clear", context)
    component._apply_state(symptom, "clear", context)
    assert len(events) == 1
    assert observations == [{
        "symptom_id": symptom, "state": FaultState.CLEARED, "additional_info": context,
    }]
    component._apply_state(symptom, "unknown", {})
    assert len(observations) == 1


def test_door_unchanged_closed_result_observes_but_dry_run_does_not():
    now = datetime.now(timezone.utc)
    state = {"state": "off", "last_changed": now.isoformat()}
    component, _, events = door_component(state, now=now)
    observations = []
    component.event_bus.subscribe("symptom_observed", lambda **data: observations.append(data))
    mechanism = component.safety_mechanisms["SafetyDoorOpenTimeoutGarageGate"]
    component.sm_safety_door_open_timeout(mechanism)
    events.clear()
    component.sm_safety_door_open_timeout(mechanism)
    assert not events
    assert len(observations) == 1
    component.sm_safety_door_open_timeout(mechanism, {"binary_sensor.garage_gate": "off"})
    assert len(observations) == 1
    state["state"] = "unavailable"
    component.sm_safety_door_open_timeout(mechanism)
    assert len(observations) == 1


def test_indoor_latched_alarm_with_unavailable_input_is_not_fresh_evidence():
    now = datetime.now(timezone.utc)
    states = {GAS_ENTITY: _snapshot("on", now), CO_ENTITY: _snapshot("off", now)}
    component, _, events = indoor_component(states, now=now)
    observations = []
    component.event_bus.subscribe("symptom_observed", lambda **data: observations.append(data))
    mechanism = component.safety_mechanisms["InternalEnv_flammable_gas_BathroomFlammableGas"]
    component.sm_iehm_flammable_gas(mechanism)
    events.clear()
    component.sm_iehm_flammable_gas(mechanism)
    assert not events
    assert any(data["symptom_id"] == mechanism.name for data in observations)
    observations.clear()
    states[GAS_ENTITY] = _snapshot("unknown", now)
    component.sm_iehm_flammable_gas(mechanism)
    assert not any(data["symptom_id"] == mechanism.name for data in observations)


@pytest.mark.parametrize("mode", ["dry", "unavailable", "exception", "pending"])
def test_core_nonqualified_evaluation_does_not_observe(mode):
    component = _make_component()
    observations = []
    component.event_bus.subscribe("symptom_observed", lambda **data: observations.append(data))
    component.symptom_states["hazard"] = FaultState.CLEARED
    component.debounce_states["hazard"] = SimpleNamespace(debounce=-2)
    mechanism = SimpleNamespace(name="hazard", isEnabled=True, sm_args={})

    def predicate(self, sm, changes):
        if mode == "exception":
            raise ValueError("invalid input")
        return SafetyMechanismResult(mode == "pending", {}, mode != "unavailable")

    evaluate = safety_mechanism_decorator(predicate)
    if mode == "exception":
        with pytest.raises(ValueError):
            evaluate(component, mechanism)
    else:
        evaluate(component, mechanism, {"sensor.test": "20"} if mode == "dry" else None)
    assert not observations


def test_application_requalification_skips_disabled_and_isolates_failure():
    app = SafetyFunctions.__new__(SafetyFunctions)
    module = SimpleNamespace(
        evaluate=Mock(), safety_mechanisms={"ready": object(), "failed": object()},
        record_evaluation=Mock(),
    )
    app.symptoms = {
        name: SimpleNamespace(
            module=module, sm_name="evaluate", sm_state=state,
        ) for name, state in (
            ("disabled", SMState.DISABLED), ("failed", SMState.ENABLED), ("ready", SMState.ENABLED),
        )
    }
    module.evaluate.side_effect = [ValueError("bad input"), False]
    app.degradation = Mock()
    app.degradation.pending_reevaluations.side_effect = [tuple(app.symptoms), (), ()]
    app.event_bus = Mock()
    app.log = Mock()
    app._reevaluate_coverage()
    assert module.evaluate.call_count == 2
    app.event_bus.publish.assert_any_call("evaluation_unavailable", symptom_id="failed")
    module.record_evaluation.assert_called_once_with(success=False)
    assert app._coverage_reevaluating is False


def test_restored_dependency_schedules_real_unchanged_evaluation_after_startup():
    component = _make_component()
    registry = _registry()
    bus = component.event_bus
    clock = [0.0]
    grace = StartupGrace(bus, {"input_a", "provider_a"}, 600, clock=lambda: clock[0])
    bus.subscribe("qualified_symptom", registry.observe)
    bus.subscribe("qualified_evaluation_unavailable", registry.mark_unavailable)
    bus.subscribe("symptom_observed", registry.observe_hazard)
    transitions = []
    bus.subscribe("qualified_symptom", lambda **data: transitions.append(data))
    app = SafetyFunctions.__new__(SafetyFunctions)
    app.event_bus = bus
    app._coverage_reevaluation_enabled = True
    app.degradation = registry
    app.reco_man = None
    app.run_in = Mock(return_value="coverage-timer")
    app._set_internal_entity = Mock()
    app.log = Mock()
    registry._on_change = app._on_coverage_changed
    mechanism = SimpleNamespace(name="room_a", isEnabled=True, sm_args={"debounce_limit": 1})
    component.safety_mechanisms["room_a"] = mechanism
    component.debounce_states["room_a"] = SimpleNamespace(debounce=-1)

    def predicate(self, sm, changes):
        return SafetyMechanismResult(False, {})

    evaluate = safety_mechanism_decorator(predicate)
    component.evaluate = lambda sm: evaluate(component, sm)
    app.symptoms = {"room_a": SimpleNamespace(
        module=component, sm_name="evaluate", sm_state=SMState.ENABLED,
    )}
    component.process_symptom("room_a", 0, False, {}, debounce_limit=1)
    bus.publish("symptom", symptom_id="room_b", state=FaultState.CLEARED)
    for name in ("input_a", "provider_a"):
        bus.publish("symptom", symptom_id=name, state=FaultState.CLEARED)
    assert not app.run_in.called
    clock[0] = 600
    grace.finish()
    assert registry.snapshot()["state"] == "UNKNOWN"
    app.run_in.assert_called_once_with(app._reevaluate_coverage, 0)
    count = len(transitions)
    app._reevaluate_coverage()
    assert registry.snapshot()["state"] == "FULL"
    assert len(transitions) == count
    assert app.run_in.call_count == 1


def test_coverage_recheck_waits_for_completed_application_initialization():
    app = SafetyFunctions.__new__(SafetyFunctions)
    app.degradation = _registry()
    app.reco_man = None
    app._set_internal_entity = Mock()
    app.run_in = Mock(return_value="timer")
    app.log = Mock()
    for name in ("input_a", "provider_a"):
        app.degradation.observe(symptom_id=name, state=FaultState.CLEARED)
    app._coverage_reevaluation_enabled = False
    app._on_coverage_changed()
    app.run_in.assert_not_called()
    app._coverage_reevaluation_enabled = True
    app._on_coverage_changed()
    app.run_in.assert_called_once_with(app._reevaluate_coverage, 0)


def test_pending_reevaluations_uses_stable_copy_during_evidence_changes():
    registry = _registry()
    registry._requires_reevaluation.add(("room_b", "temperature"))

    def observe_during_lookup(*args):
        registry._requires_reevaluation.clear()
        return ()

    registry.causes_for = observe_during_lookup
    assert registry.pending_reevaluations() == ("room_a", "room_b")


def test_custom_evaluator_failure_recovers_from_fresh_unchanged_result():
    component = _make_component()
    bus = component.event_bus
    diagnostics = SelfDiagnosticsComponent(Mock(), Mock(), bus, Mock(), {})
    diagnostics.get_symptoms_data({}, {})
    target = "room_a"
    diagnostic = f"AppHealthEvaluation_{target}"
    symptoms = diagnostics.add_targeted_causes({target}, set())
    d_symptom = symptoms[diagnostic]
    diagnostics.init_safety_mechanism(
        d_symptom.sm_name, diagnostic, d_symptom.parameters
    )
    diagnostics.enable_safety_mechanism(diagnostic, SMState.ENABLED)
    symptoms[target] = SimpleNamespace(sm_name="evaluate")
    faults = {
        target: Fault(target, ["evaluate"], 3, category=FaultCategory.H),
        diagnostic: Fault(diagnostic, ["sm_app_health"], 3, category=FaultCategory.D),
    }
    registry = DegradationRegistry(symptoms, faults, [DiagnosticBinding(
        diagnostic, (DegradationTarget(
            target, "door", target, RestrictionEffect.EVALUATION,
        ),),
    )])
    StartupGrace(bus, {diagnostic}, 0)
    bus.subscribe("qualified_symptom", registry.observe)
    bus.subscribe("qualified_evaluation_unavailable", registry.mark_unavailable)
    bus.subscribe("symptom_observed", registry.observe_hazard)
    app = SafetyFunctions.__new__(SafetyFunctions)
    app.event_bus = bus
    app.degradation = registry
    app.log = Mock()
    mechanism = object()
    component.safety_mechanisms[target] = mechanism
    failed = [True]

    def evaluate(sm):
        if failed[0]:
            raise ValueError("temporary evaluation failure")
        component.record_symptom_observation(target, FaultState.CLEARED)

    component.evaluate = evaluate
    app.symptoms = {target: SimpleNamespace(
        module=component, sm_name="evaluate", sm_state=SMState.ENABLED,
    )}
    bus.publish("evaluation_succeeded", symptom_id=target)
    app._reevaluate_coverage()
    assert registry.causes_for(target, RestrictionEffect.EVALUATION) == (diagnostic,)
    assert diagnostics._observed[diagnostic] is True
    failed[0] = False
    evaluate(mechanism)  # Normal component callback, even while coverage is blocked.
    assert diagnostics._observed[diagnostic] is False
    assert registry.snapshot()["state"] == "FULL"
