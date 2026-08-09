"""Base lifecycle and health handling for one provider adapter."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Mapping

from .http_json_client import HttpJsonClient, HttpJsonError
from .models import (
    ApiResult,
    ExternalObservation,
    ProviderHealth,
    ProviderHealthState,
    utc_now,
)


class ExternalApiComponent(ABC):
    """Provider adapter contract; deliberately separate from SafetyComponent."""

    component_name = ""

    def __init__(
        self,
        *,
        provider_config: Mapping[str, Any],
        site_config: Mapping[str, Any],
        http_client: HttpJsonClient,
    ) -> None:
        self.provider_config = dict(provider_config)
        self.site_config = dict(site_config)
        self.http_client = http_client
        self.poll_interval_seconds = int(self.provider_config["poll_interval_seconds"])
        self.request_timeout_seconds = float(self.provider_config["request_timeout_seconds"])
        self.max_retries = int(self.provider_config.get("max_retries", 0))
        self.stale_after_seconds = int(self.provider_config["stale_after_seconds"])
        self.last_attempt_at: datetime | None = None
        self.last_success_at: datetime | None = None
        self.consecutive_failures = 0
        self.last_valid_result: ApiResult | None = None

    def poll(self) -> ApiResult:
        """Fetch, normalize, cache, and diagnose one provider snapshot."""

        self.last_attempt_at = utc_now()
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                payload = self.fetch_payload()
                observations = tuple(self.normalize(payload, self.last_attempt_at))
                if observations and all(
                    observation.valid_to < self.last_attempt_at
                    for observation in observations
                ):
                    self.consecutive_failures += 1
                    cached = (
                        self.last_valid_result.observations
                        if self.last_valid_result
                        else ()
                    )
                    cached_evidence = (
                        dict(self.last_valid_result.evidence)
                        if self.last_valid_result
                        else {}
                    )
                    return ApiResult(
                        provider=self.component_name,
                        observations=cached,
                        health=self._health(
                            ProviderHealthState.STALE,
                            detail_code="stale_source_time",
                        ),
                        evidence={**cached_evidence, "cache_preserved": bool(cached)},
                    )
                self.last_success_at = utc_now()
                self.consecutive_failures = 0
                result = ApiResult(
                    provider=self.component_name,
                    observations=observations,
                    health=self._health(ProviderHealthState.OK),
                    evidence=self.build_evidence(payload, observations),
                )
                self.last_valid_result = result
                return result
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(min(2.0, 0.25 * (2**attempt)))

        self.consecutive_failures += 1
        detail_code = (
            last_error.code if isinstance(last_error, HttpJsonError) else "schema_error"
        )
        state = (
            ProviderHealthState.SCHEMA_ERROR
            if detail_code in {
                "malformed_json",
                "payload_too_deep",
                "string_too_long",
                "list_too_long",
                "mapping_too_large",
                "schema_error",
            }
            else ProviderHealthState.UNAVAILABLE
        )
        cached = self.last_valid_result.observations if self.last_valid_result else ()
        cached_evidence = dict(self.last_valid_result.evidence) if self.last_valid_result else {}
        return ApiResult(
            provider=self.component_name,
            observations=cached,
            health=self._health(state, detail_code=detail_code),
            evidence={**cached_evidence, "cache_preserved": bool(cached)},
        )

    def build_evidence(
        self,
        payload: Any,
        observations: tuple[ExternalObservation, ...],
    ) -> Mapping[str, Any]:
        """Build bounded provider evidence exposed with the health snapshot."""

        return {"observation_count": len(observations)}

    def _health(
        self,
        state: ProviderHealthState,
        *,
        detail_code: str | None = None,
    ) -> ProviderHealth:
        return ProviderHealth(
            provider=self.component_name,
            state=state,
            last_attempt_at=self.last_attempt_at,
            last_success_at=self.last_success_at,
            consecutive_failures=self.consecutive_failures,
            detail_code=detail_code,
            stale_after_seconds=self.stale_after_seconds,
        )

    @abstractmethod
    def fetch_payload(self) -> Any:
        """Fetch provider-specific payload data."""

    @abstractmethod
    def normalize(
        self, payload: Any, retrieved_at: datetime
    ) -> tuple[ExternalObservation, ...] | list[ExternalObservation]:
        """Validate and normalize a provider-specific payload."""
