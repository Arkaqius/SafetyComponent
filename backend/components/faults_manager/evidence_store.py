"""Independent atomic storage for bounded fault diagnostic evidence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Protocol


class FaultEvidenceStore(Protocol):
    """Persistence boundary for freeze frames and extended data."""

    def load(self) -> dict[str, Any]:
        ...

    def save(self, snapshot: Mapping[str, Any]) -> None:
        ...


class InMemoryFaultEvidenceStore:
    """Deterministic store for tests and installations without durability."""

    def __init__(self, snapshot: Mapping[str, Any] | None = None) -> None:
        self.snapshot = dict(snapshot or {})

    def load(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.snapshot))

    def save(self, snapshot: Mapping[str, Any]) -> None:
        self.snapshot = json.loads(json.dumps(dict(snapshot)))


class JsonFaultEvidenceStore:
    """Atomically replace a versioned JSON snapshot outside the app image."""

    def __init__(self, path: str, *, max_bytes: int = 1048576) -> None:
        self.path = Path(path)
        self.max_bytes = max_bytes

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        if self.path.stat().st_size > self.max_bytes:
            raise ValueError("Fault evidence state exceeds configured bound")
        with self.path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
        if not isinstance(payload, dict):
            raise ValueError("Fault evidence state root must be an object")
        return payload

    def save(self, snapshot: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(dict(snapshot), stream, ensure_ascii=False, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, self.path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
