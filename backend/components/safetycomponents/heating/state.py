"""Compatibility checks for durable heating evidence across additive upgrades."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

from .schema import RULE_POLICY_FIELDS


def fingerprint(config: dict[str, Any]) -> str:
    """Hash the semantic contract independently of presentation labels."""
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def legacy_fingerprint(config: dict[str, Any]) -> str:
    """Project unchanged diagnostic installations onto the original v1 schema."""
    legacy = deepcopy(config)
    legacy.pop("maximum_clock_drift_seconds", None)
    for profile in legacy["profiles"].values():
        for field in RULE_POLICY_FIELDS.values():
            if profile.pop(field, None) is not None:
                # Version 1 cannot prove compatibility of newly selected rules.
                return ""
    return fingerprint(legacy)


def compatible_contract(old: Any, new: Any, *, field: str = "") -> bool:
    """Accept additions while preserving every previously admitted contract."""
    if isinstance(old, dict) and isinstance(new, dict):
        return all(
            key in new and compatible_contract(value, new[key], field=key)
            for key, value in old.items()
        )
    if field == "enabled_rules" and isinstance(old, list) and isinstance(new, list):
        return set(old) <= set(new)
    if field in RULE_POLICY_FIELDS.values() and old is None:
        return True
    return old == new
