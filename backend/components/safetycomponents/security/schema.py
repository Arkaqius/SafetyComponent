"""Pydantic schema and validation for the door/window security component."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from pydantic import ConfigDict, Field, ValidationError

from components.core.pydantic_utils import StrictBaseModel, log_extra_keys

COMPONENT_NAME = "DoorWindowSecurityComponent"


class DoorWindowDefaults(StrictBaseModel):
    """Common defaults for door/window security entries."""

    model_config = ConfigDict(extra="allow")

    T_door_close_timeout: int = Field(default=60, ge=0)
    T_window_close_timeout: int = Field(default=120, ge=0)
    T_escalate: int = Field(default=30, ge=0)
    T_stable: int = Field(default=60, ge=0)
    AutoLockEnabled: bool = False
    AutoCloseWindowsEnabled: bool = False
    OccupancyGateStates: list[str] = Field(
        default_factory=lambda: ["Unoccupied", "Kids"]
    )


class DoorConfig(StrictBaseModel):
    """Per-door configuration for the security component."""

    model_config = ConfigDict(extra="allow")

    door_sensor: str
    lock_actuator: Optional[str] = None
    T_door_close_timeout: Optional[int] = Field(default=None, ge=0)
    T_escalate: Optional[int] = Field(default=None, ge=0)
    T_stable: Optional[int] = Field(default=None, ge=0)
    AutoLockEnabled: Optional[bool] = None

    def with_defaults(self, defaults: DoorWindowDefaults) -> Dict[str, Any]:
        """Merge per-door config with defaults."""
        merged: Dict[str, Any] = {
            "door_sensor": self.door_sensor,
            "lock_actuator": self.lock_actuator,
            "T_door_close_timeout": (
                self.T_door_close_timeout
                if self.T_door_close_timeout is not None
                else defaults.T_door_close_timeout
            ),
            "T_escalate": (
                self.T_escalate
                if self.T_escalate is not None
                else defaults.T_escalate
            ),
            "T_stable": (
                self.T_stable if self.T_stable is not None else defaults.T_stable
            ),
            "AutoLockEnabled": (
                self.AutoLockEnabled
                if self.AutoLockEnabled is not None
                else defaults.AutoLockEnabled
            ),
        }

        extras = getattr(self, "model_extra", None) or {}
        merged.update(extras)
        return merged


class WindowConfig(StrictBaseModel):
    """Per-window configuration for the security component."""

    model_config = ConfigDict(extra="allow")

    window_sensor: str
    window_actuator: Optional[str] = None
    T_window_close_timeout: Optional[int] = Field(default=None, ge=0)
    T_escalate: Optional[int] = Field(default=None, ge=0)
    T_stable: Optional[int] = Field(default=None, ge=0)
    AutoCloseWindowsEnabled: Optional[bool] = None
    OccupancyGateStates: Optional[list[str]] = None

    def with_defaults(self, defaults: DoorWindowDefaults) -> Dict[str, Any]:
        """Merge per-window config with defaults."""
        merged: Dict[str, Any] = {
            "window_sensor": self.window_sensor,
            "window_actuator": self.window_actuator,
            "T_window_close_timeout": (
                self.T_window_close_timeout
                if self.T_window_close_timeout is not None
                else defaults.T_window_close_timeout
            ),
            "T_escalate": (
                self.T_escalate
                if self.T_escalate is not None
                else defaults.T_escalate
            ),
            "T_stable": (
                self.T_stable if self.T_stable is not None else defaults.T_stable
            ),
            "AutoCloseWindowsEnabled": (
                self.AutoCloseWindowsEnabled
                if self.AutoCloseWindowsEnabled is not None
                else defaults.AutoCloseWindowsEnabled
            ),
            "OccupancyGateStates": (
                self.OccupancyGateStates
                if self.OccupancyGateStates is not None
                else list(defaults.OccupancyGateStates)
            ),
        }

        extras = getattr(self, "model_extra", None) or {}
        merged.update(extras)
        return merged


class DoorWindowSecurityComponentConfig(StrictBaseModel):
    """Configuration schema for the door/window security component."""

    model_config = ConfigDict(extra="allow")

    occupancy_sensor: str
    defaults: DoorWindowDefaults = Field(default_factory=DoorWindowDefaults)
    external_doors: Dict[str, DoorConfig] = Field(default_factory=dict)
    critical_windows: Dict[str, WindowConfig] = Field(default_factory=dict)

    def to_runtime(self) -> list[dict[str, dict[str, Any]]]:
        """Normalize door/window configuration into runtime entries."""
        runtime_entries: list[dict[str, dict[str, Any]]] = []
        for door_name, door_cfg in self.external_doors.items():
            merged = door_cfg.with_defaults(self.defaults)
            merged["entry_type"] = "door"
            merged["entry_name"] = door_name
            merged["occupancy_sensor"] = self.occupancy_sensor
            runtime_entries.append({door_name: merged})
        for window_name, window_cfg in self.critical_windows.items():
            merged = window_cfg.with_defaults(self.defaults)
            merged["entry_type"] = "window"
            merged["entry_name"] = window_name
            merged["occupancy_sensor"] = self.occupancy_sensor
            runtime_entries.append({window_name: merged})
        return runtime_entries


def validate_door_window_security_config(
    raw_cfg: dict[str, Any],
    *,
    strict_validation: bool = True,
    log: Callable[..., None] | None = None,
) -> list[dict[str, dict[str, Any]]]:
    """Validate and normalize door/window security configuration."""
    try:
        validated = DoorWindowSecurityComponentConfig.model_validate(
            raw_cfg, context={"strict_validation": strict_validation}
        )
        if not strict_validation:
            log_extra_keys(
                validated,
                log,
                f"user_config.safety_components.{COMPONENT_NAME}",
            )
            log_extra_keys(
                validated.defaults,
                log,
                f"user_config.safety_components.{COMPONENT_NAME}.defaults",
            )
            for door_name, door_cfg in validated.external_doors.items():
                log_extra_keys(
                    door_cfg,
                    log,
                    "user_config.safety_components."
                    f"{COMPONENT_NAME}.external_doors.{door_name}",
                )
            for window_name, window_cfg in validated.critical_windows.items():
                log_extra_keys(
                    window_cfg,
                    log,
                    "user_config.safety_components."
                    f"{COMPONENT_NAME}.critical_windows.{window_name}",
                )
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    return validated.to_runtime()
