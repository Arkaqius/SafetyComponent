"""Strict checkpoint, loss-aware migration and durable indoor recovery contracts."""

from copy import deepcopy
import builtins

import pytest

from components.core.snapshot_writer import SnapshotWriter
from components.safetycomponents.internal_environmental_hazard.state_store import (
    InMemoryInternalEnvironmentStateStore, IndoorCheckpoint, IndoorStateOwner,
    commissioned_checkpoint, decode_checkpoint, current_launch_id,
)
from .safety_lifecycle_support import ControlledExecutor
from .test_indoor_clear_authority import AT, binding
from components.safetycomponents.internal_environmental_hazard.observation import ClearCandidate


def owner_fixture():
    store = InMemoryInternalEnvironmentStateStore(commissioned_checkpoint("reviewed-installation", AT))
    executor = ControlledExecutor()
    owner = IndoorStateOwner(store, writer=SnapshotWriter(executor), session="current", launch_receipt=current_launch_id())
    owner.begin()
    executor.finish(0)
    owner.drain()
    return owner, store, executor


def request_clear(owner, record_id, token, eligible):
    record = owner.records[record_id]
    candidate = ClearCandidate(token, record.incident_id, record.binding_fingerprint, "session",
        0.0, 30.0, AT, AT, "context")
    return owner.request_clear(record_id, token, eligible, candidate=candidate)


def test_missing_history_is_not_a_virgin_installation():
    owner = IndoorStateOwner(InMemoryInternalEnvironmentStateStore(), writer=SnapshotWriter(ControlledExecutor()))
    assert owner.history_unknown and owner.gas_inhibited
    assert not owner.recovery_ready
    known, _, _ = owner_fixture()
    assert not known.history_unknown and not known.gas_inhibited and known.recovery_ready


def test_successful_write_does_not_mislabel_unverified_history_as_storage_failure():
    executor = ControlledExecutor()
    owner = IndoorStateOwner(InMemoryInternalEnvironmentStateStore(), writer=SnapshotWriter(executor))
    owner.begin()
    executor.finish(0)
    owner.drain()
    assert owner.history_unknown and owner.gas_inhibited
    assert owner.marker_durable and owner.durable_revision == owner.revision
    assert owner.persistence_error is None and owner.recovery_ready


@pytest.mark.parametrize("field,value", [("generation", True), ("clean", "true"), ("version", 2.0), ("unexpected", 1)])
def test_strict_envelope_rejects_coercion_and_extra_fields(field, value):
    raw = commissioned_checkpoint("receipt", AT)
    raw[field] = value
    with pytest.raises(ValueError):
        decode_checkpoint(raw)


def test_legacy_orphan_never_invents_hazard_binding_or_incident():
    old = dict(version=1, updated_at=AT.isoformat(), detectors={"Removed": dict(
        alarm_active=True, health_active=False, gas_switching_inhibited=True,
        last_authoritative_clear_at=AT.isoformat())})
    checkpoint = decode_checkpoint(old)
    record = checkpoint.records[0]
    assert record.kind == "legacy_unattributed" and record.alarm_active and record.gas_switching_inhibited
    assert record.detector_key == "Removed"
    assert record.incident_id is record.hazard is record.binding_fingerprint is None
    assert checkpoint.history_unknown
    assert record.historical_clear_at == AT.isoformat()


def test_alarm_survives_failed_set_and_clear_requires_exact_successful_ack():
    owner, store, executor = owner_fixture()
    record = owner.set_alarm(binding("flammable_gas"), {"detector": "Fixture"}, at=AT)
    assert record.alarm_active and owner.gas_inhibited
    executor.finish(1)
    owner.drain()
    assert request_clear(owner, record.record_id, "candidate", lambda: True)
    assert owner.records[record.record_id].alarm_active
    executor.finish(2)
    assert owner.records[record.record_id].alarm_active
    cleared = owner.drain()
    assert cleared == [record.record_id]
    assert not owner.records[record.record_id].alarm_active and owner.gas_inhibited
    assert store.load()["records"][0]["gas_switching_inhibited"] is True


def test_new_positive_invalidates_older_clear_ack_and_unclean_restart():
    owner, store, executor = owner_fixture()
    record = owner.set_alarm(binding(), {}, at=AT)
    executor.finish(1)
    owner.drain()
    request_clear(owner, record.record_id, "candidate", lambda: True)
    executor.finish(2)
    # Durable CLEAR exists, then a new alarm is admitted before its owner drain.
    owner.set_alarm(binding(), {}, at=AT)
    assert owner.drain() == []
    assert owner.records[record.record_id].alarm_active
    reboot = IndoorStateOwner(store, writer=SnapshotWriter(ControlledExecutor()), session="reboot")
    assert reboot.history_unknown and reboot.gas_inhibited


def test_failed_clear_and_lost_eligibility_cannot_heal():
    owner, store, executor = owner_fixture()
    record = owner.set_alarm(binding(), {}, at=AT)
    executor.finish(1)
    owner.drain()
    store.save = lambda _: (_ for _ in ()).throw(OSError("fictional failure"))
    request_clear(owner, record.record_id, "candidate", lambda: True)
    executor.finish(2)
    assert owner.drain() == []
    assert owner.records[record.record_id].alarm_active and owner.persistence_error


def test_retained_identity_is_not_rebound_by_same_detector_key():
    owner, store, executor = owner_fixture()
    original = owner.set_alarm(binding(), {}, at=AT)
    executor.finish(1)
    owner.drain()
    reboot = IndoorStateOwner(store, writer=SnapshotWriter(ControlledExecutor()))
    assert reboot.records[original.record_id].incident_id == original.incident_id
    replacement = binding(version="2")
    assert reboot.current_record(replacement) is None
    assert reboot.current_record(binding()).record_id == original.record_id


def test_new_positive_inside_final_eligibility_check_fences_clear_ack():
    owner, _, executor = owner_fixture()
    record = owner.set_alarm(binding(), {}, at=AT)
    executor.finish(1)
    owner.drain()
    checks = []
    def eligible():
        if checks:
            owner.set_alarm(binding(), {}, at=AT)
        checks.append(True)
        return True
    request_clear(owner, record.record_id, "candidate", eligible)
    executor.finish(2)
    assert owner.drain() == []
    assert owner.records[record.record_id].alarm_active


def test_known_record_bounds_and_trusted_fault_catalog():
    owner, _, _ = owner_fixture()
    owner.set_alarm(binding(), {}, at=AT)
    raw = owner.checkpoint().model_dump(mode="json")
    for field, value in [("fault_id", "ArbitraryFault"), ("entity_id", "x" * 256),
                         ("incident_id", "x" * 129), ("activated_at", "2026-11-16"),
                         ("context", {"x": float("nan")}), ("context", {"x": "x" * 4097})]:
        malformed = deepcopy(raw)
        malformed["records"][0][field] = value
        with pytest.raises(ValueError):
            decode_checkpoint(malformed)
    raw["records"] *= 4097
    with pytest.raises(ValueError):
        IndoorCheckpoint.model_validate(raw)


def test_declared_binding_mismatch_cannot_inherit_current_clear_authority():
    owner, store, executor = owner_fixture()
    owner.set_alarm(binding(), {}, at=AT)
    executor.finish(1)
    owner.drain()
    raw = store.load()
    raw["records"][0]["entity_id"] = "binary_sensor.replacement"
    store.save(raw)
    restored = IndoorStateOwner(store, writer=SnapshotWriter(ControlledExecutor()))
    assert restored.current_record(binding()) is None


@pytest.mark.parametrize("process_reset", [False, True])
def test_failed_dirty_marker_and_all_writes_cannot_retrust_prior_clean(process_reset, monkeypatch):
    owner, store, executor = owner_fixture()
    assert owner.stop()
    executor.finish(1)
    owner.drain()
    old_clean = store.load()
    assert old_clean["clean"] is True
    working_save = store.save
    store.save = lambda _: (_ for _ in ()).throw(OSError("all durable storage unavailable"))
    failed_executor = ControlledExecutor()
    failed = IndoorStateOwner(store, writer=SnapshotWriter(failed_executor))
    assert not failed.establish_session(timeout=0)
    failed.set_alarm(binding("flammable_gas"), {}, at=AT)
    failed_executor.finish(0)
    failed_executor.finish(1)
    assert store.load() == old_clean
    store.save = working_save
    if process_reset:
        monkeypatch.delitem(builtins.__dict__, "_safety_indoor_owner_witness_v2")
    restarted = IndoorStateOwner(store, writer=SnapshotWriter(ControlledExecutor()))
    assert restarted.history_unknown and restarted.gas_inhibited
    assert not restarted.records  # Never-durable original identity cannot be fabricated.


def test_persisted_commissioning_receipt_is_not_current_launch_proof(monkeypatch):
    owner, store, executor = owner_fixture()
    owner.stop()
    executor.finish(1)
    owner.drain()
    monkeypatch.delitem(builtins.__dict__, "_safety_indoor_owner_witness_v2")
    reboot = IndoorStateOwner(store, writer=SnapshotWriter(ControlledExecutor()))
    assert reboot.history_unknown and reboot.gas_inhibited


def test_clean_stop_requires_all_writes_acknowledged():
    owner, store, executor = owner_fixture()
    owner.set_alarm(binding(), {}, at=AT)
    assert not owner.stop()
    executor.finish(1)
    assert store.load()["clean"] is False


def test_exact_historical_clear_proof_can_reconcile_older_journal_only():
    owner, _, executor = owner_fixture()
    record = owner.set_alarm(binding(), {}, at=AT)
    generation = owner.revision
    executor.finish(1)
    owner.drain()
    request_clear(owner, record.record_id, "candidate", lambda: True)
    executor.finish(2)
    owner.drain()
    frame = dict(symptom=record.symptom_id, context=dict(indoor_owner_generation=generation,
        indoor_incident_id=record.incident_id))
    assert owner.covers_older_journal_activation(record.fault_id, frame)
    frame["context"]["indoor_owner_generation"] = owner.revision + 1
    assert not owner.covers_older_journal_activation(record.fault_id, frame)


def test_projection_bounds_do_not_truncate_aggregate_danger_or_gas():
    owner, _, _ = owner_fixture()
    for index in range(70):
        record = owner.set_alarm(binding(), {}, at=AT)
        # Independent source contracts, not duplicate identity in a real checkpoint.
        owner.records[str(index)] = record.model_copy(update=dict(record_id=f"record{index}",
            detector_key=f"Fixture{index}", symptom_id=f"InternalEnv_smoke_Fixture{index}",
            incident_id=f"incident{index}", binding_fingerprint=f"{index:064x}"))
        owner.records.pop(record.record_id, None)
    projection = owner.projection({}, monitoring_enabled=False)
    assert projection["retained_records_total"] == projection["retained_active_hazards"] == 70
    assert len(projection["retained_records"]) == 64
    assert projection["retained_records_omitted"] == 6
    import json
    assert len(json.dumps(projection, ensure_ascii=False).encode("utf-8")) <= 65536


def test_failed_set_retains_immediate_danger_and_gas_without_durable_claim():
    owner, store, executor = owner_fixture()
    store.save = lambda _: (_ for _ in ()).throw(OSError("SET unavailable"))
    record = owner.set_alarm(binding("flammable_gas"), {}, at=AT)
    assert owner.records[record.record_id].alarm_active and owner.gas_inhibited
    executor.finish(1)
    assert owner.drain() == []
    assert owner.persistence_error and owner.durable_revision < owner.revision
    assert not owner.stop()


def test_worker_submission_failure_is_receipt_failure_and_cannot_block_positive_alarm():
    class RejectedExecutor:
        def submit(self, *args):
            raise RuntimeError("worker unavailable")
    owner = IndoorStateOwner(InMemoryInternalEnvironmentStateStore(), writer=SnapshotWriter(RejectedExecutor()))
    owner.begin()
    record = owner.set_alarm(binding("flammable_gas"), {}, at=AT)
    assert record.alarm_active and owner.gas_inhibited
    assert owner.drain() == [] and owner.persistence_error


@pytest.mark.parametrize("context", [{"deep": {"a": {"b": {"c": {"d": 1}}}}},
    {f"field{index}": "x" * 256 for index in range(20)}, {"number": float("inf")}])
def test_context_depth_bytes_and_finite_values_are_bounded(context):
    owner, _, _ = owner_fixture()
    with pytest.raises(ValueError):
        owner.set_alarm(binding(), context, at=AT)


def test_fault_projection_omission_preserves_all_real_contributions():
    from unittest.mock import Mock
    import json
    from components.core.event_bus import EventBus
    from components.core.types_common import Fault
    from components.faults_manager.fault_manager import FaultManager
    owner, _, _ = owner_fixture()
    base = owner.set_alarm(binding(), {"cause": "x" * 256}, at=AT)
    records = {f"record{i}": base.model_copy(update=dict(record_id=f"record{i}", incident_id=f"incident{i}",
        detector_key=f"Fixture{i}", symptom_id=f"InternalEnv_smoke_Fixture{i}", binding_fingerprint=f"{i:064x}")) for i in range(100)}
    fault = Fault(name="InternalSmokeDetected", related_symptoms=["sm_iehm_smoke"], level=1)
    mqtt, app = Mock(), Mock()
    mqtt.get_attributes.return_value = {}
    manager = FaultManager(app, {}, {}, {fault.name: fault}, EventBus(), mqtt)
    manager.restore_indoor_assertions(records, uncertain_faults=set())
    manager._project_fault(fault)
    payload = mqtt.publish_sensor_state.call_args.kwargs["attributes"]
    assert payload["active"] and payload["active_contributors_total"] == 100
    assert len(fault.evaluation.active_contributors) == 100
    assert payload["retained_assertions_total"] == 100
    assert payload["retained_assertions_omitted"] > 0
    assert len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) <= 65536


def test_checkpoint_byte_overflow_retains_existing_danger_and_positive_path_is_bounded():
    from dataclasses import replace
    from time import perf_counter
    owner, _, executor = owner_fixture()
    context = {f"field{i}": "x" * 256 for i in range(12)}
    held = set()
    elapsed = 0.0
    for index in range(400):
        contract = replace(binding(), detector_key=f"Fixture{index}", entity_id=f"binary_sensor.fixture_{index}", fingerprint=f"{index:064x}")
        started = perf_counter()
        record = owner.set_alarm(contract, context, at=AT)
        elapsed = perf_counter() - started
        assert held.issubset(owner.records)
        if record.record_id not in owner.records:
            break
        held.add(record.record_id)
    else:
        pytest.fail("Fixture failed to exercise 1 MiB admission boundary")
    assert elapsed < 1  # Within the ten-second positive allocation under bounded load.
    assert owner.history_unknown and owner.gas_inhibited
    assert all(item.alarm_active for item in owner.records.values())
    assert len(executor.jobs) == 2  # Marker completed; one write hangs, one pending slot.
    assert len(owner.records) == len(held)
    with pytest.raises(ValueError, match="1 MiB"):
        decode_checkpoint({"version": 2, "padding": "x" * 1_048_576})
