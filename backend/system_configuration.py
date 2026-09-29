"""Closed source schema for the packaged system configuration."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field, ValidationError, model_validator

from components.core.mqtt_entity_manager import MqttSettings
from components.core.pydantic_utils import StrictBaseModel
from components.faults_manager.schema import FaultEntry
from components.notification_manager.schema import (
    LevelOneRepeatPolicy,
    MobileProfile,
    PersistenceConfig,
    RetryPolicy,
)
from components.safetycomponents.entity_monitor.schema import ComponentEntityOverride
from components.safetycomponents.internal_environmental_hazard.schema import (
    BinaryDetectorProfile,
    InternalEnvironmentPersistence,
)
from configuration_model import ConfigurationModelVersion


class SystemSourceModel(StrictBaseModel):
    """Closed system-source model with no undeclared fields."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SystemVersion(SystemSourceModel):
    """Shared system and user source-model version."""

    version: ConfigurationModelVersion


class AppDefinition(SystemSourceModel):
    """Packaged AppDaemon entry point and local defaults."""

    module: str
    class_name: str = Field(alias="class")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "FATAL"]
    use_dictionary_unpacking: bool


class ValidationSource(SystemSourceModel):
    """Startup validation policy."""

    strict_validation: bool
    validate_entity_id_syntax: bool
    validate_entity_existence: bool


class TemperatureCalibrationSource(SystemSourceModel):
    """Temperature mechanism calibration and overridable baselines."""

    sm_tc_1_debounce_limit: int = Field(ge=1)
    sm_tc_1_reeval_delay_seconds: int = Field(ge=0)
    sm_tc_2_debounce_limit: int = Field(ge=1)
    sm_tc_2_reeval_delay_seconds: int = Field(ge=0)
    sm_tc_2_derivative_sample_minutes: int = Field(ge=1)
    sm_tc_min_valid_temperature_c: float
    sm_tc_max_valid_temperature_c: float
    sm_tc_max_abs_rate_c_per_min: float = Field(gt=0)
    sm_tc_max_forecast_delta_c: float = Field(gt=0)
    default_low_temperature_c: float
    default_high_temperature_c: float
    forecast_horizon_hours: float = Field(gt=0)


class EntityMonitorCalibrationSource(SystemSourceModel):
    """Entity Monitor timing and dependency calibration defaults."""

    default_startup_grace_seconds: int = Field(ge=0)
    default_failure_debounce_seconds: int = Field(ge=0)
    default_recovery_debounce_seconds: int = Field(ge=0)
    default_evaluation_interval_seconds: int = Field(ge=1)
    unhealthy_summary_limit: int = Field(ge=1, le=128)
    component_overrides: dict[str, ComponentEntityOverride]


class SafetyDoorCalibrationSource(SystemSourceModel):
    """Safety Door installation-independent baseline."""

    default_timeout_seconds: int = Field(ge=1)


class WeatherCalibrationSource(SystemSourceModel):
    """Overridable weather-decision baselines."""

    forecast_horizon_hours: int = Field(ge=1, le=72)
    default_frost_watch_c: float
    default_frost_warning_c: float
    default_gust_watch_m_s: float = Field(gt=0)
    default_gust_warning_m_s: float = Field(gt=0)
    default_precipitation_warning_mm_h: float = Field(gt=0)
    default_persistence_seconds: int = Field(ge=0)
    default_hysteresis: dict[str, float]


class AirQualityCalibrationSource(SystemSourceModel):
    """Overridable outdoor-air-quality decision baselines."""

    default_standard: Literal["european_aqi"]
    default_warning_at: float = Field(gt=0)


class ExternalHazardCalibrationSource(SystemSourceModel):
    """External-hazard decision policy and defaults."""

    default_hazards: list[
        Literal["frost", "wind", "rain", "storm", "outdoor_air_pollution"]
    ] = Field(min_length=1)
    actuation_mode: Literal["manual_and_user_confirmed"]
    clear_delay_seconds: int = Field(ge=0)
    weather: WeatherCalibrationSource
    outdoor_air_quality: AirQualityCalibrationSource


class InternalHazardCalibrationSource(SystemSourceModel):
    """Internal detector profiles, health timing, and persistence."""

    profiles: dict[str, BinaryDetectorProfile] = Field(min_length=1)
    default_health_failure_debounce_seconds: int = Field(ge=0)
    default_health_recovery_debounce_seconds: int = Field(ge=0)
    persistence: InternalEnvironmentPersistence


class FunctionalSafetyCalibrationSource(SystemSourceModel):
    """Installation-independent qualification and maintenance policy."""

    evaluation_interval_seconds: int = Field(ge=5)
    memory_low_available_mib: float = Field(gt=0)
    memory_recovery_available_mib: float = Field(gt=0)
    memory_high_psi_percent: float = Field(gt=0, le=100)
    memory_recovery_psi_percent: float = Field(ge=0, lt=100)
    memory_qualification_seconds: int = Field(ge=1)
    memory_recovery_seconds: int = Field(ge=1)
    cpu_high_percent: float = Field(gt=0, le=100)
    cpu_recovery_percent: float = Field(ge=0, lt=100)
    cpu_qualification_seconds: int = Field(ge=1)
    cpu_recovery_seconds: int = Field(ge=1)
    wan_qualification_seconds: int = Field(ge=1)
    wan_recovery_seconds: int = Field(ge=1)
    battery_low_percent: float = Field(gt=0, lt=100)
    detector_test_interval_days: int = Field(ge=1)
    detector_test_state_file: str
    resource_stale_after_seconds: int = Field(ge=1)
    wan_stale_after_seconds: int = Field(ge=1)
    update_stale_after_seconds: int = Field(ge=1)
    battery_stale_after_seconds: int = Field(ge=1)
    memory_fault_level: Literal[2]
    wan_fault_level: Literal[3]
    maintenance_fault_level: Literal[4]
    cpu_fault_level: Literal[4]
    disk_low_free_mib: float = Field(gt=0, allow_inf_nan=False)
    disk_recovery_free_mib: float = Field(gt=0, allow_inf_nan=False)
    host_temperature_high_c: float = Field(gt=0, allow_inf_nan=False)
    host_temperature_recovery_c: float = Field(ge=0, allow_inf_nan=False)
    resource_qualification_seconds: int = Field(ge=1)
    resource_recovery_seconds: int = Field(ge=1)
    backup_max_age_hours: float = Field(gt=0, allow_inf_nan=False)
    backup_stale_after_seconds: int = Field(ge=1)
    notification_test_interval_days: int = Field(ge=1)
    backup_restore_test_interval_days: int = Field(ge=1)
    periodic_test_state_file: str

    @model_validator(mode="after")
    def _validate_hysteresis(self) -> "FunctionalSafetyCalibrationSource":
        if self.memory_recovery_available_mib <= self.memory_low_available_mib:
            raise ValueError("memory recovery threshold must exceed low threshold")
        if self.memory_recovery_psi_percent >= self.memory_high_psi_percent:
            raise ValueError("PSI recovery threshold must be below high threshold")
        if self.cpu_recovery_percent >= self.cpu_high_percent:
            raise ValueError("CPU recovery threshold must be below high threshold")
        if self.disk_recovery_free_mib <= self.disk_low_free_mib:
            raise ValueError("disk recovery threshold must exceed low threshold")
        if self.host_temperature_recovery_c >= self.host_temperature_high_c:
            raise ValueError("temperature recovery threshold must be below high threshold")
        return self


class CalibrationSource(SystemSourceModel):
    """All packaged safety calibration."""

    temperature: TemperatureCalibrationSource
    entity_monitor: EntityMonitorCalibrationSource
    safety_door: SafetyDoorCalibrationSource
    external_hazard: ExternalHazardCalibrationSource
    internal_environmental_hazard: InternalHazardCalibrationSource
    functional_safety: FunctionalSafetyCalibrationSource


class ProviderRuntimeSource(SystemSourceModel):
    """One external provider lifecycle and transport contract."""

    enabled: bool
    base_url: str
    poll_interval_seconds: int = Field(ge=1)
    request_timeout_seconds: int = Field(ge=1)
    max_retries: int = Field(ge=0)
    stale_after_seconds: int = Field(ge=1)


class ProviderRuntimeSet(SystemSourceModel):
    """Exact provider set supported by this release."""

    OpenMeteoWeatherApiComponent: ProviderRuntimeSource
    ImgwWarningsApiComponent: ProviderRuntimeSource
    OpenMeteoAirQualityApiComponent: ProviderRuntimeSource


class NotificationMobileSource(SystemSourceModel):
    """System-owned notification transport and presentation policy."""

    hass_timeout_seconds: int = Field(ge=1, le=30)
    profiles: dict[int, MobileProfile]


class NotificationRuntimeSource(SystemSourceModel):
    """System-owned notification lifecycle policy."""

    mobile: NotificationMobileSource
    retry: RetryPolicy
    level_one_repeat: LevelOneRepeatPolicy
    persistence: PersistenceConfig


class RecoveryRuntimeSource(SystemSourceModel):
    """Recovery runtime persistence policy."""

    persistence: PersistenceConfig


class RuntimeSource(SystemSourceModel):
    """Runtime services and stable system catalogs."""

    faults: dict[str, FaultEntry] = Field(min_length=1)
    providers: ProviderRuntimeSet
    notification: NotificationRuntimeSource
    recovery: RecoveryRuntimeSource
    mqtt: MqttSettings


class SystemConfigurationV2(SystemSourceModel):
    """Complete packaged system configuration contract."""

    system_config: SystemVersion
    app_definition: AppDefinition
    validation: ValidationSource
    calibration: CalibrationSource
    runtime_cfg: RuntimeSource


def validate_system_configuration(value: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a system configuration mapping."""

    try:
        model = SystemConfigurationV2.model_validate(
            value, context={"strict_validation": True}
        )
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    return model.model_dump(by_alias=True)


def system_configuration_schema() -> dict[str, Any]:
    """Return the complete machine-readable system source contract."""

    schema = SystemConfigurationV2.model_json_schema(by_alias=True)

    def close_declared_objects(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
            for value in node.values():
                close_declared_objects(value)
        elif isinstance(node, list):
            for value in node:
                close_declared_objects(value)

    close_declared_objects(schema)
    return schema
