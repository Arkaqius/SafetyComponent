"""Bounded, restart-safe journal of actual mobile submission attempts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from components.notification_manager.models import PendingDelivery, TargetDeliveryResult


HISTORY_LIMIT = 100
TEXT_LIMIT = 2048
_STATES = {
    "new": "SET",
    "update": "SET",
    "repeat": "SET",
    "acknowledged": "SET",
    "resolved": "CLEARED",
    "clear": "SHADOWED",
}


def submission_entry(
    delivery: PendingDelivery, target: TargetDeliveryResult, attempted_at: float
) -> dict[str, Any]:
    """Snapshot one target result without storing transport errors or payloads."""

    return {
        "id": str(uuid4()),
        "tag": delivery.tag[:256],
        "kind": delivery.kind,
        "fault_state": _STATES[delivery.kind],
        "level": delivery.level,
        "title": delivery.title[:TEXT_LIMIT],
        "message": delivery.message[:TEXT_LIMIT],
        "text_truncated": (
            len(delivery.title) > TEXT_LIMIT or len(delivery.message) > TEXT_LIMIT
        ),
        "created_at": datetime.fromtimestamp(
            delivery.created_at, timezone.utc
        ).isoformat(),
        "attempted_at": datetime.fromtimestamp(attempted_at, timezone.utc).isoformat(),
        "attempt": delivery.attempts,
        "service": target.service[:256],
        "result": target.disposition.value,
        "deadline_missed": delivery.deadline_missed,
    }


def restore_history(raw: Any) -> list[dict[str, Any]]:
    """Ignore damaged journal entries without losing active lifecycle state."""

    if not isinstance(raw, list):
        return []
    entries = []
    for entry in raw[-HISTORY_LIMIT:]:
        if not isinstance(entry, dict):
            continue
        try:
            kind = entry["kind"]
            if kind not in _STATES or entry["fault_state"] != _STATES[kind]:
                continue
            if entry["result"] not in {"accepted_by_home_assistant", "failed"}:
                continue
            if type(entry["level"]) is not int or entry["level"] not in (1, 2, 3):  # noqa: E721 - reject bool and int subclasses
                continue
            if type(entry["attempt"]) is not int or entry["attempt"] < 1:  # noqa: E721 - reject bool and int subclasses
                continue
            restored = {
                key: entry[key][:limit]
                for key, limit in {
                    "id": 256,
                    "tag": 256,
                    "title": TEXT_LIMIT,
                    "message": TEXT_LIMIT,
                    "service": 256,
                    "created_at": 64,
                    "attempted_at": 64,
                }.items()
                if isinstance(entry[key], str)
            }
            if len(restored) != 7 or not restored["id"]:
                continue
            for key in ("created_at", "attempted_at"):
                if datetime.fromisoformat(restored[key]).tzinfo is None:
                    raise ValueError("History timestamps must include a timezone")
            restored.update(
                kind=kind,
                fault_state=_STATES[kind],
                level=entry["level"],
                attempt=entry["attempt"],
                result=entry["result"],
                deadline_missed=entry.get("deadline_missed") is True,
                text_truncated=entry.get("text_truncated") is True,
            )
            entries.append(restored)
        except (KeyError, TypeError, ValueError):
            continue
    return entries
