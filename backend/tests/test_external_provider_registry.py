"""Registry contract regressions for independently configured providers."""

import pytest

from components.external_apis.core import registry
from tests.provider_plugin_support import RegionalWarnings


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    monkeypatch.setattr(
        registry, "_API_COMPONENT_REGISTRY", registry.get_registered_api_components()
    )


def test_registration_rejects_duplicate_and_derived_identity_collision():
    class Foo(RegionalWarnings):
        component_name = "Foo"

    class FooSuffix(RegionalWarnings):
        component_name = "FooApiComponent"

    registry.register_api_component(Foo)
    with pytest.raises(ValueError, match="already registered"):
        registry.register_api_component(Foo)
    with pytest.raises(ValueError, match="identity collision"):
        registry.register_api_component(FooSuffix)


def test_registration_rejects_invalid_hazard_declaration():
    class Bad(RegionalWarnings):
        component_name = "BadCoverageApiComponent"
        hazards = frozenset()

    with pytest.raises(ValueError, match="hazard"):
        registry.register_api_component(Bad)


def test_registration_rejects_mqtt_only_identity_collision():
    class FooBar(RegionalWarnings):
        component_name = "FooBar"

    class FooMiddle(RegionalWarnings):
        component_name = "FooApiComponentBar"

    registry.register_api_component(FooBar)
    with pytest.raises(ValueError, match="identity collision"):
        registry.register_api_component(FooMiddle)


def test_provider_schema_export_tracks_new_registration():
    schema = {}
    registry.describe_provider_keys(schema)
    assert RegionalWarnings.component_name not in schema.get("properties", {})
    registry.register_api_component(RegionalWarnings)
    registry.describe_provider_keys(schema)
    entry = schema["properties"][RegionalWarnings.component_name]
    assert entry["properties"]["parameters"]["additionalProperties"] is False
    assert "region_code" in entry["properties"]["parameters"]["properties"]
