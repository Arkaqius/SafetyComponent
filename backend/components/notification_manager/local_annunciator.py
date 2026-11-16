"""Optional local siren and warning-light adapter."""

from __future__ import annotations

from typing import Any, Callable

import appdaemon.plugins.hass.hassapi as hass  # type: ignore

from components.core.service_dispatcher import (
    Admission, CompletionStatus, ServiceCompletion, ServiceDispatcher, ServiceIntent,
)


class LocalAnnunciator:
    """Run local outputs independently from mobile transport."""

    def __init__(
        self, hass_app: hass.Hass, config: dict[str, Any],
        diagnostics_observer: Callable[..., None] | None = None,
        *, dispatcher: ServiceDispatcher | None = None,
        restriction_provider: Callable[[], bool] | None = None,
    ) -> None:
        self.hass_app = hass_app
        self.light_entity = config.get("light_entity")
        self.alarm_entity = config.get("alarm_entity")
        self._active_levels: dict[str, int] = {}
        self._previous_light_state: dict[str, Any] | None = None
        self._switching_inhibited = False
        self._inhibition_reason: str | None = None
        self._diagnostics_observer = diagnostics_observer
        self.dispatcher = dispatcher
        self.restriction_provider = restriction_provider
        self._enabled = True
        self._generation = 0
        self._output_results: dict[str, dict[str, Any]] = {}

    def start(self) -> None:
        """Enable new output admission without replaying physical commands."""
        self._enabled = True

    def stop(self) -> None:
        """Fence unsent output and late results without issuing an off/reset."""
        self._enabled = False
        self._generation += 1

    def _call_service(self, service: str, **kwargs: Any) -> None:
        """Report only an attempted output command, never intentional inhibition."""

        if self.dispatcher is not None:
            self._enqueue(service, kwargs)
            return

        try:
            response = self.hass_app.call_service(service, **kwargs)
            if isinstance(response, dict) and response.get("success") is False:
                raise RuntimeError(f"Local output command rejected: {service}")
        except Exception:
            if self._diagnostics_observer is not None:
                self._diagnostics_observer("local_output", True, detail=service)
            raise
        if self._diagnostics_observer is not None:
            self._diagnostics_observer("local_output", False, detail=service)

    def _enqueue(self, service: str, payload: dict[str, Any]) -> None:
        """Serialize one physical resource and check current restrictions at handoff."""
        dispatcher = self.dispatcher
        if dispatcher is None or not self._enabled:
            return
        resource = str(payload["entity_id"])
        generation = self._generation
        request = dispatcher.make_intent(
            resource=resource, service=service, payload=payload, tag="local-output",
            revision=dispatcher.next_revision(resource, "local-output"),
            deadline_at=dispatcher.clock() + 30,
        )

        def eligible(_: ServiceIntent) -> bool:
            if not self._enabled or self._generation != generation or self._switching_inhibited:
                return False
            if self.restriction_provider is not None:
                try:
                    restricted = self.restriction_provider()
                except Exception:
                    return False
                if restricted or not self._enabled or self._generation != generation:
                    return False
            if service == "alarm_control_panel/alarm_trigger":
                return any(level == 1 for level in self._active_levels.values())
            return True

        def completed(result: ServiceCompletion) -> None:
            if not self._enabled or self._generation != generation:
                return
            self._output_results[resource] = {
                "revision": result.revision, "status": result.status.value,
                "deadline_missed": result.deadline_missed, "error": result.error or "",
            }
            if self._diagnostics_observer is not None and result.status != CompletionStatus.CANCELLED:
                self._diagnostics_observer(
                    "local_output", result.status != CompletionStatus.ACCEPTED, detail=service,
                )

        admission = dispatcher.enqueue(request, before_dispatch=eligible, on_complete=completed, on_deadline=completed)
        self._output_results[resource] = {
            "revision": request.revision, "status": admission.value,
            "deadline_missed": False, "error": "",
        }
        if admission not in {Admission.QUEUED, Admission.COALESCED}:
            if self._diagnostics_observer is not None:
                self._diagnostics_observer("local_output", True, detail=service)

    def inhibit_switching(self, reason: str) -> None:
        """Persistently block local electrical switching until approved clearance."""

        self._switching_inhibited = True
        self._inhibition_reason = str(reason)

    def activate(self, level: int, tag: str) -> None:
        """Activate configured local outputs once for a newly active fault."""

        previous_level = self._active_levels.get(tag)
        if previous_level is not None and level >= previous_level:
            return
        light_was_owned = any(
            active_level in (1, 2) for active_level in self._active_levels.values()
        )
        if level in (1, 2) and not light_was_owned and self.light_entity:
            raw = self.hass_app.get_state(self.light_entity, attribute="all")
            self._previous_light_state = raw if isinstance(raw, dict) else None
        self._active_levels[tag] = level

        if self._switching_inhibited:
            return

        if level == 1 and previous_level != 1 and self.alarm_entity:
            self._call_service(
                "alarm_control_panel/alarm_trigger", entity_id=self.alarm_entity
            )
        if level in (1, 2) and previous_level not in (1, 2) and self.light_entity:
            self._call_service(
                "light/turn_on",
                entity_id=self.light_entity,
                color_name="yellow",
            )

    def clear(self, tag: str) -> None:
        """Release one fault and restore the shared light after the last fault."""

        previous_level = self._active_levels.pop(tag, None)
        if previous_level not in (1, 2) or not self.light_entity:
            return
        if any(active_level in (1, 2) for active_level in self._active_levels.values()):
            return
        if self._switching_inhibited:
            self._previous_light_state = None
            return
        self._restore_light()

    def update_level(self, level: int, tag: str) -> None:
        """Update ownership after a quiet severity decrease."""

        previous_level = self._active_levels.get(tag)
        if previous_level is None or previous_level == level:
            return
        self._active_levels[tag] = level
        if (
            previous_level in (1, 2)
            and level not in (1, 2)
            and not any(
                active_level in (1, 2)
                for other_tag, active_level in self._active_levels.items()
                if other_tag != tag
            )
        ):
            self._restore_light()

    def _restore_light(self) -> None:
        """Restore the light state captured before local ownership."""

        if self._switching_inhibited:
            self._previous_light_state = None
            return

        previous = self._previous_light_state or {}
        self._previous_light_state = None
        if previous.get("state") != "on":
            self._call_service("light/turn_off", entity_id=self.light_entity)
            return
        attributes = previous.get("attributes", {})
        restore = {
            key: attributes[key]
            for key in ("brightness", "rgb_color", "color_temp_kelvin")
            if key in attributes
        }
        self._call_service(
            "light/turn_on", entity_id=self.light_entity, **restore
        )

    def snapshot(self) -> dict[str, Any]:
        """Return state required to restore light ownership after a restart."""

        return {
            "active_levels": dict(sorted(self._active_levels.items())),
            "previous_light_state": self._previous_light_state,
            "switching_inhibited": self._switching_inhibited,
            "inhibition_reason": self._inhibition_reason,
            "outputs": {key: dict(value) for key, value in self._output_results.items()},
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore ownership state without re-triggering physical outputs."""

        active_levels = snapshot.get("active_levels", {})
        if isinstance(active_levels, dict):
            self._active_levels = {
                str(tag): int(level)
                for tag, level in active_levels.items()
                if str(tag) and int(level) in (1, 2, 3, 4)
            }
        else:
            self._active_levels = {}
        previous = snapshot.get("previous_light_state")
        self._previous_light_state = previous if isinstance(previous, dict) else None
        self._switching_inhibited = bool(snapshot.get("switching_inhibited", False))
        reason = snapshot.get("inhibition_reason")
        self._inhibition_reason = str(reason) if reason is not None else None
