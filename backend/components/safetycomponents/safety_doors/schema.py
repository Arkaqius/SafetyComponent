"""Configuration schema for monitored safety doors."""

from __future__ import annotations

from typing import Any, Callable, Dict

from pydantic import ConfigDict, Field, ValidationError

from components.core.pydantic_utils import StrictBaseModel, log_extra_keys

COMPONENT_NAME = "SafetyDoorsComponent"


class SafetyDoorDefaults(StrictBaseModel):
    """Defaults shared by every configured safety door."""

    model_config = ConfigDict(extra="allow")

    timeout_seconds: int = Field(default=120, ge=1)


class SafetyDoorConfig(StrictBaseModel):
    """Configuration of one monitored door or gate."""

    model_config = ConfigDict(extra="allow")

    entity_id: str
    timeout_seconds: int | None = Field(default=None, ge=1)

    def with_defaults(self, defaults: SafetyDoorDefaults) -> Dict[str, Any]:
        """Return the normalized runtime configuration for this door."""
        runtime: Dict[str, Any] = {
            "entity_id": self.entity_id,
            "timeout_seconds": (
                self.timeout_seconds
                if self.timeout_seconds is not None
                else defaults.timeout_seconds
            ),
        }
        runtime.update(getattr(self, "model_extra", None) or {})
        return runtime


class SafetyDoorsComponentConfig(StrictBaseModel):
    """Top-level Safety Doors component configuration."""

    model_config = ConfigDict(extra="allow")

    defaults: SafetyDoorDefaults = Field(default_factory=SafetyDoorDefaults)
    doors: Dict[str, SafetyDoorConfig] = Field(min_length=1)

    def to_runtime(self) -> list[dict[str, dict[str, Any]]]:
        """Normalize configured doors into the component runtime format."""
        return [
            {door_name: door_config.with_defaults(self.defaults)}
            for door_name, door_config in self.doors.items()
        ]


def validate_safety_doors_config(
    raw_cfg: dict[str, Any],
    *,
    strict_validation: bool = True,
    log: Callable[..., None] | None = None,
) -> list[dict[str, dict[str, Any]]]:
    """Validate and normalize a Safety Doors configuration."""
    try:
        validated = SafetyDoorsComponentConfig.model_validate(
            raw_cfg, context={"strict_validation": strict_validation}
        )
        if not strict_validation:
            base_path = f"user_config.safety_components.{COMPONENT_NAME}"
            log_extra_keys(validated, log, base_path)
            log_extra_keys(validated.defaults, log, f"{base_path}.defaults")
            for door_name, door_config in validated.doors.items():
                log_extra_keys(
                    door_config,
                    log,
                    f"{base_path}.doors.{door_name}",
                )
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    return validated.to_runtime()
