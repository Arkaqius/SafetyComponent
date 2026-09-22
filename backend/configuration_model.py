"""Compile the versioned installation model into component bindings."""

from __future__ import annotations

import copy
import re
from typing import Any, Literal

from pydantic import (
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from components.core.pydantic_utils import StrictBaseModel
from components.safetycomponents.entity_monitor.schema import (
    ComponentEntityOverride,
    ExplicitEntityConfig,
)
from components.safetycomponents.external_hazard.schema import HazardName, SiteConfig
from components.safetycomponents.internal_environmental_hazard.schema import (
    InternalDetectorConfig,
)
from components.safetycomponents.safety_doors.schema import SafetyDoorCondition

CONFIGURATION_MODEL_VERSION = 2
_STABLE_KEY = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_ENTITY_ID = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
_NOTIFY_SERVICE = re.compile(r"^notify/[a-z0-9_]+$")


class SourceModel(StrictBaseModel):
    """Closed source-schema model with no undeclared editable fields."""

    model_config = ConfigDict(extra="forbid")


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge mappings while replacing scalar and list values."""

    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


class TemperatureDefaults(SourceModel):
    """Optional installation or room overrides for temperature defaults."""

    low_temperature_c: float | None = None
    high_temperature_c: float | None = None
    forecast_horizon_hours: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _ordered_thresholds(self) -> "TemperatureDefaults":
        if (
            self.low_temperature_c is not None
            and self.high_temperature_c is not None
            and self.low_temperature_c >= self.high_temperature_c
        ):
            raise ValueError("low_temperature_c must be below high_temperature_c")
        return self

    def to_runtime(self) -> dict[str, float]:
        """Translate friendly source names to the stable runtime contract."""

        values: dict[str, float] = {}
        if self.low_temperature_c is not None:
            values["CAL_LOW_TEMP_THRESHOLD"] = self.low_temperature_c
        if self.high_temperature_c is not None:
            values["CAL_HIGH_TEMP_THRESHOLD"] = self.high_temperature_c
        if self.forecast_horizon_hours is not None:
            values["CAL_FORECAST_TIMESPAN"] = self.forecast_horizon_hours
        return values


class SafetyDoorDefaults(SourceModel):
    """Installation-wide overrides for safety-door monitoring."""

    timeout_seconds: int | None = Field(default=None, ge=1)


class ExternalHazardDefaults(SourceModel):
    """Installation-wide defaults for external-hazard opening roles."""

    hazards: list[HazardName] | None = Field(default=None, min_length=1)

    @field_validator("hazards")
    @classmethod
    def _unique_hazards(cls, value: list[HazardName] | None) -> list[HazardName] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("external hazard defaults must not contain duplicates")
        return value


class EntityMonitorDefaults(SourceModel):
    """Installation overrides for component-owned entity dependencies."""

    component_overrides: dict[str, ComponentEntityOverride] = Field(
        default_factory=dict
    )


class InstallationDefaults(SourceModel):
    """Optional installation layer between system and asset defaults."""

    temperature: TemperatureDefaults = Field(default_factory=TemperatureDefaults)
    safety_door: SafetyDoorDefaults = Field(default_factory=SafetyDoorDefaults)
    external_hazard: ExternalHazardDefaults = Field(
        default_factory=ExternalHazardDefaults
    )
    entity_monitor: EntityMonitorDefaults = Field(default_factory=EntityMonitorDefaults)


class InstallationRoom(SourceModel):
    """One physical room and its temperature-monitoring bindings."""

    area_id: str
    temperature_sensor: str
    window: str | None = None
    actuator: str | None = None
    temperature: TemperatureDefaults = Field(default_factory=TemperatureDefaults)

    @field_validator("area_id", "temperature_sensor")
    @classmethod
    def _required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("room binding values must not be empty")
        return normalized


class SafetyDoorRole(SourceModel):
    """Safety-door role attached to a physical opening."""

    timeout_seconds: int | None = Field(default=None, ge=1)
    condition: SafetyDoorCondition | None = None


class ExternalHazardRole(SourceModel):
    """External-hazard role attached to a physical opening."""

    hazards: list[HazardName] | None = Field(default=None, min_length=1)
    actuator_entity_id: str | None = None
    execution_policy: Literal["manual", "user_confirmed"] = "manual"
    confirmation_timeout_seconds: int = Field(default=120, ge=15, le=600)

    @field_validator("hazards")
    @classmethod
    def _unique_hazards(cls, value: list[HazardName] | None) -> list[HazardName] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("opening hazards must not contain duplicates")
        return value

    @model_validator(mode="after")
    def _safe_actuation(self) -> "ExternalHazardRole":
        if self.execution_policy == "manual" and self.actuator_entity_id is not None:
            raise ValueError("manual external_hazard roles cannot define an actuator")
        return self


class InstallationOpening(SourceModel):
    """One physical window, door, garage door, or gate."""

    area_id: str
    entity_id: str
    friendly_name: str
    kind: Literal["window", "door", "garage_door", "gate"]
    safety_door: SafetyDoorRole | None = None
    external_hazard: ExternalHazardRole | None = None

    @field_validator("area_id", "entity_id", "friendly_name")
    @classmethod
    def _required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("opening binding values must not be empty")
        return normalized


class LocalizationBindings(SourceModel):
    """Installation-owned language and optional display-name overrides."""

    language: Literal["en", "pl", "de"] = "en"
    entity_names: dict[str, str] = Field(default_factory=dict)

    @field_validator("entity_names")
    @classmethod
    def _nonempty_entity_names(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for entity_id, name in value.items():
            normalized_id = entity_id.strip().lower()
            normalized_name = name.strip()
            if not _ENTITY_ID.fullmatch(normalized_id) or not normalized_name:
                raise ValueError(
                    "localization.entity_names requires valid entity IDs and "
                    "non-empty names"
                )
            normalized[normalized_id] = normalized_name
        return normalized


class MobileNotificationBindings(SourceModel):
    """Installation-owned Home Assistant notify services."""

    services: list[str] = Field(min_length=1)
    default_url: str = "/"

    @field_validator("services")
    @classmethod
    def _notify_services(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.strip().lower() for item in value))
        if any(not _NOTIFY_SERVICE.fullmatch(item) for item in normalized):
            raise ValueError("notification services must use notify/<service>")
        if "notify/notify" in normalized:
            raise ValueError("notify/notify is ambiguous")
        return normalized

    @field_validator("default_url")
    @classmethod
    def _relative_url(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("default_url must be a Home Assistant relative path")
        return value


class LocalNotificationBindings(SourceModel):
    """Optional installation-owned local annunciator entities."""

    light_entity: str | None = None
    alarm_entity: str | None = None

    @field_validator("light_entity", "alarm_entity")
    @classmethod
    def _optional_entity_id(cls, value: str | None) -> str | None:
        if value is not None and not _ENTITY_ID.fullmatch(value):
            raise ValueError(f"invalid Home Assistant entity ID: {value}")
        return value


class NotificationBindings(SourceModel):
    """Installation-owned notification destinations and reachability input."""

    mobile: MobileNotificationBindings
    local: LocalNotificationBindings = Field(default_factory=LocalNotificationBindings)
    wan_entity: str | None = None

    @field_validator("wan_entity")
    @classmethod
    def _optional_wan_entity(cls, value: str | None) -> str | None:
        if value is not None and not _ENTITY_ID.fullmatch(value):
            raise ValueError(f"invalid Home Assistant entity ID: {value}")
        return value


class ProviderSelection(SourceModel):
    """Installation enablement for one system-owned provider."""

    enabled: bool = True


class ApiComponentBindings(SourceModel):
    """Installation selection of the supported external providers."""

    OpenMeteoWeatherApiComponent: ProviderSelection = Field(
        default_factory=ProviderSelection
    )
    ImgwWarningsApiComponent: ProviderSelection = Field(
        default_factory=ProviderSelection
    )
    OpenMeteoAirQualityApiComponent: ProviderSelection = Field(
        default_factory=ProviderSelection
    )


class MqttCleanupBindings(SourceModel):
    """Installation-owned MQTT discovery identities retained for cleanup."""

    legacy_discovery_entity_ids: list[str] = Field(default_factory=list)

    @field_validator("legacy_discovery_entity_ids")
    @classmethod
    def _legacy_sensor_entity_ids(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.strip().lower() for item in value))
        if any(not re.fullmatch(r"sensor\.[a-z0-9_]+", item) for item in normalized):
            raise ValueError(
                "legacy_discovery_entity_ids must contain lowercase sensor "
                "entity IDs"
            )
        return normalized


class InstallationConfig(SourceModel):
    """Normalized physical installation used to generate component bindings."""

    site: SiteConfig | None = None
    common_entities: dict[str, str] = Field(default_factory=dict)
    defaults: InstallationDefaults = Field(default_factory=InstallationDefaults)
    rooms: dict[str, InstallationRoom] = Field(default_factory=dict)
    openings: dict[str, InstallationOpening] = Field(default_factory=dict)
    detectors: dict[str, InternalDetectorConfig] = Field(default_factory=dict)
    monitored_entities: dict[str, ExplicitEntityConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_registry(self) -> "InstallationConfig":
        for collection_name, collection in (
            ("rooms", self.rooms),
            ("openings", self.openings),
            ("detectors", self.detectors),
            ("monitored_entities", self.monitored_entities),
        ):
            invalid = [key for key in collection if not _STABLE_KEY.fullmatch(key)]
            if invalid:
                raise ValueError(
                    f"installation.{collection_name} keys must use stable "
                    f"PascalCase identifiers: {', '.join(invalid)}"
                )

        referenced_openings: dict[str, str] = {}
        for room_name, room in self.rooms.items():
            if room.window is None:
                continue
            opening = self.openings.get(room.window)
            if opening is None:
                raise ValueError(
                    f"installation.rooms.{room_name}.window references unknown "
                    f"opening {room.window}"
                )
            previous_room = referenced_openings.get(room.window)
            if previous_room is not None:
                raise ValueError(
                    f"installation opening {room.window} is assigned to both "
                    f"{previous_room} and {room_name}"
                )
            if room.area_id != opening.area_id:
                raise ValueError(
                    f"installation room {room_name} and opening {room.window} "
                    "must use the same area_id"
                )
            referenced_openings[room.window] = room_name
        return self


class ComponentSelection(SourceModel):
    """Explicit enablement of every component supported by model version 2."""

    TemperatureComponent: bool
    SafetyDoorsComponent: bool
    ExternalHazardComponent: bool
    EntityMonitorComponent: bool
    InternalEnvironmentalHazardMonitorComponent: bool

    @model_validator(mode="after")
    def _at_least_one_component(self) -> "ComponentSelection":
        if not any(self.model_dump().values()):
            raise ValueError("components_enabled must enable at least one component")
        return self


class UserConfigurationV2(SourceModel):
    """Complete editable source contract for user_config.yml."""

    model_version: Literal[CONFIGURATION_MODEL_VERSION]
    components_enabled: ComponentSelection
    localization: LocalizationBindings = Field(default_factory=LocalizationBindings)
    notification: NotificationBindings
    api_components: ApiComponentBindings = Field(default_factory=ApiComponentBindings)
    mqtt: MqttCleanupBindings = Field(default_factory=MqttCleanupBindings)
    installation: InstallationConfig


def user_configuration_schema() -> dict[str, Any]:
    """Return JSON Schema aligned with strict unknown-field validation."""

    schema = UserConfigurationV2.model_json_schema()

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


def _compile_temperature(
    system_component: dict[str, Any], installation: InstallationConfig
) -> dict[str, Any]:
    defaults = deep_merge(
        system_component.get("defaults", {}),
        installation.defaults.temperature.to_runtime(),
    )
    _validate_resolved_temperature(defaults, "installation.defaults.temperature")
    rooms: dict[str, dict[str, Any]] = {}
    for room_name, room in installation.rooms.items():
        binding: dict[str, Any] = {
            "area_id": room.area_id,
            "temperature_sensor": room.temperature_sensor,
        }
        if room.window is not None:
            binding["window_sensor"] = installation.openings[room.window].entity_id
        if room.actuator is not None:
            binding["actuator"] = room.actuator
        resolved_temperature = deep_merge(defaults, room.temperature.to_runtime())
        _validate_resolved_temperature(
            resolved_temperature,
            f"installation.rooms.{room_name}.temperature",
        )
        binding.update(resolved_temperature)
        rooms[room_name] = binding
    return {"defaults": defaults, "rooms": rooms}


def _validate_resolved_temperature(values: dict[str, Any], path: str) -> None:
    """Validate temperature ordering after all default layers are resolved."""

    low = values.get("CAL_LOW_TEMP_THRESHOLD")
    high = values.get("CAL_HIGH_TEMP_THRESHOLD")
    forecast = values.get("CAL_FORECAST_TIMESPAN")
    if low is None or high is None or forecast is None:
        raise ValueError(f"{path} does not resolve all temperature defaults")
    if low >= high:
        raise ValueError(f"{path} low_temperature_c must be below high_temperature_c")


def _compile_safety_doors(
    system_component: dict[str, Any], installation: InstallationConfig
) -> dict[str, Any]:
    installation_defaults = installation.defaults.safety_door.model_dump(
        exclude_none=True
    )
    defaults = deep_merge(system_component.get("defaults", {}), installation_defaults)
    doors: dict[str, dict[str, Any]] = {}
    for opening_name, opening in installation.openings.items():
        role = opening.safety_door
        if role is None:
            continue
        binding: dict[str, Any] = {
            "area_id": opening.area_id,
            "entity_id": opening.entity_id,
        }
        binding.update(role.model_dump(exclude_none=True))
        doors[opening_name] = binding
    return {"defaults": defaults, "doors": doors}


def _compile_external_hazards(
    system_component: dict[str, Any], installation: InstallationConfig
) -> dict[str, Any]:
    system_defaults = system_component.get("defaults", {})
    install_defaults = installation.defaults.external_hazard.model_dump(
        exclude_none=True
    )
    defaults = deep_merge(system_defaults, install_defaults)
    default_hazards = defaults.get("hazards")
    openings: dict[str, dict[str, Any]] = {}
    for opening_name, opening in installation.openings.items():
        role = opening.external_hazard
        if role is None:
            continue
        role_values = role.model_dump(exclude_none=True)
        hazards = role_values.pop("hazards", None) or default_hazards
        if not hazards:
            raise ValueError(
                f"installation.openings.{opening_name}.external_hazard requires "
                "hazards or an external_hazard default"
            )
        openings[opening_name] = {
            "area_id": opening.area_id,
            "entity_id": opening.entity_id,
            "friendly_name": opening.friendly_name,
            "kind": opening.kind,
            "hazards": copy.deepcopy(hazards),
            **role_values,
        }
    return {"openings": openings}


def _compile_internal_hazards(
    system_component: dict[str, Any], installation: InstallationConfig
) -> dict[str, Any]:
    compiled = copy.deepcopy(system_component)
    compiled["detectors"] = {
        key: detector.model_dump(exclude_none=True)
        for key, detector in installation.detectors.items()
    }
    return compiled


def _compile_entity_monitor(
    system_component: dict[str, Any], installation: InstallationConfig
) -> dict[str, Any]:
    compiled = copy.deepcopy(system_component)
    compiled["explicit_entities"] = {
        key: entity.model_dump(exclude_none=True)
        for key, entity in installation.monitored_entities.items()
    }
    compiled["component_overrides"] = deep_merge(
        compiled.get("component_overrides", {}),
        {
            key: value.model_dump(exclude_none=True)
            for key, value in installation.defaults.entity_monitor.component_overrides.items()
        },
    )
    return compiled


def compile_user_config_v2(
    runtime_defaults: dict[str, Any], user_config: dict[str, Any]
) -> dict[str, Any]:
    """Compile a v2 source config while preserving the v1 runtime contract."""

    try:
        source = UserConfigurationV2.model_validate(user_config)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    installation = source.installation

    source_overrides = source.model_dump(exclude_unset=True)
    source_overrides.pop("model_version", None)
    source_overrides.pop("installation", None)
    compiled = deep_merge(runtime_defaults, source_overrides)
    compiled["common_entities"] = copy.deepcopy(installation.common_entities)
    if installation.site is None:
        compiled.pop("site", None)
    else:
        compiled["site"] = installation.site.model_dump()

    system_components = runtime_defaults.get("safety_components", {})
    compiled["safety_components"] = {
        "TemperatureComponent": _compile_temperature(
            system_components.get("TemperatureComponent", {}), installation
        ),
        "SafetyDoorsComponent": _compile_safety_doors(
            system_components.get("SafetyDoorsComponent", {}), installation
        ),
        "ExternalHazardComponent": _compile_external_hazards(
            system_components.get("ExternalHazardComponent", {}), installation
        ),
        "EntityMonitorComponent": _compile_entity_monitor(
            system_components.get("EntityMonitorComponent", {}), installation
        ),
        "InternalEnvironmentalHazardMonitorComponent": _compile_internal_hazards(
            system_components.get("InternalEnvironmentalHazardMonitorComponent", {}),
            installation,
        ),
    }
    return compiled
