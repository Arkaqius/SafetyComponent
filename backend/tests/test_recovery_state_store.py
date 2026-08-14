"""Persistent recovery-state storage tests."""

from __future__ import annotations

import json

import pytest

from components.recovery_manager.state_store import JsonRecoveryStateStore


def test_json_recovery_store_atomically_round_trips_unicode_state(tmp_path) -> None:
    path = tmp_path / "recovery-state.json"
    store = JsonRecoveryStateStore(str(path))
    snapshot = {
        "version": 1,
        "proposals": [
            {
                "proposal_id": "ExternalWeatherExposureWindExternalGate",
                "instruction": "Potwierdź zamknięcie bramy zewnętrznej.",
                "status": "AWAITING_CONFIRMATION",
            }
        ],
    }

    store.save(snapshot)

    assert store.load() == snapshot
    assert list(tmp_path.glob("*.tmp")) == []


def test_json_recovery_store_rejects_non_object_root(tmp_path) -> None:
    path = tmp_path / "recovery-state.json"
    path.write_text(json.dumps(["invalid"]), encoding="utf-8")

    with pytest.raises(ValueError, match="root must be an object"):
        JsonRecoveryStateStore(str(path)).load()


def test_json_recovery_store_returns_empty_when_snapshot_is_missing(
    tmp_path,
) -> None:
    assert JsonRecoveryStateStore(str(tmp_path / "missing.json")).load() == {}
