"""Bounded storage admission, coalescing and cross-generation acknowledgement."""

import pytest

from components.core.snapshot_writer import MAX_SNAPSHOT_BYTES, SnapshotWriter, process_snapshot_writer
from safety_lifecycle_support import ControlledExecutor


def test_stalled_writer_keeps_one_detached_inflight_and_one_latest_pending() -> None:
    executor = ControlledExecutor()
    writer = SnapshotWriter(executor)
    writer.claim("first")
    saved = []
    initial = {"value": [0]}
    assert writer.enqueue("first", 1, initial, saved.append)
    initial["value"][0] = 999
    for revision in range(2, 1001):
        assert writer.enqueue("first", revision, {"value": [revision]}, saved.append)
    assert len(executor.jobs) == 1 and saved == []
    executor.finish(0)
    assert writer.drain("first").revision == 1
    assert saved == [{"value": [0]}]
    assert len(executor.jobs) == 2
    executor.finish(1)
    assert writer.drain("first").revision == 1000
    assert saved[-1] == {"value": [1000]}


def test_new_owner_fences_old_pending_and_receipts_but_serializes_active_write() -> None:
    executor = ControlledExecutor()
    writer = SnapshotWriter(executor)
    writer.claim("old")
    saved = []
    writer.enqueue("old", 1, {"value": 1}, saved.append)
    writer.enqueue("old", 2, {"value": 2}, saved.append)
    writer.claim("new")
    assert not writer.enqueue("old", 3, {"value": 3}, saved.append)
    writer.enqueue("new", 1, {"value": 4}, saved.append)
    assert len(executor.jobs) == 1
    executor.finish(0)
    assert writer.drain("new") is None
    executor.finish(1)
    assert writer.drain("new").owner == "new"
    assert saved == [{"value": 1}, {"value": 4}]


def test_failed_write_acknowledges_exact_identity_and_keeps_latest_work() -> None:
    executor = ControlledExecutor()
    writer = SnapshotWriter(executor)
    writer.claim("fixture")

    def fail(_):
        raise OSError("fictional storage failure")

    writer.enqueue("fixture", 1, {"value": 1}, fail)
    writer.enqueue("fixture", 2, {"value": 2}, lambda _: None)
    executor.finish(0)
    receipt = writer.drain("fixture")
    assert (receipt.owner, receipt.revision, receipt.error) == ("fixture", 1, "OSError")
    executor.finish(1)
    assert writer.drain("fixture").error is None


def test_superseded_failure_is_diagnostic_only_and_cannot_cross_owners() -> None:
    executor = ControlledExecutor()
    writer = SnapshotWriter(executor)
    writer.claim("first")

    def fail(_):
        raise OSError("fictional storage failure")

    assert writer.enqueue("first", 1, {}, fail)
    assert writer.enqueue("first", 2, {}, lambda _: None)
    executor.finish(0)
    executor.finish(1)
    assert writer.drain("retired") is None
    result = writer.drain("first")
    assert (result.revision, result.error, result.superseded_error) == (2, None, "OSError")
    assert writer.drain("first") is None

    assert writer.enqueue("first", 3, {}, fail)
    writer.claim("second")
    assert writer.enqueue("second", 1, {}, lambda _: None)
    executor.finish(2)
    executor.finish(3)
    result = writer.drain("second")
    assert (result.revision, result.error, result.superseded_error) == (1, None, None)


@pytest.mark.parametrize("value", [float("nan"), object(), "x" * MAX_SNAPSHOT_BYTES], ids=["nan", "object", "oversize"])
def test_snapshot_rejection_never_starts_storage(value) -> None:
    executor = ControlledExecutor()
    writer = SnapshotWriter(executor)
    writer.claim("fixture")
    assert not writer.enqueue("fixture", 1, {"value": value}, lambda _: None)
    assert executor.jobs == []


def test_process_writer_namespace_is_finite_and_reused() -> None:
    assert process_snapshot_writer("notification_state") is process_snapshot_writer("notification_state")
    with pytest.raises(ValueError, match="namespace"):
        process_snapshot_writer("untrusted")
