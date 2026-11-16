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
