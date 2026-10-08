"""Audit or explicitly remove retained SafetyComponent state and attributes."""

from __future__ import annotations

import argparse
import os
import re
import time
import uuid
from typing import Any, Callable


class RetainedMigration:
    """Limit broker work to one clean MQTT session and exact owned topics."""

    def __init__(
        self, client: Any, base_topic: str, scan_seconds: float, timeout: float
    ) -> None:
        base_topic = base_topic.strip().strip("/")
        if (
            not base_topic
            or any(character in base_topic for character in "+#\x00")
            or "//" in base_topic
        ):
            raise ValueError("Invalid base topic")
        if not 0 < scan_seconds <= 60 or not 0 < timeout <= 60:
            raise ValueError("Scan and acknowledgement limits must be 0..60 seconds")
        self.client = client
        self.base_topic = base_topic
        self.scan_seconds = scan_seconds
        self.timeout = timeout
        self.topics: set[str] = set()
        self.connected = False
        self.subscribed = False
        self.error: str | None = None
        self._owned_topic = re.compile(
            rf"{re.escape(base_topic)}/(?:state|attributes)/[a-z0-9_]+"
        )
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_subscribe = self._on_subscribe
        client.on_message = self._on_message

    def _on_connect(
        self, client: Any, userdata: Any, flags: Any, reason: Any,
        properties: Any = None,
    ) -> None:
        if reason != 0:
            self.error = "Broker rejected the connection"
        else:
            self.connected = True

    def _on_disconnect(self, *args: Any) -> None:
        self.connected = False
        self.error = "Broker disconnected during migration"

    def _on_subscribe(
        self, client: Any, userdata: Any, mid: int, reasons: Any,
        properties: Any = None,
    ) -> None:
        if len(reasons) != 2 or any(reason != 1 for reason in reasons):
            self.error = "Broker did not grant both QoS 1 subscriptions"
        else:
            self.subscribed = True

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        if (
            message.retain
            and message.payload
            and self._owned_topic.fullmatch(message.topic)
        ):
            self.topics.add(message.topic)

    def _loop(self, timeout: float) -> None:
        if self.client.loop(timeout=timeout) != 0:
            raise RuntimeError("MQTT network operation failed")
        if self.error:
            raise RuntimeError(self.error)

    def _wait(self, ready: Callable[[], bool]) -> None:
        deadline = time.monotonic() + self.timeout
        while not ready():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("MQTT acknowledgement timed out")
            self._loop(min(remaining, 0.2))

    def scan(self) -> set[str]:
        """Collect retained messages during a bounded, acknowledged subscription."""
        self.topics.clear()
        self.subscribed = False
        result, _ = self.client.subscribe([
            (f"{self.base_topic}/state/+", 1),
            (f"{self.base_topic}/attributes/+", 1),
        ])
        if result != 0:
            raise RuntimeError("MQTT subscription failed")
        self._wait(lambda: self.subscribed)
        deadline = time.monotonic() + self.scan_seconds
        while time.monotonic() < deadline:
            self._loop(min(0.2, max(0.001, deadline - time.monotonic())))
        return set(self.topics)

    def run(self, host: str, port: int, *, apply: bool = False) -> set[str]:
        """Audit by default; apply tombstones only to retained topics observed."""
        try:
            if self.client.connect(host, port, keepalive=15) != 0:
                raise RuntimeError("MQTT connection failed")
            self._wait(lambda: self.connected)
            topics = self.scan()
            for topic in sorted(topics):
                print(topic)
            print(f"Observed retained topics: {len(topics)}")
            if not apply:
                return topics
            for topic in sorted(topics):
                result = self.client.publish(topic, payload="", qos=1, retain=True)
                if result.rc != 0:
                    raise RuntimeError(f"MQTT deletion failed: {topic}")
                self._wait(result.is_published)
            remaining = self.scan()
            if remaining:
                raise RuntimeError(
                    f"Retained messages remain after migration: {sorted(remaining)}"
                )
            print("Verification: no retained messages observed in the scan window")
            return remaining
        finally:
            self.client.disconnect()


def create_client(username: str, password: str | None, *, tls: bool) -> Any:
    """Create a unique MQTT 3.1.1 client without persistent broker subscriptions."""
    import paho.mqtt.client as mqtt

    options: dict[str, Any] = {
        "client_id": f"sc-retained-{uuid.uuid4().hex}",
        "clean_session": True,
        "protocol": mqtt.MQTTv311,
        "reconnect_on_failure": False,
    }
    if hasattr(mqtt, "CallbackAPIVersion"):
        options["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION2
    client = mqtt.Client(**options)
    client.username_pw_set(username, password)
    if tls:
        client.tls_set()
    return client


def main() -> int:
    """Run a finite broker audit, requiring an explicit flag for deletion."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--base-topic", default="safety_component")
    parser.add_argument("--scan-seconds", type=float, default=5)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--tls", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    username = os.environ.get("MQTT_USERNAME")
    if not username:
        parser.error("Set MQTT_USERNAME for an authenticated diagnostic session")
    try:
        client = create_client(
            username, os.environ.get("MQTT_PASSWORD"), tls=args.tls
        )
        migration = RetainedMigration(
            client, args.base_topic, args.scan_seconds, args.timeout
        )
        remaining = migration.run(args.host, args.port, apply=args.apply)
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"Migration failed: {error}\n")
    return 2 if remaining else 0


if __name__ == "__main__":
    raise SystemExit(main())
