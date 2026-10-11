"""Restart qualification must preserve live hazards and uncertain evidence."""

from components.core.event_bus import EventBus
from components.core.startup_grace import StartupGrace
from components.core.types_common import FaultState
from components.safetycomponents.entity_monitor.schema import EntityMonitorCalibration


def gate(seconds=600):
    """Create a deterministic startup dispatcher and capture delivered evidence."""
    now = [0.0]
    bus = EventBus()
    grace = StartupGrace(
        bus, {"input", "provider", "battery"}, seconds, clock=lambda: now[0]
    )
    delivered, unavailable = [], []
    bus.subscribe("qualified_symptom", lambda **data: delivered.append(data))
    bus.subscribe(
        "qualified_evaluation_unavailable", lambda **data: unavailable.append(data)
    )
    return now, bus, grace, delivered, unavailable


def test_validated_default_is_ten_minutes_and_explicit_zero_remains_supported():
    assert EntityMonitorCalibration().startup_grace_seconds == 600
    assert EntityMonitorCalibration(startup_grace_seconds=0).startup_grace_seconds == 0


def test_transient_failures_do_not_activate_or_replay_after_recovery():
    now, bus, grace, delivered, unavailable = gate()
    bus.publish("symptom", symptom_id="input", state=FaultState.SET)
    now[0] = 599
    bus.publish("symptom", symptom_id="input", state=FaultState.CLEARED)
    assert delivered == []
    assert unavailable == [{"symptom_id": "input"}] * 2
    assert not grace.finish()
    now[0] = 600
    assert grace.finish()
    assert delivered == [{"symptom_id": "input", "state": FaultState.CLEARED}]
    assert not grace.finish()
    assert grace.snapshot()["phase"] == "complete"


def test_still_failed_diagnostic_activates_at_deadline_and_future_events_are_immediate():
    now, bus, grace, delivered, _ = gate()
    context = {"reason": "missing_report"}
    bus.publish(
        "symptom", symptom_id="provider", state=FaultState.SET, additional_info=context
    )
    context["reason"] = "mutated"
    now[0] = 600
    grace.finish()
    assert delivered[0]["additional_info"] == {"reason": "missing_report"}
    bus.publish("symptom", symptom_id="provider", state=FaultState.CLEARED)
    assert [row["state"] for row in delivered] == [FaultState.SET, FaultState.CLEARED]


def test_unavailable_or_unseen_evidence_never_becomes_positive_clear_at_expiry():
    now, bus, grace, delivered, _ = gate()
    bus.publish("symptom", symptom_id="provider", state=FaultState.CLEARED)
    bus.publish("evaluation_unavailable", symptom_id="provider")
    bus.publish("symptom", symptom_id="battery", state=FaultState.SET)
    bus.publish("evaluation_unavailable", symptom_id="battery")
    now[0] = 600
    grace.finish()
    assert delivered == []


def test_hazard_and_application_failure_bypass_diagnostic_grace():
    _, bus, grace, delivered, _ = gate()
    for symptom in (
        "gas",
        "carbon_monoxide",
        "water_leak",
        "persistence",
        "publication",
    ):
        bus.publish("symptom", symptom_id=symptom, state=FaultState.SET)
    assert len(delivered) == 5
    assert all(row["state"] == FaultState.SET for row in delivered)
    assert grace.snapshot()["remaining_seconds"] == 600


def test_zero_grace_and_new_initialization_do_not_reuse_old_startup_phase():
    _, bus, grace, delivered, _ = gate(seconds=0)
    bus.publish("symptom", symptom_id="input", state=FaultState.SET)
    assert len(delivered) == 1
    assert grace.snapshot()["phase"] == "complete"
    _, _, restarted, _, _ = gate()
    assert restarted.snapshot()["phase"] == "settling"
    assert restarted.snapshot()["remaining_seconds"] == 600


def test_observation_arriving_at_deadline_supersedes_cached_failure_before_flush():
    now, bus, _, delivered, _ = gate()
    bus.publish("symptom", symptom_id="input", state=FaultState.SET)
    now[0] = 600
    bus.publish("symptom", symptom_id="input", state=FaultState.CLEARED)
    assert [row["state"] for row in delivered] == [FaultState.CLEARED]
