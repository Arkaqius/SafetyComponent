"""Configuration schemas for External Hazard Monitoring."""

from __future__ import annotations

import re
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from components.core.pydantic_utils import StrictBaseModel

COMPONENT_NAME = "ExternalHazardComponent"
HazardName = Literal["frost", "wind", "rain", "storm", "outdoor_air_pollution"]


class SiteConfig(StrictBaseModel):
    """Installation coordinates and administrative applicability."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str
    country_code: str
    teryt_codes: list[str] = Field(min_length=1)

    @field_validator("country_code")
    @classmethod
    def _country_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) != 2:
            raise ValueError("site.country_code must be a two-letter code")
        return normalized

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value: str) -> str:
        normalized = value.strip()
        try:
            ZoneInfo(normalized)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown site timezone: {normalized}") from exc
        return normalized

    @field_validator("teryt_codes")
    @classmethod
    def _teryt_codes(cls, value: list[str]) -> list[str]:
        normalized = [str(code).strip() for code in value]
        if any(not re.fullmatch(r"\d{4}", code) for code in normalized):
            raise ValueError("site.teryt_codes must contain four-digit powiat codes")
        if len(normalized) != len(set(normalized)):
            raise ValueError("site.teryt_codes must not contain duplicates")
        return normalized


class WeatherPolicy(StrictBaseModel):
    """Household weather thresholds."""

    forecast_horizon_hours: int = Field(default=12, ge=1, le=72)
    frost_watch_c: float
    frost_warning_c: float
    gust_watch_m_s: float = Field(gt=0)
    gust_warning_m_s: float = Field(gt=0)
    precipitation_warning_mm_h: float = Field(gt=0)
    persistence_seconds: int = Field(default=120, ge=0)
    hysteresis: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ordered_thresholds(self) -> "WeatherPolicy":
        if self.frost_warning_c > self.frost_watch_c:
            raise ValueError("frost_warning_c must not exceed frost_watch_c")
        if self.gust_warning_m_s < self.gust_watch_m_s:
            raise ValueError("gust_warning_m_s must not be below gust_watch_m_s")
        return self


class AirQualityPolicy(StrictBaseModel):
    """Conservative outdoor air-quality decision policy."""

    standard: Literal["european_aqi"] = "european_aqi"
    warning_at: float = Field(gt=0)
    gios_warning_level: int = Field(default=3, ge=0, le=5)
    conservative_source_policy: Literal["any_fresh_source"] = "any_fresh_source"


class RadiationPolicy(StrictBaseModel):
    """Ionizing-radiation semantic and anomaly policy."""

    official_alert_required_for_confirmed_fault: Literal[True] = True
    raw_anomaly_enabled: bool = False
    raw_anomaly_usv_h: float | None = Field(default=None, gt=0)
    raw_anomaly_min_stations: int = Field(default=2, ge=2)


class ExternalHazardPolicy(StrictBaseModel):
    """Global household external-hazard policy."""

    notification_only: Literal[True] = True
    decision_timeout_seconds: int = Field(default=1, ge=1, le=10)
    clear_delay_seconds: int = Field(default=120, ge=0)
    weather: WeatherPolicy
    outdoor_air_quality: AirQualityPolicy
    radiation: RadiationPolicy
    providers: dict[str, dict[str, Any]] = Field(min_length=1)


class OpeningConfig(StrictBaseModel):
    """One external opening correlated with provider hazards."""

    area_id: str
    entity_id: str
    friendly_name: str
    kind: Literal["window", "door", "garage_door"]
    hazards: list[HazardName] = Field(min_length=1)

    @field_validator("area_id", "entity_id", "friendly_name")
    @classmethod
    def _not_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("External hazard opening values must not be empty")
        return normalized

    @field_validator("hazards")
    @classmethod
    def _unique_hazards(cls, value: list[HazardName]) -> list[HazardName]:
        if len(value) != len(set(value)):
            raise ValueError("Opening hazards must not contain duplicates")
        return value


class ExternalHazardComponentConfig(StrictBaseModel):
    """House-specific opening registry."""

    openings: dict[str, OpeningConfig] = Field(min_length=1)

    @field_validator("openings")
    @classmethod
    def _stable_opening_ids(
        cls, value: dict[str, OpeningConfig]
    ) -> dict[str, OpeningConfig]:
        invalid = [name for name in value if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", name)]
        if invalid:
            raise ValueError(
                "Opening IDs must use stable PascalCase identifiers: "
                + ", ".join(invalid)
            )
        return value

    def to_runtime(self, policy: ExternalHazardPolicy) -> dict[str, Any]:
        return {
            "policy": policy.model_dump(),
            "openings": {
                name: config.model_dump() for name, config in self.openings.items()
            },
        }


def validate_external_hazard_config(
    raw_cfg: dict[str, Any],
    *,
    policy: ExternalHazardPolicy,
    strict_validation: bool,
) -> dict[str, Any]:
    """Validate and normalize the C-EXT household configuration."""

    validated = ExternalHazardComponentConfig.model_validate(
        raw_cfg, context={"strict_validation": strict_validation}
    )
    return validated.to_runtime(policy)
