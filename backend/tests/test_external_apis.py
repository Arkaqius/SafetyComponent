"""Contract tests for independent external provider adapters."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import pytest

from components.external_apis.core.http_json_client import HttpJsonClient, HttpJsonError
from components.external_apis.core.api_component import ExternalApiComponent
from components.external_apis.core.models import (
    ExternalObservation,
    HazardType,
    Measurement,
    ProviderHealthState,
)
from components.external_apis.imgw_warnings.component import ImgwWarningsApiComponent
from components.external_apis.open_meteo_air_quality.component import OpenMeteoAirQualityApiComponent
from components.external_apis.open_meteo_weather.component import OpenMeteoWeatherApiComponent

FIXTURES = Path(__file__).parent / "fixtures" / "external_apis"
RETRIEVED_AT = datetime(2026, 8, 4, 12, 5, tzinfo=timezone.utc)
SITE = {
    "latitude": 50.0125,
    "longitude": 20.1163,
    "timezone": "Europe/Warsaw",
    "teryt_codes": ["1219"],
}


def _payload(provider: str) -> object:
    return json.loads((FIXTURES / provider / "normal.json").read_text(encoding="utf-8"))


def _config(**values: object) -> dict[str, object]:
    return {
        "base_url": "https://example.invalid",
        "poll_interval_seconds": 300,
        "request_timeout_seconds": 5,
        "max_retries": 0,
        "stale_after_seconds": 900,
        **values,
    }


def _component(cls, **config: object):
    return cls(
        provider_config=_config(**config),
        site_config=SITE,
        http_client=object(),
    )


def test_open_meteo_weather_preserves_current_and_forecast_semantics() -> None:
    component = _component(OpenMeteoWeatherApiComponent, forecast_horizon_hours=12)
    observations = component.normalize(_payload("open_meteo_weather"), RETRIEVED_AT)

    assert {observation.hazard_type for observation in observations} == {
        HazardType.FROST,
        HazardType.WIND,
        HazardType.RAIN,
        HazardType.STORM,
    }
    wind = next(item for item in observations if item.hazard_type == HazardType.WIND)
    assert wind.values["current_wind_gust"].value == 7.0
    assert wind.values["forecast_max_wind_gust"].value == 21.0
    assert wind.values["forecast_max_wind_gust"].unit == "m/s"


def test_imgw_filters_warnings_by_configured_teryt_and_preserves_authority() -> None:
    component = _component(ImgwWarningsApiComponent)
    observations = component.normalize(_payload("imgw_warnings"), RETRIEVED_AT)

    assert len(observations) == 1
    assert observations[0].observation_id == "imgw-1219-storm"
    assert observations[0].hazard_type == HazardType.STORM
    assert observations[0].authority_confirmed is True
    assert observations[0].region_codes == ("1219",)

    component.last_attempt_at = RETRIEVED_AT
    evidence = component.build_evidence(_payload("imgw_warnings"), observations)
    assert evidence["warning_count"] == 1
    assert [warning["id"] for warning in evidence["warnings"]] == ["imgw-1219-storm"]
    assert evidence["warnings"][0]["locally_applicable"] is True


@pytest.mark.parametrize(
    ("payload", "expected_state", "expected_detail"),
    [
        (
            {"status": False, "message": "No products were found"},
            ProviderHealthState.OK,
            None,
        ),
        (
            {"status": False, "message": "Unknown resource"},
            ProviderHealthState.UNAVAILABLE,
            "http_404",
        ),
    ],
)
def test_imgw_distinguishes_empty_warning_feed_from_other_404_errors(
    payload: dict[str, object],
    expected_state: ProviderHealthState,
    expected_detail: str | None,
) -> None:
    class ErrorOpener:
        def open(self, request, *, timeout):  # type: ignore[no-untyped-def]
            del timeout
            raise HTTPError(
                request.full_url,
                404,
                "Not Found",
                {},
                BytesIO(json.dumps(payload).encode("utf-8")),
            )

    client = HttpJsonClient(allowed_hosts={"example.invalid"})
    client._opener = ErrorOpener()
    component = ImgwWarningsApiComponent(
        provider_config=_config(),
        site_config=SITE,
        http_client=client,
    )

    result = component.poll()

    assert result.health.state == expected_state
    assert result.health.detail_code == expected_detail
    assert result.observations == ()
    if expected_state == ProviderHealthState.OK:
        assert result.evidence == {
            "observation_count": 0,
            "warning_count": 0,
            "warnings": [],
        }


def test_open_meteo_air_quality_keeps_european_aqi_model_identity() -> None:
    component = _component(OpenMeteoAirQualityApiComponent)
    observation = component.normalize(_payload("open_meteo_air_quality"), RETRIEVED_AT)[0]

    assert observation.provider == "OpenMeteoAirQualityApiComponent"
    assert observation.values["current_european_aqi"].value == 65.0
    assert not any(name.startswith("forecast_") for name in observation.values)
    assert observation.values["current_european_aqi"].unit == "EAQI"


def test_http_json_shape_limits_reject_oversized_untrusted_values() -> None:
    client = HttpJsonClient(
        allowed_hosts={"example.com"},
        max_depth=2,
        max_list_items=2,
        max_string_length=4,
    )

    with pytest.raises(HttpJsonError, match="length"):
        client._validate_shape("remote text")
    with pytest.raises(HttpJsonError, match="item"):
        client._validate_shape([1, 2, 3])
    with pytest.raises(HttpJsonError, match="depth"):
        client._validate_shape({"a": {"b": {"c": 1}}})


def test_stale_source_result_preserves_last_fresh_provider_cache() -> None:
    class StaleProvider(ExternalApiComponent):
        component_name = "StaleProvider"

        def __init__(self) -> None:
            super().__init__(
                provider_config=_config(),
                site_config=SITE,
                http_client=object(),
            )
            self.fresh = True

        def fetch_payload(self) -> object:
            return {}

        def normalize(self, payload: object, retrieved_at: datetime):
            del payload
            valid_to = retrieved_at + timedelta(minutes=1) if self.fresh else retrieved_at - timedelta(minutes=1)
            return (
                ExternalObservation(
                    provider=self.component_name,
                    observation_id="stable-observation",
                    hazard_type=HazardType.WIND,
                    provider_level=None,
                    values={"gust": Measurement(20, "m/s")},
                    observed_at=retrieved_at,
                    valid_from=retrieved_at - timedelta(minutes=1),
                    valid_to=valid_to,
                    retrieved_at=retrieved_at,
                ),
            )

    component = StaleProvider()
    fresh = component.poll()
    component.fresh = False
    stale = component.poll()

    assert fresh.health.state == ProviderHealthState.OK
    assert stale.health.state == ProviderHealthState.STALE
    assert stale.health.detail_code == "stale_source_time"
    assert stale.observations == fresh.observations


def test_unexpected_provider_exception_becomes_schema_health_result() -> None:
    class UnexpectedProvider(ExternalApiComponent):
        component_name = "UnexpectedProvider"

        def __init__(self) -> None:
            super().__init__(
                provider_config=_config(),
                site_config=SITE,
                http_client=object(),
            )

        def fetch_payload(self) -> object:
            raise RuntimeError("unexpected provider defect")

        def normalize(self, payload: object, retrieved_at: datetime):
            raise AssertionError("normalization must not be reached")

    result = UnexpectedProvider().poll()

    assert result.health.state == ProviderHealthState.SCHEMA_ERROR
    assert result.health.detail_code == "schema_error"
    assert result.observations == ()
