"""Regression evidence for empty MQTT attributes and startup liveness."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from jinja2 import Environment, StrictUndefined

from build_app_config import compile_config
from components.core.mqtt_entity_manager import MqttEntityManager


@pytest.mark.parametrize("config", [None, {"clear_retained_state_on_start": False}])
def test_ordinary_startup_and_heartbeat_do_not_publish_tombstones(config):
    for _ in range(2):
        app = Mock()
        manager = MqttEntityManager(app, config)
        manager.register_sensor(
            "sensor.health", "Health", state="running",
            attributes={"fault": "active"},
        )
        manager.publish_availability()
        manager.publish_heartbeat()

        calls = app.call_service.call_args_list
        assert all(call.kwargs["payload"] != "" for call in calls)
        runtime_calls = [
            call for call in calls
            if call.kwargs["topic"].startswith((
                "safety_component/state/", "safety_component/attributes/",
            ))
        ]
        assert len(runtime_calls) == 4
        assert all(call.kwargs["retain"] is False for call in runtime_calls)
        discovery = next(
            call for call in calls if call.kwargs["topic"].endswith("/config")
        )
        payload = json.loads(discovery.kwargs["payload"])
        assert payload["expire_after"] == 180
        assert payload["availability_topic"] == "safety_component/status"
        assert manager.settings.heartbeat_seconds == 60


def _attributes_template():
    app = Mock()
    manager = MqttEntityManager(app)
    manager.register_sensor("sensor.health", "Health", state="running")
    discovery = next(
        call for call in app.call_service.call_args_list
        if call.kwargs["topic"].endswith("/config")
    )
    template = json.loads(discovery.kwargs["payload"])["json_attributes_template"]
    environment = Environment(undefined=StrictUndefined)
    environment.filters["to_json"] = json.dumps
    return environment.from_string(template)


@pytest.mark.parametrize("value", ["", " ", "\n\t", "\r\n"])
@pytest.mark.parametrize("current", [
    {}, {"fault": "active", "evaluated_at": "2026-10-08T06:00:00Z"},
])
def test_empty_attributes_preserve_last_evidence(value, current):
    rendered = _attributes_template().render(
        value=value, this=SimpleNamespace(attributes=current),
    )
    assert json.loads(rendered) == current


def test_valid_attributes_replace_previous_evidence_without_this_lookup():
    replacement = {"fault": "cleared", "nested": {"value": 42}}
    rendered = _attributes_template().render(value=json.dumps(replacement))
    assert json.loads(rendered) == replacement
    assert json.loads(_attributes_template().render(value="{}")) == {}


def test_nonempty_malformed_attributes_are_not_hidden_by_empty_payload_guard():
    value = "broken JSON"
    assert _attributes_template().render(value=value) == value


def test_explicit_legacy_cleanup_setting_remains_compatible():
    app = Mock()
    manager = MqttEntityManager(app, {"clear_retained_state_on_start": True})
    manager.register_sensor("sensor.health", "Health", state="running")
    manager.register_sensor("sensor.health", "Health", state="running")
    tombstones = [
        call for call in app.call_service.call_args_list
        if call.kwargs["payload"] == ""
    ]
    assert [call.kwargs["topic"] for call in tombstones] == [
        "safety_component/state/health", "safety_component/attributes/health",
    ]
    assert all(call.kwargs["retain"] is True for call in tombstones)


def test_compiled_examples_disable_ordinary_startup_cleanup():
    backend_dir = Path(__file__).parents[1]
    for user_path in (
        backend_dir / "config" / "user_config.example.yml",
        backend_dir.parent / "docs" / "examples" / "example_house_user_config.yml",
    ):
        config = compile_config(
            user_path=user_path,
            home_assistant_config={"latitude": 50.0, "longitude": 20.0},
        )["SafetyFunctions"]["user_config"]
        settings = config["mqtt"]
        assert settings["clear_retained_state_on_start"] is False
        assert settings["retain_state"] is False
        assert settings["heartbeat_seconds"] == 60
        assert settings["expire_after"] == 180
