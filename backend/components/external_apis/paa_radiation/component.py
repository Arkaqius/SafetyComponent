"""Official PAA radiological message and station measurement adapter."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Iterable

from components.external_apis.core.api_component import ExternalApiComponent
from components.external_apis.core.models import ExternalObservation, HazardType, Measurement, parse_datetime
from components.external_apis.core.registry import register_api_component


@register_api_component
class PaaRadiationApiComponent(ExternalApiComponent):
    """Preserve official messages and raw dose-rate measurements separately."""

    component_name = "PaaRadiationApiComponent"

    def fetch_payload(self) -> Any:
        language = self.provider_config.get("language", "pl")
        message_path = str(self.provider_config["radiation_message_path"]).format(language=language)
        measurement_path = str(self.provider_config["measurement_path"]).format(language=language)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://monitoring.paa.gov.pl",
            "Referer": "https://monitoring.paa.gov.pl/maps-portal/",
        }
        return {
            "messages": self.http_client.get_json(
                f"{self.provider_config['base_url']}{message_path}",
                headers=headers,
                timeout_seconds=self.request_timeout_seconds,
            ),
            "measurements": self.http_client.get_json(
                f"{self.provider_config['base_url']}{measurement_path}",
                headers=headers,
                timeout_seconds=self.request_timeout_seconds,
            ),
        }

    def normalize(self, payload: Any, retrieved_at: datetime) -> tuple[ExternalObservation, ...]:
        if not isinstance(payload, dict):
            raise ValueError("PAA composite payload must be a mapping")
        observations = list(self._normalize_messages(payload.get("messages"), retrieved_at))
        observations.extend(self._normalize_measurements(payload.get("measurements"), retrieved_at))
        return tuple(observations)

    def _normalize_messages(
        self, payload: Any, retrieved_at: datetime
    ) -> Iterable[ExternalObservation]:
        for index, item in enumerate(self._records(payload)):
            active = self._official_alert_active(item)
            if not active:
                continue
            message = self._text(self._lookup(item, "message", "content", "text", "tresc", "komunikat"), 4000)
            status = self._text(self._lookup(item, "status", "level", "state", "rodzaj"), 100)
            published = self._safe_datetime(
                self._lookup(item, "publishedAt", "publicationDate", "published", "dataPublikacji"),
                retrieved_at,
            )
            valid_from = self._safe_datetime(
                self._lookup(item, "validFrom", "startDate", "obowiazujeOd"),
                published,
            )
            valid_to = self._safe_datetime(
                self._lookup(item, "validTo", "endDate", "obowiazujeDo"),
                retrieved_at + timedelta(seconds=self.stale_after_seconds),
            )
            if valid_to < retrieved_at:
                continue
            observation_id = self._text(
                self._lookup(item, "id", "messageId", "identifier"), 100
            ) or f"official_message_{index}"
            yield ExternalObservation(
                provider=self.component_name,
                observation_id=observation_id,
                hazard_type=HazardType.IONIZING_RADIATION,
                provider_level=status or "official_alert",
                values={
                    "message": Measurement(message),
                    "status": Measurement(status or "official_alert"),
                    "result_type": Measurement("official_message"),
                },
                observed_at=published,
                valid_from=valid_from,
                valid_to=valid_to,
                retrieved_at=retrieved_at,
                authority_confirmed=True,
                source_reference="https://monitoring.paa.gov.pl/maps-portal/",
            )

    def _normalize_measurements(
        self, payload: Any, retrieved_at: datetime
    ) -> Iterable[ExternalObservation]:
        configured = {str(value) for value in self.provider_config.get("station_ids", [])}
        for index, item in enumerate(self._records(payload)):
            station_id = self._text(
                self._lookup(item, "stationId", "station_id", "id", "code"), 100
            ) or f"station_{index}"
            if configured and station_id not in configured:
                continue
            raw_value = self._lookup(item, "value", "doseRate", "measurement", "wartosc")
            raw_unit = self._text(
                self._lookup(item, "unit", "doseRateUnit", "jednostka"), 40
            )
            if raw_value is None or not raw_unit:
                continue
            normalized_value, normalized_unit = self._normalize_dose_rate(raw_value, raw_unit)
            observed_at = self._safe_datetime(
                self._lookup(item, "timestamp", "measurementDate", "date", "dataPomiaru"),
                retrieved_at,
            )
            if observed_at + timedelta(seconds=self.stale_after_seconds) < retrieved_at:
                continue
            location = self._text(
                self._lookup(item, "stationName", "name", "location", "miejscowosc"), 200
            )
            yield ExternalObservation(
                provider=self.component_name,
                observation_id=f"dose_rate_{station_id}",
                hazard_type=HazardType.RADIATION_ANOMALY,
                provider_level=None,
                values={
                    "station_id": Measurement(station_id),
                    "station_location": Measurement(location),
                    "dose_rate": Measurement(normalized_value, normalized_unit),
                    "original_value": Measurement(float(raw_value), raw_unit),
                    "result_type": Measurement("dose_rate_measurement"),
                },
                observed_at=observed_at,
                valid_from=observed_at,
                valid_to=observed_at + timedelta(seconds=self.stale_after_seconds),
                retrieved_at=retrieved_at,
                authority_confirmed=False,
                source_reference="https://monitoring.paa.gov.pl/maps-portal/",
            )

    @classmethod
    def _records(cls, value: Any) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if isinstance(value, list):
            records.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            if any(not isinstance(item, (dict, list)) for item in value.values()):
                records.append(value)
            for item in value.values():
                if isinstance(item, (dict, list)):
                    records.extend(cls._records(item))
        elif value is not None:
            raise ValueError("PAA payload must contain mappings or lists")
        return records

    @classmethod
    def _official_alert_active(cls, item: dict[str, Any]) -> bool:
        explicit = cls._lookup(item, "active", "isActive", "warning", "alarm", "isAlert")
        if isinstance(explicit, bool):
            return explicit
        if isinstance(explicit, (int, float)):
            return explicit > 0
        status = cls._text(cls._lookup(item, "status", "level", "state", "rodzaj"), 100).casefold()
        active_tokens = ("alert", "alarm", "warning", "ostrze", "zagro", "emergency", "awaryj")
        clear_tokens = ("brak", "normal", "clear", "bez zagro", "no alert")
        return bool(status) and any(token in status for token in active_tokens) and not any(
            token in status for token in clear_tokens
        )

    @staticmethod
    def _normalize_dose_rate(value: Any, unit: str) -> tuple[float, str]:
        numeric = float(value)
        compact = re.sub(r"\s+", "", unit).replace("μ", "µ").casefold()
        if compact in {"nsv/h", "nsvh", "nsv·h-1"}:
            return numeric / 1000.0, "µSv/h"
        if compact in {"µsv/h", "usv/h", "µsvh", "usvh", "µsv·h-1"}:
            return numeric, "µSv/h"
        raise ValueError(f"Unsupported PAA dose-rate unit: {unit}")

    @staticmethod
    def _lookup(mapping: dict[str, Any], *names: str) -> Any:
        normalized = {str(key).casefold(): value for key, value in mapping.items()}
        for name in names:
            if name.casefold() in normalized:
                return normalized[name.casefold()]
        return None

    @staticmethod
    def _text(value: Any, limit: int) -> str:
        return " ".join(str(value or "").replace("<", " ").replace(">", " ").split())[:limit]

    @staticmethod
    def _safe_datetime(value: Any, default: datetime) -> datetime:
        try:
            return parse_datetime(value, default=default)
        except ValueError:
            return default
