"""Pydantic schema for app configuration."""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Optional

from pydantic import ConfigDict, Field

from components.core.localization import LocalizationSettings
from components.core.mqtt_entity_manager import MqttSettings
from components.core.pydantic_utils import StrictBaseModel
from components.safetycomponents.external_hazard.schema import (
    ExternalHazardPolicy,
    SiteConfig,
)
from components.safetycomponents.entity_monitor.schema import EntityMonitorCalibration


class ValidationSettings(StrictBaseModel):
    """Validation options for entity and startup checks."""

    model_config = ConfigDict(extra="allow")

    strict_validation: bool = True
    validate_entity_id_syntax: bool = True
    validate_entity_existence: bool = True


class TemperatureCalibration(StrictBaseModel):
    """Calibration defaults for the temperature component."""

    model_config = ConfigDict(extra="allow")

    sm_tc_1_debounce_limit: int = 2
    sm_tc_1_reeval_delay_seconds: int = 30
    sm_tc_2_debounce_limit: int = 2
    sm_tc_2_reeval_delay_seconds: int = 30
    sm_tc_2_derivative_sample_minutes: int = 15
    sm_tc_min_valid_temperature_c: float = -40.0
    sm_tc_max_valid_temperature_c: float = 80.0
    sm_tc_max_abs_rate_c_per_min: float = Field(default=0.25, gt=0)
    sm_tc_max_forecast_delta_c: float = Field(default=6.0, gt=0)


class CalibrationSettings(StrictBaseModel):
    """Calibration defaults for safety components."""

    model_config = ConfigDict(extra="allow")

    temperature: TemperatureCalibration = Field(default_factory=TemperatureCalibration)
    entity_monitor: EntityMonitorCalibration = Field(
        default_factory=EntityMonitorCalibration
    )
    functional_safety: Dict[str, Any] = Field(default_factory=dict)


class AppPolicy(StrictBaseModel):
    """Application-wide configuration shared across installations."""

    model_config = ConfigDict(extra="allow")

    validation: ValidationSettings = Field(default_factory=ValidationSettings)
    calibration: CalibrationSettings = Field(default_factory=CalibrationSettings)
    external_hazard_policy: ExternalHazardPolicy | None = None
    faults: Dict[str, Dict[str, Any]]


class UserConfig(StrictBaseModel):
    """House-specific configuration."""

    model_config = ConfigDict(extra="allow")

    components_enabled: Dict[str, bool] = Field(default_factory=dict)
    notification: Dict[str, Any] = Field(default_factory=dict)
    recovery: Dict[str, Any] = Field(default_factory=dict)
    localization: LocalizationSettings = Field(default_factory=LocalizationSettings)
    mqtt: MqttSettings = Field(default_factory=MqttSettings)
    common_entities: Dict[str, str]
    safety_components: Dict[str, Dict[str, Any]]
    site: SiteConfig | None = None
    api_components: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    functional_safety: Dict[str, Any] = Field(default_factory=dict)

    def enabled_components(self) -> Dict[str, Dict[str, Any]]:
        if not self.components_enabled:
            return self.safety_components

        return {
            name: cfg
            for name, cfg in self.safety_components.items()
            if self.components_enabled.get(name, True)
        }


class AppCfg(StrictBaseModel):
    """Top-level SafetyFunctions configuration schema."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    allow_unknown_keys: ClassVar[bool] = True

    module: str
    class_name: str = Field(..., alias="class")
    log_level: Optional[str] = None
    use_dictionary_unpacking: Optional[bool] = None
    app_config: AppPolicy
    user_config: UserConfig
