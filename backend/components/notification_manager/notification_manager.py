"""Fault notification lifecycle, scheduling, persistence, and diagnostics."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping
from typing import Any, Optional

import appdaemon.plugins.hass.hassapi as hass  # type: ignore

from components.core.localization import Localizer
from components.core.types_common import FaultState
from components.notification_manager.local_annunciator import LocalAnnunciator
from components.notification_manager.mobile_push_provider import MobilePushProvider
from components.notification_manager.models import PendingDelivery
from components.notification_manager.schema import NotificationConfig
from components.notification_manager.state_store import (
    InMemoryNotificationStateStore,
    NotificationStateStore,
)


_STATE_VERSION = 1
_ACK_PREFIX = "SAFETY_ACK_"


class NotificationManager:
    """Manage one persistent, retryable mobile notification per fault."""

    def __init__(
        self,
        hass_app: hass.Hass,
        notification_config: dict[str, Any],
        *,
        localizer: Localizer | None = None,
        mobile_provider: MobilePushProvider | None = None,
        local_annunciator: LocalAnnunciator | None = None,
        state_store: NotificationStateStore | None = None,
        mqtt_entities: Any | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        """Create the manager without registering AppDaemon callbacks."""

        self.hass_app = hass_app
        required_sections = {
            "mobile",
            "retry",
            "level_one_repeat",
            "persistence",
            "local",
        }
        if required_sections.issubset(notification_config):
            # AppCfgValidator already produced the canonical runtime mapping.
            self.notification_config = notification_config
        else:
            model = NotificationConfig.model_validate(
                notification_config, context={"strict_validation": False}
            )
            self.notification_config = model.model_dump()
        self.localizer = localizer or Localizer()
        self.mobile_provider = mobile_provider or MobilePushProvider(
            hass_app, self.notification_config["mobile"]
        )
        self.local_annunciator = local_annunciator or LocalAnnunciator(
            hass_app, self.notification_config["local"]
        )
        self.state_store = state_store or InMemoryNotificationStateStore()
        self.mqtt_entities = mqtt_entities
        self._clock = clock or time.time
        self.active_notification: dict[str, dict[str, Any]] = {}
        self.pending_deliveries: dict[str, PendingDelivery] = {}
        self.wan_online: bool | None = (
            None if self.notification_config.get("wan_entity") else True
        )
        self._started = False
        self._counters: dict[str, int] = {
            "accepted_attempts": 0,
            "failed_attempts": 0,
            "deadline_misses": 0,
            "exhausted_deliveries": 0,
        }
        self._last_attempt_at: float | None = None
        self._last_success_at: float | None = None
        self._last_result = "not_attempted"
        self._last_error: str | None = None
        self._channel_status: dict[str, dict[str, Any]] = {
            service: {
                "status": "not_attempted",
                "last_attempt_at": None,
                "last_error": "",
            }
            for service in self.mobile_provider.services
        }
        self._restore_state()

    def start(self) -> None:
        """Register diagnostics, WAN monitoring, actions, and scheduler."""

        if self._started:
            return
        self.mobile_provider.validate_services()
        self._started = True
        if self.mqtt_entities is not None:
            self.mqtt_entities.register_sensor(
                self.notification_config["diagnostics_sensor_id"],
                "Notification Delivery Health",
                icon="mdi:message-alert-outline",
                entity_category="diagnostic",
            )

        wan_entity = self.notification_config.get("wan_entity")
        if wan_entity:
            current = self.hass_app.get_state(wan_entity)
            self.wan_online = self._is_wan_online(current)
            self.hass_app.listen_state(self.handle_wan_state, wan_entity)

        listen_event = getattr(self.hass_app, "listen_event", None)
        if callable(listen_event):
            listen_event(self.handle_mobile_action, "mobile_app_notification_action")
        self.hass_app.run_every(self.tick, "now", 1)
        self._publish_diagnostics()

    def stop(self) -> None:
        """Persist lifecycle state during a controlled shutdown."""

        self._persist_state()

    def notify(
        self,
        fault: str,
        level: int,
        fault_status: FaultState,
        additional_info: Optional[dict],
        fault_tag: str,
        friendly_name: Optional[str] = None,
    ) -> None:
        """Create, refresh, resolve, or remove one fault notification."""

        display_name = friendly_name or self._humanize_identifier(fault)
        safe_info = self._filter_details(additional_info)

        if fault_status == FaultState.SET:
            self._set_active_fault(display_name, level, safe_info, fault_tag)
            return
        if fault_status == FaultState.CLEARED:
            self._resolve_fault(display_name, level, safe_info, fault_tag)
            return
        if fault_status == FaultState.SHADOWED:
            self._remove_fault(level, fault_tag)
            return
        self.hass_app.log(f"Invalid fault status '{fault_status}'", level="WARNING")

    def handle_fault_event(
        self,
        *,
        fault_name: str,
        fault_friendly_name: Optional[str] = None,
        level: int,
        fault_state: FaultState,
        additional_info: Optional[dict],
        fault_tag: str,
        should_notify: bool = True,
        **_: object,
    ) -> None:
        """Consume a FaultManager EventBus event."""

        restored_fault_needs_reconciliation = (
            fault_tag in self.active_notification
            and fault_state in {FaultState.CLEARED, FaultState.SHADOWED}
        )
        if should_notify or restored_fault_needs_reconciliation:
            self.notify(
                fault_name,
                level,
                fault_state,
                additional_info,
                fault_tag,
                friendly_name=fault_friendly_name,
            )

    def handle_mobile_action(
        self, event_name: str, data: Mapping[str, Any], **_: Any
    ) -> None:
        """Acknowledge the matching fault without clearing it."""

        del event_name
        action = str(data.get("action", ""))
        if not action.startswith(_ACK_PREFIX):
            return
        tag = action[len(_ACK_PREFIX) :]
        record = self.active_notification.get(tag)
        if record is None:
            return
        record["acknowledged"] = True
        record["acknowledged_at"] = self._clock()
        record["next_repeat_at"] = None
        self.pending_deliveries.pop(f"{tag}:repeat", None)
        self._persist_state()
        self._publish_diagnostics()
        self.hass_app.log(
            f"Notification acknowledged for tag '{tag}'; repeats suppressed",
            level="INFO",
        )

    def handle_wan_state(
        self, entity: str, attribute: str, old: Any, new: Any, **_: Any
    ) -> None:
        """Queue while WAN is unconfirmed and flush after confirmed recovery."""

        del entity, attribute, old
        was_online = self.wan_online
        self.wan_online = self._is_wan_online(new)
        if self.wan_online and not was_online:
            now = self._clock()
            for delivery in self.pending_deliveries.values():
                delivery.next_attempt_at = now
            self.tick()
        else:
            self._persist_state()
            self._publish_diagnostics()

    def tick(self, **_: Any) -> None:
        """Process due retries and bounded L1 repeats."""

        now = self._clock()
        state_changed = False
        for delivery in self.pending_deliveries.values():
            if not delivery.deadline_missed and now > delivery.deadline_at:
                delivery.deadline_missed = True
                self._counters["deadline_misses"] += 1
                state_changed = True
        if self.wan_online:
            for delivery in list(self.pending_deliveries.values()):
                if delivery.next_attempt_at <= now:
                    self._attempt_delivery(delivery)

        repeat_policy = self.notification_config["level_one_repeat"]
        if repeat_policy["enabled"] and repeat_policy["max_repeats"] > 0:
            for tag, record in list(self.active_notification.items()):
                next_repeat = record.get("next_repeat_at")
                if (
                    record.get("level") == 1
                    and not record.get("acknowledged", False)
                    and next_repeat is not None
                    and float(next_repeat) <= now
                    and int(record.get("repeat_count", 0))
                    < repeat_policy["max_repeats"]
                ):
                    record["repeat_count"] = int(record.get("repeat_count", 0)) + 1
                    record["next_repeat_at"] = (
                        None
                        if record["repeat_count"] >= repeat_policy["max_repeats"]
                        else now + repeat_policy["interval_seconds"]
                    )
                    state_changed = True
                    self._queue_delivery(
                        tag=tag,
                        level=1,
                        title=str(record["title"]),
                        message=str(record["message"]),
                        kind="repeat",
                    )
        if state_changed:
            self._persist_state()
        self._publish_diagnostics()

    @staticmethod
    def _humanize_identifier(identifier: str) -> str:
        words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", identifier)
        words = words.replace("_", " ").strip()
        return words[:1].upper() + words[1:]

    def _filter_details(self, additional_info: Optional[dict]) -> dict[str, Any]:
        """Drop non-approved fault context before it reaches push or persistence."""

        if not additional_info:
            return {}
        allowed = set(self.notification_config["allowed_detail_fields"])
        return {
            str(key).strip().lower(): value
            for key, value in additional_info.items()
            if str(key).strip().lower() in allowed
        }

    @staticmethod
    def _get_detail(additional_info: Optional[dict], detail_name: str) -> Any:
        if not additional_info:
            return None
        return additional_info.get(detail_name.strip().lower())

    def _format_details(self, additional_info: Optional[dict]) -> list[str]:
        if not additional_info:
            return []
        details = []
        for key, value in additional_info.items():
            if key == "recommendation":
                continue
            label = self.localizer.detail_label(
                key, self._humanize_identifier(str(key))
            )
            details.append(f"{label}: {value}")
        return details

    def _format_active_message(
        self, friendly_name: str, additional_info: Optional[dict]
    ) -> str:
        lines = [self.localizer.text("notification.active", fault=friendly_name)]
        lines.extend(self._format_details(additional_info))
        recommendation = self._get_detail(additional_info, "recommendation")
        if recommendation:
            lines.extend(
                [
                    "",
                    self.localizer.text("notification.guidance"),
                    f"- {recommendation}",
                ]
            )
        return "\n".join(lines)

    def _format_cleared_message(
        self, friendly_name: str, additional_info: Optional[dict]
    ) -> str:
        lines = [self.localizer.text("notification.cleared", fault=friendly_name)]
        lines.extend(self._format_details(additional_info))
        return "\n".join(lines)

    def _set_active_fault(
        self,
        display_name: str,
        level: int,
        additional_info: dict[str, Any],
        tag: str,
    ) -> None:
        existing = self.active_notification.get(tag)
        is_new = existing is None
        previous_level = int((existing or {}).get("level", level))
        is_escalation = existing is not None and level < previous_level
        should_alert = is_new or is_escalation
        restored_guidance = (existing or {}).get("_recovery_messages", {})
        if isinstance(restored_guidance, list):
            recovery_messages = {
                f"legacy-{index}": str(message)
                for index, message in enumerate(restored_guidance)
            }
        elif isinstance(restored_guidance, dict):
            recovery_messages = {
                str(key): str(message)
                for key, message in restored_guidance.items()
            }
        else:
            recovery_messages = {}
        base_message = self._format_active_message(display_name, additional_info)
        title = self._title(level)
        record: dict[str, Any] = {
            "title": title,
            "message": base_message,
            "level": level,
            "_base_message": base_message,
            "_recovery_messages": recovery_messages,
            "acknowledged": (
                False
                if is_escalation
                else bool((existing or {}).get("acknowledged", False))
            ),
            "acknowledged_at": (
                None if is_escalation else (existing or {}).get("acknowledged_at")
            ),
            "repeat_count": (
                0 if is_escalation else int((existing or {}).get("repeat_count", 0))
            ),
            "next_repeat_at": (existing or {}).get("next_repeat_at"),
        }
        self._refresh_notification_message(record)
        if (
            should_alert
            and level == 1
            and self.notification_config["level_one_repeat"]["enabled"]
        ):
            record["next_repeat_at"] = (
                self._clock()
                + self.notification_config["level_one_repeat"]["interval_seconds"]
            )
        elif level != 1:
            record["next_repeat_at"] = None
        if level in (1, 2, 3):
            record["data"] = self.mobile_provider.build_payload(
                level=level,
                tag=tag,
                acknowledgement_title=self.localizer.text("notification.action.ack"),
                quiet=not should_alert,
                resolved=False,
            )
        if is_escalation:
            self._drop_pending_for_tag(tag)
        self.active_notification[tag] = record
        self._persist_state()

        if should_alert:
            try:
                self.local_annunciator.activate(level, tag)
                self._persist_state()
            except Exception as exc:
                self.hass_app.log(
                    f"Local annunciator failed for tag '{tag}': {exc}", level="ERROR"
                )
        elif existing is not None and previous_level != level:
            try:
                update_level = getattr(self.local_annunciator, "update_level", None)
                if callable(update_level):
                    update_level(level, tag)
                    self._persist_state()
            except Exception as exc:
                self.hass_app.log(
                    f"Unable to update local annunciator for tag '{tag}': {exc}",
                    level="ERROR",
                )
        if level in (1, 2, 3):
            self._queue_delivery(
                tag=tag,
                level=level,
                title=title,
                message=str(record["message"]),
                kind="new" if should_alert else "update",
            )

    def _resolve_fault(
        self,
        display_name: str,
        level: int,
        additional_info: dict[str, Any],
        tag: str,
    ) -> None:
        self.active_notification.pop(tag, None)
        self._drop_pending_for_tag(tag)
        self._clear_local(tag)
        if level in (1, 2, 3):
            self._queue_delivery(
                tag=tag,
                level=level,
                title=self._title(level),
                message=self._format_cleared_message(display_name, additional_info),
                kind="resolved",
            )

    def _remove_fault(self, level: int, tag: str) -> None:
        self.active_notification.pop(tag, None)
        self._drop_pending_for_tag(tag)
        self._clear_local(tag)
        if level in (1, 2, 3):
            self._queue_delivery(
                tag=tag,
                level=level,
                title="",
                message="clear_notification",
                kind="clear",
            )

    def _clear_local(self, tag: str) -> None:
        try:
            self.local_annunciator.clear(tag)
            self._persist_state()
        except Exception as exc:
            self.hass_app.log(
                f"Unable to restore local annunciator for tag '{tag}': {exc}",
                level="ERROR",
            )

    def _title(self, level: int) -> str:
        return self.localizer.text(f"notification.title.{level}")

    def _queue_delivery(
        self, *, tag: str, level: int, title: str, message: str, kind: str
    ) -> None:
        if level == 4:
            return
        now = self._clock()
        delivery_key = f"{tag}:{'active' if kind in {'new', 'update'} else kind}"
        target_services = tuple(self.mobile_provider.services)
        if kind == "update":
            pending_new = self.pending_deliveries.get(f"{tag}:active")
            if pending_new is not None and pending_new.kind == "new":
                pending_new.level = level
                pending_new.title = title
                pending_new.message = message
                pending_new_targets = set(pending_new.target_services)
                target_services = tuple(
                    service
                    for service in self.mobile_provider.services
                    if service not in pending_new_targets
                )
                self._persist_state()
                if not target_services:
                    self._publish_diagnostics()
                    return
                delivery_key = f"{tag}:update"
        delivery = PendingDelivery(
            delivery_id=delivery_key,
            tag=tag,
            level=level,
            title=title,
            message=message,
            kind=kind,
            created_at=now,
            deadline_at=now
            + self.notification_config["retry"]["deadlines_seconds"][level],
            next_attempt_at=now,
            target_services=target_services,
        )
        self.pending_deliveries[delivery_key] = delivery
        self._persist_state()
        if self.wan_online:
            self._attempt_delivery(delivery)
        else:
            for service in delivery.target_services:
                self._channel_status[service] = {
                    "status": "queued",
                    "last_attempt_at": None,
                    "last_error": "WAN is not positively online",
                }
            self._last_result = "queued_wan_unconfirmed"
            self._persist_state()
            self._publish_diagnostics()

    def _attempt_delivery(self, delivery: PendingDelivery) -> None:
        now = self._clock()
        if not delivery.deadline_missed and now > delivery.deadline_at:
            delivery.deadline_missed = True
            self._counters["deadline_misses"] += 1
        delivery.attempts += 1
        self._last_attempt_at = now

        if delivery.kind == "clear":
            result = self.mobile_provider.clear(
                delivery.tag, services=delivery.target_services
            )
        else:
            result = self.mobile_provider.send(
                level=delivery.level,
                title=delivery.title,
                message=delivery.message,
                tag=delivery.tag,
                acknowledgement_title=self.localizer.text("notification.action.ack"),
                quiet=delivery.kind in {"update", "resolved"},
                resolved=delivery.kind == "resolved",
                services=delivery.target_services,
            )

        completed_at = self._clock()
        self._last_attempt_at = completed_at
        if not delivery.deadline_missed and completed_at > delivery.deadline_at:
            delivery.deadline_missed = True
            self._counters["deadline_misses"] += 1

        accepted_count = sum(
            1
            for target in result.targets
            if target.disposition.value == "accepted_by_home_assistant"
        )
        self._counters["accepted_attempts"] += accepted_count
        self._counters["failed_attempts"] += len(result.failed_services)
        for target in result.targets:
            self._channel_status[target.service] = {
                "status": target.disposition.value,
                "last_attempt_at": completed_at,
                "last_error": target.error or "",
            }
        if result.completed:
            self.pending_deliveries.pop(delivery.delivery_id, None)
            if result.accepted:
                self._last_success_at = completed_at
            self._last_result = "accepted_by_home_assistant"
            self._last_error = None
        elif delivery.attempts >= self.notification_config["retry"]["max_attempts"]:
            self.pending_deliveries.pop(delivery.delivery_id, None)
            self._counters["exhausted_deliveries"] += 1
            self._last_result = "failed_exhausted"
            self._last_error = result.error
            self.hass_app.log(
                f"Notification delivery exhausted for tag '{delivery.tag}': {result.error}",
                level="ERROR",
            )
        else:
            delivery.target_services = result.failed_services
            exponent = max(0, delivery.attempts - 1)
            delay = min(
                self.notification_config["retry"]["base_delay_seconds"] * (2**exponent),
                self.notification_config["retry"]["max_delay_seconds"],
            )
            delivery.next_attempt_at = completed_at + delay
            self._last_result = "failed_retry_scheduled"
            self._last_error = result.error
        self._persist_state()
        self._publish_diagnostics()

    def _drop_pending_for_tag(self, tag: str) -> None:
        for delivery_id, delivery in list(self.pending_deliveries.items()):
            if delivery.tag == tag:
                del self.pending_deliveries[delivery_id]

    def _add_recovery_action(self, notification_msg: str, fault_tag: str) -> None:
        """Compatibility wrapper for older recovery producers."""

        self.upsert_recovery_guidance(notification_msg, notification_msg, fault_tag)

    def upsert_recovery_guidance(
        self, proposal_id: str, notification_msg: str, fault_tag: str
    ) -> None:
        """Insert or replace guidance owned by one recovery proposal."""

        notification = self.active_notification.get(fault_tag)
        if notification is None:
            return
        recovery_messages = notification.setdefault("_recovery_messages", {})
        if isinstance(recovery_messages, list):
            recovery_messages = {
                f"legacy-{index}": str(message)
                for index, message in enumerate(recovery_messages)
            }
            notification["_recovery_messages"] = recovery_messages
        recovery_messages[proposal_id] = notification_msg
        self._refresh_notification_message(notification)
        self._persist_state()
        level = int(notification["level"])
        if level in (1, 2, 3):
            self._queue_delivery(
                tag=fault_tag,
                level=level,
                title=str(notification["title"]),
                message=str(notification["message"]),
                kind="update",
            )

    def remove_recovery_guidance(self, proposal_id: str, fault_tag: str) -> None:
        """Remove guidance when its proposal is completed or withdrawn."""

        notification = self.active_notification.get(fault_tag)
        if notification is None:
            return
        recovery_messages = notification.get("_recovery_messages", {})
        if not isinstance(recovery_messages, dict):
            return
        if recovery_messages.pop(proposal_id, None) is None:
            return
        self._refresh_notification_message(notification)
        self._persist_state()

    def _refresh_notification_message(self, notification: dict[str, Any]) -> None:
        message = notification.get("_base_message", notification["message"])
        recovery_messages = notification.get("_recovery_messages", {})
        if recovery_messages:
            items = (
                recovery_messages.values()
                if isinstance(recovery_messages, dict)
                else recovery_messages
            )
            guidance = "\n".join(f"- {item}" for item in items)
            header = self.localizer.text("notification.guidance")
            message = f"{message}\n\n{header}\n{guidance}"
        notification["message"] = message

    def _is_wan_online(self, state: Any) -> bool:
        return str(state).strip().lower() in set(
            self.notification_config["wan_online_states"]
        )

    def _persist_state(self) -> None:
        snapshot = {
            "version": _STATE_VERSION,
            "active_notifications": self.active_notification,
            "pending_deliveries": [
                delivery.to_dict() for delivery in self.pending_deliveries.values()
            ],
            "counters": self._counters,
            "last_attempt_at": self._last_attempt_at,
            "last_success_at": self._last_success_at,
            "last_result": self._last_result,
            "last_error": self._last_error,
            "channel_status": self._channel_status,
            "local_annunciator": (
                self.local_annunciator.snapshot()
                if callable(getattr(self.local_annunciator, "snapshot", None))
                else {}
            ),
        }
        try:
            self.state_store.save(snapshot)
        except Exception as exc:
            self._last_result = "state_persistence_failed"
            self._last_error = str(exc)
            self.hass_app.log(
                f"Unable to persist notification state: {exc}", level="ERROR"
            )

    def _restore_state(self) -> None:
        try:
            snapshot = self.state_store.load()
            if not snapshot:
                return
            if int(snapshot.get("version", -1)) != _STATE_VERSION:
                raise ValueError("Unsupported notification state version")
            active = snapshot.get("active_notifications", {})
            if not isinstance(active, dict):
                raise ValueError("active_notifications must be an object")
            self.active_notification = {
                str(tag): dict(record)
                for tag, record in active.items()
                if isinstance(record, Mapping)
            }
            self.pending_deliveries = {}
            current_services = set(self.mobile_provider.services)
            for raw in snapshot.get("pending_deliveries", []):
                delivery = PendingDelivery.from_dict(dict(raw))
                retained_services = tuple(
                    service
                    for service in delivery.target_services
                    if service in current_services
                )
                delivery.target_services = (
                    retained_services
                    if retained_services
                    else tuple(self.mobile_provider.services)
                )
                self.pending_deliveries[delivery.delivery_id] = delivery
            restored_counters = snapshot.get("counters", {})
            for key in self._counters:
                self._counters[key] = int(restored_counters.get(key, 0))
            self._last_attempt_at = snapshot.get("last_attempt_at")
            self._last_success_at = snapshot.get("last_success_at")
            self._last_result = str(snapshot.get("last_result", "restored"))
            self._last_error = snapshot.get("last_error")
            restored_channels = snapshot.get("channel_status", {})
            if isinstance(restored_channels, Mapping):
                for service in self.mobile_provider.services:
                    restored_channel = restored_channels.get(service)
                    if isinstance(restored_channel, Mapping):
                        self._channel_status[service] = {
                            "status": str(
                                restored_channel.get("status", "not_attempted")
                            ),
                            "last_attempt_at": restored_channel.get("last_attempt_at"),
                            "last_error": str(restored_channel.get("last_error", "")),
                        }
            restore_local = getattr(self.local_annunciator, "restore", None)
            if callable(restore_local):
                restore_local(dict(snapshot.get("local_annunciator", {})))
        except Exception as exc:
            self.active_notification = {}
            self.pending_deliveries = {}
            self._last_result = "state_restore_failed"
            self._last_error = str(exc)
            self.hass_app.log(
                f"Unable to restore notification state: {exc}", level="ERROR"
            )

    def _publish_diagnostics(self) -> None:
        if self.mqtt_entities is None:
            return
        pending_count = len(self.pending_deliveries)
        if pending_count and not self.wan_online:
            state = "queued"
        elif self._last_error:
            state = "degraded"
        else:
            state = "healthy"
        attributes = {
            "active_count": len(self.active_notification),
            "acknowledged_count": sum(
                1
                for record in self.active_notification.values()
                if record.get("acknowledged")
            ),
            "queued_count": pending_count,
            "accepted_attempts": self._counters["accepted_attempts"],
            "failed_attempts": self._counters["failed_attempts"],
            "deadline_misses": self._counters["deadline_misses"],
            "exhausted_deliveries": self._counters["exhausted_deliveries"],
            "wan_online": self.wan_online,
            "last_attempt_at": self._last_attempt_at,
            "last_success_at": self._last_success_at,
            "last_result": self._last_result,
            "last_error": self._last_error or "",
            "channels": self._channel_status,
            "delivery_confirmation": "Home Assistant acceptance only; device delivery is not confirmed",
        }
        self.mqtt_entities.publish_sensor_state(
            self.notification_config["diagnostics_sensor_id"],
            state,
            attributes=attributes,
        )

    # Compatibility helper retained for existing callers/tests.
    def _clear_symptom_msg(self, notification: dict, notification_msg: str) -> None:
        notification["message"] = f" {notification_msg}"
        tag = str(notification.get("data", {}).get("tag", "legacy"))
        level = int(notification.get("level", 3))
        if level in (1, 2, 3):
            self._queue_delivery(
                tag=tag,
                level=level,
                title=str(notification.get("title", self._title(level))),
                message=str(notification["message"]),
                kind="update",
            )
