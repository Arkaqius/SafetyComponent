"""Configuration schema for official IMGW warnings."""

from urllib.parse import urlparse
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from components.core.pydantic_utils import StrictBaseModel

COMPONENT_NAME = "ImgwWarningsApiComponent"

TerytCode = Annotated[str, Field(pattern=r"^[0-9]{4}$")]
TerytCodes = Annotated[list[TerytCode], Field(max_length=10_000, json_schema_extra={"uniqueItems": True})]


class ImgwWarningsParameters(BaseModel):
    """Installation-owned county selection, required only for active IMGW."""

    model_config = ConfigDict(extra="forbid")
    teryt_codes: TerytCodes | None = Field(default=None, title="Kody TERYT", description="Czterocyfrowe kody powiatów IMGW, jeden w wierszu.")

    @field_validator("teryt_codes", mode="before")
    @classmethod
    def _codes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if not isinstance(value, list) or any(not isinstance(code, str) for code in value):
            raise ValueError("IMGW codes must be four-digit strings")
        codes = [code.strip() for code in value]
        if len(codes) != len(set(codes)):
            raise ValueError("IMGW requires unique four-digit codes in site.teryt_codes or provider parameters")
        return codes


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
