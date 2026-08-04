"""Open-Meteo/CAMS air-quality model adapter."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from components.external_apis.core.api_component import ExternalApiComponent
from components.external_apis.core.models import ExternalObservation, HazardType, Measurement, parse_datetime
from components.external_apis.core.registry import register_api_component


@register_api_component
class OpenMeteoAirQualityApiComponent(ExternalApiComponent):
    """Normalize European AQI model values separately from GIOŚ measurements."""

    component_name = "OpenMeteoAirQualityApiComponent"
    _FIELDS = (
        "european_aqi",
        "european_aqi_pm2_5",
        "european_aqi_pm10",
        "european_aqi_nitrogen_dioxide",
        "european_aqi_ozone",
        "european_aqi_sulphur_dioxide",
        "pm2_5",
        "pm10",
        "nitrogen_dioxide",
        "ozone",
        "sulphur_dioxide",
    )

    def fetch_payload(self) -> Any:
        horizon = int(self.provider_config.get("forecast_horizon_hours", 12))
        return self.http_client.get_json(
            self.provider_config["base_url"],
            params={
                "latitude": self.site_config["latitude"],
                "longitude": self.site_config["longitude"],
                "timezone": self.site_config["timezone"],
                "forecast_hours": horizon,
                "current": ",".join(self._FIELDS),
                "hourly": ",".join(self._FIELDS),
            },
            timeout_seconds=self.request_timeout_seconds,
        )

    def normalize(self, payload: Any, retrieved_at: datetime) -> tuple[ExternalObservation, ...]:
        if not isinstance(payload, dict):
            raise ValueError("Open-Meteo AQ payload must be a mapping")
        current = payload.get("current")
        hourly = payload.get("hourly")
        if not isinstance(current, dict) or not isinstance(hourly, dict):
            raise ValueError("Open-Meteo AQ current/hourly sections are required")
        observed_at = parse_datetime(current.get("time"), default=retrieved_at)
        horizon = int(self.provider_config.get("forecast_horizon_hours", 12))
        values: dict[str, Measurement] = {}
        for field in self._FIELDS:
            values[f"current_{field}"] = Measurement(self._number(current, field), self._unit(field))
            values[f"forecast_max_{field}"] = Measurement(max(self._numbers(hourly, field, horizon)), self._unit(field))
        values["forecast"] = Measurement(True)
        times = hourly.get("time")
        valid_to = retrieved_at + timedelta(hours=horizon)
        if isinstance(times, list) and times:
            valid_to = parse_datetime(times[min(len(times), horizon) - 1], default=valid_to) + timedelta(hours=1)
        return (
            ExternalObservation(
                provider=self.component_name,
                observation_id="cams_european_aqi",
                hazard_type=HazardType.OUTDOOR_AIR_POLLUTION,
                provider_level=None,
                values=values,
                observed_at=observed_at,
                valid_from=retrieved_at,
                valid_to=valid_to,
                retrieved_at=retrieved_at,
                source_reference=self.provider_config["base_url"],
            ),
        )

    @staticmethod
    def _number(section: dict[str, Any], name: str) -> float:
        try:
            return float(section[name])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid Open-Meteo AQ current.{name}") from exc

    @classmethod
    def _numbers(cls, section: dict[str, Any], name: str, limit: int) -> list[float]:
        raw = section.get(name)
        if not isinstance(raw, list) or not raw:
            raise ValueError(f"Open-Meteo AQ hourly.{name} is required")
        try:
            values = [float(value) for value in raw[:limit] if value is not None]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid Open-Meteo AQ hourly.{name}") from exc
        if not values:
            raise ValueError(f"Open-Meteo AQ hourly.{name} has no values")
        return values

    @staticmethod
    def _unit(field: str) -> str:
        return "EAQI" if field.startswith("european_aqi") else "µg/m³"
