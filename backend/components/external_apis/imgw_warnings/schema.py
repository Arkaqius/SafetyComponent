"""Configuration schema for official IMGW warnings."""

from urllib.parse import urlparse

from pydantic import Field, field_validator

from components.core.pydantic_utils import StrictBaseModel

COMPONENT_NAME = "ImgwWarningsApiComponent"


class ImgwWarningsConfig(StrictBaseModel):
    """Validated IMGW warning provider configuration."""

    enabled: bool = True
    base_url: str
    poll_interval_seconds: int = Field(ge=60)
    request_timeout_seconds: float = Field(gt=0, le=30)
    max_retries: int = Field(default=2, ge=0, le=5)
    stale_after_seconds: int = Field(ge=60)

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname != "danepubliczne.imgw.pl":
            raise ValueError("IMGW URL must use danepubliczne.imgw.pl over HTTPS")
        return value.rstrip("/")
