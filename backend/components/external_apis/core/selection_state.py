"""Publish the running process's explicit source choices before provider polls."""

from collections.abc import Mapping
from typing import Any

from .models import ProviderCapability


class AppliedSourceSelection:
    """Expose applied category selection without private provider parameters."""

    def __init__(
        self,
        mqtt_entities: Any,
        *,
        runtime_id: str,
        component_enabled: bool,
        selections: Mapping[str, str | None],
        provider_definitions: Mapping[str, Any],
        localizer: Any = None,
    ) -> None:
        if not runtime_id or len(runtime_id) > 128 or not runtime_id.isascii():
            raise ValueError("runtime_id must contain 1..128 ASCII characters")
        categories = {capability.value for capability in ProviderCapability}
        if set(selections) != categories:
            raise ValueError("Applied selection must contain exactly three categories")
        self._mqtt_entities = mqtt_entities
        self._entity_id: str | None = None
        self._name = (
            localizer.text("entity.external_source_selection")
            if localizer
            else "Applied external source selection"
        )
        values: dict[str, dict[str, Any]] = {}
        for capability, provider in selections.items():
            if provider is None:
                values[capability] = {
                    "provider": None,
                    "data_kind": None,
                    "hazards": [],
                }
                continue
            definition = provider_definitions.get(provider)
            if (
                not isinstance(provider, str)
                or not provider
                or len(provider) > 128
                or definition is None
                or definition.capability.value != capability
                or definition.data_kind not in {"live", "synthetic"}
            ):
                raise ValueError("Invalid applied provider selection")
            values[capability] = {
                "provider": provider,
                "data_kind": definition.data_kind,
                "hazards": sorted(hazard.value for hazard in definition.hazards),
            }
        self.attributes: dict[str, Any] = {
            "schema_version": 1,
            "runtime_id": runtime_id,
            "component_enabled": component_enabled,
            "selections": values,
        }

    def publish(self) -> None:
        """Publish the same applied truth even if external monitoring is off."""
        if self._entity_id is None:
            self._entity_id = self._mqtt_entities.register_sensor(
                "sensor.external_source_selection",
                self._name,
                icon="mdi:format-list-checks",
                entity_category="diagnostic",
            )
        self._mqtt_entities.publish_sensor_state(
            self._entity_id, "ready", attributes=self.attributes
        )
