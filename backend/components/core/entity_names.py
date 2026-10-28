"""Resolve operator-facing entity names without changing runtime identities."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def friendly_entity_name(app: Any, entity_id: str | None, fallback: str) -> str:
    """Use HA's current friendly name when available, otherwise retain context."""
    if not entity_id:
        return fallback
    try:
        snapshot = app.get_state(entity_id, attribute="all")
    except Exception:
        # Missing display metadata must not prevent a safety warning or task.
        return fallback
    if isinstance(snapshot, Mapping):
        attributes = snapshot.get("attributes")
        if isinstance(attributes, Mapping):
            name = attributes.get("friendly_name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return fallback
