"""Utility for validating and normalizing the SafetyFunctions app configuration."""

from __future__ import annotations

from typing import Any, Callable, ClassVar, Dict, Optional
import re

from pydantic import ConfigDict, Field, ValidationError
from shared.fault_manager import FaultManager
from shared.notification_manager import NotificationManager
from shared.pydantic_utils import StrictBaseModel, log_extra_keys
from shared.temperature_component import TemperatureComponent


class AppCfgValidationError(Exception):
    """Raised when the provided app configuration does not satisfy the schema."""

SUPPORTED_CONFIG_VERSION = 1
ENTITY_ID_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def _log_warning(log: Callable[..., None] | None, message: str) -> None:
    if not log:
        return
    try:
        log(message, level="WARNING")
    except TypeError:
        log(message)


def _collect_entity_ids(runtime_cfg: Dict[str, Any]) -> list[tuple[str, str]]:
    user_cfg = runtime_cfg.get("user_config", {})
    entity_ids: list[tuple[str, str]] = []

    common_entities = user_cfg.get("common_entities", {}) or {}
    for key, value in common_entities.items():
        if isinstance(value, str):
            entity_ids.append((f"user_config.common_entities.{key}", value))

    notification_cfg = user_cfg.get("notification", {}) or {}
    for key, value in notification_cfg.items():
        if key.endswith("_entity") and isinstance(value, str):
            entity_ids.append((f"user_config.notification.{key}", value))

    components_cfg = user_cfg.get("safety_components", {}) or {}
    temperature_cfg = components_cfg.get(TemperatureComponent.component_name)
    if isinstance(temperature_cfg, list):
        for room in temperature_cfg:
            if not isinstance(room, dict):
                continue
            for room_name, room_cfg in room.items():
                if not isinstance(room_cfg, dict):
                    continue
                for key in (
                    "temperature_sensor",
                    "temperature_sensor_rate",
                    "window_sensor",
                    "actuator",
                ):
                    value = room_cfg.get(key)
                    if isinstance(value, str):
                        entity_ids.append(
                            (
                                "user_config.safety_components."
                                f"{TemperatureComponent.component_name}."
                                f"{room_name}.{key}",
                                value,
                            )
                        )

    return entity_ids


def _validate_entity_id_syntax(entity_ids: list[tuple[str, str]]) -> list[str]:
    invalid = []
    for path, entity_id in entity_ids:
        if not ENTITY_ID_PATTERN.match(entity_id):
            invalid.append(f"{path}={entity_id}")
    return invalid


def _validate_entity_existence(
    hass: Any, entity_ids: list[tuple[str, str]]
) -> list[str]:
    missing = []
    for path, entity_id in entity_ids:
        try:
            state = hass.get_state(entity_id)
        except Exception as exc:
            missing.append(f"{path}={entity_id} ({exc})")
            continue
        if state is None:
            missing.append(f"{path}={entity_id}")
    return missing


class ValidationSettings(StrictBaseModel):
    """Validation options for entity and startup checks."""

    model_config = ConfigDict(extra="allow")

    validate_entity_id_syntax: bool = True
    validate_entity_existence: bool = True


class AppPolicy(StrictBaseModel):
    """Application-wide configuration shared across installations."""

    model_config = ConfigDict(extra="allow")

    config_version: int = Field(..., ge=1)
    strict_validation: bool = True
    validation: ValidationSettings = Field(default_factory=ValidationSettings)
    faults: Dict[str, Dict[str, Any]]


class UserConfig(StrictBaseModel):
    """House-specific configuration."""

    model_config = ConfigDict(extra="allow")

    components_enabled: Dict[str, bool] = Field(default_factory=dict)
    notification: Dict[str, Any]
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

    def to_runtime(
        self,
        strict_validation: bool = True,
        log: Callable[..., None] | None = None,
    ) -> Dict[str, Any]:
        runtime = self.model_dump(by_alias=True)
        runtime_user_cfg = runtime.get("user_config", {})

        enabled_components = self.user_config.enabled_components()
        runtime_components: Dict[str, Any] = {}
        for name, cfg in enabled_components.items():
            if name == TemperatureComponent.component_name:
                runtime_components[name] = TemperatureComponent.validate_config(
                    cfg, strict_validation=strict_validation, log=log
                )
            else:
                runtime_components[name] = cfg

        runtime_user_cfg["safety_components"] = runtime_components
        runtime_user_cfg["notification"] = NotificationManager.validate_config(
            self.user_config.notification,
            strict_validation=strict_validation,
            log=log,
        )

        runtime["user_config"] = runtime_user_cfg
        runtime["app_config"]["faults"] = FaultManager.validate_config(
            self.app_config.faults,
            strict_validation=strict_validation,
            log=log,
        )
        return runtime


class AppCfgValidator:
    """Facade for validating and normalizing the SafetyFunctions configuration."""

    @staticmethod
    def validate(
        raw_cfg: Dict[str, Any],
        *,
        hass: Any | None = None,
        log: Callable[..., None] | None = None,
    ) -> Dict[str, Any]:
        strict_validation = (
            raw_cfg.get("app_config", {}).get("strict_validation", True)
        )
        try:
            cfg = AppCfg.model_validate(
                raw_cfg, context={"strict_validation": strict_validation}
            )
            if cfg.app_config.config_version != SUPPORTED_CONFIG_VERSION:
                raise AppCfgValidationError(
                    "Unsupported config_version "
                    f"{cfg.app_config.config_version}; "
                    f"supported={SUPPORTED_CONFIG_VERSION}"
                )
            runtime_cfg = cfg.to_runtime(
                strict_validation=strict_validation,
                log=log,
            )
        except (ValidationError, ValueError) as exc:
            raise AppCfgValidationError(str(exc))

        if not strict_validation:
            log_extra_keys(cfg, log, "root")
            log_extra_keys(cfg.app_config, log, "app_config")
            log_extra_keys(cfg.app_config.validation, log, "app_config.validation")
            log_extra_keys(cfg.user_config, log, "user_config")

        entity_ids = _collect_entity_ids(runtime_cfg)

        if cfg.app_config.validation.validate_entity_id_syntax:
            invalid = _validate_entity_id_syntax(entity_ids)
            if invalid:
                raise AppCfgValidationError(
                    "Invalid entity_id syntax: " + ", ".join(invalid)
                )

        if cfg.app_config.validation.validate_entity_existence:
            if hass is None:
                _log_warning(
                    log,
                    "validate_entity_existence is true but hass was not provided; "
                    "skipping existence checks.",
                )
            else:
                missing = _validate_entity_existence(hass, entity_ids)
                if missing:
                    raise AppCfgValidationError(
                        "Missing entity_ids: " + ", ".join(missing)
                    )

        return runtime_cfg
