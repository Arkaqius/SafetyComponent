"""Home Assistant Companion mobile push transport adapter."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import appdaemon.plugins.hass.hassapi as hass

from components.core.service_dispatcher import (
    Admission, CompletionStatus, ServiceCompletion, ServiceDispatcher, ServiceIntent,
)

from components.notification_manager.models import (
    DeliveryBatchResult,
    DeliveryDisposition,
    TargetDeliveryResult,
)


class MobilePushProvider:
    """Build Companion payloads and submit them to explicit HA notify services."""

    def __init__(
        self, hass_app: hass.Hass, config: dict[str, Any], *, dispatcher: ServiceDispatcher | None = None,
    ) -> None:
        self.hass_app = hass_app
        self.services = tuple(str(service) for service in config["services"])
        self.default_url = str(config["default_url"])
        self.dispatcher = dispatcher
        self._generation = 1
        self._enabled = True
        self._urgent: dict[tuple[str, str], dict[str, Any]] = {}
        self.profiles = {
            int(level): dict(profile) for level, profile in config["profiles"].items()
        }

    def start(self) -> None:
        """Enable current provider admission; stale generation remains fenced."""
        self._enabled = True

    def stop(self) -> None:
        """Invalidate queued handoffs without claiming cancellation of issued calls."""
        self._generation += 1
        self._enabled = False

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
        acknowledged: bool = False,
        services: tuple[str, ...] | None = None,
        on_complete: Callable[[TargetDeliveryResult], None] | None = None,
        deadline_at: float | None = None,
        incident_id: str = "",
        before_dispatch: Callable[[], bool] | None = None,
        deadlines: Mapping[str, float] | None = None,
    ) -> DeliveryBatchResult:
        """Submit one notification to every configured service."""

        payload = self.build_payload(
            level=level,
            tag=tag,
            acknowledgement_title=acknowledgement_title,
            quiet=quiet,
            resolved=resolved,
            acknowledged=acknowledged,
        )
        if self.dispatcher is not None:
            return self._enqueue(
                title=title, message=message, data=payload, services=services,
                on_complete=on_complete, deadline_at=deadline_at,
                urgent=not quiet and not resolved, retire=resolved,
                incident_id=incident_id,
                before_dispatch=before_dispatch,
                deadlines=deadlines,
            )
        if on_complete is not None:
            raise ValueError("Callback delivery requires a configured dispatcher")
        return self._submit(
            title=title, message=message, data=payload, services=services
        )

    def clear(
        self, tag: str, *, services: tuple[str, ...] | None = None,
        on_complete: Callable[[TargetDeliveryResult], None] | None = None,
        deadline_at: float | None = None,
        incident_id: str = "",
        before_dispatch: Callable[[], bool] | None = None,
        deadlines: Mapping[str, float] | None = None,
    ) -> DeliveryBatchResult:
        """Send the Companion clear command for the stable notification tag."""

        if self.dispatcher is not None:
            return self._enqueue(
                title=None, message="clear_notification", data={"tag": tag}, services=services,
                on_complete=on_complete, deadline_at=deadline_at, urgent=False, retire=True,
                incident_id=incident_id,
                before_dispatch=before_dispatch,
                deadlines=deadlines,
            )
        if on_complete is not None:
            raise ValueError("Callback delivery requires a configured dispatcher")
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
        acknowledged: bool = False,
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
        if not resolved and not acknowledged:
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

    def _enqueue(
        self, *, title: str | None, message: str, data: dict[str, Any],
        services: tuple[str, ...] | None, on_complete: Callable[[TargetDeliveryResult], None] | None,
        deadline_at: float | None, urgent: bool, retire: bool,
        incident_id: str,
        before_dispatch: Callable[[], bool] | None,
        deadlines: Mapping[str, float] | None,
    ) -> DeliveryBatchResult:
        """Admit independent immutable target work; scheduling is never acceptance."""
        dispatcher = self.dispatcher
        if dispatcher is None:
            raise ValueError("Missing service dispatcher")
        generation = self._generation
        results = []
        for service in services or self.services:
            key = (service, str(data["tag"]))
            deadline = (deadlines or {}).get(service, deadline_at if deadline_at is not None else dispatcher.clock() + 30)
            if deadline <= dispatcher.clock():
                results.append(TargetDeliveryResult(service, DeliveryDisposition.FAILED, "deadline_missed", deadline_missed=True))
                continue
            if not self._enabled or (key not in self._urgent and len(self._urgent) >= 1024):
                results.append(TargetDeliveryResult(service, DeliveryDisposition.FAILED, "provider_admission_unavailable"))
                continue
            target_data = dict(data)
            if urgent:
                self._urgent[key] = dict(data)
            elif message != "clear_notification" and key in self._urgent:
                # Quiet refresh/ack cannot downgrade a still-undelivered alert.
                target_data.pop("alert_once", None)
                for name in ("priority", "ttl", "vibrationPattern", "push", "importance", "channel"):
                    if name in self._urgent[key]:
                        target_data[name] = self._urgent[key][name]
            payload: dict[str, Any] = {"message": message, "data": target_data}
            if title is not None:
                payload["title"] = title
            request = dispatcher.make_intent(
                resource=service, service=service, payload=payload, tag=key[1],
                revision=dispatcher.next_revision(*key),
                deadline_at=deadline,
                incident_id=incident_id,
            )

            def completed(
                completion: ServiceCompletion, target: str = service,
                target_key: tuple[str, str] = key, owner_generation: int = generation,
                retire_receipt: bool = retire,
            ) -> None:
                if not self._enabled or self._generation != owner_generation:
                    return
                accepted = completion.status == CompletionStatus.ACCEPTED
                if accepted:
                    self._urgent.pop(target_key, None)
                    if retire_receipt:
                        dispatcher.retire_tag(*target_key)
                if on_complete is not None:
                    on_complete(TargetDeliveryResult(
                        target, DeliveryDisposition.ACCEPTED if accepted else DeliveryDisposition.FAILED,
                        completion.error or (None if accepted else completion.status.value),
                        completion.operation_id, completion.revision, completion.deadline_missed,
                        completion.handed_off,
                        completion.completed_at,
                    ))

            def eligible(_: ServiceIntent, owner_generation: int = generation) -> bool:
                return (self._enabled and self._generation == owner_generation
                        and (before_dispatch is None or before_dispatch()))

            admission = dispatcher.enqueue(
                request, on_complete=completed, on_deadline=completed,
                before_dispatch=eligible,
            )
            results.append(TargetDeliveryResult(
                service, DeliveryDisposition.QUEUED if admission in {Admission.QUEUED, Admission.COALESCED}
                else DeliveryDisposition.FAILED,
                None if admission in {Admission.QUEUED, Admission.COALESCED} else admission.value,
                request.operation_id, request.revision,
            ))
        return DeliveryBatchResult(tuple(results))

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
                results.append(self._submission_result(service, response))
            except (
                Exception
            ) as exc:  # AppDaemon/plugin exceptions are transport failures.
                results.append(
                    TargetDeliveryResult(service, DeliveryDisposition.FAILED, str(exc))
                )
        return DeliveryBatchResult(tuple(results))

    @staticmethod
    def _submission_result(service: str, response: Any) -> TargetDeliveryResult:
        """Require explicit Boolean success; bare None cannot prove HA acceptance."""

        if isinstance(response, Mapping) and response.get("success") is True:
            return TargetDeliveryResult(service, DeliveryDisposition.ACCEPTED)
        error = (
            str(response.get("error") or response)
            if isinstance(response, Mapping)
            else str(response)
        )
        return TargetDeliveryResult(service, DeliveryDisposition.FAILED, error)
