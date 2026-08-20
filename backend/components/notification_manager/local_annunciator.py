"""Optional local siren and warning-light adapter."""

from __future__ import annotations

from typing import Any

import appdaemon.plugins.hass.hassapi as hass  # type: ignore


class LocalAnnunciator:
    """Run local outputs independently from mobile transport."""

    def __init__(self, hass_app: hass.Hass, config: dict[str, Any]) -> None:
        self.hass_app = hass_app
        self.light_entity = config.get("light_entity")
        self.alarm_entity = config.get("alarm_entity")
        self._active_levels: dict[str, int] = {}
        self._previous_light_state: dict[str, Any] | None = None

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

        if level == 1 and previous_level != 1 and self.alarm_entity:
            self.hass_app.call_service(
                "alarm_control_panel/alarm_trigger", entity_id=self.alarm_entity
            )
        if level in (1, 2) and previous_level not in (1, 2) and self.light_entity:
            self.hass_app.call_service(
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

        previous = self._previous_light_state or {}
        self._previous_light_state = None
        if previous.get("state") != "on":
            self.hass_app.call_service("light/turn_off", entity_id=self.light_entity)
            return
        attributes = previous.get("attributes", {})
        restore = {
            key: attributes[key]
            for key in ("brightness", "rgb_color", "color_temp_kelvin")
            if key in attributes
        }
        self.hass_app.call_service(
            "light/turn_on", entity_id=self.light_entity, **restore
        )

    def snapshot(self) -> dict[str, Any]:
        """Return state required to restore light ownership after a restart."""

        return {
            "active_levels": dict(sorted(self._active_levels.items())),
            "previous_light_state": self._previous_light_state,
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
