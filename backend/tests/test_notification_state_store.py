"""Persistent notification-state storage tests."""

from __future__ import annotations

import json

import pytest

from components.notification_manager.state_store import JsonNotificationStateStore


def test_json_store_atomically_round_trips_unicode_state(tmp_path) -> None:
    path = tmp_path / "notification-state.json"
    store = JsonNotificationStateStore(str(path))
    snapshot = {
        "version": 1,
        "active_notifications": {"tag": {"message": "Wymaga uwagi: temperatura."}},
    }

    store.save(snapshot)

    assert store.load() == snapshot
    assert list(tmp_path.glob("*.tmp")) == []


def test_json_store_rejects_non_object_root(tmp_path) -> None:
    path = tmp_path / "notification-state.json"
    path.write_text(json.dumps(["invalid"]), encoding="utf-8")

    with pytest.raises(ValueError, match="root must be an object"):
        JsonNotificationStateStore(str(path)).load()


def test_json_store_returns_empty_when_snapshot_does_not_exist(tmp_path) -> None:
    assert JsonNotificationStateStore(str(tmp_path / "missing.json")).load() == {}
