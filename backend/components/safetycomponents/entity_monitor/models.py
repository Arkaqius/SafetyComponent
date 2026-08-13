"""Runtime models used by Entity Health Monitoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EntitySource(str, Enum):
    """Supported sources of monitored entity dependencies."""

    EXPLICIT = "explicit"
    COMPONENT = "component"


class FaultOwner(str, Enum):
    """Owner responsible for turning a health failure into a fault."""

    ENTITY_MONITOR = "entity_monitor"
    COMPONENT = "component"
    NONE = "none"


class EntityHealthState(str, Enum):
    """Published health state for a monitored entity."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class EntityDependency:
    """Merged monitoring contract for one Home Assistant entity."""

    key: str
    entity_id: str
    sources: frozenset[EntitySource]
    owners: tuple[str, ...]
    purposes: tuple[str, ...]
    fault_owner: FaultOwner
    checks: dict[str, dict[str, Any]]
    failure_debounce_seconds: int
    recovery_debounce_seconds: int
    detection_budget_seconds: int | None = None
    area_id: str | None = None
    area_name: str | None = None


@dataclass
class CheckRuntime:
    """Mutable debounce state for one check."""

    active: bool = False
    pending_failure_since: datetime | None = None
    pending_recovery_since: datetime | None = None
    result: str = "not_tested"
    reason: str = "not_evaluated"
    observed_value: Any = None
    evaluated_at: datetime | None = None


@dataclass
class EntityRuntime:
    """Mutable state and sampling history for one monitored entity."""

    dependency: EntityDependency
    checks: dict[str, CheckRuntime] = field(default_factory=dict)
    samples: dict[str, list[tuple[datetime, float]]] = field(default_factory=dict)
    snapshot: dict[str, Any] | None = None
    last_valid_value: Any = None
    last_valid_at: datetime | None = None
    listener_handle: Any | None = None
    diagnostic_entity_id: str | None = None
