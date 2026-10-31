"""Safety contracts for generic distribution, thermal and cycling policies.

All limits below are fictional test fixtures, not commissioned equipment values.
"""

from copy import deepcopy
from dataclasses import replace

import pytest

from components.safetycomponents.heating.engine import RULES
from components.safetycomponents.heating.inputs import HeatingObservation
from components.safetycomponents.heating.rules import HeatingRuleEngine
from components.safetycomponents.heating.schema import HeatingConfig, HeatingProfile
from test_heating_monitor import build_component
from test_heating_output import attach_fault_manager
from test_heating_rules import config, observations, states, tick


STATUS = {
    "evidence_reference": "fictional commissioned fixture",
    "failure_seconds": 5,
    "recovery_seconds": 5,
}
TREND = {
    **STATUS,
    "startup_allowance_seconds": 5,
    "maximum_inhibition_seconds": 10,
    "maximum_unresolved_seconds": 180,
    "maximum_input_skew_seconds": 2,
    "inhibition_context": "none",
    "observation_window_seconds": 20,
    "minimum_sample_count": 5,
    "maximum_sample_gap_seconds": 5,
}
ALLOCATION = {
    "allocation_key": "HSM-H05/Fixture",
    "manufacturer_reference": "fictional manual",
    "hydraulic_reference": "fixture topology",
    "maximum_response_seconds": 90,
    "detection_budget_seconds": 30,
    "decision_budget_seconds": 1,
    "notification_budget_seconds": 30,
}
ENVELOPE = {
    "operating_maximum_c": 60,
    "native_hysteresis_k": 2,
    "measurement_tolerance_k": 1,
    "recovery_margin_k": 5,
}
POLICIES = {
    "R07": (
        "pump_response",
        {
            **STATUS,
            "hydraulic_reference": "fixture required pump",
            "topology_requires_pump": True,
            "startup_allowance_seconds": 5,
            "maximum_unresolved_seconds": 120,
            "maximum_input_skew_seconds": 2,
        },
    ),
    "R08": (
        "flow_return",
        {
            **TREND,
            "hydraulic_reference": "fixture circuit",
            "load_role": "power_percent",
            "minimum_load": 20,
            "minimum_flow_temperature_c": 30,
            "failure_delta_k": 20,
            "recovery_delta_k": 10,
            "inverted_failure_k": 5,
            "inverted_recovery_k": 1,
        },
    ),
    "R09": (
        "room_delivery",
        {
            **TREND,
            "delivery_reference": "fixture physical room path",
            "need_on_margin_k": 1,
            "need_off_margin_k": 0.2,
            "minimum_cooling_k": 0.3,
            "recovery_rise_k": 0.4,
            "target_stability_tolerance_k": 0.2,
            "room_inhibition_context": "mapped",
        },
    ),
    "R10": (
        "mode_temperature",
        {
            **STATUS,
            "allocation": ALLOCATION,
            "maximum_input_skew_seconds": 2,
            "envelopes": {
                phase: {**ENVELOPE, "operating_maximum_c": 70 if phase == "dhw" else 60}
                for phase in ("idle", "starting", "heating", "dhw", "pump_overrun")
            },
        },
    ),
    "R11": (
        "absolute_temperature",
        {
            **STATUS,
            "allocation": ALLOCATION,
            "absolute_limit_c": 90,
            "measurement_tolerance_k": 1,
            "recovery_margin_k": 5,
        },
    ),
    "R12": (
        "cycling",
        {
            **STATUS,
            "counter_reference": "fixture monotone mode counters",
            "maximum_input_skew_seconds": 10,
            "observation_window_seconds": 100,
            "minimum_sample_count": 21,
            "maximum_sample_gap_seconds": 5,
            "maximum_counter_gap_seconds": 10,
            "maximum_starts_ch": 2,
            "maximum_starts_dhw": 2,
            "recovery_starts_ch": 1,
            "recovery_starts_dhw": 1,
            "short_cycle_seconds": 15,
            "minimum_short_cycles": 2,
            "recovery_short_cycles": 0,
            "minimum_recovery_cycles": 1,
        },
    ),
}
EXTRA = {
    "pump_active": True,
    "return_temperature": 25.0,
    "power_percent": 50.0,
    "heat_delivery_active": True,
    "room_inhibited": False,
    "burner_starts_ch": 0.0,
    "burner_starts_dhw": 0.0,
}


def profile(*rules):
    return HeatingProfile(
        enabled_rules=["R01", *rules],
        provenance="fictional test evidence",
        **{POLICIES[rule][0]: deepcopy(POLICIES[rule][1]) for rule in rules},
    )


def evaluate(engine, rule, now, *, source_at=None, active=False, **values):
    engine.advance(now, now)
    data = observations(
        now if source_at is None else source_at,
        **{
            **EXTRA,
            "boiler_active": True,
            "heat_request": True,
            "flow_temperature": 60.0,
            **values,
        },
    )
    data["room_inhibited"] = replace(data["room_inhibited"], evidence_kind="intent")
    return engine.evaluate(rule, data, now, now, key=rule, active=active)


def configuration(tmp_path, *rules):
    selected = config(tmp_path)
    selected["profiles"]["Commissioned"] = profile(*rules).model_dump()
    for role, value in EXTRA.items():
        binding = {
            "entity_id": "sensor." + role,
            "freshness": "source_timestamp",
            "observed_at_attribute": "observed_at",
            "max_age_seconds": 10,
            "evidence_kind": "intent" if role == "room_inhibited" else "measurement",
            "independence_group": "physical",
        }
        if isinstance(value, bool):
            binding["value_map"] = {"on": True, "off": False}
        elif role == "return_temperature":
            binding["unit"] = "°C"
        elif role == "power_percent":
            binding["unit"] = "%"
        selected["systems"]["Main"]["inputs"][role] = binding
    return selected


def data():
    selected = states()
    for role, value in EXTRA.items():
        selected["sensor." + role] = {
            "state": ("on" if value else "off")
            if isinstance(value, bool)
            else str(value),
            "attributes": {"observed_at": 100},
        }
    for role in ("boiler_active", "heat_request"):
        selected["sensor." + role]["state"] = "on"
    return selected


@pytest.mark.parametrize("rule", POLICIES)
def test_complete_reviewed_profiles_are_admitted_and_callbacks_registered(
    tmp_path, rule
):
    selected = configuration(tmp_path, rule)
    HeatingConfig.model_validate(selected)
    monitor, _, _, _ = build_component(tmp_path, data(), configuration=selected)
    assert callable(getattr(monitor, RULES[rule][0]))


def test_pump_requires_ch_startup_and_shutdown_does_not_heal():
    engine = HeatingRuleEngine(profile("R07"), 5, 2)
    assert evaluate(engine, "R07", 100, pump_active=False).violation is None
    assert evaluate(engine, "R07", 105, pump_active=False).violation is True
    assert (
        evaluate(engine, "R07", 110, active=True, boiler_active=False).violation is None
    )
    assert evaluate(engine, "R07", 115, active=True, dhw_active=True).violation is None
    assert evaluate(engine, "R07", 120, active=True).violation is False


def test_brief_pump_recovery_cannot_renew_unresolved_need():
    engine = HeatingRuleEngine(profile("R07"), 5, 2)
    evaluate(engine, "R07", 100, pump_active=False)
    evaluate(engine, "R07", 105, pump_active=False)
    evaluate(engine, "R07", 110, pump_active=True)
    evaluate(engine, "R07", 115, pump_active=False)
    assert engine.episodes["R07"].onset_utc == 100


@pytest.mark.parametrize(
    "values,reason",
    [
        ({}, "distribution_excess_delta"),
        ({"return_temperature": 70.0}, "distribution_inverted_delta"),
    ],
)
def test_distribution_requires_covered_loaded_observations(values, reason):
    engine = HeatingRuleEngine(profile("R08"), 5, 2)
    for now in range(100, 126, 5):
        result = evaluate(engine, "R08", now, **values)
    assert result.violation is True and result.reason == reason
    assert result.observed_qualification_seconds == 0
    assert (
        evaluate(
            engine, "R08", 130, source_at=125, **values
        ).observed_qualification_seconds
        == 0
    )
    assert evaluate(engine, "R08", 130, **values).observed_qualification_seconds == 5
    assert evaluate(engine, "R08", 135, active=True, power_percent=0).violation is None
    assert (
        evaluate(engine, "R08", 140, active=True, boiler_active=False).violation is None
    )


def test_distribution_gap_is_quality_loss_not_mechanical_failure():
    engine = HeatingRuleEngine(profile("R08"), 5, 2)
    for now in (100, 105, 110):
        evaluate(engine, "R08", now)
    result = evaluate(engine, "R08", 120)
    assert (
        result.violation is None
        and result.quality_cause == "distribution_window_incomplete"
    )
    assert engine.episodes["R08"].onset_utc == 100


def test_room_cooling_needs_real_delivery_and_lower_target_cannot_heal():
    engine = HeatingRuleEngine(profile("R09"), 5, 2)
    for now in range(100, 136, 5):
        result = evaluate(engine, "R09", now, room_temperature=18 - (now - 100) / 40)
    assert result.violation is True and result.observed_qualification_seconds >= 5
    for values in (
        {"heat_delivery_active": False},
        {"room_inhibited": True},
        {"heating_permitted": False},
        {"target_temperature": 17},
    ):
        result = evaluate(engine, "R09", 140, active=True, **values)
        assert result.violation is None
    assert engine.episodes["R09"].reference_target == 21


def test_mode_envelope_and_original_clear_reference_survive_dhw_and_restart():
    engine = HeatingRuleEngine(profile("R10"), 5, 2)
    assert evaluate(engine, "R10", 100, flow_temperature=64).violation is True
    assert (
        evaluate(
            engine, "R10", 105, active=True, dhw_active=True, flow_temperature=65
        ).violation
        is None
    )
    restored = HeatingRuleEngine(profile("R10"), 5, 2)
    restored.restore(engine.snapshot(), {"R10"})
    assert (
        evaluate(
            restored, "R10", 110, active=True, dhw_active=True, flow_temperature=60
        ).violation
        is None
    )
    assert (
        evaluate(
            restored, "R10", 115, active=True, dhw_active=True, flow_temperature=58
        ).violation
        is False
    )


def test_absolute_temperature_needs_only_flow_and_does_not_heal_on_clock_uncertainty():
    engine = HeatingRuleEngine(profile("R11"), 5, 2)
    engine.advance(100, 100)
    engine.advance(200, 105)
    observation = HeatingObservation(
        92.0, "valid", 200, "sensor.flow", "physical", "measurement", 10
    )
    result = engine.evaluate(
        "R11", {"flow_temperature": observation}, 200, 105, key="R11", active=False
    )
    assert result.violation is True
    result = engine.evaluate(
        "R11",
        {"flow_temperature": replace(observation, value=40)},
        200,
        105,
        key="R11",
        active=True,
    )
    assert result.violation is None


def test_thermal_positive_survives_storage_failure_and_missing_unrelated_input(
    tmp_path,
):
    selected, values = configuration(tmp_path, "R11"), data()
    values["sensor.flow_temperature"]["state"] = "95"
    values["sensor.pump_active"]["state"] = "unavailable"
    monitor, app, _, clock = build_component(tmp_path, values, configuration=selected)
    manager = attach_fault_manager(monitor, app)
    monitor._restore_error = "fixture inaccessible store"
    monitor._tick()
    tick(monitor, clock, values)
    assert monitor._latches["Heating_absolute_overtemperature_Main"].active
    assert manager.faults["HeatingExcessTemperature"].evaluation.active
    values["sensor.flow_temperature"]["state"] = "40"
    tick(monitor, clock, values)
    assert monitor._latches["Heating_absolute_overtemperature_Main"].active


@pytest.mark.parametrize("change", ["age", "allocation", "envelope", "window"])
def test_impossible_safety_allocations_are_rejected(tmp_path, change):
    selected = configuration(
        tmp_path,
        "R08" if change == "window" else "R10",
        *([] if change == "window" else ["R11"]),
    )
    p = selected["profiles"]["Commissioned"]
    if change == "age":
        selected["systems"]["Main"]["inputs"]["flow_temperature"][
            "max_age_seconds"
        ] = 50
    elif change == "allocation":
        p["absolute_temperature"]["allocation"]["detection_budget_seconds"] = 10
    elif change == "envelope":
        p["mode_temperature"]["envelopes"]["dhw"]["operating_maximum_c"] = 95
    else:
        p["flow_return"]["minimum_sample_count"] = 100
    with pytest.raises(ValueError):
        HeatingConfig.model_validate(selected)


def cycling(
    engine, now, *, on=False, dhw=False, ch_starts=0, dhw_starts=0, source_at=None
):
    return evaluate(
        engine,
        "R12",
        now,
        source_at=source_at,
        boiler_active=on,
        dhw_active=dhw,
        burner_starts_ch=ch_starts,
        burner_starts_dhw=dhw_starts,
    )


def test_cycling_short_intervals_require_upper_bound_and_retain_causes_across_reset():
    engine = HeatingRuleEngine(profile("R12"), 5, 2)
    starts = 0
    for now in range(100, 231, 5):
        on = (now - 100) % 20 == 5
        if on:
            starts += 1
        result = cycling(engine, now, on=on, ch_starts=starts)
    assert result.violation is True and result.observed_qualification_seconds >= 5
    assert engine.cycling.active_modes["R12"] == {"ch"}
    restored = HeatingRuleEngine(profile("R12"), 5, 2)
    restored.restore(engine.snapshot(), set(), {"R12"})
    assert cycling(restored, 235, ch_starts=starts).violation is None
    result = cycling(restored, 240, ch_starts=0)
    assert result.violation is None and result.reason == "cycling_counter_reset"
    assert restored.cycling.active_modes["R12"] == {"ch"}
    for now in range(245, 356, 5):
        result = cycling(restored, now)
    assert result.violation is None  # Idle is not comparable recovery.


def test_room_history_before_need_does_not_count_as_delivery_failure():
    engine = HeatingRuleEngine(profile("R09"), 5, 2)
    for now, temperature in ((100, 24), (105, 23), (110, 22), (115, 21), (120, 19)):
        result = evaluate(engine, "R09", now, room_temperature=temperature)
    assert result.violation is None
    assert engine.episodes["R09"].onset_utc == 120
    assert engine.distribution.frames["R09"].started == 120


def test_absolute_uncertainty_cannot_raise_manufacturer_limit():
    engine = HeatingRuleEngine(profile("R11"), 5, 2)
    result = evaluate(engine, "R11", 100, flow_temperature=89)
    assert result.violation is True
    assert dict(result.window_evidence)["failure_threshold_c"] == 89


def test_thermal_retirement_discards_old_reference_only_after_group_clear(tmp_path):
    selected, values = configuration(tmp_path, "R10", "R11"), data()
    values["sensor.flow_temperature"]["state"] = "95"
    monitor, app, _, clock = build_component(tmp_path, values, configuration=selected)
    manager = attach_fault_manager(monitor, app)
    monitor._tick()
    tick(monitor, clock, values)
    assert manager.faults["HeatingExcessTemperature"].evaluation.active
    values["sensor.flow_temperature"]["state"] = "55"
    for _ in range(2):
        tick(monitor, clock, values)
    assert not manager.faults["HeatingExcessTemperature"].evaluation.active
    assert not monitor._engines["Main"].episodes
    restored, _, _, _ = build_component(
        tmp_path, values, initial=clock[0], configuration=selected
    )
    assert not restored._restore_error
    # Crash-safe restore either keeps the pending incident or removes orphaned references.
    if "HeatingExcessTemperature" not in restored._incidents:
        assert not restored._engines["Main"].episodes


def test_thermal_hazard_bypasses_real_diagnostic_startup_grace(tmp_path):
    from components.core.startup_grace import StartupGrace

    values = data()
    values["sensor.flow_temperature"]["state"] = "95"
    monitor, _, _, clock = build_component(
        tmp_path, values, configuration=configuration(tmp_path, "R11")
    )
    diagnostics = {
        name for name, (_, rule, _) in monitor._bindings.items() if rule == "R01"
    }
    grace = StartupGrace(monitor.event_bus, diagnostics, 600, clock=lambda: clock[0])
    delivered = []
    monitor.event_bus.subscribe(
        "qualified_symptom", lambda **event: delivered.append(event)
    )
    monitor._tick()
    tick(monitor, clock, values)
    assert grace.snapshot()["phase"] != "complete"
    assert any(
        event["symptom_id"] == "Heating_absolute_overtemperature_Main"
        and event["state"].name == "SET"
        for event in delivered
    )
    assert not any(event["symptom_id"] in diagnostics for event in delivered)


def test_unaffected_covered_cycling_assessment_can_clear_shared_fault_contributor():
    engine = HeatingRuleEngine(profile("R12"), 5, 2)
    for now in range(100, 211, 5):
        result = cycling(engine, now)
    assert result.violation is False
    assert result.observed_qualification_seconds >= 5
    assert not engine.cycling.active_modes


def test_ambiguous_sampled_cycle_duration_cannot_count_as_short():
    engine = HeatingRuleEngine(profile("R12"), 5, 2)
    starts = 0
    for now in range(100, 231, 5):
        offset = (now - 100) % 25
        on = offset in {5, 10}
        if offset == 5:
            starts += 1
        result = cycling(engine, now, on=on, ch_starts=starts)
    assert result.violation is not True  # Upper bound is exactly 15s, not below it.
    assert not engine.cycling.active_modes


def test_cycling_cached_reports_and_counter_gaps_cannot_advance_coverage():
    engine = HeatingRuleEngine(profile("R12"), 5, 2)
    for now in range(100, 211, 5):
        result = cycling(engine, now, source_at=100)
    assert result.violation is None
    assert not engine.cycling.active_modes


def test_shared_cycling_fault_recovers_with_healthy_unaffected_installation(tmp_path):
    selected = configuration(tmp_path, "R12")
    selected["systems"]["Other"] = deepcopy(selected["systems"]["Main"])
    selected["systems"]["Other"]["friendly_name"] = "Other fixture"
    monitor, app, _, _ = build_component(tmp_path, data(), configuration=selected)
    manager = attach_fault_manager(monitor, app)
    affected = HeatingRuleEngine(profile("R12"), 5, 2)
    unaffected = HeatingRuleEngine(profile("R12"), 5, 2)
    starts = 0
    saw_failure = False
    for now in range(100, 511, 5):
        offset = (now - 100) % 20 if now < 240 else (now - 240) % 100
        on = offset == 5 if now < 240 else 5 <= offset <= 55
        begins = offset == 5
        if begins:
            starts += 1
        outcome = cycling(affected, now, on=on, ch_starts=starts)
        monitor._qualify("Heating_short_cycling_Main", outcome, now)
        monitor._qualify("Heating_short_cycling_Other", cycling(unaffected, now), now)
        if manager.faults["HeatingCyclingDiagnostic"].evaluation.active:
            saw_failure = True
    assert saw_failure
    assert not manager.faults["HeatingCyclingDiagnostic"].evaluation.active


def test_cycling_recovery_requires_every_affected_mode():
    engine = HeatingRuleEngine(profile("R12"), 5, 2)
    engine.cycling.active_modes["R12"] = {"ch", "dhw"}
    starts = 0
    recovered_ch = False
    for now in range(100, 311, 5):
        offset = (now - 100) % 100
        if offset == 5:
            starts += 1
        result = cycling(engine, now, on=5 <= offset <= 55, ch_starts=starts)
        recovered_ch |= dict(result.window_evidence).get("ch_long_cycles", 0) > 0
        assert result.violation is not False
    assert recovered_ch


def test_cycling_counters_keep_independent_slower_observation_cadence():
    engine = HeatingRuleEngine(profile("R12"), 5, 2)
    for now in range(100, 221, 5):
        engine.advance(now, now)
        selected = observations(
            now, **{**EXTRA, "boiler_active": False, "dhw_active": False}
        )
        for role in ("burner_starts_ch", "burner_starts_dhw"):
            selected[role] = replace(selected[role], observed_at=now - now % 10)
        result = engine.evaluate("R12", selected, now, now, key="R12", active=False)
    assert result.violation is False
    assert dict(result.window_evidence)["ch_covered_seconds"] >= 100


def test_partial_new_distribution_tuple_cannot_reuse_old_recovery():
    engine = HeatingRuleEngine(profile("R08"), 5, 2)
    for now in range(100, 131, 5):
        evaluate(engine, "R08", now, return_temperature=55, active=True)
    selected = observations(
        130,
        **{
            **EXTRA,
            "boiler_active": True,
            "flow_temperature": 60,
            "return_temperature": 55,
        },
    )
    selected["flow_temperature"] = replace(
        selected["flow_temperature"], value=90, observed_at=132
    )
    engine.advance(132, 132)
    result = engine.evaluate("R08", selected, 132, 132, key="R08", active=True)
    assert result.violation is None
    result = evaluate(engine, "R08", 135, active=True, return_temperature=55)
    assert result.observed_qualification_seconds == 0
