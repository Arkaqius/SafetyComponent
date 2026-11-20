"""Exact durable authorization and current policy at queued command handoff."""

from unittest.mock import Mock

import pytest

from components.core.service_dispatcher import Lane, ProcessLeaseRegistry, ResourceSpec, ServiceDispatcher
from components.core.snapshot_writer import SnapshotWriter
from components.core.types_common import FaultState, RecoveryAction, RecoveryActionState, RecoveryResult
from components.recovery_manager.recovery_manager import RecoveryManager
from components.recovery_manager.state_store import InMemoryRecoveryStateStore
from safety_lifecycle_support import CallbackServiceAdapter, ControlledExecutor, LifecycleHass


def build_recovery(result=None):
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
    store = InMemoryRecoveryStateStore()
    manager = RecoveryManager(
        app, faults, {symptom.name: action}, Mock(), Mock(), Mock(), state_store=store,
        dispatcher=broker, snapshot_writer=SnapshotWriter(executor),
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
