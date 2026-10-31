"""Safety contracts for generic status, room need and CH response supervision."""

from copy import deepcopy

import pytest

from components.core.types_common import FaultState
from components.safetycomponents.heating.inputs import HeatingObservation
from components.safetycomponents.heating.rules import HeatingRuleEngine
from components.safetycomponents.heating.schema import HeatingConfig, HeatingProfile
from components.safetycomponents.heating.state import legacy_fingerprint
from test_heating_monitor import build_component


STATUS = {
    "evidence_reference": "commissioned fixture",
    "failure_seconds": 5,
    "recovery_seconds": 5,
}
POLICIES = {
    "R02": ("device_fault", STATUS),
    "R13": ("maintenance", STATUS),
    "R03": (
        "missing_demand",
        {
            **STATUS,
            "need_on_margin_k": 1,
            "need_off_margin_k": 0.2,
            "request_allowance_seconds": 10,
            "maximum_unresolved_seconds": 120,
            "maximum_input_skew_seconds": 2,
            "independent_need_reference": "independent room and schedule",
        },
    ),
    "R04": (
        "no_response",
        {
            **STATUS,
            "startup_allowance_seconds": 10,
            "maximum_inhibition_seconds": 20,
            "maximum_unresolved_seconds": 120,
            "target_recovery_margin_k": 1,
            "maximum_input_skew_seconds": 2,
            "inhibition_context": "mapped_reason",
        },
    ),
}
VALUES = {
    "device_status": "fault",
    "maintenance_status": "maintenance",
    "room_temperature": 18.0,
    "target_temperature": 21.0,
    "heating_permitted": True,
    "heat_request": False,
    "boiler_active": False,
    "dhw_active": False,
    "flow_temperature": 25.0,
    "requested_flow_temperature": 45.0,
    "inhibition_reason": "none",
}
INTENTS = {
    "heating_permitted",
    "heat_request",
    "target_temperature",
    "requested_flow_temperature",
    "inhibition_reason",
}


def profile(*rules):
    return HeatingProfile(
        enabled_rules=["R01", *rules],
        provenance="test",
        **{POLICIES[r][0]: deepcopy(POLICIES[r][1]) for r in rules},
    )


def observations(now=100, **values):
    return {
        role: HeatingObservation(
            value,
            "valid",
            now,
            "sensor." + role,
            "request" if role == "heat_request" else "independent",
            "intent" if role in INTENTS else "measurement",
            10,
        )
        for role, value in {**VALUES, **values}.items()
    }


def evaluate(engine, rule, now=100, mono=None, active=False, **values):
    mono = now if mono is None else mono
    engine.advance(now, mono)
    return engine.evaluate(
        rule, observations(now, **values), now, mono, key=rule, active=active
    )


def config(tmp_path, *rules):
    inputs = {}
    for role, value in VALUES.items():
        binding = {
            "entity_id": "sensor." + role,
            "freshness": "source_timestamp",
            "observed_at_attribute": "observed_at",
            "max_age_seconds": 10,
            "evidence_kind": "intent" if role in INTENTS else "measurement",
            "independence_group": "request"
            if role == "heat_request"
            else "independent",
        }
        if isinstance(value, bool) or isinstance(value, str):
            binding["value_map"] = (
                {"on": True, "off": False}
                if isinstance(value, bool)
                else {"clear": "clear", "fault": "fault"}
                if role == "device_status"
                else {"clear": "clear", "maintenance": "maintenance"}
                if role == "maintenance_status"
                else {"off": "none", "starting": "startup", "waiting": "anti_cycle"}
            )
        else:
            binding["unit"] = "°C"
        inputs[role] = binding
    return {
        "state_file": str(tmp_path / "legacy.json"),
        "profiles": {"Commissioned": profile(*rules).model_dump()},
        "systems": {
            "Main": {
                "friendly_name": "Kotłownia",
                "profile": "Commissioned",
                "inputs": inputs,
            }
        },
    }


def states():
    result = {}
    for role, value in VALUES.items():
        raw = (
            ("on" if value else "off")
            if isinstance(value, bool)
            else "off"
            if role == "inhibition_reason"
            else str(value)
        )
        result["sensor." + role] = {"state": raw, "attributes": {"observed_at": 100}}
    return result


def tick(monitor, clock, data, seconds=5):
    clock[0] += seconds
    for record in data.values():
        record["attributes"]["observed_at"] = clock[0]
    monitor._tick()


@pytest.mark.parametrize(
    "rule,role,failed",
    [("R02", "device_status", "fault"), ("R13", "maintenance_status", "maintenance")],
)
def test_current_status_is_explicit_and_unknown_cannot_clear(rule, role, failed):
    engine = HeatingRuleEngine(profile(rule), 5, 2)
    assert evaluate(engine, rule, **{role: failed}).violation is True
    assert (
        evaluate(engine, rule, 105, active=True, **{role: "unknown"}).violation is None
    )
    assert (
        evaluate(engine, rule, 110, active=True, **{role: "clear"}).violation is False
    )


def test_need_uses_independent_temperature_and_permission_not_controller_request():
    engine = HeatingRuleEngine(profile("R03"), 5, 2)
    assert evaluate(engine, "R03").reason == "request_allowance"
    assert evaluate(engine, "R03", 110).violation is True
    assert (
        evaluate(engine, "R03", 115, active=True, heating_permitted=False).violation
        is None
    )
    assert (
        evaluate(engine, "R03", 120, active=True, target_temperature=17).violation
        is None
    )
    assert engine.episodes["R03"].reference_target == 21
    assert (
        evaluate(engine, "R03", 125, active=True, heat_request=True).violation is False
    )
    assert engine.episodes["R03"].elapsed_seconds == 25


def test_ineligible_and_stale_samples_never_close_need_episode():
    engine = HeatingRuleEngine(profile("R03"), 5, 2)
    evaluate(engine, "R03")
    bad = observations(105, room_temperature=22)
    bad["room_temperature"] = HeatingObservation(
        22, "stale", 90, "sensor.room", "independent", "measurement", 10
    )
    engine.advance(105, 105)
    assert (
        engine.evaluate("R03", bad, 105, 105, key="R03", active=True).violation is None
    )
    assert "R03" in engine.episodes


def test_dhw_burner_and_hot_flow_are_not_ch_recovery():
    engine = HeatingRuleEngine(profile("R04"), 5, 2)
    outcome = evaluate(
        engine,
        "R04",
        heat_request=True,
        dhw_active=True,
        boiler_active=True,
        flow_temperature=60,
    )
    assert outcome.violation is None
    assert (
        evaluate(
            engine,
            "R04",
            120,
            heat_request=True,
            dhw_active=True,
            boiler_active=True,
            flow_temperature=60,
        ).violation
        is True
    )
    assert (
        evaluate(engine, "R04", 125, active=True, heat_request=False).violation is None
    )
    assert (
        evaluate(
            engine,
            "R04",
            130,
            active=True,
            heat_request=True,
            requested_flow_temperature=20,
        ).violation
        is None
    )
    assert (
        evaluate(
            engine, "R04", 135, active=True, heat_request=True, boiler_active=True
        ).violation
        is False
    )


def test_working_ch_response_is_not_relabelled_as_no_response_after_deadline():
    engine = HeatingRuleEngine(profile("R04"), 5, 2)
    evaluate(engine, "R04", heat_request=True)
    assert (
        evaluate(engine, "R04", 300, heat_request=True, boiler_active=True).violation
        is False
    )
    assert "R04" in engine.episodes  # Delivery/target tracking belongs to other rules.


def test_repeated_inhibitions_and_restart_cannot_renew_total_allowance():
    engine = HeatingRuleEngine(profile("R04"), 5, 2)
    evaluate(engine, "R04", heat_request=True, dhw_active=True)
    evaluate(engine, "R04", 105, heat_request=True, boiler_active=True)
    before = evaluate(engine, "R04", 110, heat_request=True, dhw_active=True)
    assert before.violation is None
    restored = HeatingRuleEngine(profile("R04"), 5, 2)
    restored.restore(engine.snapshot(), {"R04"})
    after = evaluate(restored, "R04", 180, mono=1, heat_request=True, dhw_active=True)
    assert after.urgent and after.violation is True
    assert after.onset_utc == 100
    assert after.elapsed_seconds == 80


@pytest.mark.parametrize("jump", [-50, 50])
def test_clock_discontinuity_is_quality_loss_not_a_mechanical_fault(jump):
    engine = HeatingRuleEngine(profile("R04"), 5, 2)
    evaluate(engine, "R04", heat_request=True)
    result = evaluate(engine, "R04", 105 + jump, mono=105, heat_request=True)
    assert result.violation is None and result.quality_cause == "clock_uncertain"
    assert engine.episodes["R04"].elapsed_seconds == 5


def test_input_coherence_and_independence_are_separate_quality_failures():
    engine = HeatingRuleEngine(profile("R03"), 5, 2)
    data = observations()
    data["heat_request"] = HeatingObservation(
        False, "valid", 95, "sensor.request", "request", "intent", 10
    )
    assert (
        engine.evaluate("R03", data, 100, 100, key="R03", active=False).quality_cause
        == "input_skew"
    )
    data["heat_request"] = HeatingObservation(
        False, "valid", 100, "sensor.request", "independent", "intent", 10
    )
    assert (
        engine.evaluate("R03", data, 100, 100, key="R03", active=False).quality_cause
        == "dependent_need"
    )


def test_stall_and_restart_never_count_as_positive_recovery_samples():
    engine = HeatingRuleEngine(profile("R03"), 5, 2)
    evaluate(engine, "R03")
    evaluate(engine, "R03", 105, room_temperature=22)
    evaluate(engine, "R03", 200, room_temperature=22)
    assert "R03" in engine.episodes
    restored = HeatingRuleEngine(profile("R03"), 5, 2)
    restored.restore(engine.snapshot(), {"R03"})
    evaluate(restored, "R03", 300, mono=1, room_temperature=22)
    assert "R03" in restored.episodes
    evaluate(restored, "R03", 305, mono=6, room_temperature=22)
    assert "R03" not in restored.episodes


def test_component_dispatches_all_four_rules_and_keeps_l4_informational(tmp_path):
    data = states()
    monitor, _, _, clock = build_component(
        tmp_path, data, configuration=config(tmp_path, "R02", "R03", "R04", "R13")
    )
    monitor._tick()
    for _ in range(3):
        tick(monitor, clock, data)
    assert monitor._latches["Heating_device_fault_Main"].active
    assert monitor._latches["Heating_maintenance_Main"].active
    assert monitor._latches["Heating_missing_demand_Main"].active
    assert not monitor._latches["Heating_no_response_Main"].active
    assert not monitor._latches["Heating_supervision_loss_Main"].active
    assert monitor.get_fault_definitions()["HeatingMaintenance"]["level"] == 4
    assert monitor.get_fault_definitions()["HeatingMaintenance"]["category"] == "D"


def test_unmapped_code_sets_quality_alarm_and_does_not_heal_device_fault(tmp_path):
    data = states()
    monitor, _, events, clock = build_component(
        tmp_path, data, configuration=config(tmp_path, "R02")
    )
    monitor._tick()
    tick(monitor, clock, data)
    data["sensor.device_status"]["state"] = "H00"
    for _ in range(3):
        tick(monitor, clock, data)
    assert monitor._latches["Heating_device_fault_Main"].active
    assert monitor._latches["Heating_supervision_loss_Main"].active
    assert not any(
        e["state"] == FaultState.CLEARED
        and e["symptom_id"] == "Heating_device_fault_Main"
        for e in events
    )


def test_v1_upgrade_preserves_active_incident_and_pending_duration(tmp_path):
    data = {
        "sensor.health": {"state": "bad", "attributes": {}},
        "sensor.flow": {"state": "30", "attributes": {}},
    }
    monitor, _, _, clock = build_component(tmp_path, data)
    monitor._tick()
    clock[0] += 5
    monitor._tick()
    snapshot = monitor._store.load()
    snapshot["version"] = 1
    snapshot["fingerprint"] = legacy_fingerprint(monitor._semantic_config)
    snapshot.pop("contract")
    snapshot.pop("engines")
    monitor._store.save(snapshot)
    restarted, _, events, _ = build_component(tmp_path, data, initial=200)
    restarted._tick()
    assert restarted._restore_error is None
    assert restarted._store.load()["version"] == 2
    assert events[0]["additional_info"]["incident_id"] == next(
        iter(snapshot["incidents"].values())
    )


def test_additive_rule_admission_preserves_existing_active_evidence(tmp_path):
    data = states()
    monitor, _, _, clock = build_component(
        tmp_path, data, configuration=config(tmp_path, "R02")
    )
    monitor._tick()
    tick(monitor, clock, data)
    incident = monitor._incidents["HeatingDeviceFault"]
    restarted, _, _, _ = build_component(
        tmp_path, data, initial=110, configuration=config(tmp_path, "R02", "R13")
    )
    assert restarted._restore_error is None
    assert restarted._latches["Heating_device_fault_Main"].active
    assert restarted._incidents["HeatingDeviceFault"] == incident


def test_changed_contract_is_fail_closed_and_durable_snapshot_survives(tmp_path):
    data = states()
    monitor, _, _, _ = build_component(
        tmp_path, data, configuration=config(tmp_path, "R04")
    )
    data["sensor.heat_request"]["state"] = "on"
    monitor._tick()
    snapshot = monitor._store.load()
    changed = config(tmp_path, "R04")
    changed["profiles"]["Commissioned"]["no_response"][
        "maximum_inhibition_seconds"
    ] = 25
    restarted, _, _, _ = build_component(tmp_path, data, configuration=changed)
    assert restarted._restore_error
    restarted._tick()
    assert restarted._store.load() == snapshot


@pytest.mark.parametrize(
    "mutation", ["freshness", "dependence", "latency", "missing", "hysteresis"]
)
def test_admission_rejects_incomplete_or_unbounded_contract(tmp_path, mutation):
    selected = config(tmp_path, "R03")
    inputs = selected["systems"]["Main"]["inputs"]
    if mutation == "freshness":
        inputs["heat_request"]["freshness"] = "availability_only"
        inputs["heat_request"].pop("observed_at_attribute")
    elif mutation == "dependence":
        inputs["room_temperature"]["independence_group"] = "request"
    elif mutation == "latency":
        inputs["heat_request"]["max_age_seconds"] = 30
    elif mutation == "missing":
        inputs.pop("heat_request")
    else:
        selected["profiles"]["Commissioned"]["missing_demand"]["need_off_margin_k"] = 2
    with pytest.raises(ValueError):
        HeatingConfig.model_validate(selected)


def test_disjoint_source_failures_do_not_share_failure_duration(tmp_path):
    data = {
        "sensor.health": {"state": "bad", "attributes": {}},
        "sensor.flow": {"state": "30", "attributes": {}},
    }
    monitor, _, events, clock = build_component(tmp_path, data)
    monitor._tick()
    clock[0] += 3
    data["sensor.health"]["state"] = "ok"
    data["sensor.flow"]["state"] = "unavailable"
    monitor._tick()
    clock[0] += 3
    monitor._tick()
    assert not events
    clock[0] += 2
    monitor._tick()
    assert events[-1]["state"] == FaultState.SET


def test_stop_after_stall_does_not_persist_fictitious_failure_samples(tmp_path):
    data = {
        "sensor.health": {"state": "bad", "attributes": {}},
        "sensor.flow": {"state": "30", "attributes": {}},
    }
    monitor, _, _, clock = build_component(tmp_path, data)
    monitor._tick()
    clock[0] += 2
    monitor._tick()
    clock[0] += 600
    monitor.stop()
    restarted, _, events, new_clock = build_component(tmp_path, data, initial=1000)
    restarted._tick()
    assert not events
    new_clock[0] += 3
    restarted._tick()
    assert events[-1]["state"] == FaultState.SET


def test_shared_source_going_from_stale_to_unavailable_cannot_clear_quality_fault(
    tmp_path,
):
    selected = config(tmp_path)
    selected["systems"]["Main"]["inputs"]["flow_temperature"][
        "shared_temperature"
    ] = True
    data = states()
    data["sensor.flow_temperature"]["attributes"]["observed_at"] = 1
    monitor, _, _, clock = build_component(tmp_path, data, configuration=selected)
    monitor._tick()
    clock[0] += 5
    monitor._tick()
    symptom = "Heating_supervision_loss_Main"
    assert monitor._latches[symptom].active
    data["sensor.flow_temperature"]["state"] = "unavailable"
    for _ in range(14):
        tick(monitor, clock, data)
    assert monitor._latches[symptom].active
    assert monitor._latches[symptom].status == "UNEVALUABLE"


def test_expired_budget_still_requires_observed_failure_qualification(tmp_path):
    data = states()
    data["sensor.heat_request"]["state"] = "on"
    selected = config(tmp_path, "R04")
    monitor, _, _, clock = build_component(tmp_path, data, configuration=selected)
    monitor._tick()
    data["sensor.flow_temperature"]["state"] = "unavailable"
    tick(monitor, clock, data, 100)
    data["sensor.flow_temperature"]["state"] = "25"
    tick(monitor, clock, data)
    symptom = "Heating_no_response_Main"
    assert not monitor._latches[symptom].active
    assert monitor._latches[symptom].status == "PENDING_FAILURE"
    tick(monitor, clock, data)
    assert monitor._latches[symptom].active


def test_final_clear_atomically_retires_incident_before_publication(tmp_path):
    data = states()
    selected = config(tmp_path, "R02")
    monitor, _, _, clock = build_component(tmp_path, data, configuration=selected)
    monitor._tick()
    tick(monitor, clock, data)
    incident = monitor._incidents["HeatingDeviceFault"]
    data["sensor.device_status"]["state"] = "clear"
    tick(monitor, clock, data)
    # Simulate interruption after the durable clear and before event publication.
    monitor._publish = lambda *args: None
    tick(monitor, clock, data)
    snapshot = monitor._store.load()
    assert "HeatingDeviceFault" not in snapshot["incidents"]
    restarted, _, _, clock2 = build_component(
        tmp_path, data, initial=clock[0], configuration=selected
    )
    data["sensor.device_status"]["state"] = "fault"
    tick(restarted, clock2, data)
    tick(restarted, clock2, data)
    assert restarted._incidents["HeatingDeviceFault"] != incident


def test_different_rule_durations_do_not_shorten_each_others_allowance():
    combined = profile("R03", "R04")
    combined.no_response.failure_seconds = 100
    combined.no_response.maximum_unresolved_seconds = 1000
    engine = HeatingRuleEngine(combined, 5, 2)
    assert evaluate(engine, "R03").reason == "request_allowance"


def test_v1_pending_duration_cannot_transfer_to_a_different_source(tmp_path):
    data = {
        "sensor.health": {"state": "bad", "attributes": {}},
        "sensor.flow": {"state": "30", "attributes": {}},
    }
    monitor, _, _, clock = build_component(tmp_path, data)
    monitor._tick()
    clock[0] += 3
    monitor._tick()
    snapshot = monitor._store.load()
    snapshot.update(version=1, fingerprint=legacy_fingerprint(monitor._semantic_config))
    for key in ("contract", "engines", "quality_pending"):
        snapshot.pop(key)
    monitor._store.save(snapshot)
    data["sensor.health"]["state"] = "ok"
    data["sensor.flow"]["state"] = "unavailable"
    restarted, _, events, clock2 = build_component(tmp_path, data, initial=1000)
    restarted._tick()
    clock2[0] += 2
    restarted._tick()
    assert not events
    clock2[0] += 3
    restarted._tick()
    assert events[-1]["state"] == FaultState.SET


def test_multiple_rooms_share_incident_until_last_positive_clear(tmp_path):
    selected = config(tmp_path, "R03")
    system = selected["systems"]["Main"]
    system["rooms"] = {
        key: {
            "friendly_name": label,
            "inputs": {
                "room_temperature": {
                    **system["inputs"]["room_temperature"],
                    "entity_id": entity,
                }
            },
        }
        for key, label, entity in (
            ("Office", "Biuro", "sensor.office"),
            ("Bedroom", "Sypialnia", "sensor.bedroom"),
        )
    }
    data = states()
    data["sensor.office"] = deepcopy(data["sensor.room_temperature"])
    data["sensor.bedroom"] = deepcopy(data["sensor.room_temperature"])
    monitor, _, events, clock = build_component(tmp_path, data, configuration=selected)
    monitor._tick()
    for _ in range(3):
        tick(monitor, clock, data)
    incident = monitor._incidents["HeatingMissingDemand"]
    failures = [item for item in events if item["state"] == FaultState.SET]
    assert {item["additional_info"]["room"] for item in failures} == {
        "Biuro",
        "Sypialnia",
    }
    assert {item["additional_info"]["incident_id"] for item in failures} == {incident}
    data["sensor.office"]["state"] = "22"
    tick(monitor, clock, data)
    tick(monitor, clock, data)
    assert monitor._incidents["HeatingMissingDemand"] == incident
    assert monitor._latches["Heating_missing_demand_Main_Bedroom"].active
    data["sensor.bedroom"]["state"] = "22"
    tick(monitor, clock, data)
    tick(monitor, clock, data)
    assert "HeatingMissingDemand" not in monitor._incidents


def test_failed_response_clear_commit_preserves_activation_and_need(tmp_path):
    data = states()
    data["sensor.heat_request"]["state"] = "on"
    monitor, _, events, clock = build_component(
        tmp_path, data, configuration=config(tmp_path, "R04")
    )
    monitor._tick()
    for _ in range(3):
        tick(monitor, clock, data)
    assert monitor._latches["Heating_no_response_Main"].active
    data["sensor.flow_temperature"]["state"] = "45"
    tick(monitor, clock, data)
    monitor._store.save = lambda *_: (_ for _ in ()).throw(OSError("disk full"))
    tick(monitor, clock, data)
    assert monitor._latches["Heating_no_response_Main"].active
    assert "Heating_no_response_Main" in monitor._engines["Main"].episodes
    assert not any(
        item["state"] == FaultState.CLEARED
        and item["symptom_id"] == "Heating_no_response_Main"
        for item in events
    )
