"""Atomic persistent storage for notification lifecycle state."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Protocol


class NotificationStateStore(Protocol):
    """Persistence boundary used by NotificationManager."""

    def load(self) -> dict[str, Any]:
        """Load the last valid state snapshot."""

    def save(self, snapshot: Mapping[str, Any]) -> None:
        """Atomically replace the stored state snapshot."""


class InMemoryNotificationStateStore:
    """Deterministic state store for unit tests and disabled persistence."""

    def __init__(self, snapshot: Mapping[str, Any] | None = None) -> None:
        self.snapshot = dict(snapshot or {})

    def load(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.snapshot))

    def save(self, snapshot: Mapping[str, Any]) -> None:
        self.snapshot = json.loads(json.dumps(dict(snapshot), default=str))


class JsonNotificationStateStore:
    """Versioned JSON state stored outside the deployed app directory."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
        if not isinstance(payload, dict):
            raise ValueError("Notification state root must be an object")
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
