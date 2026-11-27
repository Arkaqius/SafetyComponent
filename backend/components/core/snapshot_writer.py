"""Serialize bounded immutable snapshots without blocking a safety owner."""

from __future__ import annotations

import builtins
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, replace
import json
from threading import Condition, RLock
from time import monotonic
from typing import Any

from . import sqlite_state_store

MAX_SNAPSHOT_BYTES = 1024 * 1024
_NAMESPACES = frozenset({"notification_state", "recovery_state", "internal_environment_state"})
_BUSY_RETRY_DELAYS = (0.01, 0.02, 0.04)


@dataclass(frozen=True)
class WriteRequest:
    """Detached data plus exact owner identity; no mutable owner crosses threads."""

    owner: str
    revision: int
    payload: str


@dataclass(frozen=True)
class WriteResult:
    """A completed atomic write, distinct from queue admission."""

    owner: str
    revision: int
    error: str | None = None
    superseded_error: str | None = None


class SnapshotWriter:
    """One process-owned writer and one latest pending snapshot per namespace.

    Completion is polled by the owner. A hung write keeps its one worker and
    cannot cause thread growth on app reload; later owners replace only unsent
    work. The injected save adapter must own storage only, never a safety owner.
    """

    def __init__(self, executor: Any | None = None) -> None:
        self._executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="safety-state")
        self._lock = RLock()
        self._changed = Condition(self._lock)
        self._future: Future[WriteResult | None] | None = None
        self._pending: tuple[WriteRequest, Callable[[Mapping[str, Any]], None]] | None = None
        self._result: WriteResult | None = None
        self._owner: str | None = None

    def claim(self, owner: str) -> None:
        """Fence a previous app's unsent writes without cancelling active I/O."""
        with self._lock:
            if self._owner != owner:
                self._pending = None
                self._result = None
                self._owner = owner
                self._changed.notify_all()

    @property
    def busy(self) -> bool:
        """Expose unfinished process storage without transferring its ownership."""
        with self._lock:
            return self._future is not None and not self._future.done()

    def enqueue(
        self, owner: str, revision: int, snapshot: Mapping[str, Any],
        save: Callable[[Mapping[str, Any]], None],
    ) -> bool:
        """Copy and coalesce a bounded snapshot; true is admission, not durability."""
        try:
            payload = json.dumps(dict(snapshot), ensure_ascii=False, allow_nan=False)
            if len(payload.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
                return False
        except (ValueError, TypeError, RecursionError):
            return False
        with self._lock:
            if self._owner != owner:
                return False
            self._pending = (WriteRequest(owner, revision, payload), save)
            self._changed.notify_all()
            self._pump()
            return True

    def drain(self, owner: str) -> WriteResult | None:
        """Advance one completion and apply no domain state on the worker."""
        with self._lock:
            self._pump()
            result = self._result
            if result is None or result.owner != owner:
                return None
            self._result = None
            return result

    def wait_for_progress(self, timeout: float) -> bool:
        """Wait only at startup/shutdown barriers; never on alarm ingress."""
        with self._lock:
            future = self._future
            if future is None:
                return self._result is not None
        try:
            future.result(timeout=max(0, timeout))
        except TimeoutError:
            return False
        return True

    def _pump(self) -> None:
        if self._future is not None and self._future.done():
            result = self._future.result()
            if result is not None:
                self._record_completion(result)
            self._future = None
        if self._future is None and self._pending is not None:
            request, save = self._pending
            self._pending = None
            try:
                self._future = self._executor.submit(self._write, request, save)
            except Exception as exc:
                self._record_completion(
                    WriteResult(request.owner, request.revision, type(exc).__name__[:128])
                )
                return
            self._future.add_done_callback(self._completed)

    def _record_completion(self, result: WriteResult) -> None:
        if result.owner != self._owner:
            return
        previous = self._result
        if previous is not None:
            result = replace(
                result, superseded_error=previous.error or previous.superseded_error
            )
        self._result = result

    def _completed(self, _: Future[WriteResult | None]) -> None:
        # This callback advances infrastructure only. Domain acknowledgements
        # remain immutable mailbox evidence, polled on the current owner.
        with self._lock:
            self._pump()

    def _current(self, request: WriteRequest) -> bool:
        with self._lock:
            return self._owner == request.owner and (
                self._pending is None or self._pending[0].revision <= request.revision
            )

    def _write(
        self, request: WriteRequest, save: Callable[[Mapping[str, Any]], None],
    ) -> WriteResult | None:
        """Retry storage contention on this worker, never physical/domain work.

        @relation(SWR-NOT-017, scope=function, role=Implementation)
        @relation(SWR-REC-006, scope=function, role=Implementation)
        """
        failure = None
        with sqlite_state_store.storage_write_budget(
            lambda: True if attempt == 0 else self._current(request)
        ) as budget:
            for attempt in range(len(_BUSY_RETRY_DELAYS) + 1):
                if attempt and not self._current(request):
                    return failure
                try:
                    save(json.loads(request.payload))
                except sqlite_state_store.SupersededStorageWrite:
                    return failure
                except sqlite_state_store.SqliteStateError as exc:
                    failure = WriteResult(request.owner, request.revision, exc.sqlite_errorname)
                    if exc.sqlite_errorname != "SQLITE_BUSY" or attempt == len(_BUSY_RETRY_DELAYS):
                        return failure
                    # Charge the maximum native SQLite wait, not healthy
                    # initialization/encoding/FULL-commit time in this attempt.
                    budget.consume(0.05)
                    try:
                        remaining = budget.remaining()
                    except (sqlite_state_store.SqliteStateError, sqlite_state_store.SupersededStorageWrite):
                        return failure
                    with self._changed:
                        if self._current(request):
                            started = monotonic()
                            self._changed.wait(timeout=min(_BUSY_RETRY_DELAYS[attempt], remaining))
                            budget.consume(monotonic() - started)
                except Exception as exc:
                    return WriteResult(request.owner, request.revision, type(exc).__name__[:128])
                else:
                    return WriteResult(request.owner, request.revision)
        return failure


def process_snapshot_writer(namespace: str) -> SnapshotWriter:
    """Reuse at most three independent workers across application/module reloads."""
    if namespace not in _NAMESPACES:
        raise ValueError("Unknown snapshot namespace")
    lock = builtins.__dict__.setdefault("_safety_snapshot_lock_v1", RLock())
    with lock:
        writers = builtins.__dict__.setdefault("_safety_snapshot_writers_v1", {})
        if namespace not in writers:
            writers[namespace] = SnapshotWriter()
        return writers[namespace]
