"""Configuration schema for Open-Meteo air-quality forecasts."""

from urllib.parse import urlparse

from pydantic import Field, field_validator

from components.core.pydantic_utils import StrictBaseModel

COMPONENT_NAME = "OpenMeteoAirQualityApiComponent"


class OpenMeteoAirQualityConfig(StrictBaseModel):
    """Validated Open-Meteo air-quality provider configuration."""

    enabled: bool = True
    base_url: str
    poll_interval_seconds: int = Field(ge=60)
    request_timeout_seconds: float = Field(gt=0, le=30)
    max_retries: int = Field(default=2, ge=0, le=5)
    stale_after_seconds: int = Field(ge=60)
    forecast_horizon_hours: int = Field(default=12, ge=1, le=72)

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname != "air-quality-api.open-meteo.com":
            raise ValueError("Open-Meteo AQ URL must use air-quality-api.open-meteo.com over HTTPS")
        return value.rstrip("/")
