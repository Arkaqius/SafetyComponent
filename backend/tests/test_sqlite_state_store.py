"""Migration, durability, isolation and failure contracts for local SQLite."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic
from unittest.mock import Mock

import pytest

from components.core.battery_fault_catalog import BatteryFaultCatalog
from components.core.sqlite_state_store import SqliteStateDatabase, state_database_path
from components.core.types_common import FaultState, RecoveryAction, RecoveryActionState
from components.notification_manager.notification_manager import NotificationManager
from components.notification_manager.state_store import JsonNotificationStateStore


@pytest.fixture
def database(tmp_path: Path) -> SqliteStateDatabase:
    return SqliteStateDatabase(tmp_path / "safety_state.sqlite3")


@pytest.mark.parametrize(
    "name",
    [
        "notification_state",
        "recovery_state",
        "fault_evidence_state",
        "internal_environment_state",
        "periodic_test_state",
        "detector_test_state",
        "battery_fault_catalog",
    ],
)
def test_import_once_survives_restart_and_never_resurrects_old_json(
    database: SqliteStateDatabase,
    tmp_path: Path,
    name: str,
) -> None:
    legacy = tmp_path / f"{name}.json"
    original = {
        "version": 2,
        "records": {"stable-id": {"active": True, "name": "Łazienka"}},
    }
    raw = json.dumps(original, ensure_ascii=False).encode("utf-8")
    legacy.write_bytes(raw)
    store = database.store(name, legacy)
    assert store.load() == original
    store.save({"version": 2, "records": {}})
    restarted = SqliteStateDatabase(database.path).store(name, legacy)
    assert restarted.load() == {"version": 2, "records": {}}
    assert legacy.read_bytes() == raw
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT legacy_sha256 FROM stores").fetchone()[0]


def test_missing_legacy_is_also_imported_once(database, tmp_path) -> None:
    legacy = tmp_path / "later.json"
    assert database.store("state", legacy).load() == {}
    legacy.write_text('{"active": true}', encoding="utf-8")
    assert database.store("state", legacy).load() == {}


@pytest.mark.parametrize("raw", [b"broken", b"[]", b"null"])
def test_malformed_import_fails_without_marker_or_overwriting_source(
    database,
    tmp_path,
    raw,
) -> None:
    legacy = tmp_path / "broken.json"
    legacy.write_bytes(raw)
    store = database.store("state", legacy)
    with pytest.raises(ValueError):
        store.load()
    with pytest.raises(ValueError):
        store.save({"active": False})
    assert legacy.read_bytes() == raw
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM stores").fetchone()[0] == 0


def test_import_failure_rolls_back_marker_and_all_records(
    database, tmp_path, monkeypatch
) -> None:
    legacy = tmp_path / "state.json"
    legacy.write_text(
        '{"history": [{"id": "first"}, {"id": "second"}]}', encoding="utf-8"
    )
    store = database.store("state", legacy)
    write = store._write

    def interrupted(connection, snapshot):
        write(connection, snapshot)
        raise OSError("interrupted import")

    monkeypatch.setattr(store, "_write", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        store.load()
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM stores").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 0
    monkeypatch.setattr(store, "_write", write)
    assert store.load()["history"] == [{"id": "first"}, {"id": "second"}]


def test_failed_save_preserves_prior_transaction_and_other_store(
    database, tmp_path
) -> None:
    store = database.store("alarm", tmp_path / "alarm.json")
    other = database.store("recovery", tmp_path / "recovery.json")
    original = {"active": True, "records": [{"id": "incident", "ack": True}]}
    store.save(original)
    other.save({"proposal": "pending"})
    with sqlite3.connect(database.path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_write BEFORE INSERT ON records "
            "WHEN NEW.store='alarm' BEGIN SELECT RAISE(ABORT,'test interruption'); END"
        )
    with pytest.raises(OSError, match="test interruption"):
        store.save({"active": False, "records": [{"id": "replacement"}]})
    assert store.load() == original
    assert other.load() == {"proposal": "pending"}


def test_writer_lock_wait_is_short_and_failure_does_not_clear_alarm(
    database, tmp_path
) -> None:
    store = database.store("alarm", tmp_path / "alarm.json")
    store.save({"active": True})
    lock = sqlite3.connect(database.path)
    try:
        lock.execute("BEGIN IMMEDIATE")
        started = monotonic()
        with pytest.raises(OSError, match="locked"):
            store.save({"active": False})
        assert monotonic() - started < 0.5
        # WAL readers retain the previous committed state while the writer holds a lock.
        assert store.load() == {"active": True}
    finally:
        lock.rollback()
        lock.close()
    assert store.load() == {"active": True}


def test_callback_threads_use_independent_connections_and_namespaces(
    database, tmp_path
) -> None:
    database.store("init", tmp_path / "init.json").load()

    def write(name: str) -> None:
        store = database.store(name, tmp_path / f"{name}.json")
        store.save({"records": {name: {"active": True}}})

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(write, ["notification", "recovery", "internal", "evidence"]))
    for name in ("notification", "recovery", "internal", "evidence"):
        assert database.store(name, tmp_path / f"{name}.json").load() == {
            "records": {name: {"active": True}}
        }


def test_collections_are_separate_rows_and_changes_remove_only_obsolete_records(
    database, tmp_path
) -> None:
    store = database.store("state", tmp_path / "state.json")
    store.save(
        {
            "version": 1,
            "history": [{"id": "one"}, {"id": "two"}],
            "active": {"tag": True},
        }
    )
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 3
        connection.execute("CREATE TABLE updates (count INTEGER)")
        connection.execute("INSERT INTO updates VALUES (0)")
        connection.execute(
            "CREATE TRIGGER track_updates AFTER UPDATE ON records "
            "BEGIN UPDATE updates SET count=count+1; END"
        )
    store.save(store.load())
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT count FROM updates").fetchone()[0] == 0
    store.save({"version": 1, "history": [], "active": False})
    assert store.load() == {"version": 1, "history": [], "active": False}
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 0
    store.save({})
    assert store.load() == {}


@pytest.mark.parametrize("foreign", ["version", "identity", "schema", "corrupt"])
def test_future_foreign_and_corrupt_database_never_fall_back_to_json(
    database, tmp_path, foreign
) -> None:
    legacy = tmp_path / "state.json"
    legacy.write_text('{"active": false}', encoding="utf-8")
    if foreign == "corrupt":
        database.path.write_bytes(b"corrupt database")
    else:
        with sqlite3.connect(database.path) as connection:
            if foreign == "version":
                connection.execute("PRAGMA user_version=999")
            elif foreign == "identity":
                connection.execute("PRAGMA application_id=123")
            else:
                connection.execute("CREATE TABLE other_app (value TEXT)")
    before = database.path.read_bytes()
    with pytest.raises((OSError, ValueError)):
        database.store("state", legacy).load()
    assert database.path.read_bytes() == before


def test_evidence_size_bound_applies_to_import_save_and_load(
    database, tmp_path
) -> None:
    legacy = tmp_path / "evidence.json"
    store = database.store("evidence", legacy, max_bytes=80)
    store.save({"records": {"fault": {"active": True}}})
    with pytest.raises(ValueError, match="bound"):
        store.save({"records": {"fault": {"frame": "x" * 100}}})
    assert store.load()["records"]["fault"]["active"] is True
    with sqlite3.connect(database.path) as connection:
        connection.execute(
            "UPDATE records SET value=?", (json.dumps({"frame": "x" * 100}),)
        )
    with pytest.raises(ValueError, match="bound"):
        store.load()
    legacy.write_text(json.dumps({"frame": "x" * 100}), encoding="utf-8")
    with pytest.raises(ValueError, match="bound"):
        database.store("new", legacy, max_bytes=80).load()


def test_notification_history_acknowledgement_and_pending_state_survive_json_migration(
    database, tmp_path
) -> None:
    legacy = tmp_path / "notification.json"
    app = Mock()
    app.call_service.return_value = {"success": True, "result": {}}
    manager = NotificationManager(
        app, {}, state_store=JsonNotificationStateStore(str(legacy))
    )
    manager.notify("Temperature", 2, FaultState.SET, {"location": "Biuro"}, "tag")
    manager.handle_ui_acknowledgement("safety_notification_ack", {"tag": "tag"})
    snapshot = json.loads(legacy.read_text(encoding="utf-8"))
    store = database.store("notification_state", legacy)
    restored = NotificationManager(app, {}, state_store=store)
    assert restored.notification_history == manager.notification_history
    assert restored.active_notification == manager.active_notification
    assert restored.active_notification["tag"]["acknowledged"] is True
    assert store.load() == snapshot
    restored.notify("Temperature", 2, FaultState.CLEARED, None, "tag")
    restarted = NotificationManager(
        app,
        {},
        state_store=SqliteStateDatabase(database.path).store(
            "notification_state", legacy
        ),
    )
    assert restarted.active_notification == {}
    assert restarted.notification_history[-1]["fault_state"] == "CLEARED"
    assert json.loads(legacy.read_text(encoding="utf-8")) == snapshot


def test_battery_retirement_identities_survive_sqlite_restart(
    database, tmp_path
) -> None:
    legacy = tmp_path / "battery.json"
    BatteryFaultCatalog(legacy).save(
        {"RemoteBatteryLowActive"}, {"RemoteBatteryLowRetired"}
    )
    catalog = BatteryFaultCatalog(
        legacy, state_store=database.store("battery_fault_catalog", legacy)
    )
    assert catalog.load() == ({"RemoteBatteryLowActive"}, {"RemoteBatteryLowRetired"})
    catalog.save(set(), {"RemoteBatteryLowActive", "RemoteBatteryLowRetired"})
    restarted = BatteryFaultCatalog(
        legacy,
        state_store=SqliteStateDatabase(database.path).store(
            "battery_fault_catalog", legacy
        ),
    )
    assert restarted.load() == (
        set(),
        {"RemoteBatteryLowActive", "RemoteBatteryLowRetired"},
    )


def test_invalid_battery_legacy_is_not_imported_and_can_be_corrected(
    database, tmp_path
) -> None:
    legacy = tmp_path / "battery.json"
    legacy.write_text("{}", encoding="utf-8")
    store = database.store(
        "battery_fault_catalog",
        legacy,
        legacy_validator=BatteryFaultCatalog.validate_snapshot,
    )
    with pytest.raises(ValueError, match="version"):
        store.load()
    BatteryFaultCatalog(legacy).save({"RemoteBatteryLowActive"}, set())
    assert store.load()["active"] == ["RemoteBatteryLowActive"]


def test_notification_restore_failure_reports_durability_and_never_reads_legacy_clear(
    database, tmp_path
) -> None:
    legacy = tmp_path / "notification.json"
    store = database.store("notification_state", legacy)
    store.save({"version": 1, "active_notifications": {"tag": {"acknowledged": True}}})
    database.path.write_bytes(b"corrupt database")
    legacy.write_text('{"version": 1, "active_notifications": {}}', encoding="utf-8")
    observer = Mock()
    manager = NotificationManager(
        Mock(), {}, state_store=store, diagnostics_observer=observer
    )
    assert manager._last_result == "state_restore_failed"
    observer.assert_any_call(
        "persistence", True, detail="notification_state", operation="load"
    )


def test_pending_notification_deadline_survives_migration_without_resend(
    database, tmp_path
) -> None:
    legacy = tmp_path / "notification.json"
    app = Mock()
    app.call_service.return_value = {"success": False, "error": "offline"}
    manager = NotificationManager(
        app, {}, clock=lambda: 1000, state_store=JsonNotificationStateStore(str(legacy))
    )
    manager.notify("Temperature", 2, FaultState.SET, None, "tag")
    assert manager.pending_deliveries
    calls = app.call_service.call_count
    restored = NotificationManager(
        app,
        {},
        clock=lambda: 1000,
        state_store=database.store("notification_state", legacy),
    )
    assert {
        key: value.to_dict() for key, value in restored.pending_deliveries.items()
    } == {key: value.to_dict() for key, value in manager.pending_deliveries.items()}
    assert app.call_service.call_count == calls


def test_recovery_migration_rotates_confirmation_without_replaying_actuator(
    database,
    tmp_path,
    mocked_hass_app_with_temp_component,
) -> None:
    app, *_ = mocked_hass_app_with_temp_component
    app.initialize()
    manager = app.reco_man
    proposal_id = "ExternalWeatherExposureWindExternalGate"
    action = RecoveryAction(
        "CloseExternalOpeningExternalGate", {"friendly_name": "Close gate"}, Mock()
    )
    manager.recovery_actions = {proposal_id: action}
    manager._proposals = {}
    legacy = tmp_path / "recovery.json"
    legacy.write_text(
        json.dumps(
            {
                "version": 1,
                "proposals": [
                    {
                        "proposal_id": proposal_id,
                        "action_name": action.name,
                        "execution_policy": "user_confirmed",
                        "status": "AWAITING_CONFIRMATION",
                        "confirmation_token": "previous-token",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manager.state_store = database.store("recovery_state", legacy)
    app.call_service.reset_mock()
    manager._restore_state()
    restored = manager._proposals[proposal_id]
    assert restored["status"] == RecoveryActionState.AWAITING_CONFIRMATION.name
    assert restored["confirmation_token"] != "previous-token"
    assert not any(
        call.args[0] == "cover/close_cover" for call in app.call_service.call_args_list
    )


def test_database_location_follows_existing_persistent_directory() -> None:
    assert state_database_path("/config/appdaemon/fault_evidence_state.json") == Path(
        "/config/appdaemon/safety_state.sqlite3"
    )
