"""Pure explicit category selection regressions."""
import pytest
from components.external_apis.core import registry
from components.external_apis.core.configuration import resolve_provider_bindings
from tests.provider_plugin_support import RegionalWarnings, provider_policy


def choices(**values):
    return {
        "WeatherPointModel": None,
        "OfficialWeatherWarnings": None,
        "OutdoorAirQuality": None,
        **values,
    }


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    monkeypatch.setattr(
        registry, "_API_COMPONENT_REGISTRY", registry.get_registered_api_components()
    )
    registry.register_api_component(RegionalWarnings)


def test_explicit_selection_required_and_capability_checked():
    name = RegionalWarnings.component_name
    with pytest.raises(ValueError, match="category"):
        resolve_provider_bindings({name: provider_policy()}, {}, {}, {})
    with pytest.raises(ValueError, match="capability"):
        resolve_provider_bindings(
            {name: provider_policy()},
            choices(WeatherPointModel=name),
            {},
            {"country_code": "DE"},
        )


def test_selected_country_requiredness_and_disabled_parameters():
    name = RegionalWarnings.component_name
    policies = {name: provider_policy(feed_variant="custom")}
    with pytest.raises(ValueError, match="region_code"):
        resolve_provider_bindings(
            policies, choices(OfficialWeatherWarnings=name), {}, {"country_code": "DE"}
        )
    with pytest.raises(ValueError, match="country"):
        resolve_provider_bindings(
            policies,
            choices(OfficialWeatherWarnings=name),
            {name: {"region_code": "Berlin"}},
            {"country_code": "PL"},
        )
    result = resolve_provider_bindings(
        policies,
        choices(OfficialWeatherWarnings=name),
        {name: {"region_code": "Berlin"}},
        {"country_code": "DE"},
    )
    assert result[name]["enabled"] is True
    assert result[name]["parameters"] == {"region_code": "Berlin"}
    assert result[name]["feed_variant"] == "custom"
    assert "selection_origin" not in result[name]
    assert not resolve_provider_bindings(policies, choices(), {}, {})[name]["enabled"]
    with pytest.raises(ValueError, match="Unknown"):
        resolve_provider_bindings(policies, choices(), {name: {"unknown": 1}}, {})


def test_imgw_canonical_parameters_normalize_without_alias():
    name = "ImgwWarningsApiComponent"
    policy = provider_policy(
        base_url="https://danepubliczne.imgw.pl/api/data/warningsmeteo"
    )
    params = {name: {"teryt_codes": [" 0001 ", "0000"]}}
    result = resolve_provider_bindings(
        {name: policy},
        choices(OfficialWeatherWarnings=name),
        params,
        {"country_code": "PL"},
    )
    assert result[name]["parameters"] == {"teryt_codes": ["0001", "0000"]}
    assert params[name]["teryt_codes"] == [" 0001 ", "0000"]
    with pytest.raises(ValueError, match="teryt_codes"):
        resolve_provider_bindings(
            {name: policy},
            choices(OfficialWeatherWarnings=name),
            {},
            {"country_code": "PL", "teryt_codes": ["0000"]},
        )


@pytest.mark.parametrize("codes", [["1"], ["0000", " 0000 "], [1234], ["１２３４"]])
def test_imgw_rejects_malformed_supplied_codes_even_when_disabled(codes):
    name = "ImgwWarningsApiComponent"
    policy = provider_policy(
        base_url="https://danepubliczne.imgw.pl/api/data/warningsmeteo"
    )
    with pytest.raises(ValueError):
        resolve_provider_bindings(
            {name: policy}, choices(), {name: {"teryt_codes": codes}}, {}
        )


def test_disabled_component_does_not_need_site_or_required_parameters():
    name = RegionalWarnings.component_name
    result = resolve_provider_bindings(
        {name: provider_policy()},
        choices(OfficialWeatherWarnings=name),
        {},
        {},
        component_enabled=False,
    )
    assert not result[name]["enabled"]
