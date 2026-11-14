"""Bundled synthetic German scenarios never use a real warning service."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from components.external_apis.germany_dummy_warnings.component import (
    GermanyDummyWarningsApiComponent,
)
from components.external_apis.germany_dummy_warnings.schema import (
    GermanyDummyParameters,
)
from components.external_apis.core.models import (
    HazardType,
    ProviderCapability,
    ProviderHealthState,
)


@pytest.mark.parametrize(
    "scenario,state,count",
    [
        ("empty", ProviderHealthState.OK, 0),
        ("warning", ProviderHealthState.OK, 1),
        ("unavailable", ProviderHealthState.UNAVAILABLE, 0),
        ("stale", ProviderHealthState.STALE, 1),
    ],
)
def test_dummy_scenarios_are_deterministic_and_non_authoritative(
    scenario, state, count
):
    now = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
    adapter = GermanyDummyWarningsApiComponent(
        provider_config={"poll_interval_seconds": 60, "stale_after_seconds": 180},
        site_config={"country_code": "DE"},
        http_client=None,
        parameters={"region_code": "Berlin_Test-1", "scenario": scenario},
        clock=lambda: now,
    )
    assert adapter.last_attempt_at is None
    assert adapter.http_client is None
    assert adapter.data_kind == "synthetic"
    assert adapter.transport_kind == "none"
    assert adapter.capability == ProviderCapability.OFFICIAL_WARNINGS
    assert adapter.countries == frozenset({"DE"})
    assert adapter.hazards == frozenset({HazardType.WIND})
    result = adapter.poll()
    assert result.health.state == state
    assert len(result.observations) == count
    assert result == adapter.poll()
    assert all(
        not observation.authority_confirmed for observation in result.observations
    )
    assert all(
        observation.provider == adapter.component_name
        for observation in result.observations
    )
    if scenario == "stale":
        assert result.health.last_success_at is not None
        assert (now - result.health.last_success_at).total_seconds() > 180


@pytest.mark.parametrize("region", ["", "-Bad", "x" * 33, "Łódź", "has space"])
def test_dummy_rejects_invalid_synthetic_region(region):
    with pytest.raises(ValidationError):
        GermanyDummyParameters.model_validate({"region_code": region})


def test_dummy_parameters_are_closed_and_scenario_is_not_free_text():
    for parameters in ({"scenario": "live"}, {"base_url": "https://example.invalid"}):
        with pytest.raises(ValidationError):
            GermanyDummyParameters.model_validate(parameters)


@pytest.mark.parametrize("region", ["A", "x" * 32])
def test_dummy_region_boundaries_are_accepted(region):
    assert GermanyDummyParameters.model_validate({"region_code": region}).region_code == region


def test_dummy_cannot_receive_network_transport_and_never_opens_a_socket(monkeypatch):
    import socket

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Synthetic preview attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    for scenario in ("empty", "warning", "unavailable", "stale"):
        adapter = GermanyDummyWarningsApiComponent(
            provider_config={"poll_interval_seconds": 60, "stale_after_seconds": 180},
            site_config={"country_code": "DE"}, parameters={"region_code": "Test", "scenario": scenario},
        )
        adapter.poll()
    with pytest.raises(ValueError, match="HTTP client"):
        GermanyDummyWarningsApiComponent(
            provider_config={"poll_interval_seconds": 60, "stale_after_seconds": 180},
            site_config={"country_code": "DE"}, parameters={"region_code": "Test"}, http_client=object(),
        )
