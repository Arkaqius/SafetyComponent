"""Tests for the full functional-safety diagnostics handoff."""

from __future__ import annotations

from pathlib import Path

import pytest

from components.core.functional_safety_diagnostics import (
    JsonFunctionalSafetyDiagnosticsStore,
)


def test_json_store_atomically_round_trips_full_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "functional_safety.json"
    store = JsonFunctionalSafetyDiagnosticsStore(path)
    payload = {
        "schema_version": 1,
        "generated_at": "2026-09-28T20:12:21+00:00",
        "overall_state": "unknown",
        "diagnostics": {
            "remote_batteries": {
                "Remote": {"sources": [{"entity_id": "sensor.battery", "state": "73"}]}
            }
        },
    }

    store.save(payload)

    assert store.load() == payload
    assert not list(path.parent.glob("*.tmp"))


def test_json_store_rejects_non_object_root(tmp_path: Path) -> None:
    path = tmp_path / "functional_safety.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="root must be an object"):
        JsonFunctionalSafetyDiagnosticsStore(path).load()
