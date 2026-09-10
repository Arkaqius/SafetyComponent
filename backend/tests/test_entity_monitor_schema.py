"""Configuration tests for Entity Health Monitoring."""

import pytest

from components.safetycomponents.entity_monitor.schema import (
    validate_entity_monitor_config,
)


def test_entity_monitor_normalizes_explicit_checks_and_debounce_defaults():
    runtime = validate_entity_monitor_config(
        {
            "explicit_entities": {
                "BedroomTrv": {
                    "entity_id": "climate.bedroom_radiator",
                    "description": "Heating dependency",
                    "checks": {
                        "freshness": {
                            "timestamp_source": "last_updated",
                            "max_silence_seconds": 120,
                        },
                        "allowed_values": {
                            "target": "state",
                            "values": ["Heat", "Off"],
                        },
                    },
                }
            }
        },
        calibration={
            "default_failure_debounce_seconds": 12,
            "default_recovery_debounce_seconds": 45,
        },
    )

    entity = runtime["explicit_entities"][0]
    assert entity["key"] == "BedroomTrv"
    assert entity["source"] == "explicit"
    assert entity["failure_debounce_seconds"] == 12
    assert entity["recovery_debounce_seconds"] == 45
    assert entity["checks"]["allowed_values"]["values"] == ["heat", "off"]


@pytest.mark.parametrize(
    "checks",
    [
        {"numeric_range": {"target": "state"}},
        {"rate_of_change": {"target": "state", "window_seconds": 60}},
        {"freshness": {"timestamp_source": "", "max_silence_seconds": 30}},
        {"allowed_values": {"target": "state", "values": []}},
    ],
)
def test_entity_monitor_rejects_incomplete_check_calibration(checks):
    with pytest.raises(ValueError):
        validate_entity_monitor_config(
            {
                "explicit_entities": {
                    "Bad": {
                        "entity_id": "sensor.bad",
                        "description": "Invalid calibration",
                        "checks": checks,
                    }
                }
            }
        )


def test_entity_monitor_rejects_timing_outside_detection_budget():
    with pytest.raises(ValueError, match="freshness and failure debounce"):
        validate_entity_monitor_config(
            {
                "explicit_entities": {
                    "BedroomTrv": {
                        "entity_id": "climate.bedroom_radiator",
                        "description": "Heating dependency",
                        "detection_budget_seconds": 120,
                        "failure_debounce_seconds": 15,
                        "checks": {
                            "freshness": {
                                "timestamp_source": "last_updated",
                                "max_silence_seconds": 110,
                            }
                        },
                    }
                }
            }
        )


def test_entity_monitor_normalizes_component_dependency_overrides():
    runtime = validate_entity_monitor_config(
        {"explicit_entities": {}},
        calibration={
            "component_overrides": {
                "TemperatureOffice": {
                    "failure_debounce_seconds": 10,
                    "recovery_debounce_seconds": 45,
                    "detection_budget_seconds": 610,
                    "checks": {
                        "freshness": {
                            "timestamp_source": "last_updated",
                            "max_silence_seconds": 600,
                        },
                        "numeric_range": {
                            "target": "state",
                            "minimum": -40,
                            "maximum": 80,
                        },
                    },
                }
            }
        },
    )

    override = runtime["component_overrides"]["TemperatureOffice"]
    assert override["failure_debounce_seconds"] == 10
    assert override["recovery_debounce_seconds"] == 45
    assert override["checks"]["numeric_range"] == {
        "target": "state",
        "minimum": -40.0,
        "maximum": 80.0,
    }
