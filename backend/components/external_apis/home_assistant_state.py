"""Read source report timestamps that AppDaemon's state-change cache omits."""

from __future__ import annotations

import json
import os
from http.client import HTTPException
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


REPORT_TEMPLATE = """
{% set ns = namespace(rows=[]) %}
{% for entity in entities %}
  {% set matches = expand(entity) %}
  {% if matches %}
    {% set s = matches[0] %}
    {% set ns.rows = ns.rows + [dict(entity_id=s.entity_id, state=s.state,
      attributes=s.attributes, last_reported=s.last_reported.isoformat(),
      last_updated=s.last_updated.isoformat())] %}
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

    def poll(self, entities: set[str]) -> dict[str, dict[str, Any]]:
        """Return no evidence on transport/schema failure; never reuse old data."""
        if not entities:
            return {}
        request = Request(
            "http://supervisor/core/api/template",
            data=json.dumps({"template": REPORT_TEMPLATE, "variables": {"entities": sorted(entities)}}).encode(),
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=3) as response:
                body = response.read(512 * 1024 + 1)
            if len(body) > 512 * 1024:
                return {}
            rows = json.loads(body)
            if not isinstance(rows, list):
                return {}
            result = {}
            for row in rows:
                if not isinstance(row, dict) or row.get("entity_id") not in entities:
                    return {}
                if not isinstance(row.get("attributes"), dict) or not isinstance(row.get("state"), str):
                    return {}
                if not isinstance(row.get("last_reported"), str):
                    return {}
                if row["entity_id"] in result:
                    return {}
                result[row["entity_id"]] = row
            return result
        except (OSError, URLError, HTTPException, ValueError, TypeError):
            return {}
