"""Validated system-owned timing for separate recovery lifecycle stages."""

from pydantic import Field

from components.core.pydantic_utils import StrictBaseModel


class RecoveryTiming(StrictBaseModel):
    """Keep command consent, observed effect and optional manual deadlines separate."""

    consent_timeout_seconds: int = Field(default=120, ge=15, le=86400)
    effect_timeout_seconds: int = Field(default=120, ge=15, le=86400)
    manual_task_timeout_seconds: int | None = Field(default=None, ge=15, le=86400)
