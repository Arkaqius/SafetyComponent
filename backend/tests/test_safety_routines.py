"""Advisory routine safety contracts, replay handling and runtime integration."""

import copy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
import yaml
from pydantic import ValidationError

from build_app_config import compile_config
from components.core.sqlite_state_store import SqliteStateDatabase
from components.safety_routines.evaluation import evaluate_check, summarize
from components.safety_routines.runtime import (
    COMPLETED_EVENT,
    REQUEST_EVENT,
    SafetyRoutineRuntime,
)
from components.safety_routines.schema import (
    RoutineCheck,
    SafetyRoutine,
    SafetyRoutinesConfig,
)

NOW = datetime(2026, 10, 31, 20, tzinfo=timezone.utc)
CHECK = {
    "name": "Window closed",
    "entity_id": "binary_sensor.window",
    "observed_at_attribute": "observed_at",
    "expected_states": ["off"],
}


def source(value="off", **attributes):
    return {
        "state": value,
        "attributes": {"observed_at": NOW.isoformat(), **attributes},
    }


def build(tmp_path, **settings):
    clock = [NOW]
    app = Mock()
    app.get_state.return_value = source()
    store = SqliteStateDatabase(tmp_path / "state.sqlite3").store(
        "safety_routines", tmp_path / "legacy.json"
    )
    config = {
        "routines": {
            "Bedtime": {"name": "Bedtime", "checks": {"Window": CHECK}, **settings}
        }
    }
    runtime = SafetyRoutineRuntime(app, config, store, now=lambda: clock[0])
    runtime.start()
    return runtime, app, store, clock


@pytest.mark.parametrize(
    "value,status,reason",
    [
        ("off", "pass", "expected"),
        ("on", "problem", "unexpected"),
        ("unknown", "unknown", "unavailable"),
        (None, "unknown", "unavailable"),
        ({"x": 1}, "unknown", "malformed"),
    ],
)
def test_state_evidence(value, status, reason):
    result = evaluate_check(
        "Window", RoutineCheck(**CHECK), {"binary_sensor.window": source(value)}, NOW
    )
    assert (result["status"], result["reason"]) == (status, reason)


@pytest.mark.parametrize(
    "observed,reason",
    [
        (None, "timestamp_missing"),
        ("2026-10-31T20:00:00", "timestamp_missing"),
        ((NOW - timedelta(seconds=301)).isoformat(), "stale"),
        ((NOW + timedelta(seconds=1)).isoformat(), "future_timestamp"),
    ],
)
def test_no_clear_from_unqualified_time(observed, reason):
    result = evaluate_check(
        "Window",
        RoutineCheck(**CHECK),
        {"binary_sensor.window": source(observed_at=observed)},
        NOW,
    )
    assert result["status"] == "unknown"
    assert result["reason"] == reason


@pytest.mark.parametrize(
    "value,unit,status",
    [
        ("4.5", "W", "pass"),
        ("10", "W", "problem"),
        (True, "W", "unknown"),
        ("NaN", "W", "unknown"),
        ("Infinity", "W", "unknown"),
        ("x", "W", "unknown"),
        ("4", "kW", "unknown"),
        ("4", None, "unknown"),
    ],
)
def test_numeric_contract(value, unit, status):
    check = RoutineCheck(
        name="Power",
        entity_id="sensor.power",
        observed_at_attribute="observed_at",
        kind="numeric_range",
        minimum=0.0,
        maximum=5.0,
        unit="W",
    )
    result = evaluate_check(
        "Power", check, {"sensor.power": source(value, unit_of_measurement=unit)}, NOW
    )
    assert result["status"] == status


def test_unknown_condition_is_not_skipped_and_all_skipped_is_not_pass():
    check = RoutineCheck(
        **CHECK,
        condition={
            "entity_id": "sensor.occupancy",
            "observed_at_attribute": "observed_at",
            "pass_states": ["empty"],
            "skip_states": ["occupied"],
        },
    )
    states = {"binary_sensor.window": source(), "sensor.occupancy": source("unknown")}
    result = evaluate_check("Window", check, states, NOW)
    assert result["status"] == "unknown"
    states["sensor.occupancy"] = source("occupied")
    result = evaluate_check("Window", check, states, NOW)
    assert result["status"] == "skipped"
    assert summarize([result])["status"] == "not_applicable"
    states["sensor.occupancy"] = source("guest")
    assert evaluate_check("Window", check, states, NOW)["status"] == "unknown"


def test_mixed_problem_and_unknown_are_both_reported():
    assert summarize([{"status": "problem"}, {"status": "unknown"}]) == {
        "status": "problem",
        "counts": {"pass": 0, "problem": 1, "unknown": 1, "skipped": 0},
    }


@pytest.mark.parametrize(
    "override",
    [
        {"observed_at_attribute": None},
        {"max_age_seconds": True},
        {"kind": "numeric_range", "maximum": float("inf")},
        {"expected_states": []},
        {"unexpected_field": True},
    ],
)
def test_closed_check_configuration(override):
    with pytest.raises(ValidationError):
        RoutineCheck(**{**CHECK, **override})


def test_bounded_configuration_and_reserved_trigger():
    with pytest.raises(ValidationError):
        SafetyRoutine(name="Bedtime", checks={})
    with pytest.raises(ValidationError):
        SafetyRoutinesConfig(
            routines={"bad-key": {"name": "Bedtime", "checks": {"Window": CHECK}}}
        )
    with pytest.raises(ValidationError):
        SafetyRoutine(
            name="Bedtime",
            checks={"Window": CHECK},
            triggers=[{"kind": "event", "event": REQUEST_EVENT}],
        )


def test_repeat_is_immutable_and_duplicate_is_idempotent(tmp_path):
    runtime, app, _, _ = build(tmp_path)
    first = runtime.run("Bedtime", "one")["run"]
    assert first["status"] == "pass"
    app.get_state.return_value = source("on")
    repeated = runtime.run("Bedtime", "two")["run"]
    duplicate = runtime.run("Bedtime", "one")["run"]
    assert duplicate == first
    assert repeated["run_id"] != first["run_id"]
    assert repeated["status"] == "problem"
    assert runtime.history[0]["status"] == "pass"
    app.call_service.assert_not_called()
    app.set_state.assert_not_called()


def test_delayed_run_overlap_cancel_and_late_callback(tmp_path):
    runtime, app, _, clock = build(tmp_path, delay_seconds=30)
    first = runtime.run("Bedtime", "one")["run"]
    assert first["state"] == "waiting"
    app.get_state.assert_not_called()
    assert runtime.run("Bedtime", "two")["error"] == "already_running"
    callback = app.run_in.call_args.kwargs
    result = runtime._request(
        {"action": "cancel", "routine_id": "Bedtime", "run_id": first["run_id"]}
    )
    assert result["run"]["state"] == "cancelled"
    runtime.run("Bedtime", "three")
    clock[0] += timedelta(seconds=30)
    runtime._timer(**callback)
    app.get_state.assert_not_called()


def test_window_latches_problem_and_does_not_finish_early(tmp_path):
    runtime, app, _, clock = build(tmp_path, observation_seconds=10)
    app.get_state.return_value = source("on")
    first = runtime.run("Bedtime")["run"]
    assert first["state"] == "running" and first["status"] == "unknown"
    app.get_state.return_value = source("off")
    for _ in range(2):
        clock[0] += timedelta(seconds=5)
        runtime._timer(**app.run_in.call_args.kwargs)
    assert runtime.history[-1]["state"] == "completed"
    assert runtime.history[-1]["status"] == "problem"
    assert runtime.history[-1]["sample_count"] == 3


def test_restart_marks_inflight_interrupted_without_reading_or_replaying(tmp_path):
    runtime, app, store, clock = build(tmp_path, delay_seconds=30)
    runtime.run("Bedtime")
    restored = SafetyRoutineRuntime(
        app, runtime.config.model_dump(), store, now=lambda: clock[0]
    )
    restored.start()
    assert restored.history[-1]["state"] == "interrupted"
    assert restored.history[-1]["status"] == "unknown"
    app.get_state.assert_not_called()


def test_stop_prevents_late_timers_and_new_runs(tmp_path):
    runtime, app, _, _ = build(tmp_path, delay_seconds=30)
    runtime.run("Bedtime")
    callback = app.run_in.call_args.kwargs
    runtime.stop()
    runtime._timer(**callback)
    assert runtime.history[-1]["state"] == "interrupted"
    assert runtime.run("Bedtime")["error"] == "not_running"
    app.get_state.assert_not_called()


def test_read_schedule_and_storage_failures_are_explicit(tmp_path):
    runtime, app, store, _ = build(tmp_path)
    app.get_state.side_effect = RuntimeError("connection lost")
    store.save = Mock(side_effect=OSError("disk full"))
    assert runtime.run("Bedtime")["run"]["status"] == "unknown"
    assert runtime.storage_available is False
    runtime.config.routines["Bedtime"].delay_seconds = 30
    app.run_in.side_effect = RuntimeError("scheduler failed")
    assert runtime.run("Bedtime")["run"]["state"] == "interrupted"


def test_event_api_is_correlated_bounded_and_localized(tmp_path):
    runtime, app, _, _ = build(tmp_path)
    runtime.handle_request(REQUEST_EVENT, {"request_id": "bad id", "action": "run"})
    app.fire_event.assert_not_called()
    runtime.handle_request(
        REQUEST_EVENT, {"request_id": "one", "action": "run", "routine_id": "Bedtime"}
    )
    payload = app.fire_event.call_args.kwargs
    assert payload["request_id"] == "one"
    assert payload["run"]["results"][0]["reason_label"] == "Expected state confirmed"
    assert any(
        call.args[0] == COMPLETED_EVENT for call in app.fire_event.call_args_list
    )
    runtime.handle_request(REQUEST_EVENT, {"request_id": "two", "action": "list"})
    payload = app.fire_event.call_args.kwargs
    assert "results" not in payload["runs"][0]


def test_disabled_triggers_and_initial_state_do_not_run(tmp_path):
    runtime, app, _, _ = build(
        tmp_path, enabled=False, triggers=[{"kind": "event", "event": "bedtime"}]
    )
    assert app.listen_event.call_count == 1
    assert runtime.run("Bedtime")["error"] == "routine_unavailable"
    runtime.config.routines["Bedtime"].enabled = True
    runtime._state_trigger(
        "sensor.activity", "state", None, "asleep", routine_id="Bedtime"
    )
    assert runtime.history == []


def test_bounded_history_keeps_active_runs(tmp_path):
    runtime, _, _, _ = build(tmp_path)
    for _ in range(25):
        runtime.run("Bedtime")
    assert len(runtime.history) == 20


def test_configuration_compiles_and_is_optional(tmp_path):
    from pathlib import Path
    from components.app_config_validator.schema import UserConfig

    example = Path(__file__).parents[1] / "config/user_config.example.yml"
    compiled = compile_config(
        user_path=example, home_assistant_config={"latitude": 50.0, "longitude": 20.0}
    )
    user = compiled["SafetyFunctions"]["user_config"]
    model = UserConfig.model_validate(user)
    assert model.safety_routines.routines["Bedtime"].enabled is False
    source_config = yaml.safe_load(example.read_text(encoding="utf-8"))
    del source_config["user_config"]["installation"]["safety_routines"]
    path = tmp_path / "user.yml"
    path.write_text(yaml.safe_dump(source_config), encoding="utf-8")
    compiled = compile_config(
        user_path=path, home_assistant_config={"latitude": 50.0, "longitude": 20.0}
    )
    assert compiled["SafetyFunctions"]["user_config"]["safety_routines"] == {
        "routines": {}
    }


def test_damaged_history_does_not_report_success(tmp_path):
    runtime, app, store, clock = build(tmp_path)
    runtime.run("Bedtime")
    damaged = copy.deepcopy(runtime.history)
    damaged[0]["results"] = []
    store.save({"version": 1, "runs": damaged})
    restored = SafetyRoutineRuntime(
        app, runtime.config.model_dump(), store, now=lambda: clock[0]
    )
    restored.start()
    assert not restored.storage_available and restored.history == []


def test_repeated_cached_reads_do_not_qualify_window(tmp_path):
    runtime, app, _, clock = build(tmp_path, observation_seconds=5)
    runtime.run("Bedtime")
    clock[0] += timedelta(seconds=5)
    runtime._timer(**app.run_in.call_args.kwargs)
    report = runtime.history[-1]
    assert report["status"] == "unknown"
    assert report["evidence_incomplete"] is True
    assert report["results"][0]["reason"] == "observation_not_advanced"


def test_distinct_observations_qualify_window_and_gap_interrupts(tmp_path):
    runtime, app, _, clock = build(tmp_path, observation_seconds=5)
    runtime.run("Bedtime")
    clock[0] += timedelta(seconds=5)
    app.get_state.return_value = source(observed_at=clock[0].isoformat())
    runtime._timer(**app.run_in.call_args.kwargs)
    assert runtime.history[-1]["status"] == "pass"
    runtime.run("Bedtime")
    clock[0] += timedelta(seconds=11)
    runtime._timer(**app.run_in.call_args.kwargs)
    assert runtime.history[-1]["state"] == "interrupted"


def test_explicit_state_and_event_callbacks_register_and_trigger(tmp_path):
    runtime, app, _, _ = build(
        tmp_path,
        triggers=[
            {"kind": "event", "event": "bedtime"},
            {
                "kind": "state",
                "entity_id": "sensor.activity",
                "from_state": "awake",
                "to_state": "asleep",
            },
        ],
    )
    assert app.listen_event.call_count == 2
    assert app.listen_state.call_args.kwargs["old"] == "awake"
    runtime._event_trigger("bedtime", {}, {"routine_id": "Bedtime"})
    runtime._state_trigger(
        "sensor.activity", "state", "awake", "asleep", routine_id="Bedtime"
    )
    assert len(runtime.history) == 2
    assert [run["source"] for run in runtime.history] == ["event", "state"]


def test_api_invalid_commands_stale_cancel_and_request_conflict(tmp_path):
    runtime, _, _, _ = build(tmp_path, delay_seconds=5)
    run = runtime.run("Bedtime", "one")["run"]
    assert (
        runtime._request({"action": "x", "routine_id": "Bedtime"})["error"]
        == "invalid_action"
    )
    assert (
        runtime._request({"action": "run", "routine_id": "Missing"})["error"]
        == "routine_unavailable"
    )
    assert (
        runtime._request(
            {"action": "report", "routine_id": "Bedtime", "run_id": "missing"}
        )["error"]
        == "run_unavailable"
    )
    assert (
        runtime._request(
            {"action": "cancel", "routine_id": "Bedtime", "run_id": "missing"}
        )["error"]
        == "run_unavailable"
    )
    assert (
        runtime._request({"action": "report", "routine_id": "Bedtime"})["run"]["run_id"]
        == run["run_id"]
    )
    runtime.config.routines["Other"] = runtime.config.routines["Bedtime"].model_copy(
        deep=True
    )
    assert runtime.run("Other", "one")["error"] == "request_conflict"


def test_app_startup_wires_optional_routines_and_persistence(
    mocked_hass_app_with_temp_component,
):
    app, _, _, _, _ = mocked_hass_app_with_temp_component
    app.initialize()
    assert app.safety_routines.started
    assert "safety_routines" in app.self_diagnostics.persistence_stores
    assert app.safety_routines.history == []
    app.terminate()
    assert not app.safety_routines.started


def test_removed_configuration_keeps_historical_reports_readable(tmp_path):
    runtime, _, _, _ = build(tmp_path)
    run = runtime.run("Bedtime")["run"]
    del runtime.config.routines["Bedtime"]
    assert (
        runtime._request(
            {"action": "report", "routine_id": "Bedtime", "run_id": run["run_id"]}
        )["run"]["status"]
        == "pass"
    )
    assert runtime.run("Bedtime")["error"] == "routine_unavailable"


def test_failed_history_load_never_overwrites_unreadable_data(tmp_path):
    runtime, app, store, _ = build(tmp_path)
    store.save({"version": 999, "runs": []})
    restored = SafetyRoutineRuntime(
        app, runtime.config.model_dump(), store, now=lambda: NOW
    )
    restored.start()
    restored.run("Bedtime")
    assert not restored.storage_available
    assert store.load()["version"] == 999
