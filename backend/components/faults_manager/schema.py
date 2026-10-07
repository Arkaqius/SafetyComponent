"""Pydantic schema and validation for fault configuration."""

from __future__ import annotations

from typing import Any, Callable, Literal

from pydantic import ConfigDict, Field, ValidationError, model_validator

from components.core.pydantic_utils import StrictBaseModel, log_extra_keys


class FaultEntry(StrictBaseModel):
    """Schema for a single fault definition."""

    model_config = ConfigDict(extra="allow")

    name: str
    level: int = Field(..., ge=1, le=4)
    category: Literal["H", "D"] = "H"
    related_sms: list[str]
    related_symptom_ids: list[str] = Field(default_factory=list)
    shadows: list[str] = Field(default_factory=list)


class FaultEvidenceConfig(StrictBaseModel):
    """Bounded, independent freeze-frame persistence policy."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    state_file: str = Field(min_length=1)
    max_records: int = Field(ge=1, le=1024)
    max_frame_bytes: int = Field(ge=512, le=8192)
    max_total_bytes: int = Field(ge=4096, le=4194304)

    @model_validator(mode="after")
    def validate_capacity(self) -> "FaultEvidenceConfig":
        """Reserve room for at least one complete frame and record envelope."""

        if self.max_total_bytes < self.max_frame_bytes + 512:
            raise ValueError("fault evidence total bound cannot hold one frame")
        return self


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
