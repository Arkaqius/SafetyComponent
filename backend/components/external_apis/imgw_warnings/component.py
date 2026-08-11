"""Official IMGW meteorological warning adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from components.external_apis.core.api_component import ExternalApiComponent
from components.external_apis.core.http_json_client import HttpJsonError
from components.external_apis.core.models import ExternalObservation, HazardType, Measurement, parse_datetime
from components.external_apis.core.registry import register_api_component


@register_api_component
class ImgwWarningsApiComponent(ExternalApiComponent):
    """Normalize official IMGW warnings applicable to configured TERYT areas."""

    component_name = "ImgwWarningsApiComponent"

    def fetch_payload(self) -> Any:
        try:
            return self.http_client.get_json(
                self.provider_config["base_url"],
                timeout_seconds=self.request_timeout_seconds,
            )
        except HttpJsonError as exc:
            if exc.code == "http_404" and exc.payload == {
                "status": False,
                "message": "No products were found",
            }:
                return []
            raise

    def normalize(self, payload: Any, retrieved_at: datetime) -> tuple[ExternalObservation, ...]:
        configured_teryt = {str(code) for code in self.site_config.get("teryt_codes", [])}
        observations: list[ExternalObservation] = []
        for warning in self._current_warnings(payload, retrieved_at):
            regions = tuple(warning["regions"])
            if configured_teryt and not configured_teryt.intersection(regions):
                continue
            event_name = str(warning["event_name"])
            hazard_type = self._hazard_type(event_name)
            if hazard_type is None:
                continue
            observations.append(
                ExternalObservation(
                    provider=self.component_name,
                    observation_id=str(warning["id"]),
                    hazard_type=hazard_type,
                    provider_level=str(warning["degree"]) or None,
                    values={
                        "event_name": Measurement(event_name),
                        "probability": Measurement(str(warning["probability"]), "%"),
                        "content": Measurement(str(warning["content"])),
                        "comment": Measurement(str(warning["comment"])),
                        "office": Measurement(str(warning["office"])),
                    },
                    observed_at=parse_datetime(warning["published_at"]),
                    valid_from=parse_datetime(warning["valid_from"]),
                    valid_to=parse_datetime(warning["valid_to"]),
                    retrieved_at=retrieved_at,
                    region_codes=regions,
                    authority_confirmed=True,
                    source_reference=self.provider_config["base_url"],
                )
            )
        return tuple(observations)

    def build_evidence(
        self,
        payload: Any,
        observations: tuple[ExternalObservation, ...],
    ) -> Mapping[str, Any]:
        """Expose current IMGW warnings applicable to the configured home area."""

        retrieved_at = self.last_attempt_at
        if retrieved_at is None:
            raise ValueError("IMGW retrieval timestamp is missing")
        configured_teryt = {str(code) for code in self.site_config.get("teryt_codes", [])}
        warnings = [
            {**warning, "locally_applicable": True}
            for warning in self._current_warnings(payload, retrieved_at)
            if configured_teryt.intersection(warning["regions"])
        ]
        return {
            "observation_count": len(observations),
            "warning_count": len(warnings),
            "warnings": warnings,
        }

    def _current_warnings(
        self,
        payload: Any,
        retrieved_at: datetime,
    ) -> list[dict[str, Any]]:
        if not isinstance(payload, list):
            raise ValueError("IMGW warnings payload must be a list")
        warnings: list[dict[str, Any]] = []
        for raw_warning in payload:
            if not isinstance(raw_warning, dict):
                raise ValueError("IMGW warning must be a mapping")
            warning_id = self._text(raw_warning.get("id"), limit=200)
            if not warning_id:
                raise ValueError("IMGW warning id is required")
            valid_from = parse_datetime(raw_warning.get("obowiazuje_od"), default=retrieved_at)
            valid_to = parse_datetime(raw_warning.get("obowiazuje_do"), default=retrieved_at)
            if valid_to < retrieved_at:
                continue
            warnings.append(
                {
                    "id": warning_id,
                    "event_name": self._text(raw_warning.get("nazwa_zdarzenia"), limit=200),
                    "degree": self._text(raw_warning.get("stopien"), limit=50),
                    "probability": self._text(raw_warning.get("prawdopodobienstwo"), limit=50),
                    "valid_from": valid_from.isoformat(),
                    "valid_to": valid_to.isoformat(),
                    "published_at": parse_datetime(raw_warning.get("opublikowano"), default=retrieved_at).isoformat(),
                    "regions": [str(code) for code in raw_warning.get("teryt", []) if code is not None],
                    "content": self._text(raw_warning.get("tresc"), limit=3000),
                    "comment": self._text(raw_warning.get("komentarz"), limit=1000),
                    "office": self._text(raw_warning.get("biuro"), limit=200),
                }
            )
        return warnings

    @staticmethod
    def _hazard_type(name: str) -> HazardType | None:
        normalized = name.casefold()
        if "burz" in normalized:
            return HazardType.STORM
        if "wiatr" in normalized:
            return HazardType.WIND
        if "mroz" in normalized or "mróz" in normalized or "przymro" in normalized:
            return HazardType.FROST
        if "deszcz" in normalized or "opad" in normalized:
            return HazardType.RAIN
        return None

    @staticmethod
    def _text(value: Any, *, limit: int) -> str:
        return " ".join(str(value or "").replace("<", " ").replace(">", " ").split())[:limit]
