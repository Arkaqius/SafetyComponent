"""Recovery authority cannot be obtained from cached or ambiguous HA evidence."""

from datetime import datetime, timedelta, timezone

import pytest

from components.safetycomponents.internal_environmental_hazard.observation import (
    ClearAuthority, DetectorBinding, IndoorObservation, Provenance,
)

AT = datetime(2026, 11, 16, tzinfo=timezone.utc)


def binding(hazard="smoke", **overrides):
    profile = dict(version="1", provenance="reviewed fixture", alarm_states=["on"],
                   clear_states=["off"], test_states=["test"], hush_states=["hush"],
                   unavailable_states=["unknown", "unavailable"], clear_duration_seconds=30,
                   authoritative_clear=True, clear_event_contract="ha_state_changed_v1")
    profile.update(overrides)
    return DetectorBinding.from_config("Fixture", dict(entity_id="binary_sensor.fixture",
                                                      hazard=hazard, profile="binary"), profile)


def snapshot(state, seconds):
    stamp = (AT + timedelta(seconds=seconds)).isoformat()
    return dict(state=state, last_changed=stamp, last_updated=stamp)


def event(contract, state, seconds, *, old="on", old_seconds=0, received=None):
    data = dict(entity_id=contract.entity_id, old_state=snapshot(old, old_seconds),
                new_state=snapshot(state, seconds), metadata=dict(origin="LOCAL",
                time_fired=(AT + timedelta(seconds=seconds)).isoformat(), context=dict(id=f"event-{seconds}")))
    receipt = float(seconds if received is None else received)
    return IndoorObservation.event(contract, data, session="session", received=receipt, received_at=AT + timedelta(seconds=receipt))


def authority(contract):
    owner = ClearAuthority(contract, "session")
    owner.observe(event(contract, "on", 0, old="off", old_seconds=-1), "incident")
    return owner


@pytest.mark.parametrize("hazard", ["smoke", "flammable_gas", "carbon_monoxide", "water_leak"])
def test_full_new_interval_and_exact_incident_are_required(hazard):
    contract = binding(hazard)
    owner = authority(contract)
    candidate = owner.observe(event(contract, "off", 1), "incident")
    assert candidate is not None
    readback = IndoorObservation.snapshot(contract, snapshot("off", 1), provenance=Provenance.READBACK,
                                          session="session", received=31)
    assert not owner.eligible(candidate, "incident", 30.999, readback)
    assert owner.eligible(candidate, "incident", 31, readback)
    assert not owner.eligible(candidate, "other", 31, readback)
    assert readback.producer_epoch is readback.producer_sequence is readback.producer_time is None


@pytest.mark.parametrize("provenance", [Provenance.STARTUP_SNAPSHOT, Provenance.READBACK, Provenance.RESTORED_CHECKPOINT])
def test_historical_off_never_starts_clear(provenance):
    contract = binding()
    owner = authority(contract)
    observation = IndoorObservation.snapshot(contract, snapshot("off", -86400), provenance=provenance,
                                             session="session", received=1)
    assert owner.observe(observation, "incident") is None


@pytest.mark.parametrize("state", ["unknown", "unavailable", "test", "hush", "unrecognized", "on"])
def test_interruption_invalidates_old_token(state):
    contract = binding()
    owner = authority(contract)
    candidate = owner.observe(event(contract, "off", 1), "incident")
    owner.observe(event(contract, state, 2, old="off", old_seconds=1), "incident")
    assert owner.candidate is None
    readback = IndoorObservation.snapshot(contract, snapshot("off", 1), provenance=Provenance.READBACK,
                                          session="session", received=31)
    assert not owner.eligible(candidate, "incident", 31, readback)


@pytest.mark.parametrize("overrides", [dict(authoritative_clear=False), dict(clear_event_contract="unverified")])
def test_unreviewed_profile_retains_positive_alarm_without_clear_authority(overrides):
    contract = binding(**overrides)
    owner = authority(contract)
    assert owner.last_alarm is not None
    assert owner.observe(event(contract, "off", 1), "incident") is None


def test_unknown_to_clear_and_same_state_events_cannot_create_candidate():
    contract = binding()
    owner = authority(contract)
    owner.observe(event(contract, "unknown", 1), "incident")
    assert owner.observe(event(contract, "off", 2, old="unknown", old_seconds=1), "incident") is None
    assert owner.observe(event(contract, "off", 2, old="off", old_seconds=2), "incident") is None


def test_reconnect_and_reordered_clear_discard_source_authority():
    contract = binding()
    owner = authority(contract)
    owner.observe(event(contract, "off", 1), "incident")
    owner.new_session("replacement")
    assert owner.candidate is owner.last_alarm is None
    assert owner.observe(event(contract, "off", 2), "incident") is None
    owner = authority(contract)
    owner.observe(event(contract, "on", 20, old="off", old_seconds=1), "incident")
    assert owner.observe(event(contract, "off", 1), "incident") is None


def test_attribute_update_preserves_but_does_not_renew_existing_interval():
    contract = binding()
    owner = authority(contract)
    first = event(contract, "off", 1)
    candidate = owner.observe(first, "incident")
    assert owner.observe(first, "incident") is candidate
    update = event(contract, "off", 1, old="off", old_seconds=1, received=20)
    assert owner.observe(update, "incident") is candidate
    assert candidate.deadline_monotonic == 31


def test_unordered_positive_cannot_lower_alarm_watermark():
    contract = binding()
    owner = authority(contract)
    owner.observe(event(contract, "on", 20, old="off", old_seconds=1), "incident")
    owner.observe(event(contract, "on", 0, old="off", old_seconds=-1, received=21), "incident")
    assert owner.last_alarm.ha_changed_at == AT + timedelta(seconds=20)
    assert owner.observe(event(contract, "off", 1, received=22), "incident") is None


def test_future_clear_metadata_never_starts_or_completes_recovery():
    contract = binding()
    owner = authority(contract)
    assert owner.observe(event(contract, "off", 86400, received=1), "incident") is None
    owner = authority(contract)
    candidate = owner.observe(event(contract, "off", 1), "incident")
    raw = snapshot("off", 1)
    raw["last_updated"] = (AT + timedelta(days=1)).isoformat()
    readback = IndoorObservation.snapshot(contract, raw, provenance=Provenance.READBACK, session="session",
                                          received=31, received_at=AT + timedelta(seconds=31))
    assert not owner.eligible(candidate, "incident", 31, readback)
