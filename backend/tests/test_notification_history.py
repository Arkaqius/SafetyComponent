"""Evidence contracts for the notification journal exposed to SafetyHome."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from components.core.types_common import FaultState
from components.notification_manager.history import HISTORY_LIMIT
from components.notification_manager.notification_manager import NotificationManager
from components.notification_manager.state_store import JsonNotificationStateStore


def make_manager(**kwargs: Any) -> NotificationManager:
    """Create a manager whose mobile calls never leave the test process."""
    app = Mock()
    app.call_service.return_value = {"success": True, "result": {}}
    return NotificationManager(app, kwargs.pop("config", {}), **kwargs)


def test_set_and_healed_are_distinct_timestamped_records_surviving_restart(
    tmp_path: Path,
) -> None:
    store = JsonNotificationStateStore(str(tmp_path / "state.json"))
    clock = Mock(return_value=1000.0)
    manager = make_manager(state_store=store, clock=clock)
    manager.notify("Temperature", 2, FaultState.SET, {"location": "Biuro"}, "tag")
    clock.return_value = 1100.0
    manager.notify("Temperature", 2, FaultState.CLEARED, None, "tag")
    restored = make_manager(state_store=store)

    active, healed = restored.notification_history
    assert active["fault_state"] == "SET"
    assert healed["fault_state"] == "CLEARED"
    assert active["id"] != healed["id"]
    assert active["attempted_at"] == "1970-01-01T00:16:40+00:00"
    assert healed["attempted_at"] == "1970-01-01T00:18:20+00:00"
    assert active["service"] == "notify/all_phones"
    assert active["result"] == "accepted_by_home_assistant"
    assert active["tag"] == healed["tag"] == "tag"
    assert "Biuro" in active["message"]
    assert restored.active_notification == {}


def test_partial_failure_and_retry_record_only_actual_target_attempts() -> None:
    clock = Mock(return_value=1000.0)
    manager = make_manager(
        clock=clock, config={"mobile": {"services": ["notify/one", "notify/two"]}}
    )
    manager.hass_app.call_service.side_effect = [
        {"success": True},
        RuntimeError("private transport details"),
        {"success": True},
    ]
    manager.notify("Fault", 3, FaultState.SET, None, "tag")
    clock.return_value = 1060.0
    manager.tick()

    entries = manager.notification_history
    assert [(e["service"], e["result"], e["attempt"]) for e in entries] == [
        ("notify/one", "accepted_by_home_assistant", 1),
        ("notify/two", "failed", 1),
        ("notify/two", "accepted_by_home_assistant", 2),
    ]
    assert entries[-1]["deadline_missed"] is True
    assert len({e["id"] for e in entries}) == 3
    assert "private transport details" not in json.dumps(entries)
    assert manager.pending_deliveries == {}


def test_offline_queue_is_not_a_sent_notification_and_clear_replaces_unsent_set() -> (
    None
):
    manager = make_manager()
    manager.wan_online = False
    manager.notify("Fault", 2, FaultState.SET, None, "tag")
    manager.notify("Fault", 2, FaultState.CLEARED, None, "tag")
    assert manager.notification_history == []
    manager.wan_online = True
    manager.tick()
    assert [e["fault_state"] for e in manager.notification_history] == ["CLEARED"]


def test_shadowed_command_is_not_healing_and_level_four_does_not_send() -> None:
    manager = make_manager()
    manager.notify("Fault", 4, FaultState.SET, None, "info")
    assert manager.notification_history == []
    manager.notify("Fault", 2, FaultState.SHADOWED, None, "tag")
    assert manager.notification_history[0]["fault_state"] == "SHADOWED"
    assert manager.notification_history[0]["kind"] == "clear"


def test_history_is_bounded_and_records_are_not_mutated_by_later_updates() -> None:
    manager = make_manager()
    manager.notify("Fault", 2, FaultState.SET, {"location": "First"}, "tag")
    first = dict(manager.notification_history[0])
    manager.notify("Fault", 2, FaultState.SET, {"location": "Second"}, "tag")
    assert manager.notification_history[0] == first
    assert manager.notification_history[-1]["kind"] == "update"
    for index in range(HISTORY_LIMIT):
        manager.notify("Fault", 2, FaultState.SET, None, f"tag-{index}")
    assert len(manager.notification_history) == HISTORY_LIMIT
    assert manager.notification_history[0]["tag"] == "tag-0"
    assert manager.notification_history[-1]["tag"] == "tag-99"


def test_history_contains_only_filtered_bounded_message_not_private_details() -> None:
    manager = make_manager()
    manager.notify(
        "Fault",
        2,
        FaultState.SET,
        {"location": "X" * 3000, "password": "PRIVATE"},
        "tag",
    )
    entry = manager.notification_history[0]
    assert len(entry["message"]) == 2048
    assert entry["text_truncated"] is True
    assert "PRIVATE" not in json.dumps(entry)


@pytest.mark.parametrize("raw", [None, {}, "broken", [None, {}, {"kind": []}]])
def test_damaged_history_does_not_discard_active_notification(
    tmp_path: Path, raw: Any
) -> None:
    store = JsonNotificationStateStore(str(tmp_path / "state.json"))
    manager = make_manager(state_store=store)
    manager.notify("Fault", 2, FaultState.SET, None, "tag")
    snapshot = store.load()
    snapshot["notification_history"] = raw
    store.save(snapshot)
    restored = make_manager(state_store=store)
    assert "tag" in restored.active_notification
    assert restored.notification_history == []


def test_legacy_snapshot_without_history_remains_valid(tmp_path: Path) -> None:
    store = JsonNotificationStateStore(str(tmp_path / "state.json"))
    manager = make_manager(state_store=store)
    manager.notify("Fault", 2, FaultState.SET, None, "tag")
    snapshot = store.load()
    del snapshot["notification_history"]
    store.save(snapshot)
    restored = make_manager(state_store=store)
    assert "tag" in restored.active_notification
    assert restored.notification_history == []


def test_journal_is_persisted_but_not_published_as_an_mqtt_entity() -> None:
    mqtt = Mock()
    manager = make_manager(mqtt_entities=mqtt)
    manager.start()
    manager.notify("Fault", 2, FaultState.SET, None, "tag")
    manager.notify("Fault", 2, FaultState.CLEARED, None, "tag")
    assert [entry["fault_state"] for entry in manager.notification_history] == [
        "SET",
        "CLEARED",
    ]
    assert not any(
        call.args and call.args[0] == "sensor.notification_history"
        for call in mqtt.register_sensor.call_args_list
    )
    assert not any(
        call.args and call.args[0] == "sensor.notification_history"
        for call in mqtt.publish_sensor_state.call_args_list
    )


def test_l1_repeat_and_exhaustion_remain_distinguishable() -> None:
    clock = Mock(return_value=1000.0)
    manager = make_manager(clock=clock)
    manager.notify("Fault", 1, FaultState.SET, None, "tag")
    clock.return_value = 1060.0
    manager.tick()
    assert [e["kind"] for e in manager.notification_history] == ["new", "repeat"]
    manager = make_manager(config={"retry": {"max_attempts": 1}})
    manager.hass_app.call_service.side_effect = RuntimeError("failed")
    manager.notify("Fault", 2, FaultState.SET, None, "tag")
    assert manager.notification_history[-1]["result"] == "failed"
    assert manager.pending_deliveries == {}


def test_acknowledgement_refresh_is_recorded_as_active_fault_submission() -> None:
    manager = make_manager()
    manager.notify("Fault", 2, FaultState.SET, None, "tag")

    manager.handle_mobile_action(
        "mobile_app_notification_action",
        {"action": "SAFETY_ACK_tag"},
        {},
    )

    assert [entry["kind"] for entry in manager.notification_history] == [
        "new",
        "acknowledged",
    ]
    assert manager.notification_history[-1]["fault_state"] == "SET"
