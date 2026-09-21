"""Shared entity accessors for cross-component use."""

import appdaemon.plugins.hass.hassapi as hass  # type: ignore


class CommonEntities:
    """Convenience wrapper for shared Home Assistant entities."""

    def __init__(self, hass_app: hass, cfg: dict[str, str]) -> None:
        self.hass_app: hass = hass_app
        self.outside_temp_sensor: str = cfg["outside_temp"]

    def get_outisde_temperature(self) -> str | None:
        if self.hass_app:
            return self.hass_app.get_state(self.outside_temp_sensor)
        return None
