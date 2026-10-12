"""Regressions for manual work, independent causes, and stale command consent."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from components.core.localization import Localizer
from components.core.types_common import FaultState, RecoveryAction, RecoveryResult
from components.recovery_manager.manual_actions import manual_action
from components.recovery_manager.recovery_manager import RecoveryManager
from components.recovery_manager.state_store import InMemoryRecoveryStateStore
from components.recovery_manager.schema import RecoveryTiming


def make_manager(*, contact: bool = False):
    """Keep real proposal validation while isolating unrelated hazard simulation."""

    app = MagicMock()
    app.localizer = Localizer({"language": "pl"})
    states = {"binary_sensor.door": "on"}
    app.get_state.side_effect = lambda entity_id: states.get(entity_id, "unknown")
    symptom = SimpleNamespace(
        name="DoorOpen" if contact else "InputUnavailable",
        sm_name="sm_test",
        state=FaultState.SET,
        parameters={"check_key": "availability"},
        module=SimpleNamespace(),
    )
    action = manual_action(
        "CloseDoor" if contact else "InspectInput",
        subject="Garaż",
        instruction_key="recovery.manual_close" if contact else "recovery.inspect_input",
        result_key="recovery.result_closed" if contact else "recovery.result_input",
        entity_id="binary_sensor.door",
        closed_contact=contact,
    )
    faults = MagicMock()
    faults.symptoms = {symptom.name: symptom}
    faults.found_mapped_fault.return_value = SimpleNamespace(name="TestFault")
    manager = RecoveryManager(app, faults, {symptom.name: action}, Mock(), Mock(), Mock())
    manager._is_dry_test_failed = Mock(return_value=False)
    manager._isRecoveryConflict = Mock(return_value=False)
    return manager, symptom, app, states


@pytest.mark.parametrize("policy", ["manual", "unrecognized"])
def test_shared_boundary_never_dispatches_manual_or_unknown_policy(policy):
    manager, symptom, app, _ = make_manager()
    result = RecoveryResult({}, {"cover.gate": "closed"}, ["Close"], execution_policy=policy)
    manager.recovery_actions[symptom.name].rec_fun = Mock(return_value=result)

    manager.recovery(symptom, "fault-tag")
    with pytest.raises(ValueError, match="execution contract"):
        manager._execute_recovery(symptom, result, "fault-tag")

    app.call_service.assert_not_called()
    assert not manager._proposals


def test_manual_repair_has_no_fake_sensor_dependency_or_command_deadline():
    manager, symptom, app, _ = make_manager()
    manager.recovery(symptom, "fault-tag")
    proposal = manager._proposals[symptom.name]

    assert proposal["execution_policy"] == "manual"
    assert proposal["expires_at"] is None
    assert proposal["expected_postconditions"] == {}
    assert proposal["expected_result"]
    assert "Garaż" in proposal["instruction"]
    app.listen_state.assert_not_called()
    app.run_in.assert_not_called()
    app.call_service.assert_not_called()
    assert symptom.state == FaultState.SET


@pytest.mark.parametrize("new_state", ["off", "closed", "false", "0"])
def test_door_completion_requires_current_closed_evidence_and_preserves_fault(new_state):
    manager, symptom, app, states = make_manager(contact=True)
    manager.recovery(symptom, "fault-tag")
    for invalid_state in ("unknown", "unavailable", "opening", "on"):
        states["binary_sensor.door"] = invalid_state
        manager._recovery_performed(None, None, None, new_state,
                                    symptom_name=symptom.name,
                                    confirmation_entity="binary_sensor.door", expected_state="off")
        assert symptom.name in manager._proposals
    states["binary_sensor.door"] = new_state
    manager._recovery_performed(None, None, None, new_state,
                                symptom_name=symptom.name,
                                confirmation_entity="binary_sensor.door", expected_state="off")

    assert symptom.name not in manager._proposals
    assert manager._recent_outcomes[-1]["outcome"] == "completed"
    assert symptom.state == FaultState.SET
    app.call_service.assert_not_called()


def test_conditional_door_clear_with_open_contact_is_withdrawal_not_completion():
    manager, symptom, _, _ = make_manager(contact=True)
    manager.recovery(symptom, "fault-tag")
    symptom.state = FaultState.CLEARED
    manager.recovery(symptom, "fault-tag")

    assert not manager._proposals
    assert manager._recent_outcomes[-1]["outcome"] == "withdrawn"
    assert not manager._recovery_confirmation_handles


def test_repair_completion_cannot_clear_another_contributor():
    manager, symptom, app, _ = make_manager()
    other = SimpleNamespace(**vars(symptom))
    other.name = "InputStale"
    manager.fm.symptoms[other.name] = other
    manager.recovery_actions[other.name] = manager.recovery_actions[symptom.name]
    manager.recovery(symptom, "fault-tag")
    manager.recovery(other, "fault-tag")
    manager.recovery(symptom, "fault-tag")  # Repeated evidence is not a new action.
    assert len(manager._proposals) == 2
    symptom.state = FaultState.CLEARED
    manager.recovery(symptom, "fault-tag")

    assert set(manager._proposals) == {other.name}
    assert manager._recent_outcomes[-1]["outcome"] == "completed"
    assert other.state == FaultState.SET
    app.call_service.assert_not_called()


@pytest.mark.parametrize("replacement", [None, RecoveryResult({}, {"switch.device": "off"}, [], execution_policy="manual")])
def test_empty_or_rejected_replacement_withdraws_stale_guidance(replacement):
    manager, symptom, app, _ = make_manager(contact=True)
    manager.recovery(symptom, "fault-tag")
    manager.recovery_actions[symptom.name].rec_fun = Mock(return_value=replacement)
    manager.recovery(symptom, "fault-tag")

    assert not manager._proposals
    assert not manager._pending_recovery_confirmations
    assert not manager._recovery_confirmation_handles
    manager.nm.remove_recovery_guidance.assert_called_with(symptom.name, "fault-tag")
    assert manager._recent_outcomes[-1]["outcome"] == "withdrawn"
    app.call_service.assert_not_called()


def test_repeated_automatic_proposal_does_not_repeat_command_or_extend_deadline():
    manager, symptom, app, states = make_manager()
    states["binary_sensor.door"] = "on"
    result = RecoveryResult({"binary_sensor.door": "off"}, {"cover.gate": "closed"}, [])
    manager.recovery_actions[symptom.name].rec_fun = Mock(return_value=result)
    app.call_service.return_value = None
    manager.recovery(symptom, "fault-tag")
    proposal = dict(manager._proposals[symptom.name])
    manager.recovery(symptom, "fault-tag")

    app.call_service.assert_called_once_with("cover/close_cover", entity_id="cover.gate")
    app.run_in.assert_called_once()
    assert manager._proposals[symptom.name]["expires_at"] == proposal["expires_at"]
    assert manager._proposals[symptom.name]["proposal_instance_id"] == proposal["proposal_instance_id"]


@pytest.mark.parametrize("replacement", [
    {"changed_sensors": {"binary_sensor.other_door": "off"}},
    {"changed_actuators": {"cover.gate": "open"}},
])
def test_stale_confirmation_with_changed_postcondition_cannot_actuate(replacement):
    manager, symptom, app, _ = make_manager()
    result = RecoveryResult({"binary_sensor.door": "off"}, {"cover.gate": "closed"}, ["Close"],
                            execution_policy="user_confirmed")
    action = RecoveryAction("CloseGate", {}, Mock(return_value=result))
    manager.recovery_actions[symptom.name] = action
    manager.recovery(symptom, "fault-tag")
    token = manager._proposals[symptom.name]["confirmation_token"]
    manager.handle_recovery_confirmation("", {"proposal_id": symptom.name, "confirmation_token": "wrong"})
    assert symptom.name in manager._proposals
    action.rec_fun.return_value = result._replace(**replacement)
    manager.handle_recovery_confirmation("", {"proposal_id": symptom.name, "confirmation_token": token})

    app.call_service.assert_not_called()
    assert not manager._proposals
    assert not manager._recovery_deadline_handles
    assert "confirmation_token" not in manager._recent_outcomes[-1]


def test_restart_restores_outcomes_and_resumes_manual_contact_without_commands():
    manager, symptom, app, states = make_manager(contact=True)
    manager.recovery(symptom, "fault-tag")
    manager._recovery_clear_by_name(symptom.name, reason="superseded")
    manager.recovery(symptom, "fault-tag")
    snapshot = manager.state_store.load()
    manager._proposals = {}
    manager._recent_outcomes = []
    manager._cancel_recovery_confirmation_listeners(symptom.name)
    manager._pending_recovery_confirmations = {}
    manager.state_store = InMemoryRecoveryStateStore(snapshot)
    app.call_service.reset_mock()
    manager._restore_state()
    manager.resume_command_postconditions()

    assert manager._recent_outcomes[-1]["outcome"] == "withdrawn"
    assert symptom.name in manager._pending_recovery_confirmations
    states["binary_sensor.door"] = "off"
    manager._recovery_performed(None, None, None, "off", symptom_name=symptom.name,
                                confirmation_entity="binary_sensor.door", expected_state="off")
    assert manager.state_store.load()["recent_outcomes"][-1]["outcome"] == "completed"
    app.call_service.assert_not_called()


@pytest.mark.parametrize("policy", ["automatic", "user_confirmed"])
def test_restart_keeps_command_targets_without_replaying_or_losing_consent(policy):
    manager, symptom, app, _ = make_manager()
    result = RecoveryResult({"binary_sensor.door": "off"}, {"cover.gate": "closed"}, ["Close"],
                            execution_policy=policy)
    manager.recovery_actions[symptom.name].rec_fun = Mock(return_value=result)
    app.call_service.return_value = None
    manager.recovery(symptom, "fault-tag")
    snapshot = manager.state_store.load()
    manager._proposals = {}
    manager.state_store = InMemoryRecoveryStateStore(snapshot)
    app.call_service.reset_mock()
    manager._restore_state()
    restored = dict(manager._proposals[symptom.name])
    manager.recovery(symptom, "fault-tag")
    app.call_service.assert_not_called()
    assert manager._proposals[symptom.name]["actuator_targets"] == {"cover.gate": "closed"}
    assert manager._proposals[symptom.name]["confirmation_token"] == restored["confirmation_token"]
    if policy == "user_confirmed":
        manager.handle_recovery_confirmation("", {"proposal_id": symptom.name,
                                                   "confirmation_token": restored["confirmation_token"]})
        app.call_service.assert_called_once_with("cover/close_cover", entity_id="cover.gate")


def test_outcomes_are_bounded_and_allowlisted():
    manager, symptom, _, _ = make_manager()
    for _ in range(102):
        manager.recovery(symptom, "fault-tag")
        manager._proposals[symptom.name]["confirmation_token"] = "secret-token"
        manager._proposals[symptom.name]["private_payload"] = "secret-payload"
        manager._recovery_clear_by_name(symptom.name)
    outcomes = manager.state_store.load()["recent_outcomes"]
    assert len(outcomes) == 100
    assert "secret-token" not in str(outcomes)
    assert "secret-payload" not in str(outcomes)


def test_multiple_instructions_share_one_guidance_without_losing_steps():
    manager, symptom, app, _ = make_manager()
    result = RecoveryResult({}, {}, ["Check power.", "Check connection."],
                            execution_policy="manual", completion_condition="owner_clear")
    manager.recovery_actions[symptom.name].rec_fun = Mock(return_value=result)
    manager.recovery(symptom, "fault-tag")

    manager.nm.upsert_recovery_guidance.assert_called_once_with(
        symptom.name, "Check power. Check connection.", "fault-tag")
    app.call_service.assert_not_called()


def test_restart_does_not_extend_consent_deadline_and_resumes_timeout():
    manager, symptom, app, _ = make_manager()
    result = RecoveryResult({"binary_sensor.door": "off"}, {"cover.gate": "closed"}, ["Close"],
                            execution_policy="user_confirmed")
    manager.recovery_actions[symptom.name].rec_fun = Mock(return_value=result)
    manager.recovery(symptom, "fault-tag")
    deadline = manager._proposals[symptom.name]["expires_at"]
    snapshot = manager.state_store.load()
    manager._proposals = {}
    manager.state_store = InMemoryRecoveryStateStore(snapshot)
    manager._restore_state()
    manager.resume_command_postconditions()
    assert manager._proposals[symptom.name]["expires_at"] == deadline
    assert symptom.name in manager._recovery_deadline_handles
    manager._proposals[symptom.name]["expires_at"] = 0
    manager.resume_command_postconditions()
    assert manager._proposals[symptom.name]["status"] == "TIMED_OUT"
    app.call_service.assert_not_called()


def reportable_manager(condition="operator_report"):
    """Create a procedural task or observed repair with authenticated report support."""
    manager, symptom, app, states = make_manager()
    result = RecoveryResult({}, {}, ["Inspect equipment"], execution_policy="manual",
                            completion_condition=condition, manual_report_allowed=True)
    manager.recovery_actions[symptom.name].rec_fun = Mock(return_value=result)
    manager.recovery(symptom, "fault-tag")
    proposal = manager._proposals[symptom.name]
    event = {"proposal_id": symptom.name, "proposal_instance_id": proposal["proposal_instance_id"],
             "report_token": proposal["report_token"], "metadata": {"context": {"user_id": "authenticated-operator"}}}
    return manager, symptom, app, states, event


def test_operator_report_completes_only_task_and_is_persisted_with_private_attribution():
    manager, symptom, app, _, event = reportable_manager()
    manager.handle_manual_work_report("safety_recovery_report", event)
    proposal = manager._proposals[symptom.name]
    assert proposal["status"] == "CONFIRMED"
    assert proposal["report_status"] == "completed"
    assert proposal["report_token"] == ""
    assert proposal["reported_at"] == proposal["evidence_at"]
    assert symptom.state == FaultState.SET
    saved = manager.state_store.load()
    assert saved["recent_outcomes"][-1]["report_user_id"] == "authenticated-operator"
    assert "report_user_id" not in manager._public_proposal(proposal)
    assert "report_token" not in saved["recent_outcomes"][-1]
    app.call_service.assert_not_called()
    manager.handle_manual_work_report("", event)
    manager.recovery(symptom, "fault-tag")
    assert len(manager._recent_outcomes) == 1
    assert manager._proposals[symptom.name]["status"] == "CONFIRMED"


def test_observed_repair_report_keeps_fault_and_waits_for_owner_evidence():
    manager, symptom, app, _, event = reportable_manager("owner_clear")
    manager.handle_manual_work_report("", event)
    assert manager._proposals[symptom.name]["status"] == "TO_PERFORM"
    assert manager._proposals[symptom.name]["report_status"] == "awaiting_evidence"
    assert not manager._recent_outcomes
    assert symptom.state == FaultState.SET
    symptom.state = FaultState.CLEARED
    manager.recovery(symptom, "fault-tag")
    assert manager._recent_outcomes[-1]["outcome"] == "completed"
    assert manager._recent_outcomes[-1]["evidence_source"] != "operator_report"
    app.call_service.assert_not_called()


@pytest.mark.parametrize("mutation", [
    {"metadata": {}}, {"metadata": {"context": {"user_id": None}}},
    {"user_id": "forged"}, {"reported_at": "2000-01-01T00:00:00Z"},
    {"report_token": "wrong"}, {"proposal_instance_id": "older-incident"},
])
def test_manual_report_rejects_unauthenticated_forged_and_stale_requests(mutation):
    manager, symptom, app, _, event = reportable_manager()
    event.update(mutation)
    manager.handle_manual_work_report("", event)
    assert manager._proposals[symptom.name]["status"] == "TO_PERFORM"
    assert "reported_at" not in manager._proposals[symptom.name]
    assert not manager._recent_outcomes
    app.call_service.assert_not_called()


def test_advisory_has_no_report_or_completion_on_owner_clear():
    manager, symptom, app, _ = make_manager()
    manager.recovery_actions[symptom.name].rec_fun = Mock(return_value=RecoveryResult(
        {}, {}, ["Leave the building"], execution_policy="manual", completion_condition="advisory"))
    manager.recovery(symptom, "fault-tag")
    assert manager._proposals[symptom.name]["report_token"] == ""
    symptom.state = FaultState.CLEARED
    manager.recovery(symptom, "fault-tag")
    assert manager._recent_outcomes[-1]["outcome"] == "withdrawn"
    app.call_service.assert_not_called()


def test_restart_rotates_unreported_capability_and_preserves_reported_work():
    manager, symptom, app, _, event = reportable_manager("owner_clear")
    snapshot = manager.state_store.load()
    manager.state_store = InMemoryRecoveryStateStore(snapshot)
    manager._proposals = {}
    manager._restore_state()
    assert manager._proposals[symptom.name]["report_token"] != event["report_token"]
    manager.handle_manual_work_report("", event)
    assert "reported_at" not in manager._proposals[symptom.name]
    event["report_token"] = manager._proposals[symptom.name]["report_token"]
    manager.handle_manual_work_report("", event)
    manager._proposals = {}
    manager._restore_state()
    assert manager._proposals[symptom.name]["report_token"] == ""
    assert manager._proposals[symptom.name]["report_status"] == "awaiting_evidence"
    app.call_service.assert_not_called()


def test_consent_and_effect_deadlines_are_distinct_and_manual_deadline_optional():
    manager, symptom, app, _ = make_manager()
    manager.timing = RecoveryTiming(consent_timeout_seconds=30, effect_timeout_seconds=240)
    result = RecoveryResult({"binary_sensor.door": "off"}, {"cover.gate": "closed"}, [],
                            execution_policy="user_confirmed")
    manager.recovery_actions[symptom.name].rec_fun = Mock(return_value=result)
    manager.recovery(symptom, "fault-tag")
    assert app.run_in.call_args.args[1] == 30
    proposal = manager._proposals[symptom.name]
    consent_deadline = proposal["expires_at"]
    manager.handle_recovery_confirmation("", {"proposal_id": symptom.name,
                                                "confirmation_token": proposal["confirmation_token"]})
    assert app.run_in.call_args.args[1] == 240
    assert manager._proposals[symptom.name]["expires_at"] > consent_deadline + 200


def test_manual_task_deadline_survives_restart_without_becoming_command_consent():
    manager, symptom, app, _, event = reportable_manager()
    result = manager.recovery_actions[symptom.name].rec_fun.return_value._replace(manual_task_timeout_seconds=300)
    manager._recovery_clear_by_name(symptom.name)
    manager.recovery_actions[symptom.name].rec_fun.return_value = result
    manager.recovery(symptom, "fault-tag")
    proposal = manager._proposals[symptom.name]
    deadline = proposal["expires_at"]
    manager._proposals = {}
    manager._restore_state()
    manager.resume_command_postconditions()
    assert manager._proposals[symptom.name]["expires_at"] == deadline
    assert symptom.name in manager._recovery_deadline_handles
    manager._proposals[symptom.name]["expires_at"] = 0
    manager.resume_command_postconditions()
    assert manager._proposals[symptom.name]["status"] == "TIMED_OUT"
    app.call_service.assert_not_called()


def test_indoor_unresolved_evidence_blocks_opening_but_preserves_emergency_advice():
    manager, symptom, app, _ = make_manager()
    hazard = SimpleNamespace(name="InternalCarbonMonoxideDetected", evaluation=SimpleNamespace(
        active=False, status=SimpleNamespace(value="UNEVALUABLE")))
    manager.fm.faults = {hazard.name: hazard}
    result = RecoveryResult({"binary_sensor.door": "on"}, {}, ["Open window"], execution_policy="manual")
    assert not manager._validate_recovery_action(symptom, result)
    assert manager._validation_reasons[symptom.name] == "indoor_hazard_conflict"
    advisory = RecoveryResult({}, {}, ["Leave the building"], execution_policy="manual", completion_condition="advisory")
    assert manager._validate_recovery_action(symptom, advisory)
    app.call_service.assert_not_called()


def test_blocked_consent_reappears_only_after_current_policy_allows_it():
    manager, symptom, app, _ = make_manager()
    result = RecoveryResult({"binary_sensor.door": "off"}, {"cover.gate": "closed"}, [],
                            execution_policy="user_confirmed")
    manager.recovery_actions[symptom.name].rec_fun = Mock(return_value=result)
    policy = Mock()
    policy.evaluate_recovery_policy.return_value = SimpleNamespace(allowed=False, reason="policy_rejected")
    manager.register_policy_evaluator(policy)
    manager.recovery(symptom, "fault-tag")
    blocked = manager._proposals[symptom.name]
    assert blocked["status"] == "DO_NOT_PERFORM"
    assert blocked["confirmation_token"] == ""
    assert blocked["blocked_reason"]
    policy.evaluate_recovery_policy.return_value = SimpleNamespace(allowed=True)
    manager.recovery(symptom, "fault-tag")
    assert manager._proposals[symptom.name]["status"] == "AWAITING_CONFIRMATION"
    assert manager._proposals[symptom.name]["confirmation_token"]
    app.call_service.assert_not_called()


@pytest.mark.parametrize("key", ["consent_timeout_seconds", "effect_timeout_seconds", "manual_task_timeout_seconds"])
def test_explicit_invalid_deadline_does_not_fall_back_to_a_default(key):
    manager, _, _, _ = make_manager()
    with pytest.raises(ValueError):
        manager._stage_timeouts(RecoveryResult({}, {}, [], **{key: 0}))


def test_postcondition_cannot_complete_when_its_current_coverage_is_unavailable():
    manager, symptom, app, states = make_manager(contact=True)
    manager.recovery(symptom, "fault-tag")
    states["binary_sensor.door"] = "off"
    manager.degradation = Mock()
    manager.degradation.recovery_allowed.return_value = False
    assert not manager._all_recovery_postconditions_met(symptom.name)
    manager._recovery_performed(None, None, None, "off", symptom_name=symptom.name,
                                confirmation_entity="binary_sensor.door", expected_state="off")
    assert symptom.name in manager._proposals
    manager.degradation.recovery_allowed.return_value = True
    assert manager._all_recovery_postconditions_met(symptom.name)
    app.call_service.assert_not_called()


def test_unwritable_recovery_store_preserves_hazard_guidance_without_recursion_or_commands():
    manager, symptom, app, _ = make_manager()
    manager.state_store = Mock()
    manager.state_store.save.side_effect = OSError("unavailable storage")
    observer = Mock(side_effect=lambda *_args, **_kwargs: manager._persist_state())
    manager.diagnostics_observer = observer
    manager.recovery(symptom, "fault-tag")
    assert symptom.name in manager._proposals
    assert symptom.state == FaultState.SET
    assert manager._storage_available is False
    assert observer.call_count == 1
    app.call_service.assert_not_called()


def test_report_save_failure_does_not_publish_a_completed_task():
    manager, symptom, app, _, event = reportable_manager()
    manager.state_store = Mock()
    manager.state_store.save.side_effect = OSError("unavailable storage")
    manager.handle_manual_work_report("", event)
    assert manager._proposals[symptom.name]["status"] == "TO_PERFORM"
    assert "reported_at" not in manager._proposals[symptom.name]
    assert not manager._recent_outcomes
    manager.nm.remove_recovery_guidance.assert_not_called()
    app.call_service.assert_not_called()


def test_inactive_higher_priority_fault_cannot_block_current_lower_priority_action():
    manager, symptom, _, _ = make_manager()
    symptom.name = "Forecast"
    direct = SimpleNamespace(name="Direct", state=FaultState.CLEARED, sm_name="sm_direct")
    fault = SimpleNamespace(level=2, evaluation=SimpleNamespace(active=False, latched=False))
    manager.fm.symptoms["Direct"] = direct
    manager.fm.found_mapped_fault.return_value = fault
    assert not manager._check_conflict_with_matching_actions(["Direct"], 3, symptom)
    direct.state = FaultState.SET
    assert manager._check_conflict_with_matching_actions(["Direct"], 3, symptom)
    direct.state = FaultState.CLEARED
    fault.evaluation.active = True
    fault.evaluation.latched = True
    assert manager._check_conflict_with_matching_actions(["Direct"], 3, symptom)
