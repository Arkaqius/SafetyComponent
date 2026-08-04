"""GIOŚ station measurement and Polish air-quality index adapter."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from components.external_apis.core.api_component import ExternalApiComponent
from components.external_apis.core.models import ExternalObservation, HazardType, Measurement, parse_datetime
from components.external_apis.core.registry import register_api_component


@register_api_component
class GiosAirQualityApiComponent(ExternalApiComponent):
    """Return named GIOŚ index data without translating it to European AQI."""

    component_name = "GiosAirQualityApiComponent"
    _ACCEPT = {"Accept": "application/ld+json"}

    def fetch_payload(self) -> Any:
        last_error: Exception | None = None
        for station_id in self.provider_config["station_ids"]:
            try:
                index = self.http_client.get_json(
                    f"{self.provider_config['base_url']}/v1/rest/aqindex/getIndex/{station_id}",
                    headers=self._ACCEPT,
                    timeout_seconds=self.request_timeout_seconds,
                )
                sensors = self.http_client.get_json(
                    f"{self.provider_config['base_url']}/v1/rest/station/sensors/{station_id}",
                    headers=self._ACCEPT,
                    timeout_seconds=self.request_timeout_seconds,
                )
                measurements: list[dict[str, Any]] = []
                sensor_items = self._items(sensors)
                for sensor in sensor_items:
                    sensor_id = self._lookup(sensor, "Identyfikator stanowiska", "id")
                    parameter = self._lookup(sensor, "Wskaźnik - kod", "paramCode")
                    if sensor_id is None or parameter is None:
                        continue
                    try:
                        data = self.http_client.get_json(
                            f"{self.provider_config['base_url']}/v1/rest/data/getData/{sensor_id}",
                            headers=self._ACCEPT,
                            timeout_seconds=self.request_timeout_seconds,
                        )
                    except Exception:
                        continue
                    measurements.append(
                        {"sensor_id": sensor_id, "parameter": parameter, "data": data}
                    )
                return {
                    "station_id": station_id,
                    "index": index,
                    "measurements": measurements,
                }
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise ValueError("No GIOŚ station IDs configured")

    def normalize(self, payload: Any, retrieved_at: datetime) -> tuple[ExternalObservation, ...]:
        if not isinstance(payload, dict) or not isinstance(payload.get("index"), dict):
            raise ValueError("GIOŚ composite payload is invalid")
        index = payload["index"]
        station_id = str(payload["station_id"])
        category = self._lookup(index, "Nazwa kategorii indeksu", "stIndexStatus", default="Brak indeksu")
        index_value = self._lookup(index, "Wartość indeksu", "stIndexLevel", default=-1)
        calculated_at = self._lookup(index, "Data wykonania obliczeń indeksu", "stCalcDate")
        observed_at = parse_datetime(calculated_at, default=retrieved_at)

        values: dict[str, Measurement] = {
            "station_id": Measurement(station_id),
            "polish_index_name": Measurement(str(category)),
            "polish_index_level": Measurement(self._index_level(index_value, category)),
        }
        for pollutant, aliases in {
            "pm10_index": ("Wartość indeksu dla wskaźnika PM10", "pm10IndexLevel"),
            "pm25_index": ("Wartość indeksu dla wskaźnika PM2.5", "pm25IndexLevel"),
            "no2_index": ("Wartość indeksu dla wskaźnika NO2", "no2IndexLevel"),
            "o3_index": ("Wartość indeksu dla wskaźnika O3", "o3IndexLevel"),
            "so2_index": ("Wartość indeksu dla wskaźnika SO2", "so2IndexLevel"),
        }.items():
            raw = self._lookup(index, *aliases)
            if raw is not None:
                values[pollutant] = Measurement(self._index_level(raw, raw))

        measurements = payload.get("measurements", [])
        if not isinstance(measurements, list):
            raise ValueError("GIOŚ measurements must be a list")
        for measurement in measurements:
            if not isinstance(measurement, dict):
                continue
            current = self._latest_measurement(measurement.get("data"))
            if current is None:
                continue
            parameter = str(measurement.get("parameter", "unknown")).lower()
            values[f"measurement_{parameter}"] = Measurement(current[1], "µg/m³")
            values[f"measurement_{parameter}_time"] = Measurement(current[0].isoformat())

        return (
            ExternalObservation(
                provider=self.component_name,
                observation_id=f"station_{station_id}",
                hazard_type=HazardType.OUTDOOR_AIR_POLLUTION,
                provider_level=str(category),
                values=values,
                observed_at=observed_at,
                valid_from=observed_at,
                valid_to=observed_at + timedelta(seconds=self.stale_after_seconds),
                retrieved_at=retrieved_at,
                source_reference=f"{self.provider_config['base_url']}/v1/rest/aqindex/getIndex/{station_id}",
            ),
        )

    @staticmethod
    def _items(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for value in payload.values():
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        raise ValueError("GIOŚ sensor payload has no item list")

    @staticmethod
    def _lookup(mapping: dict[str, Any], *names: str, default: Any = None) -> Any:
        normalized = {str(key).casefold(): value for key, value in mapping.items()}
        for name in names:
            if name.casefold() in normalized:
                return normalized[name.casefold()]
        return default

    @classmethod
    def _index_level(cls, value: Any, category: Any) -> int:
        if isinstance(value, dict):
            nested = cls._lookup(value, "Wartość indeksu", "id", "indexLevel")
            if nested is not None:
                value = nested
            else:
                category = cls._lookup(value, "Nazwa kategorii indeksu", "indexLevelName", default=category)
        try:
            return int(value)
        except (TypeError, ValueError):
            normalized = str(category or "").casefold()
            categories = {
                "bardzo dobry": 0,
                "dobry": 1,
                "umiarkowany": 2,
                "dostateczny": 3,
                "zły": 4,
                "zly": 4,
                "bardzo zły": 5,
                "bardzo zly": 5,
            }
            return categories.get(normalized, -1)

    @classmethod
    def _latest_measurement(cls, payload: Any) -> tuple[datetime, float] | None:
        candidates: list[Any] = []
        if isinstance(payload, list):
            candidates = payload
        elif isinstance(payload, dict):
            for value in payload.values():
                if isinstance(value, list):
                    candidates = value
                    break
        for item in candidates:
            if not isinstance(item, dict):
                continue
            raw_value = cls._lookup(item, "Wartość", "value")
            raw_date = cls._lookup(item, "Data", "date")
            if raw_value is None or raw_date is None:
                continue
            try:
                return parse_datetime(raw_date), float(raw_value)
            except (TypeError, ValueError):
                continue
        return None
