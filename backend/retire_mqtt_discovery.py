"""Audit or explicitly retire selected obsolete SafetyComponent MQTT entities.

Only discovery messages are retired. State, attributes, fault evidence and
Recorder history are preserved; no synthetic PASS or fault-clear is published.
Select entity IDs verified against the current installation before --apply.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

from components.core.mqtt_entity_manager import MqttEntityManager
from migrate_mqtt_retained import RetainedMigration, create_client


class DiscoveryRetirement(RetainedMigration):
    """Retire exact selected discovery topics only after ownership validation."""

    def __init__(
        self, client: Any, entity_ids: list[str], mqtt_config: dict[str, str],
        scan_seconds: float = 5, timeout: float = 10,
    ) -> None:
        if not entity_ids or len(entity_ids) > 100:
            raise ValueError("Select 1..100 explicitly reviewed entity IDs")
        manager = MqttEntityManager(None, mqtt_config)
        self.expected: dict[str, tuple[str, str, str]] = {}
        for entity_id in entity_ids:
            canonical = manager.canonical_entity_id(entity_id, expected_domain="sensor")
            if canonical != entity_id:
                raise ValueError("Entity IDs must be canonical sensor IDs")
            for topic in (manager.discovery_topic(canonical), manager.legacy_discovery_topic(canonical)):
                self.expected[topic] = (
                    manager._unique_id(canonical), manager.state_topic(canonical),
                    manager.attributes_topic(canonical),
                )
        self.device_identifier = manager.device_identifier
        super().__init__(client, manager.base_topic, scan_seconds, timeout)

    def _on_subscribe(
        self, client: Any, userdata: Any, mid: int, reasons: Any,
        properties: Any = None,
    ) -> None:
        if len(reasons) != len(self.expected) or any(reason != 1 for reason in reasons):
            self.error = "Broker did not grant every exact discovery subscription"
        else:
            self.subscribed = True

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        if not message.retain or not message.payload or message.topic not in self.expected:
            return
        try:
            payload = json.loads(message.payload)
            unique_id, state_topic, attributes_topic = self.expected[message.topic]
            if (
                not isinstance(payload, dict)
                or payload.get("unique_id") != unique_id
                or payload.get("state_topic") != state_topic
                or payload.get("json_attributes_topic") != attributes_topic
                or payload.get("device", {}).get("identifiers") != [self.device_identifier]
            ):
                raise ValueError("Discovery ownership mismatch")
        except (ValueError, TypeError, AttributeError):
            self.error = f"Refusing unverified discovery topic: {message.topic}"
            return
        self.topics.add(message.topic)

    def scan(self) -> set[str]:
        """Scan only the selected primary/legacy discovery topics."""

        self.topics.clear()
        self.subscribed = False
        result, _ = self.client.subscribe([(topic, 1) for topic in sorted(self.expected)])
        if result != 0:
            raise RuntimeError("MQTT subscription failed")
        self._wait(lambda: self.subscribed)
        deadline = time.monotonic() + self.scan_seconds
        while time.monotonic() < deadline:
            self._loop(min(0.2, max(0.001, deadline - time.monotonic())))
        return set(self.topics)


def main() -> int:
    """Audit selected topics by default; require --apply for retirement."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--entity-id", action="append", required=True)
    parser.add_argument("--base-topic", default="safety_component")
    parser.add_argument("--discovery-prefix", default="homeassistant")
    parser.add_argument("--device-identifier", default="safety_component")
    parser.add_argument("--scan-seconds", type=float, default=5)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--tls", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    username = os.environ.get("MQTT_USERNAME")
    if not username:
        parser.error("Set MQTT_USERNAME for an authenticated diagnostic session")
    try:
        migration = DiscoveryRetirement(
            create_client(username, os.environ.get("MQTT_PASSWORD"), tls=args.tls),
            args.entity_id,
            {"base_topic": args.base_topic, "discovery_prefix": args.discovery_prefix,
             "device_identifier": args.device_identifier},
            args.scan_seconds, args.timeout,
        )
        remaining = migration.run(args.host, args.port, apply=args.apply)
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"Retirement failed: {error}\n")
    return 2 if remaining else 0


if __name__ == "__main__":
    raise SystemExit(main())
