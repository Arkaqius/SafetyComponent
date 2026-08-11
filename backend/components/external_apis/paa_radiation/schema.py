"""Configuration schema for official PAA radiological data."""

from urllib.parse import urlparse

from pydantic import Field, field_validator

from components.core.pydantic_utils import StrictBaseModel

COMPONENT_NAME = "PaaRadiationApiComponent"


class PaaRadiationConfig(StrictBaseModel):
    """Validated PAA message and measurement configuration."""

    enabled: bool = True
    base_url: str
    radiation_message_path: str
    measurement_path: str
    poll_interval_seconds: int = Field(ge=60)
    request_timeout_seconds: float = Field(gt=0, le=30)
    max_retries: int = Field(default=2, ge=0, le=5)
    stale_after_seconds: int = Field(ge=60)
    language: str = "pl"
    station_ids: list[str] = Field(default_factory=list)

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname != "monitoring.paa.gov.pl":
            raise ValueError("PAA URL must use monitoring.paa.gov.pl over HTTPS")
        return value.rstrip("/")

    @field_validator("radiation_message_path", "measurement_path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        if not value.startswith("/") or ".." in value:
            raise ValueError("PAA endpoint paths must be absolute safe paths")
        return value

    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: str) -> str:
        language = value.strip().lower()
        if language not in {"pl", "en"}:
            raise ValueError("PAA language must be pl or en")
        return language
