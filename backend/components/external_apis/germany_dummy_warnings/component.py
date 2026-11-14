"""Offline German scenarios for the isolated synthetic preview boundary."""

from datetime import datetime, timedelta
from typing import Any, Callable, Mapping

from components.external_apis.core.api_component import ExternalApiComponent
from components.external_apis.core.models import (
    ApiResult,
    ExternalObservation,
    HazardType,
    Measurement,
    ProviderCapability,
    ProviderHealth,
    ProviderHealthState,
    utc_now,
)
from components.external_apis.core.registry import register_api_component

from .schema import GermanyDummyConfig, GermanyDummyParameters


@register_api_component
class GermanyDummyWarningsApiComponent(ExternalApiComponent):
    """Produce explicit test data without pretending to be a real authority."""

    component_name = "GermanyDummyWarningsApiComponent"
    config_model = GermanyDummyConfig
    parameter_model = GermanyDummyParameters
    required_when_selected = frozenset({"region_code"})
    capability = ProviderCapability.OFFICIAL_WARNINGS
    hazards = frozenset({HazardType.WIND})
    countries = frozenset({"DE"})
    data_kind = "synthetic"
    transport_kind = "none"
    display_name = "Niemcy — źródło testowe"
    description = (
        "Dane syntetyczne. Nie są ostrzeżeniami urzędowymi i nie sterują domem."
    )

    def __init__(
        self,
        *,
        provider_config: Mapping[str, Any],
        site_config: Mapping[str, Any],
        parameters: Mapping[str, Any],
        http_client: None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if http_client is not None:
            raise ValueError("Synthetic source must not receive an HTTP client")
        super().__init__(
            provider_config=provider_config,
            site_config=site_config,
            parameters=parameters,
            http_client=None,
        )
        self._clock = clock
        self._selected_parameters = GermanyDummyParameters.model_validate(parameters)

    def fetch_payload(self) -> Any:
        """Return a local scenario name, never an external payload."""
        return self._selected_parameters.scenario

    def normalize(
        self, payload: Any, retrieved_at: datetime
    ) -> tuple[ExternalObservation, ...]:
        """Describe a synthetic wind event only for event-bearing scenarios."""
        if payload not in {"warning", "stale"}:
            return ()
        event_time = (
            retrieved_at - timedelta(seconds=181)
            if payload == "stale"
            else retrieved_at
        )
        return (
            ExternalObservation(
                provider=self.component_name,
                observation_id="synthetic-wind",
                hazard_type=HazardType.WIND,
                provider_level="test",
                values={"event_name": Measurement("Testowe ostrzeżenie przed wiatrem")},
                observed_at=event_time,
                valid_from=event_time,
                valid_to=event_time + timedelta(seconds=120),
                retrieved_at=retrieved_at,
                region_codes=(self._selected_parameters.region_code or "",),
                authority_confirmed=False,
                source_reference="synthetic://germany-dummy",
            ),
        )

    def poll(self) -> ApiResult:
        """Return deterministic preview health without network, retries or sleeps."""
        now = self._clock()
        scenario = self._selected_parameters.scenario
        self.last_attempt_at = now
        state = {
            "unavailable": ProviderHealthState.UNAVAILABLE,
            "stale": ProviderHealthState.STALE,
        }.get(scenario, ProviderHealthState.OK)
        last_success = (
            None
            if scenario == "unavailable"
            else now - timedelta(seconds=181)
            if scenario == "stale"
            else now
        )
        self.last_success_at = last_success
        self.consecutive_failures = 1 if scenario == "unavailable" else 0
        observations = self.normalize(scenario, now)
        self.validate_observations(observations)
        health = ProviderHealth(
            self.component_name,
            state,
            now,
            last_success,
            self.consecutive_failures,
            f"synthetic_{scenario}",
            180,
        )
        return ApiResult(
            self.component_name,
            observations,
            health,
            {"scenario": scenario, "data_kind": "synthetic"},
        )
