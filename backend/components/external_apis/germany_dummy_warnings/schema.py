"""Closed settings for the offline German synthetic warning source."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class GermanyDummyParameters(BaseModel):
    """Select a synthetic region and a repeatable preview scenario."""

    model_config = ConfigDict(extra="forbid")
    region_code: Annotated[
        str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
    ] | None = Field(
        default=None,
        title="Region testowy",
        description="Identyfikator testowy, bez znaczenia urzędowego.",
    )
    scenario: Literal["empty", "warning", "unavailable", "stale"] = Field(
        default="empty",
        title="Scenariusz testowy",
        description="Wyłącznie syntetyczny podgląd, bez wpływu na bezpieczeństwo domu.",
    )


class GermanyDummyConfig(BaseModel):
    """System-owned schedule for a provider with no network transport."""

    model_config = ConfigDict(extra="forbid")
    poll_interval_seconds: Literal[60] = 60
    stale_after_seconds: Literal[180] = 180
