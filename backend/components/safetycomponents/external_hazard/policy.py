"""Pure household policy for normalized external observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any, Mapping

from components.external_apis.core.models import ExternalObservation, HazardType, WarningUrgency


@dataclass(frozen=True)
class HazardAssessment:
    """One policy assessment with notification-ready evidence."""

    active: bool
    severity: str
    observed_value: str
    threshold: str
    evidence_kind: str
    inhibits_opening_advice: bool = False
    immediate_exposure: bool = False


def evaluate_observation(
    observation: ExternalObservation,
    policy: Mapping[str, Any],
    now: datetime,
    *,
    previously_active: bool = False,
) -> HazardAssessment:
    """Evaluate one fresh normalized observation against household policy."""

    if observation.valid_to < now:
        return HazardAssessment(False, "unknown", "stale", "fresh data", "stale")
    values = observation.values
    if observation.authority_confirmed:
        return HazardAssessment(
            True,
            "warning",
            _measurement(values, "event_name", "Official weather warning"),
            _measurement(values, "level_label", observation.provider_level or "Official weather warning"),
            "official_warning",
            observation.hazard_type in {HazardType.WIND, HazardType.STORM},
            immediate_exposure=observation.warning_urgency == WarningUrgency.IMMEDIATE,
        )
    if observation.hazard_type == HazardType.FROST:
        current = _number(values, "current_temperature")
        forecast = _number(values, "forecast_min_temperature")
        measured = min(current, forecast)
        weather = policy["weather"]
        threshold = float(weather["frost_watch_c"])
        if previously_active:
            threshold += _hysteresis(weather, "temperature_c")
        active = measured <= threshold
        severity = "warning" if measured <= float(weather["frost_warning_c"]) else "watch"
        return HazardAssessment(active, severity, f"{measured:.1f} °C", f"≤ {threshold} °C", _evidence_kind(current, forecast, measured))
    if observation.hazard_type == HazardType.WIND:
        current = _number(values, "current_wind_gust")
        forecast = _number(values, "forecast_max_wind_gust")
        measured = max(current, forecast)
        weather = policy["weather"]
        threshold = float(weather["gust_watch_m_s"])
        if previously_active:
            threshold -= _hysteresis(weather, "gust_m_s")
        active = measured >= threshold
        severity = "warning" if measured >= float(weather["gust_warning_m_s"]) else "watch"
        return HazardAssessment(active, severity, f"{measured:.1f} m/s", f"≥ {threshold} m/s", _evidence_kind(current, forecast, measured), active)
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
    return HazardAssessment(False, "unknown", "unsupported observation", "supported hazard type", "unknown")


def _measurement(values: Mapping[str, Any], name: str, default: str) -> str:
    measurement = values.get(name)
    return str(getattr(measurement, "value", default))


def _number(values: Mapping[str, Any], name: str) -> float:
    measurement = values.get(name)
    try:
        value = float(measurement.value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"Missing normalized measurement {name}") from exc
    if not isfinite(value):
        raise ValueError(f"Non-finite normalized measurement {name}")
    return value


def _hysteresis(weather: Mapping[str, Any], name: str) -> float:
    value = float(weather.get("hysteresis", {}).get(name, 0))
    return max(0.0, value) if isfinite(value) else 0.0


def _evidence_kind(current: float, forecast: float, selected: float) -> str:
    return "current" if selected == current else "forecast"
