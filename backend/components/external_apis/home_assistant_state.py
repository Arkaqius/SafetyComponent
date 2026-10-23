"""Read source report timestamps that AppDaemon's state-change cache omits."""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from http.client import HTTPException
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from components.external_apis.battery_inventory import BATTERY_TEMPLATE, group_batteries

REPORT_TIMEOUT_SECONDS = 120
FAST_REPORT_TIMEOUT_SECONDS = 4
INVENTORY_TIMEOUT_SECONDS = 3

REPORT_TEMPLATE = """
{% set ns = namespace(rows=[]) %}
{% for entity in entities %}
  {% set matches = expand(entity) %}
  {% if matches %}
    {% set s = matches[0] %}
    {% set contact = namespace(rows=[]) %}
    {% set is_sensor = entity.startswith('sensor.') or entity.startswith('binary_sensor.') %}
    {% set device = device_id(entity) if is_sensor else none %}
    {% for sibling in (device_entities(device) if device else []) %}
      {# HA appends a numeric suffix when resolving entity ID collisions. #}
      {% set name_parts = sibling.rsplit('_', 1) %}
      {% set contact_name = name_parts[0] if name_parts[-1].isdigit() else sibling %}
      {% if sibling.startswith('sensor.') and contact_name.endswith('_last_seen') %}
        {% set contact.rows = contact.rows + [dict(entity_id=sibling, state=states(sibling))] %}
      {% endif %}
    {% endfor %}
    {% set ns.rows = ns.rows + [dict(entity_id=s.entity_id, state=s.state,
      attributes=s.attributes, last_reported=s.last_reported.isoformat(),
      device_last_seen=contact.rows[0] if contact.rows | length == 1 else none,
      device_last_seen_count=contact.rows | length,
      last_updated=s.last_updated.isoformat(), last_changed=s.last_changed.isoformat())] %}
  {% endif %}
{% endfor %}
{{ ns.rows | to_json }}
"""


class HomeAssistantStateProvider:
    """Fetch a bounded batch of live reports without inventing freshness."""

    def __init__(self, token: str) -> None:
        self._token = token

    @classmethod
    def from_environment(cls) -> HomeAssistantStateProvider | None:
        """Use the App's existing Supervisor authorization when available."""
        token = os.environ.get("SUPERVISOR_TOKEN")
        return cls(token) if token else None

    def poll(
        self, entities: set[str], *, timeout_seconds: int = REPORT_TIMEOUT_SECONDS
    ) -> dict[str, dict[str, Any]]:
        """Return no evidence on transport/schema failure; never reuse old data."""
        if not entities:
            return {}
        rows = self.render(
            REPORT_TEMPLATE, {"entities": sorted(entities)}, timeout_seconds=timeout_seconds
        )
        if not isinstance(rows, list):
            return {}
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict) or row.get("entity_id") not in entities:
                return {}
            if not isinstance(row.get("attributes"), dict) or not isinstance(row.get("state"), str):
                return {}
            if not isinstance(row.get("last_reported"), str) or row["entity_id"] in result:
                return {}
            normalized = dict(row)
            contact = normalized.pop("device_last_seen", None)
            contact_count = normalized.pop("device_last_seen_count", None)
            if isinstance(contact_count, int) and not isinstance(contact_count, bool) and contact_count >= 0:
                normalized["last_contact_source_count"] = contact_count
            if isinstance(contact, dict):
                timestamp = parse_device_contact(contact.get("state"))
                source = contact.get("entity_id")
                if isinstance(source, str) and source.startswith("sensor."):
                    normalized["last_contact_source_entity"] = source
                    if timestamp is not None:
                        normalized["last_contact_at"] = timestamp.isoformat()
            result[row["entity_id"]] = normalized
        return result

    def discover_batteries(self) -> dict[str, Any]:
        """Read enabled HA battery states plus associated registry device IDs."""
        return group_batteries(
            self.render(BATTERY_TEMPLATE, {}, timeout_seconds=INVENTORY_TIMEOUT_SECONDS)
        )

    def render(
        self,
        template: str,
        variables: dict[str, Any],
        *,
        timeout_seconds: int = REPORT_TIMEOUT_SECONDS,
    ) -> Any:
        """Render only provider-owned templates using existing App authorization."""
        request = Request(
            "http://supervisor/core/api/template",
            data=json.dumps({"template": template, "variables": variables}).encode(),
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                body = response.read(512 * 1024 + 1)
            if len(body) > 512 * 1024:
                return None
            return json.loads(body)
        except (OSError, URLError, HTTPException, ValueError, TypeError):
            return None


def parse_device_contact(value: Any) -> datetime | None:
    """Normalize device last-seen data without inventing contact from HA writes."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        epoch = float(value)
    except OverflowError:
        return None
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        try:
            parsed = parsed.astimezone(timezone.utc)
        except (OverflowError, ValueError):
            return None
    else:
        if not math.isfinite(epoch) or epoch <= 0:
            return None
        # Zigbee2MQTT may expose Unix milliseconds rather than seconds.
        if epoch >= 100_000_000_000:
            epoch /= 1000
        try:
            parsed = datetime.fromtimestamp(epoch, timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    return parsed if parsed <= datetime.now(timezone.utc) else None
