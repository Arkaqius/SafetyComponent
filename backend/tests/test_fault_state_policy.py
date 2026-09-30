"""Fault-owned evaluation and priority contract tests."""

from unittest.mock import Mock
from pathlib import Path

import pytest
import yaml

from components.core.fault_state_policy import (
    FaultCategory,
    FaultEvaluation,
    FaultEvaluationStatus as Status,
    PRIORITY_PROFILES,
)
from components.core.types_common import Fault, FaultState, Symptom
from components.core.event_bus import EventBus
from components.safetycomponents.core.safety_component import (
    SafetyMechanismResult,
    safety_mechanism_decorator,
)
from components.faults_manager.fault_manager import FaultManager
from components.faults_manager.schema import validate_faults_config
from components.faults_manager.cfg_parser import get_faults
from components.recovery_manager.recovery_manager import RecoveryManager


def test_boolean_boundary_rejects_invalid_predicate_results() -> None:
    evaluation = FaultEvaluation({"room"})
    for invalid in (None, 0, 1, "false", Status.FAIL):
        with pytest.raises(TypeError):
            evaluation.observe("room", invalid)  # type: ignore[arg-type]
    assert evaluation.status is Status.NOT_EVALUATED


def test_mixed_evidence_preserves_active_condition_until_all_inputs_recover() -> None:
    evaluation = FaultEvaluation({"office", "kitchen"})
    assert evaluation.observe("office", True) is Status.FAIL
    assert evaluation.active
    assert evaluation.mark_unavailable("office") is Status.UNEVALUABLE
    assert evaluation.active
    assert evaluation.observe("kitchen", False) is Status.UNEVALUABLE
    assert evaluation.active
    assert evaluation.observe("office", False) is Status.PASS
    assert not evaluation.active
    assert not evaluation.active_contributors


def test_valid_positive_evidence_is_actionable_with_other_input_unavailable() -> None:
    evaluation = FaultEvaluation({"office", "kitchen"})
    assert evaluation.observe("office", True) is Status.FAIL
    assert evaluation.active_contributors == {"office"}


def test_failure_and_recovery_qualification_are_fault_owned() -> None:
    time = [0.0]
    evaluation = FaultEvaluation(
        {"room"}, failure_delay_seconds=5, recovery_delay_seconds=10,
        clock=lambda: time[0],
    )
    assert evaluation.observe("room", True) is Status.PENDING_FAILURE
    assert not evaluation.active
    time[0] = 5
    assert evaluation.observe("room", True) is Status.FAIL
    time[0] = 6
    assert evaluation.observe("room", False) is Status.PENDING_RECOVERY
    assert evaluation.active
    assert evaluation.mark_unavailable("room") is Status.UNEVALUABLE
    time[0] = 20
    assert evaluation.observe("room", False) is Status.PENDING_RECOVERY
    time[0] = 30
    assert evaluation.observe("room", False) is Status.PASS
    assert not evaluation.active


def test_control_status_does_not_erase_active_evidence() -> None:
    evaluation = FaultEvaluation({"room"})
    evaluation.observe("room", True)
    assert evaluation.set_control(inhibited=True) is Status.INHIBITED
    assert evaluation.active
    assert evaluation.set_control(disabled=True) is Status.DISABLED
    assert evaluation.active
    assert evaluation.set_control() is Status.FAIL


def test_priority_equals_notification_level_and_category_is_independent() -> None:
    assert set(PRIORITY_PROFILES) == {1, 2, 3, 4}
    for level, profile in PRIORITY_PROFILES.items():
        fault = Fault("Example", ["sm"], level, category=FaultCategory.D)
        assert fault.level == profile.level
        assert fault.priority_profile is profile
        assert fault.category is FaultCategory.D
    assert PRIORITY_PROFILES[1].latch_required
    assert not any(PRIORITY_PROFILES[level].latch_required for level in (2, 3, 4))
    assert not PRIORITY_PROFILES[4].mobile
    with pytest.raises(ValueError):
        Fault("Invalid", ["sm"], 5)
    with pytest.raises(ValueError):
        validate_faults_config({"Invalid": {"name": "x", "level": 5, "related_sms": ["sm"]}})


def test_packaged_notification_profile_matches_priority_defaults() -> None:
    system_path = Path(__file__).parents[1] / "config" / "system_config.yml"
    with system_path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    notification = config["runtime_cfg"]["notification"]
    mobile_levels = set(notification["mobile"]["profiles"])
    assert mobile_levels == {level for level, profile in PRIORITY_PROFILES.items() if profile.mobile}
    assert notification["retry"]["deadlines_seconds"] == {
        level: profile.submission_deadline_seconds
        for level, profile in PRIORITY_PROFILES.items()
        if profile.mobile
    }
    assert notification["level_one_repeat"]["enabled"] == PRIORITY_PROFILES[1].repeat_on_activation


def test_category_round_trips_through_fault_config() -> None:
    validated = validate_faults_config({
        "SensorUnavailable": {
            "name": "Sensor unavailable", "level": 3,
            "category": "D", "related_sms": ["sm_sensor"],
        }
    })
    assert validated["SensorUnavailable"]["category"] == "D"
    assert get_faults(validated)["SensorUnavailable"].category is FaultCategory.D


@pytest.mark.parametrize("failure", ["invalid_result", "exception"])
def test_invocation_failure_is_reported_separately_from_false(failure: str) -> None:
    events: list[str] = []
    bus = EventBus()
    bus.subscribe("evaluation_unavailable", lambda *, symptom_id: events.append(symptom_id))
    component = Mock(event_bus=bus)
    sm = Mock(name="room")
    sm.name = "room"
    sm.isEnabled = True

    def predicate(_component, _sm, _changes):
        if failure == "exception":
            raise RuntimeError("source failed")
        return SafetyMechanismResult(1, None)

    with pytest.raises((RuntimeError, TypeError)):
        safety_mechanism_decorator(predicate)(component, sm, {"entity": "changed"})
    assert events == ["room"]


def test_disabling_active_contributor_does_not_clear_legacy_fault() -> None:
    symptom = Symptom("room", "sm", Mock(), {})
    fault = Fault("Hazard", ["sm"], 2)
    manager = FaultManager(Mock(), {}, {"room": symptom}, {"Hazard": fault}, EventBus(), Mock())
    manager.set_symptom("room")
    manager.mqtt_entities.publish_sensor_state.reset_mock()
    manager.disable_symptom("room", {})
    assert fault.state is FaultState.SET
    assert fault.evaluation.status is Status.UNEVALUABLE
    assert fault.evaluation.active
    assert not manager.mqtt_entities.publish_sensor_state.called


def test_shadowing_with_two_owners_withdraws_and_restores_correct_fault() -> None:
    symptoms = {
        name: Symptom(name, f"sm_{name}", Mock(), {})
        for name in ("forecast", "direct", "another")
    }
    faults = {
        "Forecast": Fault("Forecast", ["sm_forecast"], 3),
        "Direct": Fault("Direct", ["sm_direct"], 2, shadows=["Forecast"]),
        "Another": Fault("Another", ["sm_another"], 2, shadows=["Forecast"]),
    }
    events: list[dict] = []
    bus = EventBus()
    bus.subscribe("fault", lambda **payload: events.append(payload))
    manager = FaultManager(Mock(), {}, symptoms, faults, bus, Mock())
    manager.set_symptom("forecast")
    manager.set_symptom("direct")
    assert faults["Forecast"].state is FaultState.SHADOWED
    assert faults["Forecast"].evaluation.active
    assert faults["Forecast"].evaluation.shadowed_by == {"Direct"}
    shadow_event = events[-1]
    assert shadow_event["fault_name"] == "Forecast"
    assert shadow_event["symptom"] is symptoms["forecast"]
    manager.set_symptom("another")
    assert faults["Forecast"].evaluation.shadowed_by == {"Direct", "Another"}
    manager.clear_symptom("direct", {})
    assert faults["Forecast"].state is FaultState.SHADOWED
    manager.clear_symptom("another", {})
    assert faults["Forecast"].state is FaultState.SET
    assert faults["Forecast"].evaluation.shadowed_by == set()
    assert faults["Forecast"].evaluation.active


def test_shadowing_withdraws_every_active_recovery_contributor() -> None:
    first = Symptom("first", "sm_forecast", Mock(), {})
    second = Symptom("second", "sm_forecast", Mock(), {})
    inactive = Symptom("inactive", "sm_forecast", Mock(), {})
    first.state = second.state = FaultState.SET
    fault = Fault("Forecast", ["sm_forecast"], 3)
    recovery = RecoveryManager.__new__(RecoveryManager)
    recovery.fm = Mock(
        faults={"Forecast": fault},
        symptoms={item.name: item for item in (first, second, inactive)},
    )
    recovery._recovery_clear = Mock()

    recovery.handle_fault_event(
        symptom=first, fault_tag="tag", fault_state=FaultState.SHADOWED,
        fault_name="Forecast",
    )

    assert recovery._recovery_clear.call_count == 2
    recovery._recovery_clear.assert_any_call(first)
    recovery._recovery_clear.assert_any_call(second)
