"""Open-Meteo weather adapter."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from components.external_apis.core.api_component import ExternalApiComponent
from components.external_apis.core.models import (
    ExternalObservation,
    HazardType,
    Measurement,
    parse_datetime,
)
from components.external_apis.core.registry import register_api_component


@register_api_component
class OpenMeteoWeatherApiComponent(ExternalApiComponent):
    """Fetch current and 12-hour point weather observations and forecasts."""

    component_name = "OpenMeteoWeatherApiComponent"

    def fetch_payload(self) -> Any:
        return self.http_client.get_json(
            self.provider_config["base_url"],
            params={
                "latitude": self.site_config["latitude"],
                "longitude": self.site_config["longitude"],
                "timezone": self.site_config["timezone"],
                "forecast_hours": int(self.provider_config.get("forecast_horizon_hours", 12)),
                "wind_speed_unit": "ms",
                "current": ",".join(
                    (
                        "temperature_2m",
                        "apparent_temperature",
                        "precipitation",
                        "rain",
                        "weather_code",
                        "wind_speed_10m",
                        "wind_gusts_10m",
                    )
                ),
                "hourly": ",".join(
                    (
                        "temperature_2m",
                        "precipitation_probability",
                        "precipitation",
                        "rain",
                        "weather_code",
                        "wind_speed_10m",
                        "wind_gusts_10m",
                    )
                ),
            },
            timeout_seconds=self.request_timeout_seconds,
        )

    def normalize(
        self, payload: Any, retrieved_at: datetime
    ) -> tuple[ExternalObservation, ...]:
        if not isinstance(payload, dict):
            raise ValueError("Open-Meteo weather payload must be a mapping")
        current = payload.get("current")
        hourly = payload.get("hourly")
        current_units = payload.get("current_units", {})
        if not isinstance(current, dict) or not isinstance(hourly, dict):
            raise ValueError("Open-Meteo weather current/hourly sections are required")
        if current_units.get("temperature_2m") not in {"°C", "C"}:
            raise ValueError("Open-Meteo weather temperature unit must be Celsius")
        if current_units.get("wind_gusts_10m") not in {"m/s", "ms"}:
            raise ValueError("Open-Meteo weather wind unit must be m/s")

        observed_at = parse_datetime(current.get("time"), default=retrieved_at)
        horizon = int(self.provider_config.get("forecast_horizon_hours", 12))
        valid_to = retrieved_at + timedelta(hours=horizon)
        times = self._series(hourly, "time")[:horizon]
        if times:
            valid_to = parse_datetime(times[-1], default=valid_to) + timedelta(hours=1)

        temperatures = self._numbers(hourly, "temperature_2m", horizon)
        gusts = self._numbers(hourly, "wind_gusts_10m", horizon)
        speeds = self._numbers(hourly, "wind_speed_10m", horizon)
        precip = self._numbers(hourly, "precipitation", horizon)
        rain = self._numbers(hourly, "rain", horizon)
        probability = self._numbers(hourly, "precipitation_probability", horizon)
        codes = self._numbers(hourly, "weather_code", horizon)

        common = {
            "provider": self.component_name,
            "provider_level": None,
            "observed_at": observed_at,
            "valid_from": retrieved_at,
            "valid_to": valid_to,
            "retrieved_at": retrieved_at,
            "source_reference": self.provider_config["base_url"],
        }
        return (
            ExternalObservation(
                observation_id="point_frost",
                hazard_type=HazardType.FROST,
                values={
                    "current_temperature": Measurement(self._number(current, "temperature_2m"), "°C"),
                    "forecast_min_temperature": Measurement(min(temperatures), "°C"),
                    "forecast": Measurement(True),
                },
                **common,
            ),
            ExternalObservation(
                observation_id="point_wind",
                hazard_type=HazardType.WIND,
                values={
                    "current_wind_speed": Measurement(self._number(current, "wind_speed_10m"), "m/s"),
                    "current_wind_gust": Measurement(self._number(current, "wind_gusts_10m"), "m/s"),
                    "forecast_max_wind_speed": Measurement(max(speeds), "m/s"),
                    "forecast_max_wind_gust": Measurement(max(gusts), "m/s"),
                    "forecast": Measurement(True),
                },
                **common,
            ),
            ExternalObservation(
                observation_id="point_rain",
                hazard_type=HazardType.RAIN,
                values={
                    "current_precipitation": Measurement(self._number(current, "precipitation"), "mm"),
                    "current_rain": Measurement(self._number(current, "rain"), "mm"),
                    "forecast_max_precipitation": Measurement(max(precip), "mm"),
                    "forecast_max_rain": Measurement(max(rain), "mm"),
                    "forecast_max_probability": Measurement(max(probability), "%"),
                    "forecast": Measurement(True),
                },
                **common,
            ),
            ExternalObservation(
                observation_id="point_storm",
                hazard_type=HazardType.STORM,
                values={
                    "current_weather_code": Measurement(int(self._number(current, "weather_code")), "wmo_code"),
                    "forecast_weather_codes": Measurement(",".join(str(int(code)) for code in codes), "wmo_code"),
                    "forecast": Measurement(True),
                },
                **common,
            ),
        )

    @staticmethod
    def _series(section: dict[str, Any], name: str) -> list[Any]:
        values = section.get(name)
        if not isinstance(values, list) or not values:
            raise ValueError(f"Open-Meteo weather hourly.{name} is required")
        return values

    @classmethod
    def _numbers(cls, section: dict[str, Any], name: str, limit: int) -> list[float]:
        values = cls._series(section, name)[:limit]
        try:
            return [float(value) for value in values if value is not None]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid Open-Meteo weather hourly.{name}") from exc

    @staticmethod
    def _number(section: dict[str, Any], name: str) -> float:
        try:
            return float(section[name])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid Open-Meteo weather current.{name}") from exc
