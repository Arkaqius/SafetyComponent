"""Threshold and authority tests for external-hazard household policy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from components.external_apis.core.models import (
    ExternalObservation,
    HazardType,
    Measurement,
)
from components.safetycomponents.external_hazard.policy import evaluate_observation

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
POLICY = {
    "weather": {
        "frost_watch_c": 2.0,
        "frost_warning_c": 0.0,
        "gust_watch_m_s": 15.0,
        "gust_warning_m_s": 20.0,
        "precipitation_warning_mm_h": 2.5,
    },
    "outdoor_air_quality": {"warning_at": 60, "gios_warning_level": 3},
}


def _observation(
    hazard: HazardType,
    values: dict[str, Measurement],
    *,
    provider: str = "OpenMeteoWeatherApiComponent",
    confirmed: bool = False,
    valid_to: datetime | None = None,
) -> ExternalObservation:
    expires_at = valid_to or NOW + timedelta(hours=1)
    return ExternalObservation(
        provider=provider,
        observation_id=f"{provider}-{hazard.value}",
        hazard_type=hazard,
        provider_level="2" if confirmed else None,
        values=values,
        observed_at=NOW,
        valid_from=min(NOW, expires_at),
        valid_to=expires_at,
        retrieved_at=NOW,
        authority_confirmed=confirmed,
    )


@pytest.mark.parametrize(
    ("observation", "active", "severity", "evidence"),
    [
        (
            _observation(
                HazardType.FROST,
                {
                    "current_temperature": Measurement(4.0),
                    "forecast_min_temperature": Measurement(1.0),
                },
            ),
            True,
            "watch",
            "forecast",
        ),
        (
            _observation(
                HazardType.WIND,
                {
                    "current_wind_gust": Measurement(21.0),
                    "forecast_max_wind_gust": Measurement(18.0),
                },
            ),
            True,
            "warning",
            "current",
        ),
        (
            _observation(
                HazardType.RAIN,
                {
                    "current_precipitation": Measurement(0.0),
                    "current_rain": Measurement(0.0),
                    "forecast_max_precipitation": Measurement(3.0),
                    "forecast_max_rain": Measurement(2.0),
                },
            ),
            True,
            "warning",
            "forecast",
        ),
        (
            _observation(
                HazardType.STORM,
                {
                    "current_weather_code": Measurement(3),
                    "forecast_weather_codes": Measurement("80,95"),
                },
            ),
            True,
            "warning",
            "forecast",
        ),
    ],
)
def test_weather_thresholds_keep_current_and_forecast_evidence(
    observation: ExternalObservation,
    active: bool,
    severity: str,
    evidence: str,
) -> None:
    assessment = evaluate_observation(observation, POLICY, NOW)

    assert assessment.active is active
    assert assessment.severity == severity
    assert assessment.evidence_kind == evidence


def test_official_imgw_warning_overrides_numeric_weather_thresholds() -> None:
    observation = _observation(
        HazardType.STORM,
        {"event_name": Measurement("Burze")},
        provider="ImgwWarningsApiComponent",
        confirmed=True,
    )

    assessment = evaluate_observation(observation, POLICY, NOW)

    assert assessment.active is True
    assert assessment.evidence_kind == "official_warning"
    assert assessment.inhibits_opening_advice is True


def test_air_quality_sources_keep_their_distinct_index_semantics() -> None:
    gios = evaluate_observation(
        _observation(
            HazardType.OUTDOOR_AIR_POLLUTION,
            {
                "polish_index_level": Measurement(3),
                "polish_index_name": Measurement("Dostateczny"),
            },
            provider="GiosAirQualityApiComponent",
        ),
        POLICY,
        NOW,
    )
    model = evaluate_observation(
        _observation(
            HazardType.OUTDOOR_AIR_POLLUTION,
            {
                "current_european_aqi": Measurement(35),
                "forecast_max_european_aqi": Measurement(61),
            },
            provider="OpenMeteoAirQualityApiComponent",
        ),
        POLICY,
        NOW,
    )

    assert gios.active is True
    assert "GIO" in gios.observed_value
    assert model.active is True
    assert model.evidence_kind == "forecast"


def test_only_authority_confirmed_radiation_message_is_severe() -> None:
    official = evaluate_observation(
        _observation(
            HazardType.IONIZING_RADIATION,
            {"status": Measurement("alarm")},
            provider="PaaRadiationApiComponent",
            confirmed=True,
        ),
        POLICY,
        NOW,
    )
    raw = evaluate_observation(
        _observation(
            HazardType.RADIATION_ANOMALY,
            {"dose_rate": Measurement(0.5, "uSv/h")},
            provider="PaaRadiationApiComponent",
        ),
        POLICY,
        NOW,
    )

    assert official.active is True
    assert official.severity == "severe"
    assert raw.active is False
    assert raw.severity == "unknown"


def test_stale_or_incomplete_normalized_data_cannot_be_positive_evidence() -> None:
    stale = evaluate_observation(
        _observation(
            HazardType.WIND,
            {
                "current_wind_gust": Measurement(30),
                "forecast_max_wind_gust": Measurement(30),
            },
            valid_to=NOW - timedelta(seconds=1),
        ),
        POLICY,
        NOW,
    )

    assert stale.active is False
    assert stale.evidence_kind == "stale"

    incomplete = _observation(
        HazardType.FROST,
        {"current_temperature": Measurement(1)},
    )
    with pytest.raises(ValueError, match="forecast_min_temperature"):
        evaluate_observation(incomplete, POLICY, NOW)
