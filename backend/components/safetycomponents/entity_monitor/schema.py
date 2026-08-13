"""Configuration schema for Entity Health Monitoring."""

from __future__ import annotations

from typing import Any, Callable

from pydantic import ConfigDict, Field, ValidationError, field_validator, model_validator

from components.core.pydantic_utils import StrictBaseModel, log_extra_keys

COMPONENT_NAME = "EntityMonitorComponent"
SUPPORTED_CHECKS = frozenset(
    {
        "freshness",
        "required_value",
        "allowed_values",
        "finite_number",
        "numeric_range",
        "rate_of_change",
    }
)


class EntityMonitorCalibration(StrictBaseModel):
    """Global timing and bounded-publication defaults."""

    model_config = ConfigDict(extra="allow")

    startup_grace_seconds: int = Field(default=60, ge=0)
    default_failure_debounce_seconds: int = Field(default=15, ge=0)
    default_recovery_debounce_seconds: int = Field(default=60, ge=0)
    evaluation_interval_seconds: int = Field(default=5, ge=1)
    unhealthy_summary_limit: int = Field(default=32, ge=1, le=128)


class TargetCheck(StrictBaseModel):
    """Base schema for a check targeting state or one attribute."""

    model_config = ConfigDict(extra="allow")

    target: str = "state"

    @field_validator("target")
    @classmethod
    def _target_not_empty(cls, value: str) -> str:
        target = value.strip()
        if not target:
            raise ValueError("check target must not be empty")
        return target


class FreshnessCheck(StrictBaseModel):
    """Freshness check calibration."""

    model_config = ConfigDict(extra="allow")

    timestamp_source: str
    max_silence_seconds: int = Field(ge=1)

    @field_validator("timestamp_source")
    @classmethod
    def _timestamp_source_not_empty(cls, value: str) -> str:
        source = value.strip()
        if not source:
            raise ValueError("timestamp_source must not be empty")
        return source


class AllowedValuesCheck(TargetCheck):
    """Allowed normalized values for a target."""

    values: list[str] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def _normalize_values(cls, values: list[str]) -> list[str]:
        normalized = [str(value).strip().lower() for value in values]
        if any(not value for value in normalized):
            raise ValueError("allowed values must not be empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("allowed values must not contain duplicates")
        return normalized


class NumericRangeCheck(TargetCheck):
    """Inclusive numeric bounds for a target."""

    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def _validate_bounds(self) -> "NumericRangeCheck":
        if self.minimum is None and self.maximum is None:
            raise ValueError("numeric_range requires minimum or maximum")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("numeric_range minimum must not exceed maximum")
        return self


class RateOfChangeCheck(TargetCheck):
    """Per-minute rate bounds for a target."""

    window_seconds: int = Field(ge=1)
    min_samples: int = Field(default=2, ge=2)
    maximum_rise_per_minute: float | None = Field(default=None, ge=0)
    maximum_fall_per_minute: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_direction_bound(self) -> "RateOfChangeCheck":
        if self.maximum_rise_per_minute is None and self.maximum_fall_per_minute is None:
            raise ValueError("rate_of_change requires a rise or fall bound")
        return self


class EntityChecks(StrictBaseModel):
    """Optional checks enabled for one entity."""

    model_config = ConfigDict(extra="allow")

    freshness: FreshnessCheck | None = None
    required_value: TargetCheck | None = None
    allowed_values: AllowedValuesCheck | None = None
    finite_number: TargetCheck | None = None
    numeric_range: NumericRangeCheck | None = None
    rate_of_change: RateOfChangeCheck | None = None


class ExplicitEntityConfig(StrictBaseModel):
    """Installation-owned Group A dependency."""

    model_config = ConfigDict(extra="allow")

    entity_id: str
    area_id: str | None = None
    description: str
    enabled: bool = True
    failure_debounce_seconds: int | None = Field(default=None, ge=0)
    recovery_debounce_seconds: int | None = Field(default=None, ge=0)
    detection_budget_seconds: int | None = Field(default=None, ge=1)
    checks: EntityChecks = Field(default_factory=EntityChecks)

    @field_validator("entity_id", "description")
    @classmethod
    def _required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized


class EntityMonitorComponentConfig(StrictBaseModel):
    """Top-level Group A configuration."""

    model_config = ConfigDict(extra="allow")

    explicit_entities: dict[str, ExplicitEntityConfig] = Field(default_factory=dict)


def validate_entity_monitor_config(
    raw_cfg: dict[str, Any],
    *,
    calibration: dict[str, Any] | None = None,
    strict_validation: bool = True,
    log: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Validate Group A and attach global Entity Monitor policy."""

    try:
        validated = EntityMonitorComponentConfig.model_validate(
            raw_cfg, context={"strict_validation": strict_validation}
        )
        policy = EntityMonitorCalibration.model_validate(
            calibration or {}, context={"strict_validation": strict_validation}
        )
        if not strict_validation:
            base = f"user_config.safety_components.{COMPONENT_NAME}"
            log_extra_keys(validated, log, base)
            for key, entity in validated.explicit_entities.items():
                log_extra_keys(entity, log, f"{base}.explicit_entities.{key}")
                log_extra_keys(entity.checks, log, f"{base}.explicit_entities.{key}.checks")
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    explicit: list[dict[str, Any]] = []
    for key, entity in validated.explicit_entities.items():
        if not entity.enabled:
            continue
        item = entity.model_dump(exclude_none=True)
        item["key"] = key
        item["source"] = "explicit"
        item["owner"] = "installation"
        item["purpose"] = entity.description
        item["fault_owner"] = "entity_monitor"
        item["failure_debounce_seconds"] = (
            entity.failure_debounce_seconds
            if entity.failure_debounce_seconds is not None
            else policy.default_failure_debounce_seconds
        )
        item["recovery_debounce_seconds"] = (
            entity.recovery_debounce_seconds
            if entity.recovery_debounce_seconds is not None
            else policy.default_recovery_debounce_seconds
        )
        item["checks"] = entity.checks.model_dump(exclude_none=True)
        budget = entity.detection_budget_seconds
        if budget is not None:
            if item["failure_debounce_seconds"] > budget:
                raise ValueError(
                    f"{key} availability debounce exceeds detection budget"
                )
            freshness = item["checks"].get("freshness")
            if freshness and (
                freshness["max_silence_seconds"]
                + item["failure_debounce_seconds"]
                > budget
            ):
                raise ValueError(
                    f"{key} freshness and failure debounce exceed detection budget"
                )
        explicit.append(item)

    return {
        "explicit_entities": explicit,
        "component_entities": [],
        **policy.model_dump(),
    }
