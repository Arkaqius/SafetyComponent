"""MQTT discovery and state publishing for SafetyFunctions internal entities."""

from __future__ import annotations

import json
import math
import re
import time
from collections import deque
from functools import wraps
from typing import Any, Mapping

import appdaemon.plugins.hass.hassapi as hass
from pydantic import (
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from components.core.localization import Localizer, LocalizationSettings
from components.core.pydantic_utils import StrictBaseModel
from components.core.mqtt_projection import MqttProjectionQueue, ProjectionGroup
from components.core.service_dispatcher import ServiceDispatcher


_UNSET = object()
_MQTT_TOPIC_FORBIDDEN_CHARACTERS = frozenset({"+", "#", "\x00"})


def coherent_projection(method: Any) -> Any:
    """Collect a public entity update before enqueueing its whole desired state."""
    @wraps(method)
    def apply(self: Any, entity_id: str, *args: Any, **kwargs: Any) -> Any:
        outer = self._projection_depth == 0
        self._projection_depth += 1
        if outer:
            self._projection_messages = []
        try:
            result = method(self, entity_id, *args, **kwargs)
        finally:
            self._projection_depth -= 1
        if outer and self.projections is not None and self._projection_messages:
            canonical = self.canonical_entity_id(entity_id, expected_domain="sensor")
            if method.__name__ == "remove_sensor":
                self._removed_projections[canonical] = list(self._projection_messages)
                self.projections.enqueue(canonical, self._projection_messages, {"removed": True})
            else:
                self._queue_projection(canonical)
        return result
    return apply


class MqttSettings(StrictBaseModel):
    """Validated MQTT discovery, state, and lifecycle settings."""

    discovery_prefix: StrictStr = "homeassistant"
    base_topic: StrictStr = "safety_component"
    availability_topic: StrictStr | None = None
    device_identifier: StrictStr = "safety_component"
    device_name: StrictStr = "Safety Component"
    retain_discovery: StrictBool = True
    retain_state: StrictBool = False
    clear_retained_state_on_start: StrictBool = False
    qos: StrictInt = Field(default=0, ge=0, le=2)
    heartbeat_seconds: StrictInt = Field(default=60, ge=0)
    expire_after: StrictInt = Field(default=180, ge=0)

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
        localization: LocalizationSettings | Mapping[str, Any] | None = None,
        dispatcher: ServiceDispatcher | None = None,
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
        self.localizer = Localizer(localization)

        self.entity_attributes: dict[str, dict[str, Any]] = {}
        self.entity_states: dict[str, Any] = {}
        self.discovered_entities: set[str] = set()
        self._discovery_payloads: dict[str, str] = {}
        self._prepared_entities: set[str] = set()
        self._heartbeat_queue: deque[tuple[str, bool]] = deque()
        self._heartbeat_due = 0.0
        self._heartbeat_batch_size = 16
        self._projection_depth = 0
        self._projection_messages: list[dict[str, Any]] = []
        self._cleanup_pending: set[str] = set()
        self.accepted_states: dict[str, Any] = {}
        self.accepted_attributes: dict[str, dict[str, Any]] = {}
        self.accepted_discovery: dict[str, str] = {}
        self._removed_projections: dict[str, list[dict[str, Any]]] = {}
        self.accepted_availability: bool | None = None
        self._desired_availability: bool | None = None
        self.projections = (
            MqttProjectionQueue(dispatcher, self._accept_projection, self._queue_projection)
            if dispatcher is not None else None
        )

    def start(self) -> None:
        """Start owned asynchronous projection processing when configured."""
        if self.projections is not None:
            self.projections.start()

    def stop(self) -> None:
        """Fence future state traffic; offline awaits outstanding MQTT completion.

        The process broker owns the barrier across app reloads. Remote offline
        stays unconfirmed while an already-handed-off call remains unresolved.
        """
        if self.projections is None:
            self.publish_availability(False)
            return
        self.projections.stop()
        self.projections.dispatcher.registry.mqtt_offline_fence({
            "topic": self.availability_topic, "payload": "offline", "retain": True, "qos": self.qos,
        })
        self.projections.dispatcher.tick()

    def _queue_projection(self, entity_id: str) -> None:
        if self.projections is None:
            return
        if entity_id == "availability" and self._desired_availability is not None:
            self.publish_availability(self._desired_availability)
            return
        if entity_id in self._removed_projections and entity_id not in self.discovered_entities:
            self.projections.enqueue(entity_id, self._removed_projections[entity_id], {"removed": True})
            return
        messages = []

        def add(topic: str, payload: str, retain: bool) -> None:
            messages.append({"topic": topic, "payload": payload, "retain": retain, "qos": self.qos})

        if entity_id in self._cleanup_pending:
            add(self.state_topic(entity_id), "", True)
            add(self.attributes_topic(entity_id), "", True)
        if entity_id in self._discovery_payloads:
            add(self.discovery_topic(entity_id), self._discovery_payloads[entity_id], self.retain_discovery)
        if entity_id in self.entity_attributes:
            add(self.attributes_topic(entity_id), self._json_payload(self.entity_attributes[entity_id]), self.retain_state)
        if entity_id in self.entity_states:
            add(self.state_topic(entity_id), self._state_payload(self.entity_states[entity_id]), self.retain_state)
        self.projections.enqueue(entity_id, messages, {
            "discovery": self._discovery_payloads.get(entity_id),
            "has_state": entity_id in self.entity_states,
            "state": self.entity_states.get(entity_id),
            "attributes": self.entity_attributes.get(entity_id),
        })

    def _accept_projection(self, group: ProjectionGroup) -> None:
        snapshot = json.loads(group.snapshot_json)
        if "availability" in snapshot:
            self.accepted_availability = snapshot["availability"]
            return
        if snapshot.get("removed"):
            self.accepted_states.pop(group.entity, None)
            self.accepted_attributes.pop(group.entity, None)
            self.accepted_discovery.pop(group.entity, None)
            self._removed_projections.pop(group.entity, None)
            if self.projections is not None:
                self.projections.retire(group.entity)
            return
        self._cleanup_pending.discard(group.entity)
        if snapshot.get("discovery") is not None:
            self.accepted_discovery[group.entity] = snapshot["discovery"]
        if snapshot.get("has_state"):
            self.accepted_states[group.entity] = snapshot["state"]
        if snapshot.get("attributes") is not None:
            self.accepted_attributes[group.entity] = snapshot["attributes"]

    def publish_availability(self, online: bool = True) -> None:
        """Publish app availability to the configured MQTT availability topic."""
        if self.projections is not None:
            self._desired_availability = online
            if not online:
                self.projections.dispatcher.registry.mqtt_offline_fence({
                    "topic": self.availability_topic, "payload": "offline", "retain": True, "qos": self.qos,
                })
                return
            self.projections.enqueue("availability", [{
                "topic": self.availability_topic, "payload": "online" if online else "offline",
                "retain": True, "qos": self.qos,
            }], {"availability": online, "barrier": {
                entity: self.projections.desired_revisions[entity]
                for entity in self.discovered_entities
                if entity in self.projections.desired_revisions
            }})
            return
        self._publish(
            self.availability_topic,
            "online" if online else "offline",
            retain=True,
        )

    @coherent_projection
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
        display_name = self.localizer.entity_name(canonical_id, name)

        discovery_payload = self._sensor_discovery_payload(
            canonical_id,
            display_name,
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

        effective_attributes = attributes
        state_label = self.localizer.state_label(canonical_id, state)
        if state_label is not None:
            effective_attributes = dict(
                attributes
                if attributes is not None
                else self.entity_attributes.get(canonical_id, {})
            )
            effective_attributes["state_label"] = state_label
            if state is not _UNSET:
                effective_attributes["publication_state"] = self._state_payload(state)

        if effective_attributes is not None:
            self.publish_sensor_attributes(canonical_id, effective_attributes)
        if state is not _UNSET:
            self.publish_sensor_state(canonical_id, state)
        return canonical_id

    @coherent_projection
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

        effective_attributes = attributes
        state_label = self.localizer.state_label(canonical_id, state)
        if state_label is not None:
            effective_attributes = dict(
                attributes
                if attributes is not None
                else self.entity_attributes.get(canonical_id, {})
            )
            effective_attributes["state_label"] = state_label
            effective_attributes["publication_state"] = self._state_payload(state)

        if effective_attributes is not None:
            self.publish_sensor_attributes(canonical_id, effective_attributes)

        if (
            canonical_id in self.entity_states
            and self._state_payload(self.entity_states[canonical_id])
            == self._state_payload(state)
        ):
            return

        self._publish(
            self.state_topic(canonical_id),
            self._state_payload(state),
            retain=self.retain_state,
        )
        self.entity_states[canonical_id] = state

    @coherent_projection
    def publish_sensor_attributes(
        self, entity_id: str, attributes: Mapping[str, Any]
    ) -> None:
        """Publish JSON attributes for a registered sensor."""
        canonical_id = self.canonical_entity_id(entity_id, expected_domain="sensor")
        next_attributes = dict(attributes)
        current_attributes = self.entity_attributes.get(canonical_id)
        if (
            current_attributes is not None
            and self._json_payload(current_attributes)
            == self._json_payload(next_attributes)
        ):
            return

        self._publish_json(
            self.attributes_topic(canonical_id),
            next_attributes,
            retain=self.retain_state,
        )
        self.entity_attributes[canonical_id] = next_attributes

    def publish_heartbeat(self) -> None:
        """Refresh cached state and attributes after restarts and for expiry."""
        if self.projections is not None:
            for entity in self.discovered_entities:
                self._queue_projection(entity)
            return
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

    def publish_heartbeat_batch(self) -> None:
        """Refresh current cached values in bounded, interleaved scheduler work."""
        now = time.monotonic()
        if not self._heartbeat_queue:
            if now < self._heartbeat_due:
                return
            self._heartbeat_queue.extend((key, False) for key in self.entity_states)
            self._heartbeat_queue.extend((key, True) for key in self.entity_attributes)
            interval = max(1, self.settings.heartbeat_seconds)
            self._heartbeat_batch_size = max(
                16, math.ceil(len(self._heartbeat_queue) / interval)
            )
            self._heartbeat_due = now + interval
        for _ in range(min(self._heartbeat_batch_size, len(self._heartbeat_queue))):
            entity_id, attributes = self._heartbeat_queue[0]
            if self.projections is not None:
                self._queue_projection(entity_id)
                self._heartbeat_queue.popleft()
                continue
            # Read at dispatch, never replay a snapshot from the cycle's start.
            cache = self.entity_attributes if attributes else self.entity_states
            if entity_id in cache:
                if attributes:
                    self._publish_json(
                        self.attributes_topic(entity_id), cache[entity_id],
                        retain=self.retain_state,
                    )
                else:
                    self._publish(
                        self.state_topic(entity_id), self._state_payload(cache[entity_id]),
                        retain=self.retain_state,
                    )
            # A failed publication stays at the head for the next attempt.
            self._heartbeat_queue.popleft()

    def get_attributes(self, entity_id: str) -> dict[str, Any]:
        """Return the last attributes published for an MQTT entity."""
        canonical_id = self.canonical_entity_id(entity_id, expected_domain="sensor")
        return dict(self.entity_attributes.get(canonical_id, {}))

    @coherent_projection
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
            if self.projections is not None:
                self._cleanup_pending.add(entity_id)
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
            "json_attributes_template": (
                "{{ value if value | trim else this.attributes | to_json }}"
            ),
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
            self._json_payload(payload),
            retain=retain,
        )

    @staticmethod
    def _json_payload(payload: Mapping[str, Any]) -> str:
        return json.dumps(dict(payload), sort_keys=True, default=str)

    def _publish(self, topic: str, payload: str, *, retain: bool) -> None:
        if self.projections is not None:
            self._projection_messages.append({
                "topic": topic, "payload": payload, "retain": retain, "qos": self.qos,
            })
            return
        response = self.hass_app.call_service(
            "mqtt/publish",
            topic=topic,
            payload=payload,
            retain=retain,
            qos=self.qos,
        )
        if isinstance(response, Mapping) and response.get("success") is False:
            raise RuntimeError(f"MQTT publish failed for {topic}: {response}")
