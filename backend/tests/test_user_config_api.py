"""Tests for the installation-owned configuration API store."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from user_config_api import RevisionConflictError, UserConfigStore


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _store(tmp_path: Path) -> UserConfigStore:
    user_path = tmp_path / "user_config.yml"
    user_path.write_text(
        (BACKEND_DIR / "config" / "user_config.example.yml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    return UserConfigStore(
        user_path=user_path,
        system_path=BACKEND_DIR / "config" / "system_config.yml",
    )


def test_read_returns_only_user_source_and_revision(tmp_path: Path) -> None:
    result = _store(tmp_path).read()

    assert result["user_config"]["model_version"] == 2
    assert result["revision"]
    assert result["restart_required"] is False
    assert "system_config" not in result


def test_save_validates_and_atomically_replaces_user_source(tmp_path: Path) -> None:
    store = _store(tmp_path)
    original = store.read()
    edited = original["user_config"]
    edited["installation"]["defaults"]["temperature"] = {
        "low_temperature_c": 17.0,
        "high_temperature_c": 27.0,
    }

    saved = store.save(edited, original["revision"])
    persisted = yaml.safe_load(store.user_path.read_text(encoding="utf-8"))

    assert saved["restart_required"] is True
    assert saved["revision"] != original["revision"]
    assert (
        persisted["user_config"]["installation"]["defaults"]["temperature"]
        ["low_temperature_c"]
        == 17.0
    )


def test_save_rejects_stale_revision_without_changing_file(tmp_path: Path) -> None:
    store = _store(tmp_path)
    original = store.read()
    original_bytes = store.user_path.read_bytes()

    with pytest.raises(RevisionConflictError):
        store.save(original["user_config"], "stale")

    assert store.user_path.read_bytes() == original_bytes


def test_save_rejects_invalid_config_without_changing_file(tmp_path: Path) -> None:
    store = _store(tmp_path)
    original = store.read()
    original_bytes = store.user_path.read_bytes()
    edited = original["user_config"]
    del edited["installation"]["rooms"]["LivingRoom"]["temperature_sensor"]

    with pytest.raises(ValueError):
        store.save(edited, original["revision"])

    assert store.user_path.read_bytes() == original_bytes
