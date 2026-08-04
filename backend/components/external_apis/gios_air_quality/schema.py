"""Configuration schema for GIOŚ station air-quality data."""

from urllib.parse import urlparse

from pydantic import Field, field_validator

from components.core.pydantic_utils import StrictBaseModel

COMPONENT_NAME = "GiosAirQualityApiComponent"


class GiosAirQualityConfig(StrictBaseModel):
    """Validated GIOŚ station provider configuration."""

    enabled: bool = True
    base_url: str
    poll_interval_seconds: int = Field(ge=60)
    request_timeout_seconds: float = Field(gt=0, le=30)
    max_retries: int = Field(default=2, ge=0, le=5)
    stale_after_seconds: int = Field(ge=60)
    station_ids: list[int] = Field(min_length=1)

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname != "api.gios.gov.pl":
            raise ValueError("GIOŚ URL must use api.gios.gov.pl over HTTPS")
        return value.rstrip("/")
