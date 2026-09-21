"""Open-Meteo current air-quality model adapter."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from components.external_apis.core.api_component import ExternalApiComponent
from components.external_apis.core.models import ExternalObservation, HazardType, Measurement, parse_datetime
from components.external_apis.core.registry import register_api_component


@register_api_component
class OpenMeteoAirQualityApiComponent(ExternalApiComponent):
    """Normalize current European AQI model values for the configured home."""

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
        return self.http_client.get_json(
            self.provider_config["base_url"],
            params={
                "latitude": self.site_config["latitude"],
                "longitude": self.site_config["longitude"],
                "timezone": self.site_config["timezone"],
                "current": ",".join(self._FIELDS),
            },
            timeout_seconds=self.request_timeout_seconds,
        )

    def normalize(self, payload: Any, retrieved_at: datetime) -> tuple[ExternalObservation, ...]:
        if not isinstance(payload, dict):
            raise ValueError("Open-Meteo AQ payload must be a mapping")
        current = payload.get("current")
        if not isinstance(current, dict):
            raise ValueError("Open-Meteo AQ current section is required")
        observed_at = parse_datetime(current.get("time"), default=retrieved_at)
        values: dict[str, Measurement] = {}
        for field in self._FIELDS:
            values[f"current_{field}"] = Measurement(self._number(current, field), self._unit(field))
        return (
            ExternalObservation(
                provider=self.component_name,
                observation_id="cams_european_aqi",
                hazard_type=HazardType.OUTDOOR_AIR_POLLUTION,
                provider_level=None,
                values=values,
                observed_at=observed_at,
                valid_from=observed_at,
                valid_to=observed_at + timedelta(seconds=self.stale_after_seconds),
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

    @staticmethod
    def _unit(field: str) -> str:
        return "EAQI" if field.startswith("european_aqi") else "µg/m³"
