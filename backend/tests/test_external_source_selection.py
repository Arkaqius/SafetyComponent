"""Applied source truth remains independent from provider telemetry."""

from types import SimpleNamespace

import pytest

from components.external_apis.core.models import HazardType, ProviderCapability
from components.external_apis.core.selection_state import AppliedSourceSelection


class SelectionMqtt:
    def __init__(self):
        self.calls = []

    def register_sensor(self, entity_id, name, **kwargs):
        self.calls.append(("register", entity_id, name))
        return entity_id

    def publish_sensor_state(self, entity_id, state, *, attributes):
        self.calls.append(("publish", entity_id, state, attributes))


@pytest.mark.parametrize("enabled", [False, True])
def test_applied_selection_publishes_all_categories_even_when_component_off(enabled):
    mqtt = SelectionMqtt()
    selections = {capability.value: None for capability in ProviderCapability}
    selections[ProviderCapability.OFFICIAL_WARNINGS.value] = "Controlled"
    definitions = {
        "Controlled": SimpleNamespace(
            capability=ProviderCapability.OFFICIAL_WARNINGS,
            data_kind="synthetic",
            hazards=frozenset({HazardType.WIND}),
        )
    }
    publisher = AppliedSourceSelection(
        mqtt,
        runtime_id="start-1",
        component_enabled=enabled,
        selections=selections,
        provider_definitions=definitions,
    )
    publisher.publish()
    _, entity, state, attributes = mqtt.calls[-1]
    assert entity == "sensor.external_source_selection"
    assert state == "ready"
    assert attributes["runtime_id"] == "start-1"
    assert attributes["schema_version"] == 1
    assert attributes["component_enabled"] is enabled
    assert len(attributes["selections"]) == 3
    assert attributes["selections"]["OfficialWeatherWarnings"] == {
        "provider": "Controlled",
        "data_kind": "synthetic",
        "hazards": ["wind"],
    }
    assert attributes["selections"]["WeatherPointModel"] == {
        "provider": None,
        "data_kind": None,
        "hazards": [],
    }


@pytest.mark.parametrize("runtime_id", ["", "x" * 129, "zażółć"])
def test_applied_selection_rejects_invalid_generation(runtime_id):
    with pytest.raises(ValueError):
        AppliedSourceSelection(
            SelectionMqtt(),
            runtime_id=runtime_id,
            component_enabled=False,
            selections={cap.value: None for cap in ProviderCapability},
            provider_definitions={},
        )


def test_applied_selection_rejects_missing_category_and_mismatched_definition():
    with pytest.raises(ValueError):
        AppliedSourceSelection(
            SelectionMqtt(),
            runtime_id="start",
            component_enabled=False,
            selections={},
            provider_definitions={},
        )
    with pytest.raises(ValueError):
        AppliedSourceSelection(
            SelectionMqtt(),
            runtime_id="start",
            component_enabled=True,
            selections={cap.value: "Unknown" for cap in ProviderCapability},
            provider_definitions={},
        )
