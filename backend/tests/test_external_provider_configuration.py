"""Pure provider-resolution and pre-persistence validation regressions."""

import pytest

from components.external_apis.core import registry
from components.external_apis.core.configuration import resolve_provider_bindings
from tests.provider_plugin_support import RegionalWarnings, provider_policy


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    monkeypatch.setattr(
        registry, "_API_COMPONENT_REGISTRY", registry.get_registered_api_components()
    )
    registry.register_api_component(RegionalWarnings)


def test_inherited_incompatible_default_is_inactive_but_explicit_is_error():
    name = RegionalWarnings.component_name
    assert not resolve_provider_bindings(
        {name: provider_policy()}, {}, {"country_code": "PL"}
    )[name]["enabled"]
    with pytest.raises(ValueError, match="country"):
        resolve_provider_bindings(
            {name: provider_policy()}, {name: {"enabled": True}}, {"country_code": "PL"}
        )


def test_active_requiredness_and_disabled_incomplete_parameters():
    name = RegionalWarnings.component_name
    policies = {name: provider_policy(feed_variant="custom")}
    site = {"country_code": "DE"}
    with pytest.raises(ValueError, match="region_code"):
        resolve_provider_bindings(policies, {}, site)
    result = resolve_provider_bindings(
        policies, {name: {"parameters": {"region_code": "Berlin"}}}, site
    )
    assert result[name]["parameters"] == {"region_code": "Berlin"}
    assert result[name]["selection_origin"] == "inherited"
    assert result[name]["feed_variant"] == "custom"
    assert not resolve_provider_bindings(policies, {name: {"enabled": False}}, site)[
        name
    ]["enabled"]
    with pytest.raises(ValueError, match="unknown"):
        resolve_provider_bindings(
            policies, {name: {"enabled": False, "parameters": {"unknown": 1}}}, site
        )


def test_imgw_legacy_resolves_before_requiredness_and_conflicts_fail():
    name = "ImgwWarningsApiComponent"
    policy = provider_policy(
        base_url="https://danepubliczne.imgw.pl/api/data/warningsmeteo"
    )
    site = {"country_code": "PL", "teryt_codes": ["0000", "0001"]}
    assert resolve_provider_bindings({name: policy}, {}, site)[name]["parameters"][
        "teryt_codes"
    ] == ["0000", "0001"]
    equal = {name: {"parameters": {"teryt_codes": ["0001", "0000"]}}}
    resolve_provider_bindings({name: policy}, equal, site)
    with pytest.raises(ValueError, match="conflict"):
        resolve_provider_bindings(
            {name: policy}, {name: {"parameters": {"teryt_codes": ["0002"]}}}, site
        )


@pytest.mark.parametrize("codes", [["1"], ["0000", " 0000 "], [1234], ["１２３４"]])
def test_imgw_rejects_malformed_supplied_codes_even_when_disabled(codes):
    name = "ImgwWarningsApiComponent"
    policy = provider_policy(
        base_url="https://danepubliczne.imgw.pl/api/data/warningsmeteo"
    )
    with pytest.raises(ValueError):
        resolve_provider_bindings(
            {name: policy},
            {name: {"enabled": False, "parameters": {"teryt_codes": codes}}},
            {"country_code": "PL"},
        )


def test_imgw_normalization_and_provenance_do_not_mutate_input():
    name = "ImgwWarningsApiComponent"
    selection = {name: {"parameters": {"teryt_codes": [" 0001 ", "0000"]}}}
    site = {"country_code": "pl", "teryt_codes": ["0000", "0001"]}
    policy = provider_policy(
        base_url="https://danepubliczne.imgw.pl/api/data/warningsmeteo"
    )
    result = resolve_provider_bindings({name: policy}, selection, site)
    assert result[name]["enabled"] is True
    assert result[name]["parameters"]["teryt_codes"] == ["0001", "0000"]
    assert selection[name]["parameters"]["teryt_codes"] == [" 0001 ", "0000"]
    assert site["country_code"] == "pl"


def test_disabled_component_does_not_need_site_or_provider_parameters():
    result = resolve_provider_bindings(
        {RegionalWarnings.component_name: provider_policy()},
        {},
        {},
        component_enabled=False,
    )
    assert not result[RegionalWarnings.component_name]["enabled"]
