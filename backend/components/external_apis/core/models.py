"""Immutable normalized contracts shared by external API adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class HazardType(str, Enum):
    """Hazard identities understood by the external-hazard policy."""

    FROST = "frost"
    WIND = "wind"
    RAIN = "rain"
    STORM = "storm"
    OUTDOOR_AIR_POLLUTION = "outdoor_air_pollution"


class ProviderHealthState(str, Enum):
    """Stable provider diagnostic states."""

    OK = "ok"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    SCHEMA_ERROR = "schema_error"


@dataclass(frozen=True)
class Measurement:
    """One provider value with its original unit and semantics."""

    value: float | int | str | bool
    unit: str | None = None


@dataclass(frozen=True)
class ExternalObservation:
    """Normalized provider observation consumed by household policy."""

    provider: str
    observation_id: str
    hazard_type: HazardType
    provider_level: str | None
    values: Mapping[str, Measurement]
    observed_at: datetime | None
    valid_from: datetime
    valid_to: datetime
    retrieved_at: datetime
    region_codes: tuple[str, ...] = ()
    confidence: float | None = None
    authority_confirmed: bool = False
    source_reference: str = ""

    def __post_init__(self) -> None:
        for value in (self.observed_at, self.valid_from, self.valid_to, self.retrieved_at):
            if value is not None and value.tzinfo is None:
                raise ValueError("External observation datetimes must be timezone-aware")
        if self.valid_to < self.valid_from:
            raise ValueError("External observation valid_to precedes valid_from")


@dataclass(frozen=True)
class ProviderHealth:
    """Health snapshot for one provider adapter."""

    provider: str
    state: ProviderHealthState
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    consecutive_failures: int
    detail_code: str | None = None
    stale_after_seconds: int = 0


@dataclass(frozen=True)
class ApiResult:
    """One complete provider snapshot returned by a poll."""

    provider: str
    observations: tuple[ExternalObservation, ...]
    health: ProviderHealth
    evidence: Mapping[str, Any] = field(default_factory=dict)


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def parse_datetime(value: Any, *, default: datetime | None = None) -> datetime:
    """Parse common provider timestamps and normalize them to UTC."""

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        candidate = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            parsed = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    parsed = datetime.strptime(candidate, fmt)
                    break
                except ValueError:
                    continue
            if parsed is None:
                raise ValueError(f"Unsupported datetime value: {value!r}")
    elif default is not None:
        parsed = default
    else:
        raise ValueError(f"Missing datetime value: {value!r}")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
