"""Exact durable authorization and current policy at queued command handoff."""

import sqlite3
from contextlib import closing
from unittest.mock import Mock

import pytest

from components.core.event_bus import EventBus
from components.core.self_diagnostics import SelfDiagnosticsComponent
from components.core.service_dispatcher import Lane, ProcessLeaseRegistry, ResourceSpec, ServiceDispatcher
from components.core.snapshot_writer import SnapshotWriter
from components.core.sqlite_state_store import SqliteStateDatabase
from components.core.types_common import FaultState, RecoveryAction, RecoveryActionState, RecoveryResult
from components.recovery_manager.recovery_manager import RecoveryManager
from components.recovery_manager.state_store import InMemoryRecoveryStateStore
from components.safety_routines.runtime import SafetyRoutineRuntime
from safety_lifecycle_support import CallbackServiceAdapter, ControlledExecutor, LifecycleHass


def build_recovery(result=None, *, store=None, diagnostics_observer=None):
    app, transport, executor = LifecycleHass(), CallbackServiceAdapter(), ControlledExecutor()
    app.call_service = transport.call_service
    app.get_state = Mock(return_value="on")
    broker = ServiceDispatcher(
        app, [ResourceSpec("cover.fixture", Lane.RECOVERY, frozenset({"cover/close_cover"}))],
        clock=app.clock, registry=ProcessLeaseRegistry(),
    )
    broker.start()
    symptom = Mock(name="fixture")
    symptom.name, symptom.sm_name, symptom.state = "FixtureOpening", "fixture", FaultState.SET
    result = result or RecoveryResult(
        {"binary_sensor.fixture": "off"}, {"cover.fixture": "closed"}, ["Close opening"],
        execution_policy="user_confirmed", completion_condition="entity_state",
    )
    action = RecoveryAction("CloseFixture", {}, Mock(return_value=result))
    faults = Mock()
    faults.symptoms, faults.faults = {symptom.name: symptom}, {}
    fault = Mock()
    fault.name = "FixtureFault"
    fault.evaluation.active = True
    fault.evaluation.shadowed_by = ()
    faults.found_mapped_fault.return_value = fault
    faults.response_identity.return_value = ("fixture-runtime", "fixture-incident", 1)
    if store is None:
        store = InMemoryRecoveryStateStore()
    manager = RecoveryManager(
        app, faults, {symptom.name: action}, Mock(), Mock(), Mock(), state_store=store,
        dispatcher=broker, snapshot_writer=SnapshotWriter(executor),
        diagnostics_observer=diagnostics_observer,
    )
    manager._is_dry_test_failed = Mock(return_value=False)
    manager._isRecoveryConflict = Mock(return_value=False)
    manager.start()
    manager._execute_recovery(symptom, result, "fixture-tag")
    proposal = manager._proposals[symptom.name]
    if result.execution_policy == "user_confirmed":
        token = proposal["confirmation_token"]
        manager.handle_recovery_confirmation("safety_recovery_confirm", {
            "proposal_id": symptom.name, "confirmation_token": token,
        })
    return manager, broker, app, transport, executor, store, symptom, action


def acknowledge_authorization(manager, executor):
    # The initial proposal and the consumed permission are separate snapshots.
    executor.finish(0)
    manager._drain_writes()
    executor.finish(1)
    manager._drain_writes()


def test_command_waits_for_exact_consumed_permission_snapshot_and_owner_drain() -> None:
    manager, broker, _, transport, executor, store, symptom, _ = build_recovery()
    assert len(executor.jobs) == 1 and not transport.calls
    executor.finish(0)
    manager._drain_writes()
    broker.tick()
    assert not transport.calls
    assert store.load()["proposals"][0]["status"] == "AWAITING_CONFIRMATION"
    executor.finish(1)
    assert not transport.calls
    assert store.load()["proposals"][0]["status"] == "EXECUTING"
    assert not store.load()["proposals"][0].get("confirmation_token")
    manager._drain_writes()
    assert not transport.calls
    broker.tick()
    assert len(transport.calls) == 1 and transport.calls[0][0] == "cover/close_cover"
    transport.complete(0, {"success": True})
    broker.tick()
    assert manager._proposals[symptom.name]["status"] == RecoveryActionState.EXECUTING.name


@pytest.mark.parametrize("change", ["restriction", "clear", "expired", "resource", "postcondition", "stop"])
def test_queued_command_rechecks_current_policy_before_handoff(change) -> None:
    manager, broker, app, transport, executor, _, symptom, action = build_recovery()
    acknowledge_authorization(manager, executor)
    if change == "restriction":
        manager.degradation = Mock()
        manager.degradation.recovery_allowed.return_value = False
    elif change == "clear":
        symptom.state = FaultState.CLEARED
    elif change == "expired":
        manager._pending_async_commands[symptom.name]["authorization_expires"] = 0
    elif change == "resource":
        action.rec_fun.return_value = action.rec_fun.return_value._replace(changed_actuators={"cover.changed": "closed"})
    elif change == "postcondition":
        app.get_state.return_value = "off"
    else:
        manager.stop()
        manager.start()
    broker.tick()
    assert not transport.calls


def test_failed_authorization_write_denies_command_without_consuming_new_permission() -> None:
    manager, broker, _, transport, executor, _, symptom, _ = build_recovery()
    # Replace the exact captured save adapter for the consumed-permission write.
    # A fresh current snapshot with the failing adapter coalesces that pending write.
    manager.state_store.save = Mock(side_effect=OSError("fixture failure"))
    manager._persist_state()
    acknowledge_authorization(manager, executor)
    broker.tick()
    assert not transport.calls and not manager._storage_available
    assert manager._proposals[symptom.name]["status"] == RecoveryActionState.FAILED.name
    assert not manager._proposals[symptom.name]["confirmation_token"]


def test_superseded_write_failure_is_logged_without_overriding_durable_authorization() -> None:
    store = InMemoryRecoveryStateStore()
    save = store.save
    attempts = 0

    def fail_initial_save(snapshot):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("fixture write failure")
        save(snapshot)

    store.save = fail_initial_save
    observer = Mock()
    manager, broker, app, transport, executor, _, _, _ = build_recovery(
        store=store, diagnostics_observer=observer,
    )
    executor.finish(0)
    executor.finish(1)
    assert not transport.calls

    manager._drain_writes()
    assert manager._storage_available
    assert store.load()["proposals"][0]["status"] == "EXECUTING"
    observer.assert_called_with("persistence", False, detail="recovery_state", operation="save")
    assert not any(call.args[1] for call in observer.call_args_list)
    assert any(
        "superseded snapshot write failed (OSError)" in message
        for level, message in app.logs if level == "ERROR"
    )
    broker.tick()
    assert len(transport.calls) == 1 and transport.calls[0][0] == "cover/close_cover"


def test_shared_sqlite_lock_preserves_history_and_denies_unpersisted_recovery(tmp_path) -> None:
    database = SqliteStateDatabase(tmp_path / "safety_state.sqlite3")
    recovery_store = database.record_store("recovery_state", max_bytes=1024 * 1024)
    routine_store = database.record_store("safety_routines", max_bytes=1024 * 1024)
    diagnostics = SelfDiagnosticsComponent(
        Mock(), Mock(), EventBus(), Mock(), {},
        persistence_stores=frozenset({"recovery_state", "safety_routines"}),
    )
    observe = diagnostics.record_app_cause
    manager, broker, app, transport, executor, _, symptom, _ = build_recovery(
        store=recovery_store, diagnostics_observer=observe,
    )
    routines = SafetyRoutineRuntime(app, {}, routine_store, diagnostics_observer=observe)
    routines.start()
    previous_history = routine_store.load()
    executor.finish(0)
    manager._drain_writes()
    previous_recovery = recovery_store.load()
    assert previous_recovery["proposals"][0]["status"] == "AWAITING_CONFIRMATION"
    routines.history.append({"state": "interrupted"})

    with closing(sqlite3.connect(database.path)) as lock, lock:
        lock.execute("BEGIN IMMEDIATE")
        routines._persist()
        executor.finish(1)
        manager._drain_writes()
        broker.tick()
        assert routine_store.load() == previous_history
        assert recovery_store.load() == previous_recovery
        assert not transport.calls and not manager._storage_available
        assert manager._proposals[symptom.name]["status"] == "FAILED"
        errors = [message for level, message in app.logs if level == "ERROR"]
        assert any("routine history" in message and "SQLITE_BUSY" in message for message in errors)
        assert any("recovery state" in message and "SQLITE_BUSY" in message for message in errors)

    operations = diagnostics._persistence_operations
    assert operations["safety_routines"]["write"] is True
    assert operations["recovery_state"]["save"] is True
    observe("persistence", True, detail="recovery_state", operation="load")
    # The failure outcome can now be written, but cannot replay the command.
    executor.finish(2)
    manager._drain_writes()
    broker.tick()
    assert not transport.calls
    assert recovery_store.load()["proposals"][0]["status"] == "FAILED"
    assert operations["recovery_state"] == {"load": True, "save": False}
    assert operations["safety_routines"]["write"] is True


def test_rejected_snapshot_keeps_save_fault_despite_older_success(monkeypatch) -> None:
    manager, broker, app, transport, executor, _, _, _ = build_recovery()
    manager.diagnostics_observer = Mock()
    monkeypatch.setattr(manager._writer, "enqueue", Mock(return_value=False))
    assert not manager._persist_state()
    executor.finish(0)
    manager._drain_writes()
    broker.tick()
    assert not transport.calls and not manager._storage_available
    manager.diagnostics_observer.assert_called_with(
        "persistence", True, detail="recovery_state", operation="save",
    )
    errors = [message for level, message in app.logs if level == "ERROR"]
    assert any("recovery state" in message and "snapshot admission rejected" in message for message in errors)


@pytest.mark.parametrize(
    "restore", ["locked", "invalid_snapshot", "proposals_mapping", "proposal_value", "not_started"]
)
def test_missing_recovery_restore_preserves_existing_sqlite_state_on_stop(tmp_path, restore) -> None:
    database = SqliteStateDatabase(tmp_path / "safety_state.sqlite3")
    store = database.record_store("recovery_state", max_bytes=4096)
    snapshot = {
        "version": 1,
        "recent_outcomes": [{
            "proposal_id": "fixture", "action_name": "Inspect", "outcome": "completed",
            "recorded_at": "2026-01-01T00:00:00Z",
        }],
        "command_failures": [],
        "proposals": [],
    }
    if restore == "invalid_snapshot":
        snapshot["command_failures"] = [{"symptom_id": "fixture"}]
    elif restore == "proposals_mapping":
        snapshot["proposals"] = {"fixture": {"status": "FAILED"}}
    elif restore == "proposal_value":
        snapshot["proposals"] = ["fixture"]
    store.save(snapshot)
    app, executor = LifecycleHass(), ControlledExecutor()
    observer = Mock()
    manager = RecoveryManager(
        app, Mock(), {}, Mock(), Mock(), Mock(), state_store=store,
        diagnostics_observer=observer, snapshot_writer=SnapshotWriter(executor),
    )
    assert not manager._persist_state()
    if restore != "not_started":
        with closing(sqlite3.connect(database.path)) as lock, lock:
            if restore == "locked":
                lock.execute("PRAGMA locking_mode = EXCLUSIVE")
                lock.execute("BEGIN EXCLUSIVE")
            manager.start()

        assert manager.failed_recovery_commands() is None
        assert not manager._storage_available
        observer.assert_called_once_with("persistence", True, detail="recovery_state", operation="load")
        assert not manager._persist_state()
    manager.stop()

    assert not executor.jobs
    assert store.load() == snapshot


def test_new_recovery_owner_cannot_overwrite_a_retired_owners_inflight_write(tmp_path) -> None:
    database = SqliteStateDatabase(tmp_path / "safety_state.sqlite3")
    store = database.record_store("recovery_state", max_bytes=4096)
    store.save({"version": 1, "proposals": []})
    executor = ControlledExecutor()
    writer = SnapshotWriter(executor)
    writer.claim("retired")
    final_state = {"version": 1, "proposals": [{"proposal_id": "retained"}]}
    assert writer.enqueue("retired", 1, final_state, store.save)
    manager = RecoveryManager(
        LifecycleHass(), Mock(), {}, Mock(), Mock(), Mock(),
        state_store=store, snapshot_writer=writer,
    )
    manager.start()
    executor.finish(0)
    assert not manager._persist_state()
    manager.stop()
    assert len(executor.jobs) == 1
    assert store.load() == final_state


def test_unknown_command_is_never_retried_and_old_completion_cannot_replay_it() -> None:
    manager, broker, app, transport, executor, _, symptom, action = build_recovery()
    acknowledge_authorization(manager, executor)
    broker.tick()
    app.clock.advance(121)
    broker.tick()
    assert len(transport.calls) == 1 and broker.registry.quarantined_count == 1
    assert manager._proposals[symptom.name]["status"] == RecoveryActionState.FAILED.name
    for _ in range(3):
        manager._execute_recovery(symptom, action.rec_fun.return_value, "fixture-tag")
        manager._drain_writes()
        broker.tick()
    assert len(transport.calls) == 1
    transport.complete(0, {"success": True})
    broker.tick()
    assert len(transport.calls) == 1
    assert manager._proposals[symptom.name]["status"] == RecoveryActionState.FAILED.name


def test_reentrant_policy_stop_cannot_handoff_an_old_command() -> None:
    manager, broker, _, transport, executor, _, _, _ = build_recovery()
    acknowledge_authorization(manager, executor)
    evaluator = Mock()

    def stop_owner(_result):
        manager.stop()
        return Mock(allowed=True)

    evaluator.evaluate_recovery_policy.side_effect = stop_owner
    manager.register_policy_evaluator(evaluator)
    broker.tick()
    assert not transport.calls and not manager.scope.eligible


def test_new_authoritative_incident_denies_old_queued_permission() -> None:
    manager, broker, _, transport, executor, _, _, _ = build_recovery()
    acknowledge_authorization(manager, executor)
    manager.fm.response_identity.return_value = ("fixture-runtime", "new-incident", 2)
    broker.tick()
    assert not transport.calls


def test_handoff_replaces_consent_timer_with_full_effect_interval() -> None:
    manager, broker, app, transport, executor, _, symptom, _ = build_recovery()
    acknowledge_authorization(manager, executor)
    manager._schedule_recovery_deadline(symptom.name, 1)
    old = manager._recovery_deadline_handles[symptom.name]
    broker.tick()
    assert len(transport.calls) == 1
    current = manager._recovery_deadline_handles[symptom.name]
    assert current != old and app.handles[current][2] == app.clock() + 120
    app.clock.advance(1)
    app.deliver(old)
    assert manager._proposals[symptom.name]["status"] == RecoveryActionState.EXECUTING.name


@pytest.mark.parametrize("failed", [False, True])
def test_operator_report_confirmation_waits_for_exact_durable_acknowledgement(failed) -> None:
    result = RecoveryResult({}, {}, ["Inspect fixture"], execution_policy="manual",
                            completion_condition="operator_report", manual_report_allowed=True)
    manager, broker, _, transport, executor, _, symptom, _ = build_recovery(result)
    proposal = manager._proposals[symptom.name]
    if failed:
        manager.state_store.save = Mock(side_effect=OSError("fictional storage failure"))
    manager.handle_manual_work_report("safety_recovery_report", {
        "proposal_id": symptom.name, "proposal_instance_id": proposal["proposal_instance_id"],
        "report_token": proposal["report_token"], "metadata": {"context": {"user_id": "fixture-user"}},
    })
    assert manager._public_proposal(proposal)["status"] == RecoveryActionState.TO_PERFORM.name
    acknowledge_authorization(manager, executor)
    current = manager._proposals[symptom.name]
    expected = RecoveryActionState.TO_PERFORM if failed else RecoveryActionState.CONFIRMED
    assert manager._public_proposal(current)["status"] == expected.name
    assert bool(manager._recent_outcomes) is not failed
    broker.tick()
    assert not transport.calls
