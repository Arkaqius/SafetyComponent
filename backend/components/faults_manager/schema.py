"""Pydantic schema and validation for fault configuration."""

from __future__ import annotations

from typing import Any, Callable

from pydantic import ConfigDict, Field, ValidationError

from components.core.pydantic_utils import StrictBaseModel, log_extra_keys


class FaultEntry(StrictBaseModel):
    """Schema for a single fault definition."""

    model_config = ConfigDict(extra="allow")

    name: str
    level: int = Field(..., ge=1)
    related_sms: list[str]
    inhibits: list[str] = Field(default_factory=list)


def validate_faults_config(
    faults_cfg: dict[str, Any],
    *,
    strict_validation: bool = True,
    log: Callable[..., None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Validate fault configuration entries."""

    try:
        validated: dict[str, dict[str, Any]] = {}
        for name, cfg in faults_cfg.items():
            model = FaultEntry.model_validate(
                cfg, context={"strict_validation": strict_validation}
            )
            if not strict_validation:
                log_extra_keys(model, log, f"app_config.faults.{name}")
            validated[name] = model.model_dump()
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    return validated
