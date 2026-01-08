"""Pydantic schema for app configuration."""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Optional

from pydantic import ConfigDict, Field

from components.core.pydantic_utils import StrictBaseModel


class ValidationSettings(StrictBaseModel):
    """Validation options for entity and startup checks."""

    model_config = ConfigDict(extra="allow")

    validate_entity_id_syntax: bool = True
    validate_entity_existence: bool = True


class TemperatureCalibration(StrictBaseModel):
    """Calibration defaults for the temperature component."""

    model_config = ConfigDict(extra="allow")

    SM_TC_1_DEBOUNCE_LIMIT: int = 2
    SM_TC_1_REEVAL_DELAY_SECONDS: int = 30
    SM_TC_2_DEBOUNCE_LIMIT: int = 2
    SM_TC_2_REEVAL_DELAY_SECONDS: int = 30
    SM_TC_2_DERIVATIVE_SAMPLE_MINUTES: int = 15


class CalibrationSettings(StrictBaseModel):
    """Calibration defaults for safety components."""

    model_config = ConfigDict(extra="allow")

    temperature: TemperatureCalibration = Field(default_factory=TemperatureCalibration)


class AppPolicy(StrictBaseModel):
    """Application-wide configuration shared across installations."""

    model_config = ConfigDict(extra="allow")

    config_version: int = Field(..., ge=1)
    strict_validation: bool = True
    validation: ValidationSettings = Field(default_factory=ValidationSettings)
    calibration: CalibrationSettings = Field(default_factory=CalibrationSettings)
    faults: Dict[str, Dict[str, Any]]


class UserConfig(StrictBaseModel):
    """House-specific configuration."""

    model_config = ConfigDict(extra="allow")

    components_enabled: Dict[str, bool] = Field(default_factory=dict)
    notification: Dict[str, Any] = Field(default_factory=dict)
    common_entities: Dict[str, str]
    safety_components: Dict[str, Dict[str, Any]]

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
