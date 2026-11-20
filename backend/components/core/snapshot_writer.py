"""Serialize bounded immutable snapshots without blocking a safety owner."""

from __future__ import annotations

import builtins
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
import json
from threading import RLock
from typing import Any

MAX_SNAPSHOT_BYTES = 1024 * 1024
_NAMESPACES = frozenset({"notification_state", "recovery_state", "internal_environment_state"})


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


class SnapshotWriter:
    """One process-owned writer and one latest pending snapshot per namespace.

    Completion is polled by the owner. A hung write keeps its one worker and
    cannot cause thread growth on app reload; later owners replace only unsent
    work. The injected save adapter must own storage only, never a safety owner.
    """

    def __init__(self, executor: Any | None = None) -> None:
        self._executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="safety-state")
        self._lock = RLock()
        self._future: Future[WriteResult] | None = None
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
            self._pump()
            return True

    def drain(self, owner: str) -> WriteResult | None:
        """Advance one completion and apply no domain state on the worker."""
        with self._lock:
            self._pump()
            result, self._result = self._result, None
            return result if result is not None and result.owner == owner else None

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
            self._result = self._future.result()
            self._future = None
        if self._future is None and self._pending is not None:
            request, save = self._pending
            self._pending = None
            try:
                self._future = self._executor.submit(self._write, request, save)
            except Exception as exc:
                self._result = WriteResult(request.owner, request.revision, type(exc).__name__[:128])
                return
            self._future.add_done_callback(self._completed)

    def _completed(self, _: Future[WriteResult]) -> None:
        # This callback advances infrastructure only. Domain acknowledgements
        # remain immutable mailbox evidence, polled on the current owner.
        with self._lock:
            self._pump()

    @staticmethod
    def _write(request: WriteRequest, save: Callable[[Mapping[str, Any]], None]) -> WriteResult:
        try:
            save(json.loads(request.payload))
        except Exception as exc:
            return WriteResult(request.owner, request.revision, type(exc).__name__[:128])
        return WriteResult(request.owner, request.revision)


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
