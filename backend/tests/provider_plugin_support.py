"""Controlled regional providers for configuration and full-startup acceptance."""

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from components.external_apis.core.api_component import ExternalApiComponent
from components.external_apis.core.models import (
    ApiResult,
    HazardType,
    ProviderCapability,
    ProviderHealth,
    ProviderHealthState,
)


class RegionalParameters(BaseModel):
    """Installation-only region selection for a synthetic provider."""

    model_config = ConfigDict(extra="forbid")
    region_code: str | None = Field(
        default=None, min_length=1, max_length=32, title="Region"
    )


class RegionalTransport(BaseModel):
    """Packaged lifecycle schema proving provider-specific system fields."""

    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    base_url: str
    poll_interval_seconds: int = Field(ge=60)
    request_timeout_seconds: float = Field(gt=0, le=30)
    max_retries: int = Field(default=0, ge=0, le=5)
    stale_after_seconds: int = Field(ge=60)
    feed_variant: str = "controlled"


class RegionalWarnings(ExternalApiComponent):
    """Synthetic non-Polish wind warning adapter without network access."""

    component_name = "RegionalWarningsApiComponent"
    config_model = RegionalTransport
    parameter_model = RegionalParameters
    required_when_enabled = frozenset({"region_code"})
    capability = ProviderCapability.OFFICIAL_WARNINGS
    hazards = frozenset({HazardType.WIND})
    countries = frozenset({"DE"})
    display_name = "Regionalne ostrzeżenia testowe"
    description = "Kontrolowane źródło do testów."

    def fetch_payload(self) -> Any:
        """Return a complete controlled empty feed."""
        return []

    def normalize(self, payload: Any, retrieved_at: datetime) -> tuple:
        """Return no current warnings without inventing measurements."""
        return ()


class PeerRegionalWarnings(RegionalWarnings):
    """Second source with the same capability for independence tests."""

    component_name = "PeerRegionalWarningsApiComponent"


def provider_policy(**overrides: Any) -> dict[str, Any]:
    """Return sanitized system-owned provider defaults."""
    return {
        "enabled": True,
        "base_url": "https://example.invalid/warnings",
        "poll_interval_seconds": 300,
        "request_timeout_seconds": 5,
        "max_retries": 0,
        "stale_after_seconds": 900,
        **overrides,
    }


class ControlledClock:
    """Advance deterministic UTC time without real waiting in provider tests."""

    def __init__(self) -> None:
        self.now = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)

    def advance(self, seconds: float) -> datetime:
        """Advance and return the controlled time."""
        self.now += timedelta(seconds=seconds)
        return self.now


def provider_result(
    name: str,
    *,
    state: ProviderHealthState = ProviderHealthState.OK,
    at: datetime | None = None,
) -> ApiResult:
    """Build a complete empty warning result with explicit independent health."""
    timestamp = at or ControlledClock().now
    return ApiResult(
        name,
        (),
        ProviderHealth(
            name,
            state,
            timestamp,
            timestamp if state == ProviderHealthState.OK else None,
            0 if state == ProviderHealthState.OK else 1,
            stale_after_seconds=900,
        ),
    )
