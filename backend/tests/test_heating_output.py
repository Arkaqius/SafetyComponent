"""Observed-window, persistence and shared-fault contracts for CH output."""

from unittest.mock import Mock
from dataclasses import replace

import pytest

from components.core.fault_state_policy import FaultCategory
from components.core.types_common import Fault, FaultState, Symptom
from components.faults_manager.fault_manager import FaultManager
from components.safetycomponents.heating.rules import HeatingRuleEngine
from components.safetycomponents.heating.engine import RULES, HeatingResult
from components.safetycomponents.heating.schema import HeatingConfig, HeatingProfile
from test_heating_monitor import build_component
from test_heating_rules import config, observations, states, tick


def output_profile(*rules):
    common = {
        "evidence_reference": "commissioned output fixture",
        "failure_seconds": 5,
        "recovery_seconds": 5,
        "startup_allowance_seconds": 5,
        "maximum_inhibition_seconds": 10,
        "maximum_unresolved_seconds": 180,
        "maximum_input_skew_seconds": 2,
        "inhibition_context": "mapped_reason",
        "observation_window_seconds": 20,
        "minimum_sample_count": 5,
        "maximum_sample_gap_seconds": 5,
        "target_stability_tolerance_k": 0.2,
    }
    extra = {}
    if "R05" in rules:
        extra["flow_rise"] = {
            **common,
            "minimum_target_deficit_k": 5,
            "minimum_rise_k": 1,
            "recovery_rise_k": 2,
            "target_recovery_margin_k": 0.5,
        }
    if "R06" in rules:
        extra["flow_tracking"] = {
            **common,
            "failure_deficit_k": 5,
            "recovery_deficit_k": 1,
        }
    return HeatingProfile(
        enabled_rules=["R01", *rules], provenance="output fixture", **extra
    )


def output_config(tmp_path, *rules):
    selected = config(tmp_path)
    selected["profiles"]["Commissioned"] = output_profile(*rules).model_dump()
    return selected


def output_data():
    data = states()
    data["sensor.heat_request"]["state"] = "on"
    data["sensor.boiler_active"]["state"] = "on"
    return data


def evaluate(engine, rule, now, *, source_at=None, active=False, **values):
    engine.advance(now, now)
    data = observations(
        now if source_at is None else source_at,
        heat_request=True,
        boiler_active=True,
        **values,
    )
    return engine.evaluate(rule, data, now, now, key=rule, active=active)


@pytest.mark.parametrize("rule", ["R05", "R06"])
def test_physical_failure_needs_startup_covered_window_and_new_qualification_samples(
    rule,
):
    engine = HeatingRuleEngine(output_profile(rule), 5, 2)
    assert evaluate(engine, rule, 100).reason == "starting_allowance"
    for now in (105, 110, 115, 120):
        assert evaluate(engine, rule, now).violation is None
    first = evaluate(engine, rule, 125)
    assert first.violation is True and first.observed_qualification_seconds == 0
    cached = evaluate(engine, rule, 130, source_at=125)
    assert cached.observed_qualification_seconds == 0
    fresh = evaluate(engine, rule, 130)
    assert fresh.observed_qualification_seconds == 5


@pytest.mark.parametrize("rule", ["R05", "R06"])
def test_missing_observations_are_quality_loss_not_output_failure(rule):
    engine = HeatingRuleEngine(output_profile(rule), 5, 2)
    for now in (100, 105, 110):
        evaluate(engine, rule, now)
    gap = evaluate(engine, rule, 120)
    assert gap.violation is None
    assert gap.quality_cause == "output_window_incomplete"
    assert engine.episodes[rule].onset_utc == 100


def test_rise_and_tracking_have_distinct_physical_meaning():
    engine = HeatingRuleEngine(output_profile("R05", "R06"), 5, 2)
    results = {}
    for now in range(100, 136, 5):
        for rule in ("R05", "R06"):
            results[rule] = evaluate(
                engine, rule, now, flow_temperature=25 + (now - 100) / 10
            )
    assert results["R05"].violation is False  # adequate rise
    assert results["R06"].violation is True  # still far from the target


@pytest.mark.parametrize("rule", ["R05", "R06"])
def test_dhw_burner_off_and_lowered_targets_do_not_heal_output(rule):
    engine = HeatingRuleEngine(output_profile(rule), 5, 2)
    for now in range(100, 136, 5):
        evaluate(engine, rule, now)
    assert (
        evaluate(
            engine, rule, 140, active=True, dhw_active=True, flow_temperature=60
        ).violation
        is None
    )
    assert (
        evaluate(
            engine, rule, 145, active=True, requested_flow_temperature=20
        ).violation
        is None
    )
    data = observations(
        150, heat_request=True, boiler_active=False, flow_temperature=50
    )
    engine.advance(150, 150)
    assert (
        engine.evaluate(rule, data, 150, 150, key=rule, active=True).violation is None
    )
    assert engine.episodes[rule].reference_target == 45


@pytest.mark.parametrize("rule", ["R05", "R06"])
def test_restart_keeps_need_deadline_but_rebuilds_real_observation_window(rule):
    engine = HeatingRuleEngine(output_profile(rule), 5, 2)
    for now in range(100, 131, 5):
        evaluate(engine, rule, now)
    restored = HeatingRuleEngine(output_profile(rule), 5, 2)
    restored.restore(engine.snapshot(), {rule})
    expired = evaluate(restored, rule, 260, active=True)
    assert (
        expired.violation is None
        and expired.quality_cause == "output_window_incomplete"
    )
    assert expired.elapsed_seconds == 160 and expired.onset_utc == 100
    assert len(restored.output.windows[rule].samples) == 0


def test_target_changes_discard_samples_without_renewing_need_budget():
    engine = HeatingRuleEngine(output_profile("R06"), 5, 2)
    for now in range(100, 131, 5):
        evaluate(engine, "R06", now)
    changed = evaluate(engine, "R06", 135, requested_flow_temperature=50)
    assert changed.violation is None
    assert engine.episodes["R06"].onset_utc == 100
    assert engine.episodes["R06"].elapsed_seconds == 35
    assert engine.output.windows["R06"].samples == []


def test_component_uses_observed_time_instead_of_cached_runtime_for_activation(
    tmp_path,
):
    data = output_data()
    monitor, _, _, clock = build_component(
        tmp_path, data, configuration=output_config(tmp_path, "R05")
    )
    monitor._tick()
    for _ in range(5):
        tick(monitor, clock, data)
    name = "Heating_no_flow_rise_Main"
    assert monitor._latches[name].status == "PENDING_FAILURE"
    clock[0] += 5
    monitor._tick()  # original timestamp unchanged
    assert not monitor._latches[name].active
    tick(monitor, clock, data, 0)
    assert monitor._latches[name].active


def attach_fault_manager(monitor, app):
    symptoms = {
        name: Symptom(
            module=monitor,
            name=name,
            sm_name=RULES[rule][0],
            parameters={},
        )
        for name, (_, rule, _) in monitor._bindings.items()
    }
    faults = {
        name: Fault(
            name,
            definition["related_sms"],
            definition["level"],
            category=FaultCategory(definition["category"]),
            related_symptom_ids=definition["related_symptom_ids"],
        )
        for name, definition in monitor.get_fault_definitions().items()
    }
    mqtt = Mock()
    mqtt.get_attributes.return_value = {}
    manager = FaultManager(
        app,
        {monitor.component_name: monitor},
        symptoms,
        faults,
        monitor.event_bus,
        mqtt,
    )
    monitor.event_bus.subscribe("symptom", manager.handle_symptom_event)
    monitor.event_bus.subscribe(
        "evaluation_unavailable",
        lambda symptom_id: manager.mark_evaluation_unavailable(symptom_id),
    )
    monitor.event_bus.subscribe("evaluation_pending", manager.mark_evaluation_pending)
    return manager


def test_shared_incident_survives_unevaluable_contributor_and_restart(tmp_path):
    data = output_data()
    selected = output_config(tmp_path, "R05", "R06")
    selected["profiles"]["Commissioned"]["flow_tracking"]["failure_deficit_k"] = 30
    monitor, app, _, clock = build_component(tmp_path, data, configuration=selected)
    manager = attach_fault_manager(monitor, app)
    monitor._tick()
    for _ in range(6):
        tick(monitor, clock, data)
    incident = monitor._incidents["HeatingInsufficientOutput"]
    # Keep one contributor unevaluable while the other positively recovers.
    monitor._engines["Main"].evaluate = Mock(
        side_effect=lambda rule, *args, **kwargs: HeatingResult(
            False, "flow_rise_recovered", observed_qualification_seconds=5
        )
        if rule == "R05"
        else HeatingResult(None, "unqualified_input")
    )
    tick(monitor, clock, data)
    assert manager.faults["HeatingInsufficientOutput"].evaluation.active
    assert monitor._incidents["HeatingInsufficientOutput"] == incident
    assert not any(
        latch.active for name, latch in monitor._latches.items() if "flow" in name
    )
    restarted, app2, _, _ = build_component(
        tmp_path, data, initial=clock[0], configuration=selected
    )
    restored_manager = attach_fault_manager(restarted, app2)
    restarted._tick()
    assert restarted._restore_error is None
    assert restarted._incidents["HeatingInsufficientOutput"] == incident
    assert restored_manager.faults["HeatingInsufficientOutput"].evaluation.active


@pytest.mark.parametrize(
    "mutation", ["age", "window", "count", "gap", "budget", "bands", "missing"]
)
def test_output_admission_rejects_unachievable_or_incomplete_policy(tmp_path, mutation):
    selected = output_config(tmp_path, "R06")
    policy = selected["profiles"]["Commissioned"]["flow_tracking"]
    if mutation == "age":
        selected["systems"]["Main"]["inputs"]["flow_temperature"][
            "max_age_seconds"
        ] = 30
    elif mutation == "window":
        policy["observation_window_seconds"] = 2
    elif mutation == "count":
        policy["minimum_sample_count"] = 100
    elif mutation == "gap":
        policy["maximum_sample_gap_seconds"] = 2
    elif mutation == "budget":
        policy["maximum_unresolved_seconds"] = 80
    elif mutation == "bands":
        policy["recovery_deficit_k"] = 6
    else:
        selected["systems"]["Main"]["inputs"].pop("dhw_active")
    with pytest.raises(ValueError):
        HeatingConfig.model_validate(selected)


@pytest.mark.parametrize("rule", ["R05", "R06"])
def test_reduced_target_cannot_hide_expired_coverage_deadline(rule):
    engine = HeatingRuleEngine(output_profile(rule), 5, 2)
    evaluate(engine, rule, 100)
    result = evaluate(engine, rule, 300, requested_flow_temperature=20)
    assert result.violation is None
    assert result.quality_cause == "output_window_incomplete"
    assert result.onset_utc == 100 and result.remaining_seconds == 0


def test_expired_deadline_does_not_bypass_new_physical_startup():
    policy = output_profile("R06")
    policy.flow_tracking.startup_allowance_seconds = 100
    policy.flow_tracking.maximum_unresolved_seconds = 400
    engine = HeatingRuleEngine(policy, 5, 2)
    for now in range(100, 451, 5):
        evaluate(engine, "R06", now, dhw_active=True)
    for now in range(455, 575, 5):
        result = evaluate(engine, "R06", now)
        assert result.violation is None
        assert result.quality_cause == "output_window_incomplete"
    assert evaluate(engine, "R06", 575).observed_qualification_seconds == 0
    assert evaluate(engine, "R06", 580).observed_qualification_seconds == 5


def test_known_window_loss_stays_lost_during_renewed_startup():
    policy = output_profile("R06")
    policy.flow_tracking.startup_allowance_seconds = 100
    policy.flow_tracking.maximum_unresolved_seconds = 400
    engine = HeatingRuleEngine(policy, 5, 2)
    for now in range(100, 206, 5):
        evaluate(engine, "R06", now)
    result = evaluate(engine, "R06", 220)
    assert result.violation is None
    assert result.quality_cause == "output_window_incomplete"


def test_rise_recovery_cannot_overlap_large_deficit_activation(tmp_path):
    selected = output_config(tmp_path, "R05")
    selected["profiles"]["Commissioned"]["flow_rise"]["target_recovery_margin_k"] = 5
    with pytest.raises(ValueError, match="narrower"):
        HeatingConfig.model_validate(selected)


def test_output_freeze_evidence_contains_bounded_physical_decision_window(tmp_path):
    data = output_data()
    monitor, _, events, clock = build_component(
        tmp_path, data, configuration=output_config(tmp_path, "R05")
    )
    monitor._tick()
    for _ in range(6):
        tick(monitor, clock, data)
    event = next(
        item
        for item in events
        if item["symptom_id"] == "Heating_no_flow_rise_Main"
        and item["state"] == FaultState.SET
    )
    window = event["diagnostic_evidence"]["heating"]["output_window"]
    assert window["sample_count"] == 5
    assert window["observed_span_seconds"] == window["runtime_span_seconds"] == 20
    assert window["rise_k"] == 0 and window["latest_deficit_k"] == 20
    assert window["latest_at"] - window["anchor_at"] == 20
    assert window["observed_qualification_seconds"] == window["failure_seconds"] == 5
    assert window["minimum_rise_k"] == 1
    assert len(window) < 32


def test_new_unevaluable_contributor_prevents_transient_false_group_heal(tmp_path):
    data = output_data()
    selected = output_config(tmp_path, "R05", "R06")
    selected["profiles"]["Commissioned"]["flow_tracking"].update(
        failure_deficit_k=30, recovery_deficit_k=25
    )
    monitor, app, _, clock = build_component(tmp_path, data, configuration=selected)
    manager = attach_fault_manager(monitor, app)
    transitions = []
    monitor.event_bus.subscribe("fault", lambda **payload: transitions.append(payload))
    monitor._tick()
    for _ in range(6):
        tick(monitor, clock, data)
    assert monitor._latches["Heating_flow_tracking_Main"].status == "PASS"
    incident = monitor._incidents["HeatingInsufficientOutput"]
    transitions.clear()
    monitor._engines["Main"].evaluate = Mock(
        side_effect=lambda rule, *args, **kwargs: HeatingResult(
            False, "flow_rise_recovered", observed_qualification_seconds=5
        )
        if rule == "R05"
        else HeatingResult(None, "unqualified_input")
    )
    tick(monitor, clock, data)
    assert manager.faults["HeatingInsufficientOutput"].evaluation.active
    assert monitor._incidents["HeatingInsufficientOutput"] == incident
    assert not any(
        item["fault_state"] == FaultState.CLEARED
        for item in transitions
        if item["fault_name"] == "HeatingInsufficientOutput"
    )
    # The inactive contributor still needs its own observed positive interval.
    monitor._engines["Main"].evaluate = Mock(
        side_effect=lambda rule, *args, **kwargs: HeatingResult(
            False,
            "flow_tracking_recovered",
            observed_qualification_seconds=5 if rule == "R05" else 0,
        )
    )
    tick(monitor, clock, data)
    assert manager.faults["HeatingInsufficientOutput"].evaluation.active
    monitor._engines["Main"].evaluate = Mock(
        return_value=HeatingResult(
            False, "flow_tracking_recovered", observed_qualification_seconds=5
        )
    )
    tick(monitor, clock, data)
    assert not manager.faults["HeatingInsufficientOutput"].evaluation.active
    assert "HeatingInsufficientOutput" not in monitor._incidents
    heals = [
        item
        for item in transitions
        if item["fault_name"] == "HeatingInsufficientOutput"
        and item["fault_state"] == FaultState.CLEARED
    ]
    assert heals[-1]["additional_info"]["incident_id"] == incident
    monitor._engines["Main"].evaluate = Mock(
        return_value=HeatingResult(
            True, "flow_tracking_deficit", observed_qualification_seconds=5
        )
    )
    tick(monitor, clock, data)
    assert monitor._incidents["HeatingInsufficientOutput"] != incident


def test_failed_output_clear_commit_keeps_public_sensor_active(tmp_path):
    data = output_data()
    monitor, _, _, clock = build_component(
        tmp_path, data, configuration=output_config(tmp_path, "R05")
    )
    monitor._tick()
    for _ in range(6):
        tick(monitor, clock, data)
    monitor.mqtt_entities.publish_sensor_state = Mock()
    data["sensor.flow_temperature"]["state"] = "45"
    tick(monitor, clock, data)
    monitor._store.save = Mock(side_effect=OSError("test full disk"))
    tick(monitor, clock, data)
    assert monitor._latches["Heating_no_flow_rise_Main"].active
    attrs = monitor.mqtt_entities.publish_sensor_state.call_args.kwargs["attributes"]
    assert attrs["persistence_error"]
    assert "HeatingInsufficientOutput" in attrs["active_faults"]


def test_output_deadline_reserves_the_longer_r01_qualification():
    policy = output_profile("R06")
    policy.failure_seconds = 18
    policy.flow_tracking.failure_seconds = 0
    engine = HeatingRuleEngine(policy, 5, 2)
    evaluate(engine, "R06", 100)
    engine.advance(225, 225)
    data = {
        key: replace(value, maximum_age_seconds=1)
        for key, value in observations(
            225, heat_request=True, boiler_active=True, requested_flow_temperature=20
        ).items()
    }
    result = engine.evaluate("R06", data, 225, 225, key="R06", active=False)
    assert result.quality_cause == "output_window_incomplete"


def test_cached_target_attainment_does_not_advance_recovery():
    engine = HeatingRuleEngine(output_profile("R06"), 5, 2)
    for now in range(100, 131, 5):
        evaluate(engine, "R06", now)
    first = evaluate(engine, "R06", 135, active=True, flow_temperature=45)
    cached = evaluate(
        engine, "R06", 140, source_at=135, active=True, flow_temperature=45
    )
    assert first.violation is False and cached.violation is False
    assert (
        first.observed_qualification_seconds
        == cached.observed_qualification_seconds
        == 0
    )
    assert (
        evaluate(
            engine, "R06", 140, active=True, flow_temperature=45
        ).observed_qualification_seconds
        == 5
    )
