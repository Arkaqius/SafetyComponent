"""sc-88u: bounded progress across real SQLite namespace writers."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
import importlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import textwrap
from threading import Event
from time import monotonic

import pytest

from components.core.snapshot_writer import SnapshotWriter
import components.core.sqlite_state_store as storage
from components.core.sqlite_state_store import SqliteStateDatabase, SqliteStateError
from safety_lifecycle_support import ControlledExecutor


def test_background_namespace_progresses_after_normal_writer_overlap(tmp_path: Path) -> None:
    """SC88U-001: competing normal namespace writes eventually commit independently.

    @relation(SWR-FLT-021, scope=function, role=Test)
    @relation(SWR-REC-006, scope=function, role=Test)
    """
    db = SqliteStateDatabase(tmp_path / "state.sqlite3")
    evidence = db.record_store("fault_evidence_state", max_bytes=4096)
    recovery = db.record_store("recovery_state", max_bytes=4096)
    evidence.save({"generation": 0})
    recovery.save({"generation": 0})
    entered, release, attempted = Event(), Event(), Event()
    original = evidence._write

    def hold(connection, sections):
        original(connection, sections)
        entered.set()
        assert release.wait(2)

    evidence._write = hold

    def competing_save(snapshot):
        attempted.set()
        recovery.save(snapshot)

    with ThreadPoolExecutor(max_workers=1) as holder, ThreadPoolExecutor(max_workers=1) as worker:
        writing = holder.submit(evidence.save, {"generation": 1})
        try:
            assert entered.wait(1)
            writer = SnapshotWriter(worker)
            writer.claim("current")
            started = monotonic()
            assert writer.enqueue("current", 1, {"generation": 1}, competing_save)
            assert monotonic() - started < 0.05
            assert attempted.wait(1)
            # Keep the transaction held past the old SQLite busy timeout.
            assert not writer.wait_for_progress(0.12)
        finally:
            release.set()
        writing.result(timeout=1)
        assert writer.wait_for_progress(1)
        result = writer.drain("current")
        assert result is not None and result.error is None
    assert evidence.load() == recovery.load() == {"generation": 1}


def test_identical_snapshot_skips_record_mutations_but_observes_peer_updates(tmp_path: Path) -> None:
    """SC88U-002: no-op is proved from SQLite, never from an instance cache.

    @relation(SWR-REC-006, scope=function, role=Test)
    """
    db = SqliteStateDatabase(tmp_path / "state.sqlite3")
    store = db.record_store("recovery_state", max_bytes=4096)
    store.save({"generation": "A"})
    writes = []
    original = store._write

    def record(connection, sections):
        writes.append(True)
        original(connection, sections)

    store._write = record
    store.save({"generation": "A"})
    assert writes == []
    peer = SqliteStateDatabase(db.path).record_store("recovery_state", max_bytes=4096)
    peer.save({"generation": "B"})
    store.save({"generation": "A"})
    assert writes == [True]
    assert peer.load() == {"generation": "A"}


def test_synchronous_contention_keeps_existing_callback_wait_budget(tmp_path: Path) -> None:
    """SC88U-003: foreground persistence cannot wait out a stalled worker.

    @relation(SWR-FLT-025, scope=function, role=Test)
    @relation(SWR-NOT-017, scope=function, role=Test)
    """
    db = SqliteStateDatabase(tmp_path / "state.sqlite3")
    first = db.record_store("recovery_state", max_bytes=4096)
    second = db.record_store("fault_evidence_state", max_bytes=4096)
    first.save({"generation": 0})
    second.save({"generation": 0})
    entered, release = Event(), Event()
    original = first._write

    def hold(connection, sections):
        entered.set()
        assert release.wait(2)
        original(connection, sections)

    first._write = hold
    with ThreadPoolExecutor(max_workers=1) as worker:
        writing = worker.submit(first.save, {"generation": 1})
        try:
            assert entered.wait(1)
            started = monotonic()
            with pytest.raises(SqliteStateError, match="SQLITE_BUSY"):
                second.save({"generation": 1})
            assert monotonic() - started < 0.2
            assert second.load() == {"generation": 0}
        finally:
            release.set()
        writing.result(timeout=1)


def test_permanent_external_contention_is_bounded_and_preserves_commit(tmp_path: Path, monkeypatch) -> None:
    """SC88U-004: exhausted worker retries retain data and an exact failure receipt.

    @relation(SWR-FLT-021, scope=function, role=Test)
    @relation(SWR-REC-006, scope=function, role=Test)
    """
    db = SqliteStateDatabase(tmp_path / "state.sqlite3")
    store = db.record_store("recovery_state", max_bytes=4096)
    store.save({"generation": 0})
    with closing(sqlite3.connect(db.path)) as locked, locked, ThreadPoolExecutor(max_workers=1) as worker:
        locked.execute("BEGIN IMMEDIATE")
        timeouts: list[int] = []
        connect = sqlite3.connect

        class ObservedConnection(sqlite3.Connection):
            def execute(self, sql: str, parameters: tuple = ()) -> sqlite3.Cursor:
                if sql == "BEGIN IMMEDIATE":
                    timeouts.append(super().execute("PRAGMA busy_timeout").fetchone()[0])
                return super().execute(sql, parameters)

        def observe_connect(*args, **kwargs):
            return connect(*args, **kwargs, factory=ObservedConnection)

        monkeypatch.setattr(sqlite3, "connect", observe_connect)
        writer = SnapshotWriter(worker)
        writer.claim("current")
        assert writer.enqueue("current", 9, {"generation": 1}, store.save)
        # This is a test watchdog, not a filesystem or scheduler deadline.
        # SC88U-006 separately proves the remaining contention-wait allocation.
        assert writer.wait_for_progress(5)
        assert len(timeouts) == 4
        assert all(0 < timeout <= 50 for timeout in timeouts)
        result = writer.drain("current")
        assert (result.owner, result.revision, result.error) == ("current", 9, "SQLITE_BUSY")
        assert store.load() == {"generation": 0}
    assert store.load() == {"generation": 0}


def test_inflight_b_then_latest_a_does_not_reuse_an_old_durable_a(tmp_path: Path) -> None:
    """SC88U-005: no-op proof follows the submitted B before latest A.

    @relation(SWR-REC-006, scope=function, role=Test)
    """
    store = SqliteStateDatabase(tmp_path / "state.sqlite3").record_store("recovery_state", max_bytes=4096)
    store.save({"generation": "A"})
    executor = ControlledExecutor()
    writer = SnapshotWriter(executor)
    writer.claim("current")
    assert writer.enqueue("current", 1, {"generation": "B"}, store.save)
    assert writer.enqueue("current", 2, {"generation": "A"}, store.save)
    executor.finish(0)
    assert store.load() == {"generation": "B"}
    executor.finish(1)
    result = writer.drain("current")
    assert (result.revision, result.error) == (2, None)
    assert store.load() == {"generation": "A"}


def test_sqlite_lock_wait_uses_only_remaining_foreground_budget(tmp_path: Path, monkeypatch) -> None:
    """SC88U-006: 30 ms coordination leaves only 20 ms SQLite lock waiting.

    @relation(SWR-NOT-017, scope=function, role=Test)
    """
    db = SqliteStateDatabase(tmp_path / "state.sqlite3")
    db.record_store("state", max_bytes=4096).save({"generation": 0})

    @contextmanager
    def delayed_admission(budget):
        budget.consume(0.03)
        yield

    monkeypatch.setattr(db._coordinator, "mutation", delayed_admission)
    with db.connect() as connection, db.write_transaction(connection):
        timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
        assert 19 <= timeout <= 20


def test_healthy_slow_initialization_import_and_commit_are_not_contention(tmp_path: Path, monkeypatch) -> None:
    """SC88U-007: healthy filesystem work cannot fabricate a BUSY failure.

    @relation(SWR-FLT-021, scope=function, role=Test)
    @relation(SWR-REC-006, scope=function, role=Test)
    """
    clock = [100.0]
    monkeypatch.setattr(storage, "monotonic", lambda: clock[0])
    db = SqliteStateDatabase(tmp_path / "state.sqlite3")
    store = db.record_store("recovery_state", max_bytes=4096)
    initialize, write = db._initialize, store._write

    def slow_initialize(connection):
        initialize(connection)
        clock[0] += 2

    def slow_write(connection, sections):
        write(connection, sections)
        clock[0] += 2

    monkeypatch.setattr(db, "_initialize", slow_initialize)
    monkeypatch.setattr(store, "_write", slow_write)
    store.save({"generation": 0})
    executor = ControlledExecutor()
    writer = SnapshotWriter(executor)
    writer.claim("current")
    assert writer.enqueue("current", 1, {"generation": 1}, store.save)
    executor.finish(0)
    assert writer.drain("current").error is None
    assert store.load() == {"generation": 1}


@pytest.mark.parametrize("change", ["newer", "new_owner"])
def test_busy_retry_fences_obsolete_unsent_attempts(change: str) -> None:
    """SC88U-008: newest state and owner replace unsent retries, never first I/O.

    @relation(SWR-NOT-017, scope=function, role=Test)
    @relation(SWR-REC-006, scope=function, role=Test)
    """
    executor = ControlledExecutor()
    writer = SnapshotWriter(executor)
    writer.claim("old")
    attempts = []

    def first(snapshot):
        attempts.append(snapshot)
        if change == "new_owner":
            writer.claim("new")
        writer.enqueue("new" if change == "new_owner" else "old", 2, {"generation": 2}, attempts.append)
        raise SqliteStateError("fixture", sqlite3.OperationalError("database is locked"))

    writer.enqueue("old", 1, {"generation": 1}, first)
    executor.finish(0)
    executor.finish(1)
    result = writer.drain("new" if change == "new_owner" else "old")
    assert attempts == [{"generation": 1}, {"generation": 2}]
    assert (result.revision, result.error) == (2, None)
    assert result.superseded_error == (None if change == "new_owner" else "SQLITE_BUSY")


@pytest.mark.parametrize("message", ["database or disk is full", "attempt to write a readonly database"])
def test_worker_never_retries_permanent_storage_failures(message: str) -> None:
    """SC88U-009: only BUSY, never FULL/READONLY, permits another storage attempt.

    @relation(SWR-FLT-021, scope=function, role=Test)
    """
    executor = ControlledExecutor()
    writer = SnapshotWriter(executor)
    writer.claim("current")
    attempts = []

    def fail(snapshot):
        attempts.append(snapshot)
        raise SqliteStateError("fixture", sqlite3.OperationalError(message))

    writer.enqueue("current", 1, {"generation": 1}, fail)
    executor.finish(0)
    result = writer.drain("current")
    assert len(attempts) == 1
    assert result.error in {"SQLITE_FULL", "SQLITE_READONLY"}


def test_coordinator_identity_survives_path_alias_and_module_reload(tmp_path: Path) -> None:
    """SC88U-010: database objects/reloaded modules share the process mutation gate.

    @relation(SWR-NOT-017, scope=function, role=Test)
    """
    # Load a fresh module under a temporary name, leaving the module's public
    # error identities used by all other tests unchanged.
    spec = importlib.util.spec_from_file_location("sc88u_storage_reload", storage.__file__)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        first = storage.SqliteStateDatabase(tmp_path / "state.sqlite3")
        spec.loader.exec_module(module)
        second = module.SqliteStateDatabase(tmp_path / "unused" / ".." / "state.sqlite3")
        assert first._coordinator is second._coordinator
        spec.loader.exec_module(module)
        third = module.SqliteStateDatabase(os.path.normcase(str(first.path)))
        assert third._coordinator is first._coordinator
    finally:
        del sys.modules[spec.name]


def test_foreground_writer_is_admitted_before_a_waiting_background_writer(tmp_path: Path) -> None:
    """SC88U-011: pending callbacks have priority without exceeding their wait cap.

    @relation(SWR-NOT-017, scope=function, role=Test)
    @relation(SWR-FLT-025, scope=function, role=Test)
    """
    db = SqliteStateDatabase(tmp_path / "state.sqlite3")
    stores = {key: db.record_store(key, max_bytes=4096) for key in ("holder", "background", "foreground")}
    for store in stores.values():
        store.save({"generation": 0})
    entered, release, attempted = Event(), Event(), Event()
    order = []
    for key, store in stores.items():
        original = store._write

        def record(connection, sections, key=key, original=original):
            if key == "holder":
                entered.set()
                assert release.wait(2)
            order.append(key)
            original(connection, sections)

        store._write = record

    def background(snapshot):
        attempted.set()
        stores["background"].save(snapshot)

    with ThreadPoolExecutor(max_workers=2) as foreground, ThreadPoolExecutor(max_workers=1) as worker:
        held = foreground.submit(stores["holder"].save, {"generation": 1})
        try:
            assert entered.wait(1)
            writer = SnapshotWriter(worker)
            writer.claim("current")
            writer.enqueue("current", 1, {"generation": 1}, background)
            assert attempted.wait(1)
            waiting = foreground.submit(stores["foreground"].save, {"generation": 1})
            with db._coordinator.condition:
                assert db._coordinator.condition.wait_for(lambda: db._coordinator.foreground_waiters == 1, timeout=1)
            release.set()
            held.result(timeout=1)
            waiting.result(timeout=1)
            assert writer.wait_for_progress(1)
            assert writer.drain("current").error is None
        finally:
            release.set()
    assert order == ["holder", "foreground", "background"]


def test_retained_writer_classifies_errors_after_storage_module_reload() -> None:
    """SC88U-012: retained process workers recognize reloaded storage exceptions.

    @relation(SWR-NOT-017, scope=function, role=Test)
    """
    script = textwrap.dedent("""
        import importlib
        import sqlite3
        from concurrent.futures import ThreadPoolExecutor
        import components.core.sqlite_state_store as storage
        from components.core.snapshot_writer import SnapshotWriter
        with ThreadPoolExecutor(max_workers=1) as executor:
            writer = SnapshotWriter(executor)
            writer.claim('current')
            importlib.reload(storage)
            attempts = []
            def save(snapshot):
                attempts.append(snapshot)
                if len(attempts) == 1:
                    raise storage.SqliteStateError('fixture', sqlite3.OperationalError('database is locked'))
            writer.enqueue('current', 1, {'generation': 1}, save)
            assert writer.wait_for_progress(1)
            result = writer.drain('current')
            assert result.error is None, result
            assert len(attempts) == 2, attempts
        """)
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    # Bound a deadlocked child without treating loaded-host interpreter startup
    # as a product deadline; the child's write/receipt assertions stay unchanged.
    result = subprocess.run([sys.executable, "-B", "-c", script], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
