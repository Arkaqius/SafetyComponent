"""Official IMGW meteorological warning adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from components.external_apis.core.api_component import ExternalApiComponent
from components.external_apis.core.models import ExternalObservation, HazardType, Measurement, parse_datetime
from components.external_apis.core.registry import register_api_component


@register_api_component
class ImgwWarningsApiComponent(ExternalApiComponent):
    """Normalize official IMGW warnings applicable to configured TERYT areas."""

    component_name = "ImgwWarningsApiComponent"

    def fetch_payload(self) -> Any:
        return self.http_client.get_json(
            self.provider_config["base_url"],
            timeout_seconds=self.request_timeout_seconds,
        )

    def normalize(self, payload: Any, retrieved_at: datetime) -> tuple[ExternalObservation, ...]:
        if not isinstance(payload, list):
            raise ValueError("IMGW warnings payload must be a list")
        configured_teryt = {str(code) for code in self.site_config.get("teryt_codes", [])}
        observations: list[ExternalObservation] = []
        for warning in payload:
            if not isinstance(warning, dict):
                raise ValueError("IMGW warning must be a mapping")
            regions = tuple(str(code) for code in warning.get("teryt", []) if code is not None)
            if configured_teryt and not configured_teryt.intersection(regions):
                continue
            event_name = self._text(warning.get("nazwa_zdarzenia"), limit=200)
            hazard_type = self._hazard_type(event_name)
            if hazard_type is None:
                continue
            warning_id = self._text(warning.get("id"), limit=200)
            if not warning_id:
                raise ValueError("IMGW warning id is required")
            valid_from = parse_datetime(warning.get("obowiazuje_od"), default=retrieved_at)
            valid_to = parse_datetime(warning.get("obowiazuje_do"), default=retrieved_at)
            if valid_to < retrieved_at:
                continue
            published_at = parse_datetime(warning.get("opublikowano"), default=retrieved_at)
            observations.append(
                ExternalObservation(
                    provider=self.component_name,
                    observation_id=warning_id,
                    hazard_type=hazard_type,
                    provider_level=self._text(warning.get("stopien"), limit=50) or None,
                    values={
                        "event_name": Measurement(event_name),
                        "probability": Measurement(self._text(warning.get("prawdopodobienstwo"), limit=50), "%"),
                        "content": Measurement(self._text(warning.get("tresc"), limit=3000)),
                        "comment": Measurement(self._text(warning.get("komentarz"), limit=1000)),
                        "office": Measurement(self._text(warning.get("biuro"), limit=200)),
                    },
                    observed_at=published_at,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    retrieved_at=retrieved_at,
                    region_codes=regions,
                    authority_confirmed=True,
                    source_reference=self.provider_config["base_url"],
                )
            )
        return tuple(observations)

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
