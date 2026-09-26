"""Compile the versioned installation model into component bindings."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import (
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from build_appdaemon_config import validated_number
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

ConfigurationModelVersion = Literal[2]
CONFIGURATION_MODEL_VERSION: ConfigurationModelVersion = 2
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
        return values


class SafetyDoorDefaults(SourceModel):
    """Installation-wide overrides for safety-door monitoring."""

    timeout_seconds: int | None = Field(default=None, ge=1)


class ExternalHazardDefaults(SourceModel):
    """Installation-specific external-hazard decision thresholds."""

    weather: "WeatherOverrides" = Field(default_factory=lambda: WeatherOverrides())
    outdoor_air_quality: "AirQualityOverrides" = Field(
        default_factory=lambda: AirQualityOverrides()
    )


class WeatherOverrides(SourceModel):
    """Installation overrides for weather decision defaults."""

    frost_watch_c: float | None = None
    frost_warning_c: float | None = None
    gust_watch_m_s: float | None = Field(default=None, gt=0)
    gust_warning_m_s: float | None = Field(default=None, gt=0)
    precipitation_warning_mm_h: float | None = Field(default=None, gt=0)
    persistence_seconds: int | None = Field(default=None, ge=0)
    hysteresis: dict[str, float] | None = None

    @model_validator(mode="after")
    def _ordered_thresholds(self) -> "WeatherOverrides":
        if (
            self.frost_watch_c is not None
            and self.frost_warning_c is not None
            and self.frost_warning_c > self.frost_watch_c
        ):
            raise ValueError("frost_warning_c must not exceed frost_watch_c")
        if (
            self.gust_watch_m_s is not None
            and self.gust_warning_m_s is not None
            and self.gust_warning_m_s < self.gust_watch_m_s
        ):
            raise ValueError("gust_warning_m_s must not be below gust_watch_m_s")
        return self


class AirQualityOverrides(SourceModel):
    """Installation overrides for outdoor-air-quality decision defaults."""

    standard: Literal["european_aqi"] | None = None
    warning_at: float | None = Field(default=None, gt=0)


class EntityMonitorDefaults(SourceModel):
    """Installation overrides for component-owned entity dependencies."""

    startup_grace_seconds: int | None = Field(default=None, ge=0)
    evaluation_interval_seconds: int | None = Field(default=None, ge=1)
    component_overrides: dict[str, ComponentEntityOverride] = Field(
        default_factory=dict
    )


class ComponentSettings(SourceModel):
    """Installation-specific settings grouped by their owning component."""

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
    """Installation-owned language selection; names live in locale files."""

    language: Literal["en", "pl", "de"] = "en"


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


class ProviderBindings(SourceModel):
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


class InstallationSite(SourceModel):
    """Administrative location; geographic coordinates always come from HA."""

    timezone: str
    country_code: str
    teryt_codes: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_site(self) -> "InstallationSite":
        # The runtime coordinates are supplied later; validate the remaining
        # administrative fields through the same strict site contract.
        SiteConfig.model_validate({"latitude": 0, "longitude": 0, **self.model_dump()})
        return self


class HostMemoryBindings(SourceModel):
    """Host-available memory and PSI entities from the same HA host."""

    available_entity: str
    psi_entity: str

    @field_validator("available_entity", "psi_entity")
    @classmethod
    def _entity_id(cls, value: str) -> str:
        if not value.startswith("sensor.") or not _ENTITY_ID.fullmatch(value):
            raise ValueError(f"expected sensor entity ID: {value}")
        return value

    @model_validator(mode="after")
    def _different_sources(self) -> "HostMemoryBindings":
        if self.available_entity == self.psi_entity:
            raise ValueError("available memory and PSI need distinct entities")
        return self


class UpdateBindings(SourceModel):
    """Optional Home Assistant update entities for known products."""

    home_assistant_core: str | None = None
    home_assistant_os: str | None = None
    home_assistant_supervisor: str | None = None
    safety_component: str | None = None

    @field_validator("home_assistant_core", "home_assistant_os", "home_assistant_supervisor", "safety_component")
    @classmethod
    def _update_entity(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("update."):
            raise ValueError(f"expected update entity ID: {value}")
        if value is not None and not _ENTITY_ID.fullmatch(value):
            raise ValueError(f"invalid Home Assistant entity ID: {value}")
        return value


class RemoteBatteryBinding(SourceModel):
    """One physical remote device, optionally exposing two battery forms."""

    friendly_name: str = Field(min_length=1)
    percentage_entity: str | None = None
    low_entity: str | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def _validate_sources(self) -> "RemoteBatteryBinding":
        if not self.percentage_entity and not self.low_entity:
            raise ValueError("a remote battery needs percentage_entity or low_entity")
        if self.percentage_entity is not None and not self.percentage_entity.startswith("sensor."):
            raise ValueError("percentage_entity must be a sensor")
        if self.low_entity is not None and not self.low_entity.startswith("binary_sensor."):
            raise ValueError("low_entity must be a binary_sensor")
        for value in (self.percentage_entity, self.low_entity):
            if value is not None and not _ENTITY_ID.fullmatch(value):
                raise ValueError(f"invalid Home Assistant entity ID: {value}")
        return self


class BatteryMonitoring(SourceModel):
    """Automatic device discovery with persistent registry-ID exclusions."""

    enabled: bool = True
    excluded_devices: list[str] = Field(default_factory=list, max_length=512)

    @field_validator("excluded_devices")
    @classmethod
    def _device_ids(cls, value: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[0-9a-f]{32}", device) for device in value):
            raise ValueError("excluded_devices must contain Home Assistant device registry IDs")
        return list(dict.fromkeys(value))


class FunctionalSafetyBindings(SourceModel):
    """Installation-owned sources; absence means uncovered, not healthy."""

    host_memory: HostMemoryBindings | None = None
    host_cpu_entity: str | None = None
    updates: UpdateBindings = Field(default_factory=UpdateBindings)
    remote_batteries: dict[str, RemoteBatteryBinding] = Field(default_factory=dict)
    battery_monitoring: BatteryMonitoring = Field(default_factory=BatteryMonitoring)

    @field_validator("host_cpu_entity")
    @classmethod
    def _cpu_entity(cls, value: str | None) -> str | None:
        if value is not None and (not value.startswith("sensor.") or not _ENTITY_ID.fullmatch(value)):
            raise ValueError(f"expected sensor entity ID: {value}")
        return value

    @model_validator(mode="after")
    def _validate_keys(self) -> "FunctionalSafetyBindings":
        invalid = [key for key in self.remote_batteries if not _STABLE_KEY.fullmatch(key)]
        if invalid:
            raise ValueError("remote_batteries keys must use stable PascalCase identifiers: " + ", ".join(invalid))
        return self


class InstallationConfig(SourceModel):
    """Normalized physical installation used to generate component bindings."""

    site: InstallationSite | None = None
    common_entities: dict[str, str] = Field(default_factory=dict)
    component_settings: ComponentSettings = Field(default_factory=ComponentSettings)
    rooms: dict[str, InstallationRoom] = Field(default_factory=dict)
    openings: dict[str, InstallationOpening] = Field(default_factory=dict)
    detectors: dict[str, InternalDetectorConfig] = Field(default_factory=dict)
    monitored_entities: dict[str, ExplicitEntityConfig] = Field(default_factory=dict)
    functional_safety: FunctionalSafetyBindings = Field(default_factory=FunctionalSafetyBindings)

    @model_validator(mode="after")
    def _validate_registry(self) -> "InstallationConfig":
        registries: dict[str, set[str]] = {
            "rooms": set(self.rooms),
            "openings": set(self.openings),
            "detectors": set(self.detectors),
            "monitored_entities": set(self.monitored_entities),
        }
        for collection_name, collection in registries.items():
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

    model_version: ConfigurationModelVersion
    components_enabled: ComponentSelection
    localization: LocalizationBindings = Field(default_factory=LocalizationBindings)
    notification: NotificationBindings
    providers: ProviderBindings = Field(default_factory=ProviderBindings)
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


def validate_user_configuration_v2(
    user_config: dict[str, Any],
) -> UserConfigurationV2:
    """Validate and normalize the complete editable source configuration."""

    try:
        return UserConfigurationV2.model_validate(user_config)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


def _compile_temperature(
    system_component: dict[str, Any], installation: InstallationConfig
) -> dict[str, Any]:
    defaults = deep_merge(
        system_component.get("defaults", {}),
        installation.component_settings.temperature.to_runtime(),
    )
    _validate_resolved_temperature(
        defaults, "installation.component_settings.temperature"
    )
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
    installation_defaults = installation.component_settings.safety_door.model_dump(
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
    install_defaults = installation.component_settings.external_hazard.model_dump(
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
            for key, value in installation.component_settings.entity_monitor.component_overrides.items()
        },
    )
    return compiled


def compile_user_config_v2(
    runtime_defaults: dict[str, Any],
    user_config: dict[str, Any],
    home_assistant_config: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile a v2 source config while preserving the v1 runtime contract."""

    source = validate_user_configuration_v2(user_config)
    installation = source.installation

    source_overrides = source.model_dump(exclude_unset=True)
    source_overrides.pop("model_version", None)
    source_overrides.pop("installation", None)
    provider_overrides = source_overrides.pop("providers", {})
    compiled = deep_merge(runtime_defaults, source_overrides)
    compiled["api_components"] = deep_merge(
        runtime_defaults.get("api_components", {}), provider_overrides
    )
    compiled["common_entities"] = copy.deepcopy(installation.common_entities)
    compiled["functional_safety"] = installation.functional_safety.model_dump(exclude_none=True)
    if installation.site is None:
        compiled.pop("site", None)
    else:
        compiled["site"] = SiteConfig.model_validate(
            {
                **installation.site.model_dump(),
                "latitude": validated_number(home_assistant_config, "latitude"),
                "longitude": validated_number(home_assistant_config, "longitude"),
            }
        ).model_dump()

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
