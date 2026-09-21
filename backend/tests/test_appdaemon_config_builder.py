"""Tests for Home Assistant-derived AppDaemon runtime configuration."""

import io
import json

import pytest
import yaml

import build_appdaemon_config
from build_appdaemon_config import fetch_core_config, render_appdaemon_config


TEMPLATE = """appdaemon:
  latitude: __HOME_ASSISTANT_LATITUDE__
  longitude: __HOME_ASSISTANT_LONGITUDE__
  elevation: __HOME_ASSISTANT_ELEVATION__
  time_zone: __HOME_ASSISTANT_TIME_ZONE__
  plugins:
    HASS:
      token: !env_var SUPERVISOR_TOKEN
"""


def test_render_appdaemon_config_adds_required_location_fields() -> None:
    rendered = render_appdaemon_config(
        TEMPLATE,
        {
            "latitude": 50.0125,
            "longitude": 19.9375,
            "elevation": 219,
            "time_zone": "Europe/Warsaw",
        },
    )
    parsed = yaml.safe_load(rendered.replace("!env_var SUPERVISOR_TOKEN", "token"))

    assert parsed["appdaemon"] == {
        "latitude": 50.0125,
        "longitude": 19.9375,
        "elevation": 219,
        "time_zone": "Europe/Warsaw",
        "plugins": {"HASS": {"token": "token"}},
    }
    assert "__HOME_ASSISTANT_" not in rendered
    assert "token: !env_var SUPERVISOR_TOKEN" in rendered


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", True),
        ("longitude", float("nan")),
        ("elevation", "219"),
        ("time_zone", ""),
    ],
)
def test_render_appdaemon_config_rejects_invalid_core_values(
    field: str,
    value: object,
) -> None:
    core_config = {
        "latitude": 50.0,
        "longitude": 20.0,
        "elevation": 219,
        "time_zone": "Europe/Warsaw",
    }
    core_config[field] = value

    with pytest.raises(ValueError, match=field):
        render_appdaemon_config(TEMPLATE, core_config)


def test_fetch_core_config_uses_supervisor_bearer_token(monkeypatch) -> None:
    payload = {
        "latitude": 50.0,
        "longitude": 20.0,
        "elevation": 219,
        "time_zone": "Europe/Warsaw",
    }
    response = io.BytesIO(json.dumps(payload).encode("utf-8"))
    response.__enter__ = lambda: response
    response.__exit__ = lambda *args: None

    def fake_urlopen(request, timeout):
        assert request.get_header("Authorization") == "Bearer test-token"
        assert request.full_url == build_appdaemon_config.CORE_CONFIG_URL
        assert timeout == 3.0
        return response

    monkeypatch.setattr(build_appdaemon_config, "urlopen", fake_urlopen)

    assert fetch_core_config(
        build_appdaemon_config.CORE_CONFIG_URL,
        "test-token",
        timeout=3.0,
    ) == payload
