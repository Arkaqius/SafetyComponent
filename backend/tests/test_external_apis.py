"""Contract tests for independent external provider adapters."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from components.external_apis.core.http_json_client import HttpJsonClient, HttpJsonError
from components.external_apis.core.api_component import ExternalApiComponent
from components.external_apis.core.models import (
    ExternalObservation,
    HazardType,
    Measurement,
    ProviderHealthState,
)
from components.external_apis.gios_air_quality.component import GiosAirQualityApiComponent
from components.external_apis.imgw_warnings.component import ImgwWarningsApiComponent
from components.external_apis.open_meteo_air_quality.component import OpenMeteoAirQualityApiComponent
from components.external_apis.open_meteo_weather.component import OpenMeteoWeatherApiComponent
from components.external_apis.paa_radiation.component import PaaRadiationApiComponent

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


def test_gios_keeps_polish_index_and_station_measurement_distinct() -> None:
    component = _component(GiosAirQualityApiComponent, station_ids=[402])
    observation = component.normalize(_payload("gios_air_quality"), RETRIEVED_AT)[0]

    assert observation.values["polish_index_name"].value == "Dostateczny"
    assert observation.values["polish_index_level"].value == 3
    assert observation.values["measurement_pm10"].value == 58.2
    assert observation.values["measurement_pm10"].unit == "µg/m³"


def test_open_meteo_air_quality_keeps_european_aqi_model_identity() -> None:
    component = _component(OpenMeteoAirQualityApiComponent)
    observation = component.normalize(_payload("open_meteo_air_quality"), RETRIEVED_AT)[0]

    assert observation.provider == "OpenMeteoAirQualityApiComponent"
    assert observation.values["current_european_aqi"].value == 65.0
    assert not any(name.startswith("forecast_") for name in observation.values)
    assert observation.values["current_european_aqi"].unit == "EAQI"


def test_paa_keeps_official_message_and_raw_measurement_semantics_separate() -> None:
    component = _component(
        PaaRadiationApiComponent,
        radiation_message_path="/RadiationMessage/{language}",
        measurement_path="/Measurement/{language}",
        language="pl",
        station_ids=[],
    )
    observations = component.normalize(_payload("paa_radiation"), RETRIEVED_AT)

    official = next(item for item in observations if item.hazard_type == HazardType.IONIZING_RADIATION)
    measurement = next(item for item in observations if item.hazard_type == HazardType.RADIATION_ANOMALY)
    assert official.authority_confirmed is True
    assert official.values["result_type"].value == "official_message"
    assert measurement.authority_confirmed is False
    assert measurement.values["result_type"].value == "dose_rate_measurement"
    assert measurement.values["dose_rate"].value == pytest.approx(0.095)
    assert measurement.values["dose_rate"].unit == "µSv/h"


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


def test_gios_fetch_falls_back_between_stations_and_skips_failed_sensors() -> None:
    class GiosClient:
        def get_json(self, url: str, **_: object) -> object:
            if "getIndex/401" in url:
                raise TimeoutError("primary station unavailable")
            if "getIndex/402" in url:
                return {"stIndexStatus": "Dobry", "stIndexLevel": 1}
            if "sensors/402" in url:
                return {
                    "items": [
                        {"id": 10, "paramCode": "PM10"},
                        {"id": 11},
                        {"id": 12, "paramCode": "NO2"},
                    ]
                }
            if "getData/10" in url:
                return [{"date": "2026-08-04T12:00:00Z", "value": 18.5}]
            if "getData/12" in url:
                raise TimeoutError("one sensor unavailable")
            raise AssertionError(url)

    component = GiosAirQualityApiComponent(
        provider_config=_config(station_ids=[401, 402]),
        site_config=SITE,
        http_client=GiosClient(),
    )

    payload = component.fetch_payload()

    assert payload["station_id"] == 402
    assert payload["measurements"] == [
        {
            "sensor_id": 10,
            "parameter": "PM10",
            "data": [{"date": "2026-08-04T12:00:00Z", "value": 18.5}],
        }
    ]


def test_gios_helpers_reject_malformed_payloads_and_map_named_levels() -> None:
    component = _component(GiosAirQualityApiComponent, station_ids=[])

    with pytest.raises(ValueError, match="No GIO"):
        component.fetch_payload()
    with pytest.raises(ValueError, match="composite"):
        component.normalize([], RETRIEVED_AT)
    with pytest.raises(ValueError, match="item list"):
        component._items({"unexpected": "value"})

    assert component._items([{"id": 1}, "ignored"]) == [{"id": 1}]
    assert component._index_level({"indexLevelName": "Bardzo dobry"}, None) == 0
    assert component._index_level("not-a-level", "Nieznany") == -1
    assert component._latest_measurement(
        {"values": [{"date": "invalid", "value": "invalid"}]}
    ) is None


def test_paa_fetch_uses_separate_official_and_measurement_endpoints() -> None:
    calls: list[str] = []

    class PaaClient:
        def get_json(self, url: str, **_: object) -> object:
            calls.append(url)
            return {"url": url}

    component = PaaRadiationApiComponent(
        provider_config=_config(
            radiation_message_path="/messages/{language}",
            measurement_path="/measurements/{language}",
            language="pl",
            station_ids=[],
        ),
        site_config=SITE,
        http_client=PaaClient(),
    )

    payload = component.fetch_payload()

    assert calls == [
        "https://example.invalid/messages/pl",
        "https://example.invalid/measurements/pl",
    ]
    assert payload == {
        "messages": {"url": calls[0]},
        "measurements": {"url": calls[1]},
    }


def test_paa_rejects_ambiguous_data_and_filters_stale_or_unconfigured_records() -> None:
    component = _component(
        PaaRadiationApiComponent,
        radiation_message_path="/messages/{language}",
        measurement_path="/measurements/{language}",
        language="pl",
        station_ids=["wanted"],
    )

    with pytest.raises(ValueError, match="mapping"):
        component.normalize([], RETRIEVED_AT)
    with pytest.raises(ValueError, match="mappings or lists"):
        component._records("unexpected")
    with pytest.raises(ValueError, match="Unsupported"):
        component._normalize_dose_rate(1, "mSv/h")

    payload = {
        "messages": [
            {"status": "brak alarmu"},
            {
                "active": True,
                "status": "alarm",
                "validTo": "2026-08-04T11:00:00Z",
            },
        ],
        "measurements": [
            {"stationId": "ignored", "value": 95, "unit": "nSv/h"},
            {
                "stationId": "wanted",
                "value": 95,
                "unit": "nSv/h",
                "timestamp": "2026-08-04T11:00:00Z",
            },
            {"stationId": "wanted", "unit": "nSv/h"},
        ],
    }

    assert component.normalize(payload, RETRIEVED_AT) == ()
    assert component._official_alert_active({"warning": 1}) is True
    assert component._official_alert_active({"status": "normal"}) is False
    assert component._safe_datetime("invalid", RETRIEVED_AT) == RETRIEVED_AT
