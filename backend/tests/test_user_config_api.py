"""Tests for the installation-owned configuration API store."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
import yaml

from user_config_api import (
    ConfigurationHttpServer,
    RevisionConflictError,
    UserConfigRequestHandler,
    UserConfigStore,
)


BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("available", [True, False])
def test_battery_inventory_is_read_only_and_failure_is_explicit(tmp_path: Path, monkeypatch, available: bool) -> None:
    store = _store(tmp_path)
    before = store.user_path.read_bytes()
    class Provider:
        def discover_batteries(self):
            return {"status": "ready", "devices": []}
    monkeypatch.setattr("user_config_api.HomeAssistantStateProvider.from_environment", lambda: Provider() if available else None)
    UserConfigRequestHandler.store = store
    server = ConfigurationHttpServer(("127.0.0.1", 0), UserConfigRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/api/batteries") as response:
            assert json.load(response) == {"status": "ready" if available else "error", "devices": []}
        assert store.user_path.read_bytes() == before
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture(autouse=True)
def _mock_home_assistant_location(monkeypatch) -> None:
    monkeypatch.setattr(
        UserConfigStore,
        "_fetch_home_assistant_config",
        staticmethod(lambda: {"latitude": 50.0, "longitude": 20.0}),
    )


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
    assert result["setup_required"] is False
    assert result["system_defaults"]["detector_profiles"] == [
        "home_assistant_binary_alarm"
    ]
    assert "system_config" not in result


def test_restart_target_revalidates_saved_revision_without_writing(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    original = store.read()
    before = store.user_path.read_bytes()
    monkeypatch.setattr("user_config_api.own_app_slug", lambda: "local_safety_component_dev")
    assert store.restart_target(original["revision"]) == {"app_slug": "local_safety_component_dev"}
    assert store.user_path.read_bytes() == before
    with pytest.raises(RevisionConflictError):
        store.restart_target("old-revision")
    store.user_path.write_text("user_config: {}", encoding="utf-8")
    with pytest.raises(ValueError):
        store.restart_target(store._revision(store.user_path.read_bytes()))


@pytest.mark.parametrize("confirmed", [True, False, "true"])
def test_restart_preparation_http_requires_literal_confirmation(tmp_path: Path, monkeypatch, confirmed) -> None:
    store = _store(tmp_path)
    monkeypatch.setattr("user_config_api.own_app_slug", lambda: "local_safety_component_dev")
    UserConfigRequestHandler.store = store
    server = ConfigurationHttpServer(("127.0.0.1", 0), UserConfigRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = Request(f"http://127.0.0.1:{server.server_port}/api/config/restart-target", data=json.dumps({"confirmed": confirmed, "revision": store.read()["revision"]}).encode(), headers={"Content-Type": "application/json"})
        if confirmed is True:
            with urlopen(request) as response:
                assert json.load(response) == {"app_slug": "local_safety_component_dev"}
        else:
            with pytest.raises(HTTPError) as error:
                urlopen(request)
            assert error.value.code == 422
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_first_start_serves_example_without_creating_user_file(tmp_path: Path) -> None:
    store = UserConfigStore(
        user_path=tmp_path / "user_config.yml",
        system_path=BACKEND_DIR / "config" / "system_config.yml",
    )

    draft = store.read()

    assert draft["setup_required"] is True
    assert draft["revision"] == "absent"
    assert draft["user_config"]["model_version"] == 2
    assert not store.user_path.exists()

    saved = store.save(draft["user_config"], draft["revision"])

    assert saved["setup_required"] is False
    assert store.user_path.exists()
    assert store.read()["revision"] == saved["revision"]


def test_reset_template_is_public_and_read_does_not_modify_private_source(tmp_path: Path) -> None:
    store = _store(tmp_path)
    original = store.read()
    draft = original["user_config"]
    draft["installation"]["component_settings"]["temperature"] = {"low_temperature_c": 17.0}
    store.save(draft, original["revision"])
    before = store.user_path.read_bytes()

    result = store.read()

    assert store.user_path.read_bytes() == before
    assert result["user_config"] != result["template_user_config"]
    assert result["template_user_config"] == yaml.safe_load(store.example_path.read_text(encoding="utf-8"))["user_config"]


def test_first_start_rejects_save_after_another_session_created_file(
    tmp_path: Path,
) -> None:
    store = UserConfigStore(user_path=tmp_path / "user_config.yml")
    draft = store.read()
    store.user_path.write_text("user_config: {}\n", encoding="utf-8")

    with pytest.raises(RevisionConflictError):
        store.save(draft["user_config"], draft["revision"])


def test_invalid_existing_source_stays_editable_with_its_revision(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.user_path.write_text("user_config: {model_version: 1}\n", encoding="utf-8")

    draft = store.read()

    assert draft["setup_required"] is False
    assert draft["user_config"]["model_version"] == 1
    assert draft["validation_error"]
    assert draft["revision"] != "absent"


def test_malformed_existing_yaml_can_be_replaced_after_import(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.user_path.write_text("user_config: [\n", encoding="utf-8")
    draft = store.read()
    source = (BACKEND_DIR / "config" / "user_config.example.yml").read_text(
        encoding="utf-8"
    )

    imported = store.import_yaml(source)
    saved = store.save(imported["user_config"], draft["revision"])

    assert draft["validation_error"]
    assert saved["setup_required"] is False
    assert store.read()["validation_error"] is None


def test_import_previews_valid_yaml_without_replacing_existing_file(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    before = store.user_path.read_bytes()
    source = (BACKEND_DIR / "config" / "user_config.example.yml").read_text(
        encoding="utf-8"
    )

    preview = store.import_yaml(source)

    assert preview["user_config"]["model_version"] == 2
    assert store.user_path.read_bytes() == before


def test_import_rejects_system_config_and_invalid_user_source(tmp_path: Path) -> None:
    store = _store(tmp_path)
    source = (BACKEND_DIR / "config" / "user_config.example.yml").read_text(
        encoding="utf-8"
    )

    with pytest.raises(ValueError, match="only a user_config mapping"):
        store.import_yaml(source + "\nsystem_config: {}\n")
    with pytest.raises(ValueError):
        store.import_yaml("user_config:\n  model_version: 2\n")


def test_http_first_setup_import_and_save(tmp_path: Path) -> None:
    store = UserConfigStore(user_path=tmp_path / "user_config.yml")
    UserConfigRequestHandler.store = store
    server = ConfigurationHttpServer(("127.0.0.1", 0), UserConfigRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = f"http://127.0.0.1:{server.server_port}/api/config"
    source = (BACKEND_DIR / "config" / "user_config.example.yml").read_text(
        encoding="utf-8"
    )
    try:
        with urlopen(address) as response:
            draft = json.load(response)
        with urlopen(
            Request(
                address + "/import",
                data=json.dumps({"yaml": source}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ) as response:
            imported = json.load(response)
        assert not store.user_path.exists()

        with urlopen(
            Request(
                address,
                data=json.dumps(
                    {
                        "user_config": imported["user_config"],
                        "revision": draft["revision"],
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
        ) as response:
            saved = json.load(response)

        assert draft["setup_required"] is True
        assert saved["setup_required"] is False
        assert saved["restart_required"] is True
        assert store.user_path.exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_save_validates_and_atomically_replaces_user_source(tmp_path: Path) -> None:
    store = _store(tmp_path)
    original = store.read()
    edited = original["user_config"]
    edited["installation"]["component_settings"]["temperature"] = {
        "low_temperature_c": 17.0,
        "high_temperature_c": 27.0,
    }

    saved = store.save(edited, original["revision"])
    persisted = yaml.safe_load(store.user_path.read_text(encoding="utf-8"))

    assert saved["restart_required"] is True
    assert saved["revision"] != original["revision"]
    assert (
        persisted["user_config"]["installation"]["component_settings"]["temperature"][
            "low_temperature_c"
        ]
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


def test_save_rejects_unavailable_ha_location_without_changing_file(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.home_assistant_config_provider = lambda: {}
    original = store.read()
    original_bytes = store.user_path.read_bytes()

    with pytest.raises(ValueError, match="latitude"):
        store.save(original["user_config"], original["revision"])

    assert store.user_path.read_bytes() == original_bytes
