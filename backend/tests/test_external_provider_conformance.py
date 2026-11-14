"""Cross-language provider catalogue and bounded metadata conformance."""

from copy import deepcopy
import json
from pathlib import Path

import pytest
import yaml

from components.external_apis.core import registry
from components.external_apis.core.configuration import (
    _validate_schema_budget,
    export_provider_catalogue,
)
from configuration_model import UserConfigurationV2
from user_config_api import configuration_error_payload
from tests.provider_plugin_support import (
    PeerRegionalWarnings,
    RegionalWarnings,
    provider_policy,
)


FIXTURES = Path(__file__).parent / "fixtures" / "external_apis"
ROOT = Path(__file__).parents[2]


def test_shared_catalogue_matches_live_definitions_and_source_schema(monkeypatch):
    """One sanitized fixture describes every bundled and controlled provider."""
    production = registry.get_registered_api_components()
    assert RegionalWarnings.component_name not in production
    assert PeerRegionalWarnings.component_name not in production
    monkeypatch.setattr(registry, "_API_COMPONENT_REGISTRY", dict(production))
    registry.register_api_component(RegionalWarnings)
    registry.register_api_component(PeerRegionalWarnings)
    system = yaml.safe_load(
        (ROOT / "backend/config/system_config.yml").read_text(encoding="utf-8")
    )
    policies = system["runtime_cfg"]["providers"]
    policies[RegionalWarnings.component_name] = provider_policy(feed_variant="regional")
    policies[PeerRegionalWarnings.component_name] = provider_policy()
    fixture = json.loads(
        (FIXTURES / "provider_contract.json").read_text(encoding="utf-8")
    )
    assert fixture == {
        "provider_metadata_version": 2,
        "provider_plugins": export_provider_catalogue(policies),
    }
    schema = UserConfigurationV2.model_json_schema()
    serialized = json.dumps(schema)
    for name in fixture["provider_plugins"]:
        assert name in serialized
    regional = fixture["provider_plugins"][RegionalWarnings.component_name]
    assert regional["hazards"] == ["wind"]
    assert regional["required_when_selected"] == ["region_code"]
    assert policies[RegionalWarnings.component_name]["feed_variant"] == "regional"


@pytest.mark.parametrize(
    ("key", "limit"), [("title", 256), ("description", 2048), ("pattern", 256)]
)
def test_schema_text_budgets_accept_limit_and_reject_one_over(key, limit):
    _validate_schema_budget({key: "x" * limit})
    with pytest.raises(ValueError):
        _validate_schema_budget({key: "x" * (limit + 1)})


@pytest.mark.parametrize(("key", "limit"), [("properties", 64), ("$defs", 128)])
def test_schema_collection_budgets_accept_limit_and_reject_one_over(key, limit):
    at_limit = {key: {f"f{i}": {} for i in range(limit)}}
    _validate_schema_budget(at_limit)
    over = deepcopy(at_limit)
    over[key]["extra"] = {}
    with pytest.raises(ValueError):
        _validate_schema_budget(over)


def test_schema_enum_and_depth_budgets():
    _validate_schema_budget({"enum": list(range(1024))})
    with pytest.raises(ValueError):
        _validate_schema_budget({"enum": list(range(1025))})
    _validate_schema_budget({"enum": ["x" * 256]})
    with pytest.raises(ValueError):
        _validate_schema_budget({"enum": ["x" * 257]})
    nested = {}
    for _ in range(8):
        nested = {"child": nested}
    _validate_schema_budget(nested)
    with pytest.raises(ValueError):
        _validate_schema_budget({"child": nested})


def test_schema_byte_budget_counts_utf8_and_catalogue_entry_limit():
    # An unconstrained extension value isolates the serialized byte boundary.
    overhead = len(json.dumps({"x-extra": ""}, ensure_ascii=False).encode("utf-8"))
    schema = {"x-extra": "x" * (65_536 - overhead)}
    _validate_schema_budget(schema)
    with pytest.raises(ValueError):
        _validate_schema_budget({"x-extra": schema["x-extra"] + "x"})
    with pytest.raises(ValueError, match="64 entries"):
        export_provider_catalogue({f"P{i}": {} for i in range(65)})


def test_field_error_budgets_are_bounded_without_losing_legacy_envelope():
    """Oversized validation output remains safe for the generic client decoder."""
    error = ValueError("configuration rejected")
    error.field_errors = [
        {"path": ["p" * 129] * 17, "code": "c" * 129, "message": "m" * 513}
        for _ in range(33)
    ]
    payload = configuration_error_payload(error)
    assert payload["error"] == "invalid_configuration"
    assert payload["message"] == "configuration rejected"
    assert len(payload["field_errors"]) == 32
    assert all(len(item["path"]) == 16 for item in payload["field_errors"])
    assert all(
        len(part) == 128 for item in payload["field_errors"] for part in item["path"]
    )
    assert all(
        len(item["code"]) == 128 and len(item["message"]) == 512
        for item in payload["field_errors"]
    )
    assert configuration_error_payload(ValueError("old server error")) == {
        "error": "invalid_configuration",
        "message": "old server error",
    }


def test_catalogue_accepts_sixty_four_valid_entries_then_rejects_sixty_five(
    monkeypatch,
):
    production = registry.get_registered_api_components()
    monkeypatch.setattr(registry, "_API_COMPONENT_REGISTRY", dict(production))
    policies = {}
    for i in range(65):
        plugin = type(
            f"Controlled{i}", (RegionalWarnings,), {"component_name": f"Controlled{i}"}
        )
        registry.register_api_component(plugin)
        policies[plugin.component_name] = provider_policy()
        if i == 63:
            assert len(export_provider_catalogue(policies)) == 64
    with pytest.raises(ValueError, match="64 entries"):
        export_provider_catalogue(policies)
