"""Pydantic schema and validation for the temperature component."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from pydantic import ConfigDict, ValidationError, model_validator

from components.core.pydantic_utils import StrictBaseModel, log_extra_keys

COMPONENT_NAME = "TemperatureComponent"


class TemperatureDefaults(StrictBaseModel):
    """Common defaults for temperature rooms."""

    model_config = ConfigDict(extra="allow")

    CAL_LOW_TEMP_THRESHOLD: float
    CAL_FORECAST_TIMESPAN: float


class TemperatureRoom(StrictBaseModel):
    """Per-room configuration for the temperature component."""

    model_config = ConfigDict(extra="allow")

    temperature_sensor: str
    temperature_sensor_rate: str
    window_sensor: Optional[str] = None
    CAL_LOW_TEMP_THRESHOLD: Optional[float] = None
    CAL_FORECAST_TIMESPAN: Optional[float] = None

    @model_validator(mode="after")
    def _ensure_thresholds_present(self) -> "TemperatureRoom":
        if self.CAL_LOW_TEMP_THRESHOLD is None and self.CAL_FORECAST_TIMESPAN is None:
            return self
        if self.CAL_LOW_TEMP_THRESHOLD is None:
            raise ValueError(
                "CAL_LOW_TEMP_THRESHOLD missing while CAL_FORECAST_TIMESPAN provided"
            )
        if self.CAL_FORECAST_TIMESPAN is None:
            raise ValueError(
                "CAL_FORECAST_TIMESPAN missing while CAL_LOW_TEMP_THRESHOLD provided"
            )
        return self

    def with_defaults(self, defaults: TemperatureDefaults) -> Dict[str, Any]:
        merged: Dict[str, Any] = {
            "temperature_sensor": self.temperature_sensor,
            "temperature_sensor_rate": self.temperature_sensor_rate,
            "window_sensor": self.window_sensor,
        }

        low_temp = (
            self.CAL_LOW_TEMP_THRESHOLD
            if self.CAL_LOW_TEMP_THRESHOLD is not None
            else defaults.CAL_LOW_TEMP_THRESHOLD
        )
        forecast = (
            self.CAL_FORECAST_TIMESPAN
            if self.CAL_FORECAST_TIMESPAN is not None
            else defaults.CAL_FORECAST_TIMESPAN
        )

        if low_temp is None or forecast is None:
            raise ValueError(
                "TemperatureComponent room configuration requires "
                "CAL_LOW_TEMP_THRESHOLD and CAL_FORECAST_TIMESPAN"
            )

        merged["CAL_LOW_TEMP_THRESHOLD"] = low_temp
        merged["CAL_FORECAST_TIMESPAN"] = forecast

        extras = getattr(self, "model_extra", None) or {}
        merged.update(extras)
        return merged


class TemperatureComponentConfig(StrictBaseModel):
    """Configuration schema for the temperature component."""

    model_config = ConfigDict(extra="allow")

    defaults: TemperatureDefaults
    rooms: Dict[str, TemperatureRoom]

    def to_runtime(
        self, calibration: Dict[str, Any]
    ) -> list[Dict[str, Dict[str, Any]]]:
        runtime_rooms: list[Dict[str, Dict[str, Any]]] = []
        for room_name, room_cfg in self.rooms.items():
            merged = room_cfg.with_defaults(self.defaults)
            merged.update(calibration)
            runtime_rooms.append({room_name: merged})
        return runtime_rooms


def validate_temperature_config(
    raw_cfg: dict[str, Any],
    *,
    strict_validation: bool = True,
    log: Callable[..., None] | None = None,
    calibration: Dict[str, Any] | None = None,
) -> list[dict[str, dict[str, Any]]]:
    """Validate and normalize a temperature component configuration."""

    try:
        validated = TemperatureComponentConfig.model_validate(
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
            for room_name, room_cfg in validated.rooms.items():
                log_extra_keys(
                    room_cfg,
                    log,
                    "user_config.safety_components."
                    f"{COMPONENT_NAME}.rooms.{room_name}",
                )
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    calibration_defaults = {
        "SM_TC_1_DEBOUNCE_LIMIT": 2,
        "SM_TC_1_REEVAL_DELAY_SECONDS": 30,
        "SM_TC_2_DEBOUNCE_LIMIT": 2,
        "SM_TC_2_REEVAL_DELAY_SECONDS": 30,
        "SM_TC_2_DERIVATIVE_SAMPLE_MINUTES": 15,
    }
    if calibration:
        calibration_defaults.update(calibration)

    return validated.to_runtime(calibration_defaults)
