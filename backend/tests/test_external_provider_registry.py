"""Registry contract regressions for independently configured providers."""

from typing import Any

import pytest
from pydantic import ValidationError

from components.external_apis.core import registry
from components.external_apis.core.models import HazardType, ProviderCapability
from tests.provider_plugin_support import RegionalWarnings, provider_policy


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


def test_registration_rejects_undeclared_activation_requirement() -> None:
    """An activation rule cannot require a field absent from its parameter model."""

    class BadRequired(RegionalWarnings):
        component_name = "BadRequiredApiComponent"
        required_when_enabled = frozenset({"undeclared_region"})

    with pytest.raises(ValueError, match="unknown required parameters"):
        registry.register_api_component(BadRequired)
    assert BadRequired.component_name not in registry.get_registered_api_components()


@pytest.mark.parametrize(
    ("capability", "hazard"),
    [
        (ProviderCapability.AIR_QUALITY, HazardType.WIND),
        (ProviderCapability.WEATHER_MODEL, HazardType.OUTDOOR_AIR_POLLUTION),
        (ProviderCapability.OFFICIAL_WARNINGS, HazardType.OUTDOOR_AIR_POLLUTION),
    ],
)
def test_registration_rejects_capability_hazard_mismatch(
    capability: ProviderCapability, hazard: HazardType
) -> None:
    """A provider cannot declare evidence outside its capability's hazard family."""

    class BadCapability(RegionalWarnings):
        component_name = "BadCapabilityApiComponent"

    BadCapability.capability = capability
    BadCapability.hazards = frozenset({hazard})
    with pytest.raises(ValueError, match="incompatible hazard coverage"):
        registry.register_api_component(BadCapability)
    assert BadCapability.component_name not in registry.get_registered_api_components()


def test_runtime_schema_preserves_closed_provider_owned_packaged_fields() -> None:
    """A registered transport model retains its own fields and rejects extras."""

    registry.register_api_component(RegionalWarnings)
    schema: dict[str, Any] = {}
    registry.describe_runtime_provider_keys(schema)
    entry = schema["properties"][RegionalWarnings.component_name]
    assert schema["additionalProperties"] is False
    assert entry["additionalProperties"] is False
    assert entry["properties"]["feed_variant"]["default"] == "controlled"
    transport = RegionalWarnings.config_model.model_validate(
        provider_policy(feed_variant="test-region")
    )
    assert transport.model_dump()["feed_variant"] == "test-region"
    with pytest.raises(ValidationError, match="extra_forbidden"):
        RegionalWarnings.config_model.model_validate(provider_policy(unknown_policy=1))
