"""Normalize HA battery sources and preserve device identity across renames."""

from __future__ import annotations

import re
from typing import Any, Mapping

DEVICE_ID = re.compile(r"^[0-9a-f]{32}$")

BATTERY_TEMPLATE = """
{% set ns = namespace(rows=[]) %}
{% for s in states.sensor | list + states.binary_sensor | list %}
  {% if s.attributes.get('device_class') == 'battery' %}
    {% set device = device_id(s.entity_id) %}
    {% if device and (s.domain == 'binary_sensor' or s.attributes.get('unit_of_measurement') == '%') %}
      {% set ns.rows = ns.rows + [dict(entity_id=s.entity_id, device_id=device,
        friendly_name=device_attr(device, 'name_by_user') or device_attr(device, 'name') or device,
        state=s.state, attributes=s.attributes, last_reported=s.last_reported.isoformat())] %}
    {% endif %}
  {% endif %}
{% endfor %}
{{ ns.rows | to_json }}
"""


def group_batteries(rows: Any) -> dict[str, Any]:
    """Fail closed on malformed/oversized inventory; group all valid sources."""
    if not isinstance(rows, list) or len(rows) > 512:
        return {"status": "error", "devices": []}
    devices: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            return {"status": "error", "devices": []}
        device, entity, attrs = row.get("device_id"), row.get("entity_id"), row.get("attributes")
        if not isinstance(device, str) or not DEVICE_ID.fullmatch(device):
            return {"status": "error", "devices": []}
        if not isinstance(entity, str) or not isinstance(attrs, dict) or attrs.get("device_class") != "battery":
            return {"status": "error", "devices": []}
        if entity.startswith("sensor.") and attrs.get("unit_of_measurement") == "%":
            kind = "percentage"
        elif entity.startswith("binary_sensor."):
            kind = "low"
        else:
            return {"status": "error", "devices": []}
        if entity in seen or not isinstance(row.get("state"), str) or not isinstance(row.get("last_reported"), str):
            return {"status": "error", "devices": []}
        seen.add(entity)
        item = devices.setdefault(device, {
            "device_id": device, "key": f"Battery{device}",
            "friendly_name": str(row.get("friendly_name") or device),
            "percentage_entities": [], "low_entities": [], "sources": [],
        })
        item[f"{kind}_entities"].append(entity)
        item["sources"].append({
            "entity_id": entity, "kind": kind, "state": row["state"], "last_reported": row["last_reported"],
        })
    return {"status": "ready", "devices": sorted(devices.values(), key=lambda item: item["device_id"])}


def battery_entities(binding: Mapping[str, Any], kind: str) -> list[str]:
    """Support existing manual bindings and internally generated source lists."""
    return list(dict.fromkeys(list(binding.get(f"{kind}_entities", [])) + ([binding[f"{kind}_entity"]] if binding.get(f"{kind}_entity") else [])))


def resolve_batteries(manual: Mapping[str, Any], inventory: Mapping[str, Any], excluded: list[str]) -> dict[str, Any]:
    """Apply device exclusions and prefer manual owners without duplicate faults."""
    result = dict(manual)
    for device in inventory.get("devices", []):
        sources = set(device["percentage_entities"] + device["low_entities"])
        owners = [key for key, binding in manual.items() if sources.intersection(battery_entities(binding, "percentage") + battery_entities(binding, "low"))]
        if device["device_id"] in excluded:
            for owner in owners:
                result[owner] = {**manual[owner], "enabled": False}
            continue
        if owners:
            owner = owners[0]
            result[owner] = {
                **manual[owner], "device_id": device["device_id"],
                "percentage_entities": list(dict.fromkeys(device["percentage_entities"] + battery_entities(manual[owner], "percentage"))),
                "low_entities": list(dict.fromkeys(device["low_entities"] + battery_entities(manual[owner], "low"))),
            }
            for duplicate in owners[1:]:
                result[duplicate] = {**manual[duplicate], "enabled": False}
        else:
            result[device["key"]] = {key: value for key, value in device.items() if key != "sources"}
    return result
