"""Self-contained regressions for the shared lifecycle safety boundary."""

from typing import Any

import pytest

from components.core.lifecycle import CancellationKind, LifecyclePhase, LifecycleScope
from components.core.types_common import ExecutionOutcome, OutcomeKind
from components.safetycomponents.core.safety_mechanism import SafetyMechanism


class Source:
    """Small independent source, deliberately retaining cancelled callbacks."""

    def __init__(self) -> None:
        self.callbacks: list[Any] = []
        self.cancelled: list[int] = []
        self.fail_cancel = False

    def subscribe(self, callback: Any) -> int:
        self.callbacks.append(callback)
        return len(self.callbacks)

    def cancel(self, handle: int) -> None:
        if self.fail_cancel:
            raise RuntimeError("cannot cancel")
        self.cancelled.append(handle)


def test_scope_is_inert_idempotent_and_restarts_with_new_generation():
    source, calls = Source(), []
    scope = LifecycleScope("fixture", enabled=True)
    scope.declare("input", CancellationKind.STATE, source.subscribe,
                  lambda *_: calls.append("live"), source.cancel)
    assert scope.phase == LifecyclePhase.CONSTRUCTED
    assert not source.callbacks
    scope.start()
    generation = scope.generation
    scope.start()
    assert len(source.callbacks) == scope.handle_count == 1
    source.callbacks[0]()
    scope.stop()
    scope.stop()
    source.callbacks[0]()
    assert calls == ["live"]
    assert scope.handle_count == 0
    scope.start()
    scope.set_enabled(True)
    assert scope.generation > generation
    source.callbacks[0]()
    source.callbacks[-1]()
    assert calls == ["live", "live"]


def test_disable_invalidates_work_without_changing_domain_assertions():
    source, danger = Source(), [True]
    scope = LifecycleScope("fixture", enabled=True)
    scope.start()
    scope.schedule("clear", source.subscribe, lambda: danger.clear(), source.cancel)
    scope.set_enabled(False)
    source.callbacks[0]()
    scope.set_enabled(True)
    source.callbacks[0]()
    assert danger == [True]
    assert scope.handle_count == 0


def test_failed_cancellation_is_visible_but_old_callbacks_remain_fenced():
    source, calls = Source(), []
    scope = LifecycleScope("fixture", enabled=True)
    scope.start()
    scope.schedule("clear", source.subscribe, lambda: calls.append(1), source.cancel)
    source.fail_cancel = True
    scope.stop()
    source.callbacks[0]()
    assert not calls
    assert scope.cancellation_failures == 1
    assert scope.last_cancellation_error
    assert scope.handle_count == 0


def test_unprintable_cancellation_error_cannot_abort_remaining_cleanup():
    class BrokenError(Exception):
        def __str__(self):
            raise RuntimeError("formatting failed")

    source = Source()
    scope = LifecycleScope("fixture", enabled=True)

    def cancel(handle):
        if handle == 1:
            raise BrokenError()
        source.cancel(handle)

    scope.declare("first", CancellationKind.STATE, source.subscribe, lambda: None, cancel)
    scope.declare("second", CancellationKind.STATE, source.subscribe, lambda: None, cancel)
    scope.start()
    scope.stop()
    assert source.cancelled == [2]
    assert scope.handle_count == 0
    assert scope.cancellation_failures == 1


def test_timer_replacement_fences_old_slot_and_releases_fired_handle():
    source, calls = Source(), []
    scope = LifecycleScope("fixture", enabled=True)
    scope.start()
    for value in range(100):
        scope.schedule("clear", source.subscribe, lambda v=value: calls.append(v), source.cancel)
        assert scope.handle_count == 1
    for callback in source.callbacks:
        callback()
    assert calls == [99]
    assert scope.handle_count == 0


def test_parent_stop_fences_children_but_child_stop_preserves_shared_input():
    source, calls = Source(), []
    parent = LifecycleScope("parent", enabled=True)
    child = parent.child("child", enabled=True)
    parent.declare("input", CancellationKind.STATE, source.subscribe,
                   lambda: calls.append("parent"), source.cancel)
    parent.start()
    child.start()
    child.stop()
    source.callbacks[0]()
    child.start()
    child.set_enabled(True)
    late = child.guard(lambda: calls.append("child"))
    parent.stop()
    late()
    assert calls == ["parent"]
    assert parent.handle_count == child.handle_count == 0


def test_stop_during_registration_cancels_handle_returned_after_invalidation():
    source = Source()
    scope = LifecycleScope("fixture", enabled=True)

    def register(callback):
        handle = source.subscribe(callback)
        callback()
        return handle

    scope.declare("source", CancellationKind.STATE, register, scope.stop, source.cancel)
    scope.start()
    assert scope.phase == LifecyclePhase.STOPPED
    assert scope.handle_count == 0
    assert source.cancelled == [1]


def test_mechanism_construction_never_infers_entity_from_descriptive_metadata():
    class App:
        def __init__(self):
            self.inputs = []

        def listen_state(self, callback, entity):
            self.inputs.append(entity)
            return entity

        def cancel_listen_state(self, _handle):
            pass

        def log(self, *_args, **_kwargs):
            pass

    app = App()
    mechanism = SafetyMechanism(
        app, lambda _: None, "fixture", False,
        monitored_entities=["sensor.temperature", "sensor.temperature"],
        location="sensor.descriptive_text", actuator="switch.metadata",
        policy=["binary_sensor.also_metadata"],
    )
    assert not app.inputs
    mechanism.start()
    assert app.inputs == ["sensor.temperature"]
    assert mechanism.sm_args["location"] == "sensor.descriptive_text"


@pytest.mark.parametrize("kind", [OutcomeKind.UNEVALUABLE, OutcomeKind.INHIBITED,
                                  OutcomeKind.DISABLED])
def test_noneligible_outcome_cannot_be_used_as_negative_recovery_proof(kind):
    result = ExecutionOutcome("fixture", 1, 0.0, kind)
    assert not result.is_evaluable
    assert result.result is None


def test_only_valid_boolean_evidence_creates_eligible_positive_or_negative():
    positive = ExecutionOutcome.from_result("fixture", 1, 0.0, True)
    negative = ExecutionOutcome.from_result("fixture", 1, 0.0, False)
    missing = ExecutionOutcome.from_result("fixture", 1, 0.0, False, evaluable=False)
    assert positive.kind == OutcomeKind.ELIGIBLE_POSITIVE
    assert negative.kind == OutcomeKind.ELIGIBLE_NEGATIVE
    assert missing.kind == OutcomeKind.UNEVALUABLE
    with pytest.raises(TypeError):
        ExecutionOutcome.from_result("fixture", 1, 0.0, None)
    contradictory = ExecutionOutcome.from_result(
        "fixture", 1, 0.0, False, evaluable=False, kind=OutcomeKind.ELIGIBLE_NEGATIVE,
    )
    assert contradictory.kind == OutcomeKind.UNEVALUABLE
    assert contradictory.result is None
    with pytest.raises(ValueError):
        ExecutionOutcome.from_result("fixture", 1, 0.0, True, kind=OutcomeKind.ELIGIBLE_NEGATIVE)


def test_stop_during_predicate_cannot_apply_a_negative_result():
    from unittest.mock import Mock
    from components.core.event_bus import EventBus
    from components.core.types_common import FaultState
    from components.safetycomponents.core.safety_component import (
        DebounceState, SafetyComponent, SafetyMechanismResult, safety_mechanism_decorator,
    )

    owner = SafetyComponent.__new__(SafetyComponent)
    owner.hass_app, owner.event_bus = Mock(), EventBus()
    owner.symptom_states = {"fixture": FaultState.SET}
    owner.debounce_states = {"fixture": DebounceState(1, False)}

    @safety_mechanism_decorator
    def predicate(self, mechanism, changes):
        mechanism.stop()
        return SafetyMechanismResult(False)

    mechanism = SafetyMechanism(owner.hass_app, lambda _: None, "fixture", True)
    mechanism.start()
    predicate(owner, mechanism)
    assert owner.symptom_states == {"fixture": FaultState.SET}
    assert owner.debounce_states == {"fixture": DebounceState(1, False)}
    owner.hass_app.record_safety_evaluation.assert_called_once()


def test_listener_and_timer_entry_points_report_one_evaluation_each():
    from unittest.mock import Mock
    from components.core.event_bus import EventBus
    from components.safetycomponents.core.safety_component import (
        DebounceState, SafetyComponent, SafetyMechanismResult, safety_mechanism_decorator,
    )

    owner = SafetyComponent.__new__(SafetyComponent)
    owner.hass_app, owner.event_bus = Mock(), EventBus()
    owner.symptom_states = {}
    owner.debounce_states = {"fixture": DebounceState(0, False)}

    @safety_mechanism_decorator
    def predicate(self, mechanism, changes):
        return SafetyMechanismResult(True)

    owner.evaluate = predicate.__get__(owner)
    mechanism = SafetyMechanism(owner.hass_app, owner.evaluate, "fixture", True,
                                monitored_entities=["sensor.fixture"])
    mechanism.start()
    mechanism.entity_changed("sensor.fixture")
    owner.hass_app.record_safety_evaluation.assert_called_once()
    owner.hass_app.record_safety_evaluation.reset_mock()
    owner.evaluate(mechanism)
    owner.hass_app.record_safety_evaluation.assert_called_once()


def test_terminated_application_fences_old_root_callbacks(mocked_hass_app_basic):
    app, *_ = mocked_hass_app_basic
    app.initialize()
    callbacks = [
        (call.args[0], call.kwargs) for call in app.run_every.call_args_list
        if hasattr(call.args[0], "__wrapped__")
    ]
    app.terminate()
    app.call_service.reset_mock()
    for callback, kwargs in callbacks:
        # Managers migrate separately; exercise only the scope-owned root/samplers.
        callback(**kwargs)
    app.call_service.assert_not_called()
    assert app._root_scope.handle_count == 0
    assert all(component.scope.handle_count == 0 for component in app.sm_modules.values())


def test_stop_from_evaluation_consumer_cannot_apply_negative_result():
    from unittest.mock import Mock
    from components.core.event_bus import EventBus
    from components.core.types_common import FaultState
    from components.safetycomponents.core.safety_component import (
        DebounceState, SafetyComponent, SafetyMechanismResult, safety_mechanism_decorator,
    )

    owner = SafetyComponent.__new__(SafetyComponent)
    owner.hass_app, owner.event_bus = Mock(), EventBus()
    owner.symptom_states = {"fixture": FaultState.SET}
    owner.debounce_states = {"fixture": DebounceState(-1, False)}

    @safety_mechanism_decorator
    def predicate(self, mechanism, changes):
        return SafetyMechanismResult(False)

    mechanism = SafetyMechanism(owner.hass_app, lambda _: None, "fixture", True)
    mechanism.start()
    owner.event_bus.subscribe("evaluation_succeeded", lambda **_: mechanism.stop())
    predicate(owner, mechanism)
    assert owner.symptom_states == {"fixture": FaultState.SET}
    assert owner.debounce_states == {"fixture": DebounceState(-1, False)}


@pytest.mark.parametrize("kind", list(OutcomeKind))
def test_qualified_boundary_preserves_quality_and_readonly_simulation(kind):
    from unittest.mock import Mock
    from components.core.event_bus import EventBus
    from components.safetycomponents.core.safety_component import (
        SafetyComponent, SafetyMechanismResult, qualified_safety_mechanism_decorator,
    )

    owner = SafetyComponent.__new__(SafetyComponent)
    owner.hass_app, owner.event_bus = Mock(), EventBus()

    @qualified_safety_mechanism_decorator
    def predicate(self, mechanism, changes):
        return SafetyMechanismResult(kind == OutcomeKind.ELIGIBLE_POSITIVE, outcome_kind=kind)

    owner.evaluate = predicate.__get__(owner)
    mechanism = SafetyMechanism(owner.hass_app, owner.evaluate, "fixture", True)
    mechanism.start()
    owner.evaluate(mechanism)
    assert mechanism.last_outcome.kind == kind
    owner.hass_app.record_safety_evaluation.assert_called_once()
    before = mechanism.last_outcome
    owner.hass_app.reset_mock()
    result = owner.simulate(mechanism, {}, evaluator=owner.evaluate)
    assert result.kind == kind
    assert mechanism.last_outcome is before
    owner.hass_app.record_safety_evaluation.assert_not_called()
    owner.hass_app.run_in.assert_not_called()


def test_nested_evaluation_entry_reports_exception_once_without_clearing_danger():
    from unittest.mock import Mock
    from components.core.event_bus import EventBus
    from components.core.types_common import FaultState
    from components.safetycomponents.core.safety_component import SafetyComponent, evaluation_entry

    owner = SafetyComponent.__new__(SafetyComponent)
    owner.hass_app, owner.event_bus = Mock(), EventBus()
    owner.symptom_states = {"fixture": FaultState.SET}
    mechanism = SafetyMechanism(owner.hass_app, lambda _: None, "fixture", True)
    mechanism.start()
    owner.safety_mechanisms = {"fixture": mechanism}

    @evaluation_entry
    def nested(self):
        self.record_evaluation()
        raise RuntimeError("failed evaluation")

    @evaluation_entry
    def outer(self):
        nested(self)

    with pytest.raises(RuntimeError, match="failed evaluation"):
        outer(owner)
    owner.hass_app.record_safety_evaluation.assert_called_once_with("UNKNOWN", success=False)
    assert owner.symptom_states == {"fixture": FaultState.SET}
    assert mechanism.last_outcome.kind == OutcomeKind.UNEVALUABLE


def test_heating_simulation_does_not_claim_a_negative_for_unsupported_kernel(tmp_path):
    from components.core.types_common import OutcomeKind
    from test_heating_monitor import build_component

    component, app, _, _ = build_component(tmp_path, {
        "sensor.health": {"state": "ok", "attributes": {}},
        "sensor.flow": {"state": "30", "attributes": {}},
    })
    mechanism = next(iter(component.safety_mechanisms.values()))
    app.reset_mock()
    before = mechanism.last_outcome
    result = component.simulate(mechanism, {"sensor.health": "ok"})
    assert result.kind == OutcomeKind.UNEVALUABLE
    assert result.result is None
    assert mechanism.last_outcome is before
    app.call_service.assert_not_called()
    app.run_in.assert_not_called()


def test_indoor_unknown_is_alarm_uncertainty_but_can_be_health_failure():
    from datetime import datetime, timezone
    from components.core.types_common import OutcomeKind
    from test_internal_environmental_hazard_component import _build_component, GAS_ENTITY

    component, app, _ = _build_component({}, now=datetime.now(timezone.utc))
    alarm = next(sm for name, sm in component.safety_mechanisms.items()
                 if component._symptom_bindings[name][1] == "alarm")
    health = next(sm for name, sm in component.safety_mechanisms.items()
                  if component._symptom_bindings[name][0] == component._symptom_bindings[alarm.name][0]
                  and component._symptom_bindings[name][1] == "health")
    app.reset_mock()
    changes = {GAS_ENTITY: "unknown"}
    assert component.simulate(alarm, changes).kind == OutcomeKind.UNEVALUABLE
    assert component.simulate(health, changes).kind == OutcomeKind.ELIGIBLE_POSITIVE
    app.get_state.assert_not_called()
    app.record_safety_evaluation.assert_not_called()


def test_external_missing_hypothetical_input_does_not_prove_clear():
    from components.core.types_common import OutcomeKind
    from test_external_hazard_component import _component

    component, _, _, _ = _component()
    mechanism = next(sm for sm in component.safety_mechanisms.values() if "hazard" in sm.sm_args)
    before = mechanism.last_outcome
    result = component.simulate(mechanism, {})
    assert result.kind == OutcomeKind.UNEVALUABLE
    assert result.result is None
    assert mechanism.last_outcome is before


@pytest.mark.parametrize("family", ["temperature", "doors", "entity", "heating", "indoor", "external"])
@pytest.mark.parametrize("failed_cancellation", [False, True])
def test_real_family_scopes_stop_and_restart_without_obsolete_domain_entry(
    family, mocked_hass_app_basic, tmp_path, failed_cancellation,
):
    from datetime import datetime, timezone
    from components.core.types_common import SMState

    now = datetime.now(timezone.utc)
    if family == "temperature":
        app, *_ = mocked_hass_app_basic
        app.initialize()
        component = app.sm_modules["TemperatureComponent"]
    elif family == "doors":
        from test_safety_doors_component import _build_component
        component, _, _ = _build_component({"state": "closed", "last_changed": now.isoformat()}, now=now)
    elif family == "entity":
        from test_entity_monitor_component import _component, _config
        _, _, component = _component(mocked_hass_app_basic)
        symptoms, _ = component.get_symptoms_data({component.component_name: component}, _config())
        for symptom in symptoms.values():
            component.init_safety_mechanism(symptom.sm_name, symptom.name, symptom.parameters)
            component.enable_safety_mechanism(symptom.name, SMState.ENABLED)
    elif family == "heating":
        from test_heating_monitor import build_component
        component, _, _, _ = build_component(tmp_path, {
            "sensor.health": {"state": "ok", "attributes": {}},
            "sensor.flow": {"state": "30", "attributes": {}},
        })
    elif family == "indoor":
        from test_internal_environmental_hazard_component import _build_component
        component, _, _ = _build_component({}, now=now)
    else:
        from test_external_hazard_component import _component
        component, _, _, _ = _component()
    from dataclasses import replace
    component.stop()
    captured = []
    scopes = [component.scope, *(sm.scope for sm in component.safety_mechanisms.values())]
    for scope in scopes:
        for key, registration in tuple(scope._declarations.items()):
            def register(callback, original=registration.register):
                captured.append(callback)
                return original(callback)
            def cancel(handle, original=registration.cancel):
                if failed_cancellation:
                    raise RuntimeError("fictional cancellation failure")
                return original(handle)
            scope._declarations[key] = replace(registration, register=register, cancel=cancel)
    component.start()
    for name in component.safety_mechanisms:
        component.enable_safety_mechanism(name, SMState.ENABLED)
    expected_inputs = {"temperature": 12, "doors": 1, "entity": 3, "heating": 1, "indoor": 5, "external": 4}
    assert sum(len(scope._declarations) for scope in scopes) == expected_inputs[family]
    assert len(captured) == expected_inputs[family]
    handles = (component.scope.handle_count,
               sum(sm.scope.handle_count for sm in component.safety_mechanisms.values()))
    # Child eligibility changes retain every still-required shared parent input.
    for name, mechanism in component.safety_mechanisms.items():
        parent_handles = component.scope.handle_count
        component.enable_safety_mechanism(name, SMState.DISABLED)
        assert component.scope.handle_count == parent_handles
        assert not mechanism.scope.eligible
        component.enable_safety_mechanism(name, SMState.ENABLED)
        assert mechanism.scope.eligible
    # Presentation metadata must not add input dependencies or subscriptions.
    declarations = sum(len(scope._declarations) for scope in scopes)
    for mechanism in component.safety_mechanisms.values():
        mechanism.sm_args["area_name"] = "Updated display label"
    assert sum(len(scope._declarations) for scope in scopes) == declarations
    component.start()
    component.start()
    assert handles[0] == component.scope.handle_count
    # Eligibility invalidation may discard domain timers, but never duplicates
    # declarations; each live source has at most one current owned handle.
    assert sum(len(scope._declarations) for scope in scopes) == declarations
    old = list(captured)
    for name in ("_tick", "_evaluate_all", "_entity_changed"):
        callback = getattr(component, name, None)
        if callable(callback):
            old.append(component.scope.guard(callback))
    component.stop()
    component.stop()
    assert component.scope.handle_count == 0
    assert all(sm.scope.handle_count == 0 for sm in component.safety_mechanisms.values())
    if failed_cancellation:
        assert sum(scope.cancellation_failures for scope in scopes) > 0
    stopped = dict(component.symptom_states)
    def submission_count():
        app = component.hass_app
        calls = getattr(app, "service_calls", None)
        if isinstance(calls, list):
            return len(calls)
        return len(getattr(app.call_service, "call_args_list", []))
    before_submissions = submission_count()
    for callback in old:
        callback()
    assert component.symptom_states == stopped
    assert submission_count() == before_submissions
    component.start()
    for name in component.safety_mechanisms:
        component.enable_safety_mechanism(name, SMState.ENABLED)
    restarted = dict(component.symptom_states)
    before_submissions = submission_count()
    for callback in old:
        callback()
    assert component.symptom_states == restarted
    assert submission_count() == before_submissions
    component.stop()
