"""MQTT discovery and state publishing for SafetyFunctions internal entities."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

import appdaemon.plugins.hass.hassapi as hass  # type: ignore
from pydantic import (
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from components.core.pydantic_utils import StrictBaseModel


_UNSET = object()
_MQTT_TOPIC_FORBIDDEN_CHARACTERS = frozenset({"+", "#", "\x00"})


class MqttSettings(StrictBaseModel):
    """Validated MQTT discovery, state, and lifecycle settings."""

    discovery_prefix: StrictStr = "homeassistant"
    base_topic: StrictStr = "safety_component"
    availability_topic: StrictStr | None = None
    device_identifier: StrictStr = "safety_component"
    device_name: StrictStr = "Safety Component"
    retain_discovery: StrictBool = True
    retain_state: StrictBool = False
    clear_retained_state_on_start: StrictBool = True
    qos: StrictInt = Field(default=0, ge=0, le=2)
    heartbeat_seconds: StrictInt = Field(default=60, ge=0)
    expire_after: StrictInt = Field(default=180, ge=0)
    legacy_discovery_entity_ids: list[StrictStr] = Field(default_factory=list)

    @field_validator("discovery_prefix", "base_topic", mode="before")
    @classmethod
    def _normalize_required_topic(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        return cls._normalize_topic(value)

    @field_validator("availability_topic", mode="before")
    @classmethod
    def _normalize_optional_topic(cls, value: Any) -> Any:
        if value is None or not isinstance(value, str):
            return value
        return cls._normalize_topic(value)

    @field_validator("legacy_discovery_entity_ids")
    @classmethod
    def _validate_legacy_entity_ids(cls, value: list[str]) -> list[str]:
        for entity_id in value:
            if not re.fullmatch(r"sensor\.[a-z0-9_]+", entity_id):
                raise ValueError(
                    "legacy_discovery_entity_ids must contain lowercase "
                    "sensor entity IDs"
                )
        return value

    @field_validator("device_identifier")
    @classmethod
    def _validate_device_identifier(cls, value: str) -> str:
        identifier = value.strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", identifier):
            raise ValueError(
                "device_identifier must contain only lowercase letters, "
                "digits, underscores, or hyphens"
            )
        return identifier

    @field_validator("device_name")
    @classmethod
    def _validate_device_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("device_name must not be empty")
        return name

    @model_validator(mode="after")
    def _complete_and_validate_lifecycle(self) -> "MqttSettings":
        if self.availability_topic is None:
            self.availability_topic = f"{self.base_topic}/status"

        if not self.retain_discovery:
            raise ValueError(
                "retain_discovery must be true so entities survive MQTT reloads"
            )
        if self.heartbeat_seconds == 0 and self.expire_after != 0:
            raise ValueError(
                "expire_after must be 0 when heartbeat_seconds is disabled"
            )
        if (
            self.heartbeat_seconds > 0
            and self.expire_after <= self.heartbeat_seconds
        ):
            raise ValueError(
                "expire_after must be greater than heartbeat_seconds"
            )
        return self

    @staticmethod
    def _normalize_topic(value: str) -> str:
        topic = value.strip().strip("/")
        if not topic:
            raise ValueError("MQTT topics must not be empty")
        if any(character in topic for character in _MQTT_TOPIC_FORBIDDEN_CHARACTERS):
            raise ValueError("MQTT topics must not contain '+', '#', or NUL")
        if "//" in topic:
            raise ValueError("MQTT topics must not contain empty path segments")
        return topic


class MqttEntityManager:
    """
    Publish SafetyFunctions entities through Home Assistant MQTT discovery.

    The manager owns discovery, state, JSON attributes, availability, retained
    cleanup, and heartbeat publication for internal SafetyFunctions sensors.
    """

    def __init__(
        self,
        hass_app: hass.Hass,
        mqtt_config: MqttSettings | Mapping[str, Any] | None = None,
        *,
        strict_validation: bool = True,
    ) -> None:
        self.hass_app = hass_app
        if isinstance(mqtt_config, MqttSettings):
            self.settings = mqtt_config
        else:
            self.settings = MqttSettings.model_validate(
                dict(mqtt_config or {}),
                context={"strict_validation": strict_validation},
            )

        self.discovery_prefix = self.settings.discovery_prefix
        self.base_topic = self.settings.base_topic
        self.availability_topic = str(self.settings.availability_topic)
        self.device_identifier = self.settings.device_identifier
        self.device_name = self.settings.device_name
        self.retain_discovery = self.settings.retain_discovery
        self.retain_state = self.settings.retain_state
        self.qos = self.settings.qos

        self.entity_attributes: dict[str, dict[str, Any]] = {}
        self.entity_states: dict[str, Any] = {}
        self.discovered_entities: set[str] = set()
        self._discovery_payloads: dict[str, str] = {}
        self._prepared_entities: set[str] = set()

    def cleanup_legacy_discovery_topics(self) -> None:
        """Remove explicitly configured legacy retained discovery messages."""
        for entity_id in self.settings.legacy_discovery_entity_ids:
            self._publish(self.legacy_discovery_topic(entity_id), "", retain=True)

    def publish_availability(self, online: bool = True) -> None:
        """Publish app availability to the configured MQTT availability topic."""
        self._publish(
            self.availability_topic,
            "online" if online else "offline",
            retain=True,
        )

    def register_sensor(
        self,
        entity_id: str,
        name: str,
        *,
        state: Any = _UNSET,
        attributes: dict[str, Any] | None = None,
        icon: str | None = None,
        device_class: str | None = None,
        unit_of_measurement: str | None = None,
        state_class: str | None = None,
        entity_category: str | None = None,
    ) -> str:
        """
        Register an MQTT sensor and optionally publish its initial state.

        Returns:
            str: The canonical Home Assistant entity ID.
        """
        canonical_id = self.canonical_entity_id(entity_id, expected_domain="sensor")
        self._prepare_entity_topics(canonical_id)

        discovery_payload = self._sensor_discovery_payload(
            canonical_id,
            name,
            icon=icon,
            device_class=device_class,
            unit_of_measurement=unit_of_measurement,
            state_class=state_class,
            entity_category=entity_category,
        )
        encoded_discovery = json.dumps(
            discovery_payload, sort_keys=True, default=str
        )
        if self._discovery_payloads.get(canonical_id) != encoded_discovery:
            self._publish(
                self.discovery_topic(canonical_id),
                encoded_discovery,
                retain=self.retain_discovery,
            )
            self._discovery_payloads[canonical_id] = encoded_discovery

        self.discovered_entities.add(canonical_id)

        if attributes is not None:
            self.publish_sensor_attributes(canonical_id, attributes)
        if state is not _UNSET:
            self.publish_sensor_state(canonical_id, state)
        return canonical_id

    def publish_sensor_state(
        self,
        entity_id: str,
        state: Any,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Publish a sensor state and optional JSON attributes."""
        canonical_id = self.canonical_entity_id(entity_id, expected_domain="sensor")
        if canonical_id not in self.discovered_entities:
            self.register_sensor(
                canonical_id,
                self._friendly_name(canonical_id),
                state=state,
                attributes=attributes,
            )
            return

        if attributes is not None:
            self.publish_sensor_attributes(canonical_id, attributes)

        self.entity_states[canonical_id] = state
        self._publish(
            self.state_topic(canonical_id),
            self._state_payload(state),
            retain=self.retain_state,
        )

    def publish_sensor_attributes(
        self, entity_id: str, attributes: Mapping[str, Any]
    ) -> None:
        """Publish JSON attributes for a registered sensor."""
        canonical_id = self.canonical_entity_id(entity_id, expected_domain="sensor")
        self.entity_attributes[canonical_id] = dict(attributes)
        self._publish_json(
            self.attributes_topic(canonical_id),
            self.entity_attributes[canonical_id],
            retain=self.retain_state,
        )

    def publish_heartbeat(self) -> None:
        """Refresh cached state and attributes after restarts and for expiry."""
        for entity_id, state in list(self.entity_states.items()):
            self._publish(
                self.state_topic(entity_id),
                self._state_payload(state),
                retain=self.retain_state,
            )
        for entity_id, attributes in list(self.entity_attributes.items()):
            self._publish_json(
                self.attributes_topic(entity_id),
                attributes,
                retain=self.retain_state,
            )

    def get_attributes(self, entity_id: str) -> dict[str, Any]:
        """Return the last attributes published for an MQTT entity."""
        canonical_id = self.canonical_entity_id(entity_id, expected_domain="sensor")
        return dict(self.entity_attributes.get(canonical_id, {}))

    def remove_sensor(self, entity_id: str, *, remove_legacy_topic: bool = False) -> None:
        """Remove a sensor's retained discovery, state, and attribute messages."""
        canonical_id = self.canonical_entity_id(entity_id, expected_domain="sensor")
        topics = [
            self.discovery_topic(canonical_id),
            self.state_topic(canonical_id),
            self.attributes_topic(canonical_id),
        ]
        if remove_legacy_topic:
            topics.append(self.legacy_discovery_topic(canonical_id))

        for topic in dict.fromkeys(topics):
            self._publish(topic, "", retain=True)

        self.discovered_entities.discard(canonical_id)
        self._prepared_entities.discard(canonical_id)
        self._discovery_payloads.pop(canonical_id, None)
        self.entity_states.pop(canonical_id, None)
        self.entity_attributes.pop(canonical_id, None)

    def state_topic(self, entity_id: str) -> str:
        """Return the state topic for an entity."""
        canonical_id = self.canonical_entity_id(entity_id)
        return f"{self.base_topic}/state/{self._object_id(canonical_id)}"

    def attributes_topic(self, entity_id: str) -> str:
        """Return the JSON attributes topic for an entity."""
        canonical_id = self.canonical_entity_id(entity_id)
        return f"{self.base_topic}/attributes/{self._object_id(canonical_id)}"

    def discovery_topic(self, entity_id: str) -> str:
        """Return the collision-resistant discovery topic for a sensor."""
        canonical_id = self.canonical_entity_id(entity_id, expected_domain="sensor")
        return (
            f"{self.discovery_prefix}/sensor/"
            f"{self._unique_id(canonical_id)}/config"
        )

    def legacy_discovery_topic(self, entity_id: str) -> str:
        """Return the discovery topic generated by the pre-migration code."""
        canonical_id = self.canonical_entity_id(entity_id, expected_domain="sensor")
        return (
            f"{self.discovery_prefix}/sensor/"
            f"{self._object_id(canonical_id)}/config"
        )

    def _prepare_entity_topics(self, entity_id: str) -> None:
        if entity_id in self._prepared_entities:
            return
        if self.settings.clear_retained_state_on_start:
            self._publish(self.state_topic(entity_id), "", retain=True)
            self._publish(self.attributes_topic(entity_id), "", retain=True)
        self._prepared_entities.add(entity_id)

    def _sensor_discovery_payload(
        self,
        entity_id: str,
        name: str,
        *,
        icon: str | None,
        device_class: str | None,
        unit_of_measurement: str | None,
        state_class: str | None,
        entity_category: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": name,
            "unique_id": self._unique_id(entity_id),
            "default_entity_id": entity_id,
            "state_topic": self.state_topic(entity_id),
            "json_attributes_topic": self.attributes_topic(entity_id),
            "availability_topic": self.availability_topic,
            "qos": self.qos,
            "device": {
                "identifiers": [self.device_identifier],
                "name": self.device_name,
                "manufacturer": "SafetyComponent",
                "model": "AppDaemon Safety Component",
            },
            "origin": {
                "name": "SafetyComponent",
                "sw_version": "1",
                "support_url": "https://github.com/Arkaqius/SafetyComponent",
            },
        }
        if self.settings.expire_after > 0:
            payload["expire_after"] = self.settings.expire_after

        optional_values = {
            "icon": icon,
            "device_class": device_class,
            "unit_of_measurement": unit_of_measurement,
            "state_class": state_class,
            "entity_category": entity_category,
        }
        payload.update(
            {key: value for key, value in optional_values.items() if value is not None}
        )
        return payload

    def _unique_id(self, entity_id: str) -> str:
        return f"{self._slug(self.device_identifier)}_{self._object_id(entity_id)}"

    def _object_id(self, entity_id: str) -> str:
        return entity_id.split(".", 1)[1]

    @classmethod
    def canonical_entity_id(
        cls, entity_id: str, *, expected_domain: str | None = None
    ) -> str:
        """Return a lowercase valid entity ID while preserving legacy tokens."""
        if not isinstance(entity_id, str) or entity_id.count(".") != 1:
            raise ValueError(f"Invalid Home Assistant entity_id: {entity_id!r}")
        raw_domain, raw_object_id = entity_id.split(".", 1)
        domain = cls._slug(raw_domain)
        object_id = cls._slug(raw_object_id)
        if not domain or not object_id:
            raise ValueError(f"Invalid Home Assistant entity_id: {entity_id!r}")
        if expected_domain and domain != expected_domain:
            raise ValueError(
                f"Expected a {expected_domain} entity, got {entity_id!r}"
            )
        return f"{domain}.{object_id}"

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", value)
        slug = re.sub(r"_+", "_", slug).strip("_")
        return slug.lower()

    @staticmethod
    def _friendly_name(entity_id: str) -> str:
        return entity_id.split(".", 1)[-1].replace("_", " ").title()

    @staticmethod
    def _state_payload(state: Any) -> str:
        if state is None:
            return "None"
        return str(state)

    def _publish_json(
        self, topic: str, payload: Mapping[str, Any], *, retain: bool
    ) -> None:
        self._publish(
            topic,
            json.dumps(dict(payload), sort_keys=True, default=str),
            retain=retain,
        )

    def _publish(self, topic: str, payload: str, *, retain: bool) -> None:
        response = self.hass_app.call_service(
            "mqtt/publish",
            topic=topic,
            payload=payload,
            retain=retain,
            qos=self.qos,
        )
        if isinstance(response, Mapping) and response.get("success") is False:
            raise RuntimeError(f"MQTT publish failed for {topic}: {response}")
