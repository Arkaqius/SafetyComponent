"""Pure household policy for normalized external observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from components.external_apis.core.models import ExternalObservation, HazardType


@dataclass(frozen=True)
class HazardAssessment:
    """One policy assessment with notification-ready evidence."""

    active: bool
    severity: str
    observed_value: str
    threshold: str
    evidence_kind: str
    inhibits_opening_advice: bool = False


def evaluate_observation(
    observation: ExternalObservation,
    policy: Mapping[str, Any],
    now: datetime,
) -> HazardAssessment:
    """Evaluate one fresh normalized observation against household policy."""

    if observation.valid_to < now:
        return HazardAssessment(False, "unknown", "stale", "fresh data", "stale")
    values = observation.values
    if observation.authority_confirmed and observation.provider == "ImgwWarningsApiComponent":
        return HazardAssessment(
            True,
            "warning",
            _measurement(values, "event_name", observation.provider_level or "IMGW warning"),
            f"IMGW degree {observation.provider_level or 'unspecified'}",
            "official_warning",
            observation.hazard_type in {HazardType.WIND, HazardType.STORM},
        )
    if observation.hazard_type == HazardType.FROST:
        current = _number(values, "current_temperature")
        forecast = _number(values, "forecast_min_temperature")
        measured = min(current, forecast)
        weather = policy["weather"]
        active = measured <= float(weather["frost_watch_c"])
        severity = "warning" if measured <= float(weather["frost_warning_c"]) else "watch"
        return HazardAssessment(active, severity, f"{measured:.1f} °C", f"≤ {weather['frost_watch_c']} °C", _evidence_kind(current, forecast, measured))
    if observation.hazard_type == HazardType.WIND:
        current = _number(values, "current_wind_gust")
        forecast = _number(values, "forecast_max_wind_gust")
        measured = max(current, forecast)
        weather = policy["weather"]
        active = measured >= float(weather["gust_watch_m_s"])
        severity = "warning" if measured >= float(weather["gust_warning_m_s"]) else "watch"
        return HazardAssessment(active, severity, f"{measured:.1f} m/s", f"≥ {weather['gust_watch_m_s']} m/s", _evidence_kind(current, forecast, measured), active)
    if observation.hazard_type == HazardType.RAIN:
        current = max(_number(values, "current_precipitation"), _number(values, "current_rain"))
        forecast = max(_number(values, "forecast_max_precipitation"), _number(values, "forecast_max_rain"))
        measured = max(current, forecast)
        threshold = float(policy["weather"]["precipitation_warning_mm_h"])
        return HazardAssessment(measured >= threshold, "warning", f"{measured:.1f} mm/h", f"≥ {threshold} mm/h", _evidence_kind(current, forecast, measured))
    if observation.hazard_type == HazardType.STORM:
        current_code = int(_number(values, "current_weather_code"))
        forecast_codes = {
            int(value) for value in _measurement(values, "forecast_weather_codes", "").split(",") if value
        }
        active = current_code in {95, 96, 99} or bool(forecast_codes.intersection({95, 96, 99}))
        kind = "current" if current_code in {95, 96, 99} else "forecast"
        return HazardAssessment(active, "warning", f"WMO {current_code if kind == 'current' else sorted(forecast_codes)}", "WMO 95/96/99", kind, active)
    if observation.hazard_type == HazardType.OUTDOOR_AIR_POLLUTION:
        aq_policy = policy["outdoor_air_quality"]
        current = _number(values, "current_european_aqi")
        threshold = float(aq_policy["warning_at"])
        return HazardAssessment(current >= threshold, "warning", f"EAQI {current:.0f}", f"EAQI ≥ {threshold:.0f}", "current", current >= threshold)
    if observation.hazard_type == HazardType.IONIZING_RADIATION:
        active = observation.authority_confirmed
        return HazardAssessment(active, "severe", _measurement(values, "status", "official alert"), "official PAA message", "official_warning", active)
    return HazardAssessment(False, "unknown", "raw measurement", "corroborated anomaly policy", "measurement")


def _measurement(values: Mapping[str, Any], name: str, default: str) -> str:
    measurement = values.get(name)
    return str(getattr(measurement, "value", default))


def _number(values: Mapping[str, Any], name: str) -> float:
    measurement = values.get(name)
    try:
        return float(getattr(measurement, "value"))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"Missing normalized measurement {name}") from exc


def _evidence_kind(current: float, forecast: float, selected: float) -> str:
    return "current" if selected == current else "forecast"
