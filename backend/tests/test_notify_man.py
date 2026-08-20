"""Notification lifecycle, transport, retry, and persistence contracts."""

from __future__ import annotations

from unittest.mock import Mock, call

import pytest

from components.core.localization import Localizer
from components.core.types_common import FaultState
from components.notification_manager.local_annunciator import LocalAnnunciator
from components.notification_manager.notification_manager import NotificationManager
from components.notification_manager.state_store import (
    InMemoryNotificationStateStore,
)


class Clock:
    def __init__(self, value: float = 1_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def make_hass() -> Mock:
    hass = Mock()
    # AppDaemon normally returns None after a service call completes without error.
    hass.call_service = Mock(return_value=None)
    hass.get_state = Mock(return_value=None)
    hass.listen_state = Mock()
    hass.listen_event = Mock()
    hass.run_every = Mock(return_value="timer")
    hass.log = Mock()
    return hass


def notify_calls(hass: Mock) -> list:
    return [
        item
        for item in hass.call_service.call_args_list
        if item.args[0].startswith("notify/")
    ]


def test_l1_uses_explicit_group_and_exact_cross_platform_profile() -> None:
    hass = make_hass()
    manager = NotificationManager(hass, {})

    manager.notify(
        "SmokeAlarm",
        1,
        FaultState.SET,
        {"location": "Kitchen"},
        "tag-l1",
        friendly_name="Smoke alarm",
    )

    service_call = notify_calls(hass)[-1]
    assert service_call.args == ("notify/all_phones",)
    assert "return_result" not in service_call.kwargs
    assert service_call.kwargs["title"] == "Immediate action needed"
    assert service_call.kwargs["message"] == (
        "Smoke alarm needs your attention.\nLocation: Kitchen"
    )
    assert service_call.kwargs["data"] == {
        "tag": "tag-l1",
        "url": "https://ha.kojbito.org/5c36e1c9_hakit",
        "clickAction": "https://ha.kojbito.org/5c36e1c9_hakit",
        "persistent": True,
        "sticky": True,
        "color": "#FF0000",
        "notification_icon": "mdi:exit-run",
        "channel": "Safety critical",
        "importance": "max",
        "actions": [{"action": "SAFETY_ACK_tag-l1", "title": "Acknowledge"}],
        "priority": "high",
        "ttl": 0,
        "vibrationPattern": "100, 1000, 100, 1000, 100",
        "push": {"interruption-level": "time-sensitive"},
    }
    assert manager.pending_deliveries == {}
    assert manager._last_result == "accepted_by_home_assistant"


@pytest.mark.parametrize(
    ("level", "channel", "importance", "priority", "interruption"),
    [
        (2, "Safety hazards", "high", "high", "time-sensitive"),
        (3, "Safety warnings", "default", "normal", "active"),
    ],
)
def test_l2_l3_profiles(
    level: int,
    channel: str,
    importance: str,
    priority: str,
    interruption: str,
) -> None:
    hass = make_hass()
    manager = NotificationManager(hass, {})

    manager.notify("Fault", level, FaultState.SET, None, f"tag-{level}")

    data = notify_calls(hass)[-1].kwargs["data"]
    assert data["channel"] == channel
    assert data["importance"] == importance
    assert data["priority"] == priority
    assert data["push"] == {"interruption-level": interruption}


def test_active_update_is_quiet_and_keeps_recovery_guidance() -> None:
    hass = make_hass()
    manager = NotificationManager(hass, {})
    manager.notify(
        "RiskyTemperature",
        2,
        FaultState.SET,
        {"location": "Office"},
        "same-tag",
        friendly_name="Unsafe temperature",
    )
    manager._add_recovery_action("Close the office window.", "same-tag")
    manager.notify(
        "RiskyTemperature",
        2,
        FaultState.SET,
        {"location": "Office, Kitchen"},
        "same-tag",
        friendly_name="Unsafe temperature",
    )

    assert list(manager.active_notification) == ["same-tag"]
    assert manager.active_notification["same-tag"]["message"] == (
        "Unsafe temperature needs your attention.\n"
        "Location: Office, Kitchen\n\n"
        "What you can do:\n- Close the office window."
    )
    data = notify_calls(hass)[-1].kwargs["data"]
    assert data["alert_once"] is True
    assert data["priority"] == "normal"
    assert data["push"] == {"interruption-level": "passive"}
    assert "ttl" not in data


def test_same_tag_escalation_is_a_new_alert_and_starts_l1_policy() -> None:
    hass = make_hass()
    clock = Clock()
    manager = NotificationManager(
        hass,
        {"local": {"alarm_entity": "alarm_control_panel.house"}},
        clock=clock,
    )
    manager.notify("Fault", 3, FaultState.SET, None, "escalation-tag")
    hass.call_service.reset_mock()

    manager.notify("Fault", 1, FaultState.SET, None, "escalation-tag")

    push = notify_calls(hass)[0].kwargs
    assert "alert_once" not in push["data"]
    assert push["data"]["priority"] == "high"
    assert manager.active_notification["escalation-tag"]["acknowledged"] is False
    assert manager.active_notification["escalation-tag"]["next_repeat_at"] == 1060
    assert (
        call(
            "alarm_control_panel/alarm_trigger",
            entity_id="alarm_control_panel.house",
        )
        in hass.call_service.call_args_list
    )


def test_same_tag_deescalation_cancels_l1_repeat_schedule() -> None:
    hass = make_hass()
    hass.get_state.return_value = {
        "state": "on",
        "attributes": {"brightness": 20},
    }
    manager = NotificationManager(hass, {"local": {"light_entity": "light.warning"}})
    manager.notify("Fault", 1, FaultState.SET, None, "deescalation-tag")
    hass.call_service.reset_mock()

    manager.notify("Fault", 3, FaultState.SET, None, "deescalation-tag")

    assert manager.active_notification["deescalation-tag"]["next_repeat_at"] is None
    assert (
        call("light/turn_on", entity_id="light.warning", brightness=20)
        in hass.call_service.call_args_list
    )


def test_shadowed_fault_uses_companion_clear_command() -> None:
    hass = make_hass()
    manager = NotificationManager(hass, {})
    manager.notify("Fault", 2, FaultState.SET, None, "tag-clear")
    hass.call_service.reset_mock()

    manager.notify("Fault", 2, FaultState.SHADOWED, None, "tag-clear")

    hass.call_service.assert_called_once_with(
        "notify/all_phones",
        message="clear_notification",
        data={"tag": "tag-clear"},
    )
    assert "tag-clear" not in manager.active_notification


def test_cleared_fault_uses_same_tag_and_resolved_quiet_profile() -> None:
    hass = make_hass()
    manager = NotificationManager(hass, {})
    manager.notify("Fault", 3, FaultState.SET, None, "tag-resolved")
    hass.call_service.reset_mock()

    manager.notify("Fault", 3, FaultState.CLEARED, None, "tag-resolved")

    sent = hass.call_service.call_args
    assert sent.kwargs["title"] == "Safety issue resolved"
    assert sent.kwargs["message"] == "Good news - Fault is no longer active."
    assert sent.kwargs["data"]["tag"] == "tag-resolved"
    assert sent.kwargs["data"]["persistent"] is False
    assert sent.kwargs["data"]["sticky"] is False
    assert sent.kwargs["data"]["push"] == {"interruption-level": "passive"}
    assert "actions" not in sent.kwargs["data"]


def test_allowlist_prevents_unapproved_context_from_push_and_state() -> None:
    hass = make_hass()
    store = InMemoryNotificationStateStore()
    manager = NotificationManager(hass, {}, state_store=store)

    manager.notify(
        "Fault",
        3,
        FaultState.SET,
        {"location": "Office", "access_token": "must-not-leak"},
        "safe-tag",
    )

    assert "must-not-leak" not in hass.call_service.call_args.kwargs["message"]
    assert "must-not-leak" not in str(store.snapshot)


def test_partial_failure_retries_only_failed_target() -> None:
    hass = make_hass()
    clock = Clock()
    failed_once = True

    def service_result(service: str, **_: object):
        nonlocal failed_once
        if service == "notify/phone_two" and failed_once:
            failed_once = False
            return {"success": False, "error": "temporary"}
        return {"success": True}

    hass.call_service.side_effect = service_result
    manager = NotificationManager(
        hass,
        {"mobile": {"services": ["notify/phone_one", "notify/phone_two"]}},
        clock=clock,
    )

    manager.notify("Fault", 2, FaultState.SET, None, "retry-tag")
    assert manager.pending_deliveries["retry-tag:active"].target_services == (
        "notify/phone_two",
    )
    clock.advance(5)
    manager.tick()

    assert manager.pending_deliveries == {}
    assert [item.args[0] for item in hass.call_service.call_args_list] == [
        "notify/phone_one",
        "notify/phone_two",
        "notify/phone_two",
    ]


def test_update_keeps_undelivered_target_alerting_and_quiets_completed_target() -> None:
    hass = make_hass()
    clock = Clock()
    phone_two_attempts = 0

    def service_result(service: str, **_: object) -> dict[str, object]:
        nonlocal phone_two_attempts
        if service == "notify/phone_two":
            phone_two_attempts += 1
            if phone_two_attempts == 1:
                return {"success": False, "error": "temporary"}
        return {"success": True}

    hass.call_service.side_effect = service_result
    manager = NotificationManager(
        hass,
        {"mobile": {"services": ["notify/phone_one", "notify/phone_two"]}},
        clock=clock,
    )
    manager.notify("Fault", 2, FaultState.SET, None, "split-tag")
    hass.call_service.reset_mock()

    manager.notify("Fault", 2, FaultState.SET, {"location": "Office"}, "split-tag")

    quiet_update = hass.call_service.call_args_list[0]
    assert quiet_update.args[0] == "notify/phone_one"
    assert quiet_update.kwargs["data"]["alert_once"] is True
    pending_new = manager.pending_deliveries["split-tag:active"]
    assert pending_new.kind == "new"
    assert pending_new.target_services == ("notify/phone_two",)
    assert "Office" in pending_new.message

    clock.advance(5)
    manager.tick()

    phone_two_retry = hass.call_service.call_args_list[-1]
    assert phone_two_retry.args[0] == "notify/phone_two"
    assert "alert_once" not in phone_two_retry.kwargs["data"]


def test_wan_unknown_queues_and_confirmed_recovery_flushes() -> None:
    hass = make_hass()
    hass.get_state.return_value = "unavailable"
    manager = NotificationManager(hass, {"wan_entity": "binary_sensor.wan"})
    manager.start()

    manager.notify("Fault", 2, FaultState.SET, None, "wan-tag")
    assert notify_calls(hass) == []
    assert "wan-tag:active" in manager.pending_deliveries
    assert manager._channel_status["notify/all_phones"]["status"] == "queued"

    manager.handle_wan_state("binary_sensor.wan", "state", "unavailable", "on")
    assert len(notify_calls(hass)) == 1
    assert manager.pending_deliveries == {}


def test_deadline_miss_is_recorded_when_wan_queue_flushes_late() -> None:
    hass = make_hass()
    clock = Clock()
    manager = NotificationManager(
        hass, {"wan_entity": "binary_sensor.wan"}, clock=clock
    )
    manager.wan_online = False
    manager.notify("Fault", 1, FaultState.SET, None, "late-tag")
    clock.advance(11)

    manager.handle_wan_state("binary_sensor.wan", "state", "off", "on")

    assert manager._counters["deadline_misses"] == 1


def test_deadline_miss_is_recorded_while_wan_remains_offline() -> None:
    clock = Clock()
    manager = NotificationManager(
        make_hass(), {"wan_entity": "binary_sensor.wan"}, clock=clock
    )
    manager.wan_online = False
    manager.notify("Fault", 1, FaultState.SET, None, "offline-late-tag")
    clock.advance(11)

    manager.tick()
    manager.tick()

    assert manager._counters["deadline_misses"] == 1
    assert manager.pending_deliveries["offline-late-tag:active"].deadline_missed is True


def test_deadline_miss_includes_time_spent_waiting_for_ha_acceptance() -> None:
    clock = Clock()
    hass = make_hass()

    def delayed_acceptance(*_: object, **__: object) -> dict[str, bool]:
        clock.advance(11)
        return {"success": True}

    hass.call_service.side_effect = delayed_acceptance
    manager = NotificationManager(hass, {}, clock=clock)

    manager.notify("Fault", 1, FaultState.SET, None, "slow-ha-tag")

    assert manager._counters["deadline_misses"] == 1
    assert manager._last_success_at == 1011


def test_acknowledgement_suppresses_l1_repeats_without_clearing_fault() -> None:
    hass = make_hass()
    clock = Clock()
    manager = NotificationManager(hass, {}, clock=clock)
    manager.notify("Fault", 1, FaultState.SET, None, "ack-tag")
    manager.handle_mobile_action(
        "mobile_app_notification_action",
        {"action": "SAFETY_ACK_ack-tag"},
    )
    call_count = len(notify_calls(hass))
    clock.advance(120)
    manager.tick()

    assert len(notify_calls(hass)) == call_count
    assert manager.active_notification["ack-tag"]["acknowledged"] is True


def test_l1_repeats_are_bounded() -> None:
    hass = make_hass()
    clock = Clock()
    manager = NotificationManager(
        hass,
        {
            "level_one_repeat": {
                "enabled": True,
                "interval_seconds": 10,
                "max_repeats": 2,
            }
        },
        clock=clock,
    )
    manager.notify("Fault", 1, FaultState.SET, None, "repeat-tag")
    for _ in range(3):
        clock.advance(10)
        manager.tick()

    assert len(notify_calls(hass)) == 3  # initial + two repeats
    assert manager.active_notification["repeat-tag"]["repeat_count"] == 2
    assert manager.active_notification["repeat-tag"]["next_repeat_at"] is None


def test_active_state_and_acknowledgement_restore_after_restart() -> None:
    store = InMemoryNotificationStateStore()
    first = NotificationManager(make_hass(), {}, state_store=store)
    first.notify("Fault", 1, FaultState.SET, None, "persisted-tag")
    first.handle_mobile_action(
        "mobile_app_notification_action",
        {"action": "SAFETY_ACK_persisted-tag"},
    )

    restored = NotificationManager(make_hass(), {}, state_store=store)

    assert restored.active_notification["persisted-tag"]["acknowledged"] is True
    assert restored.active_notification["persisted-tag"]["next_repeat_at"] is None


def test_authoritative_clear_reconciles_restored_fault_even_when_not_new() -> None:
    store = InMemoryNotificationStateStore()
    first = NotificationManager(make_hass(), {}, state_store=store)
    first.notify("Fault", 2, FaultState.SET, None, "restored-clear-tag")
    restored_hass = make_hass()
    restored = NotificationManager(restored_hass, {}, state_store=store)

    restored.handle_fault_event(
        fault_name="Fault",
        level=2,
        fault_state=FaultState.CLEARED,
        additional_info=None,
        fault_tag="restored-clear-tag",
        should_notify=False,
    )

    assert "restored-clear-tag" not in restored.active_notification
    assert notify_calls(restored_hass)[-1].kwargs["message"].startswith("Good news")


def test_restored_retry_uses_current_explicit_service_configuration() -> None:
    clock = Clock()
    failing_hass = make_hass()
    failing_hass.call_service.return_value = {
        "success": False,
        "error": "offline",
    }
    store = InMemoryNotificationStateStore()
    first = NotificationManager(
        failing_hass,
        {"mobile": {"services": ["notify/old_phone"]}},
        state_store=store,
        clock=clock,
    )
    first.notify("Fault", 2, FaultState.SET, None, "route-tag")

    restored = NotificationManager(
        make_hass(),
        {"mobile": {"services": ["notify/new_phone"]}},
        state_store=store,
        clock=clock,
    )

    assert restored.pending_deliveries["route-tag:active"].target_services == (
        "notify/new_phone",
    )


def test_appdaemon_none_result_is_accepted_without_retry() -> None:
    hass = make_hass()
    hass.call_service.return_value = None
    manager = NotificationManager(hass, {})

    manager.notify("Fault", 3, FaultState.SET, None, "legacy-tag")

    assert manager.pending_deliveries == {}
    assert manager._last_result == "accepted_by_home_assistant"
    assert manager._counters["accepted_attempts"] == 1
    assert manager._counters["failed_attempts"] == 0
    assert manager._last_success_at is not None


def test_start_rejects_configured_service_missing_from_registry() -> None:
    hass = make_hass()
    hass.list_services.return_value = [
        {"namespace": "default", "domain": "notify", "service": "phone_one"}
    ]
    manager = NotificationManager(
        hass, {"mobile": {"services": ["notify/missing_phone"]}}
    )

    with pytest.raises(ValueError, match="unavailable: notify/missing_phone"):
        manager.start()


def test_local_annunciator_ownership_restores_with_manager_state() -> None:
    hass = make_hass()
    hass.get_state.return_value = {
        "state": "on",
        "attributes": {"brightness": 25},
    }
    store = InMemoryNotificationStateStore()
    config = {"local": {"light_entity": "light.warning"}}
    first = NotificationManager(hass, config, state_store=store)
    first.notify("Fault", 2, FaultState.SET, None, "light-tag")

    restored_hass = make_hass()
    restored = NotificationManager(restored_hass, config, state_store=store)
    restored.notify("Fault", 2, FaultState.CLEARED, None, "light-tag")

    assert (
        call("light/turn_on", entity_id="light.warning", brightness=25)
        in restored_hass.call_service.call_args_list
    )


def test_diagnostics_distinguish_ha_acceptance_from_device_delivery() -> None:
    hass = make_hass()
    mqtt = Mock()
    manager = NotificationManager(hass, {}, mqtt_entities=mqtt)
    manager.start()
    manager.notify("Fault", 3, FaultState.SET, None, "diag-tag")

    _, state = mqtt.publish_sensor_state.call_args.args
    attributes = mqtt.publish_sensor_state.call_args.kwargs["attributes"]
    assert state == "healthy"
    assert attributes["last_result"] == "accepted_by_home_assistant"
    assert attributes["delivery_confirmation"] == (
        "Home Assistant acceptance only; device delivery is not confirmed"
    )
    assert attributes["channels"]["notify/all_phones"] == {
        "status": "accepted_by_home_assistant",
        "last_attempt_at": manager._last_attempt_at,
        "last_error": "",
    }


def test_channel_diagnostics_show_partial_target_failure() -> None:
    hass = make_hass()
    hass.call_service.side_effect = [
        {"success": True},
        {"success": False, "error": "phone offline"},
    ]
    mqtt = Mock()
    manager = NotificationManager(
        hass,
        {"mobile": {"services": ["notify/phone_one", "notify/phone_two"]}},
        mqtt_entities=mqtt,
    )

    manager.notify("Fault", 2, FaultState.SET, None, "channel-tag")

    attributes = mqtt.publish_sensor_state.call_args.kwargs["attributes"]
    assert attributes["channels"]["notify/phone_one"]["status"] == (
        "accepted_by_home_assistant"
    )
    assert attributes["channels"]["notify/phone_two"] == {
        "status": "failed",
        "last_attempt_at": manager._last_attempt_at,
        "last_error": "phone offline",
    }


def test_local_annunciator_runs_once_and_is_independent_from_push_updates() -> None:
    hass = make_hass()
    hass.get_state.return_value = {
        "state": "on",
        "attributes": {"brightness": 40},
    }
    local = LocalAnnunciator(hass, {"light_entity": "light.warning"})
    manager = NotificationManager(hass, {}, local_annunciator=local)

    manager.notify("Fault", 2, FaultState.SET, None, "local-tag")
    manager.notify("Fault", 2, FaultState.SET, None, "local-tag")
    light_on_calls = [
        item
        for item in hass.call_service.call_args_list
        if item.args[0] == "light/turn_on"
    ]
    assert len(light_on_calls) == 1

    manager.notify("Fault", 2, FaultState.CLEARED, None, "local-tag")
    assert (
        call("light/turn_on", entity_id="light.warning", brightness=40)
        in hass.call_service.call_args_list
    )


def test_local_annunciator_runs_before_blocking_mobile_submission() -> None:
    hass = make_hass()
    hass.get_state.return_value = {"state": "off", "attributes": {}}
    manager = NotificationManager(hass, {"local": {"light_entity": "light.warning"}})

    manager.notify("Fault", 2, FaultState.SET, None, "ordering-tag")

    service_order = [item.args[0] for item in hass.call_service.call_args_list]
    assert service_order.index("light/turn_on") < service_order.index(
        "notify/all_phones"
    )


def test_non_local_l3_fault_does_not_block_l2_light_restore() -> None:
    hass = make_hass()
    hass.get_state.return_value = {
        "state": "on",
        "attributes": {"brightness": 35},
    }
    manager = NotificationManager(hass, {"local": {"light_entity": "light.warning"}})
    manager.notify("Advisory", 3, FaultState.SET, None, "l3-tag")
    manager.notify("Hazard", 2, FaultState.SET, None, "l2-tag")
    hass.call_service.reset_mock()

    manager.notify("Hazard", 2, FaultState.CLEARED, None, "l2-tag")

    assert (
        call("light/turn_on", entity_id="light.warning", brightness=35)
        in hass.call_service.call_args_list
    )


def test_level_four_never_calls_mobile_transport() -> None:
    hass = make_hass()
    manager = NotificationManager(hass, {})

    manager.notify("Info", 4, FaultState.SET, None, "level-four")

    assert notify_calls(hass) == []


def test_polish_copy_and_acknowledgement_action_are_localized() -> None:
    hass = make_hass()
    manager = NotificationManager(hass, {}, localizer=Localizer({"language": "pl"}))
    manager.notify(
        "RiskyTemperature",
        2,
        FaultState.SET,
        {"location": "Biuro"},
        "tag-pl",
        friendly_name="Niebezpieczna temperatura",
    )

    sent = notify_calls(hass)[-1].kwargs
    assert sent["title"] == "Wykryto zagrożenie w domu"
    assert sent["data"]["actions"][0]["title"] == "Potwierdź"
    assert sent["message"] == (
        "Wymaga uwagi: Niebezpieczna temperatura.\nLokalizacja: Biuro"
    )
