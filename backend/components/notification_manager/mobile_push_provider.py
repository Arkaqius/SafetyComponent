"""Home Assistant Companion mobile push transport adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import appdaemon.plugins.hass.hassapi as hass  # type: ignore

from components.notification_manager.models import (
    DeliveryBatchResult,
    DeliveryDisposition,
    TargetDeliveryResult,
)


class MobilePushProvider:
    """Build Companion payloads and submit them to explicit HA notify services."""

    def __init__(self, hass_app: hass.Hass, config: dict[str, Any]) -> None:
        self.hass_app = hass_app
        self.services = tuple(str(service) for service in config["services"])
        self.default_url = str(config["default_url"])
        self.profiles = {
            int(level): dict(profile) for level, profile in config["profiles"].items()
        }

    def validate_services(self) -> None:
        """Fail fast when AppDaemon exposes a registry missing a target service."""

        list_services = getattr(self.hass_app, "list_services", None)
        if not callable(list_services):
            return
        registered = list_services()
        if not isinstance(registered, list) or not registered:
            return
        available = {
            f"{item.get('domain')}/{item.get('service')}"
            for item in registered
            if isinstance(item, Mapping)
        }
        missing = sorted(set(self.services) - available)
        if missing:
            raise ValueError(
                "Configured mobile notify services are unavailable: "
                + ", ".join(missing)
            )

    def send(
        self,
        *,
        level: int,
        title: str,
        message: str,
        tag: str,
        acknowledgement_title: str,
        quiet: bool = False,
        resolved: bool = False,
        services: tuple[str, ...] | None = None,
    ) -> DeliveryBatchResult:
        """Submit one notification to every configured service."""

        payload = self.build_payload(
            level=level,
            tag=tag,
            acknowledgement_title=acknowledgement_title,
            quiet=quiet,
            resolved=resolved,
        )
        return self._submit(
            title=title, message=message, data=payload, services=services
        )

    def clear(
        self, tag: str, *, services: tuple[str, ...] | None = None
    ) -> DeliveryBatchResult:
        """Send the Companion clear command for the stable notification tag."""

        return self._submit(
            title=None,
            message="clear_notification",
            data={"tag": tag},
            services=services,
        )

    def build_payload(
        self,
        *,
        level: int,
        tag: str,
        acknowledgement_title: str,
        quiet: bool,
        resolved: bool,
    ) -> dict[str, Any]:
        """Build one cross-platform Companion payload."""

        profile = self.profiles[level]
        data: dict[str, Any] = {
            "tag": tag,
            "url": self.default_url,
            "clickAction": self.default_url,
            "persistent": not resolved,
            "sticky": not resolved,
            "color": profile["color"],
            "notification_icon": profile["notification_icon"],
            "channel": profile["android_channel"],
            "importance": profile["android_importance"],
        }
        if not resolved:
            data["actions"] = [
                {
                    "action": f"SAFETY_ACK_{tag}",
                    "title": acknowledgement_title,
                }
            ]

        if quiet or resolved:
            data["alert_once"] = True
            data["priority"] = "normal"
            data["push"] = {"interruption-level": "passive"}
            return data

        data["priority"] = profile["android_priority"]
        data["ttl"] = profile["android_ttl"]
        if profile.get("vibration_pattern"):
            data["vibrationPattern"] = profile["vibration_pattern"]

        push: dict[str, Any] = {"interruption-level": profile["ios_interruption_level"]}
        if profile.get("ios_critical_sound"):
            push["sound"] = {"name": "default", "critical": 1, "volume": 1.0}
        data["push"] = push
        return data

    def _submit(
        self,
        *,
        title: str | None,
        message: str,
        data: dict[str, Any],
        services: tuple[str, ...] | None = None,
    ) -> DeliveryBatchResult:
        results: list[TargetDeliveryResult] = []
        for service in services or self.services:
            kwargs: dict[str, Any] = {
                "message": message,
                "data": data,
            }
            if title is not None:
                kwargs["title"] = title
            try:
                response = self.hass_app.call_service(service, **kwargs)
                if isinstance(response, Mapping) and response.get("success") is False:
                    results.append(
                        TargetDeliveryResult(
                            service,
                            DeliveryDisposition.FAILED,
                            str(response.get("error") or response),
                        )
                    )
                else:
                    results.append(
                        TargetDeliveryResult(service, DeliveryDisposition.ACCEPTED)
                    )
            except (
                Exception
            ) as exc:  # AppDaemon/plugin exceptions are transport failures.
                results.append(
                    TargetDeliveryResult(service, DeliveryDisposition.FAILED, str(exc))
                )
        return DeliveryBatchResult(tuple(results))
