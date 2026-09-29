"""Share full functional-safety diagnostics outside Home Assistant Recorder."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Protocol


DIAGNOSTICS_SCHEMA_VERSION = 1
DEFAULT_FUNCTIONAL_SAFETY_DIAGNOSTICS_PATH = Path(
    "/run/safety-component/functional_safety.json"
)


class FunctionalSafetyDiagnosticsStore(Protocol):
    """Storage boundary shared by the monitor and same-origin UI API."""

    def load(self) -> dict[str, Any]:
        """Load the latest complete diagnostics snapshot."""

    def save(self, snapshot: Mapping[str, Any]) -> None:
        """Atomically replace the complete diagnostics snapshot."""


class InMemoryFunctionalSafetyDiagnosticsStore:
    """Keep a deterministic diagnostics snapshot for tests."""

    def __init__(self, snapshot: Mapping[str, Any] | None = None) -> None:
        self.snapshot = dict(snapshot or {})

    def load(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.snapshot))

    def save(self, snapshot: Mapping[str, Any]) -> None:
        self.snapshot = json.loads(json.dumps(dict(snapshot), default=str))


class JsonFunctionalSafetyDiagnosticsStore:
    """Store one ephemeral JSON snapshot without partial-read windows."""

    def __init__(
        self, path: Path | str = DEFAULT_FUNCTIONAL_SAFETY_DIAGNOSTICS_PATH
    ) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
        if not isinstance(payload, dict):
            raise ValueError("functional safety diagnostics root must be an object")
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
