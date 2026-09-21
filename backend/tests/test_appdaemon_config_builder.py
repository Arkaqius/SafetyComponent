"""Tests for Home Assistant-derived AppDaemon runtime configuration."""

import io
import json
import sys

import pytest
import yaml

import build_appdaemon_config
from build_appdaemon_config import (
    fetch_core_config,
    fetch_core_config_with_retry,
    render_appdaemon_config,
    write_appdaemon_config,
)


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


def test_write_appdaemon_config_creates_parent_and_output(tmp_path) -> None:
    template_path = tmp_path / "templates" / "appdaemon.yaml"
    output_path = tmp_path / "runtime" / "appdaemon.yaml"
    template_path.parent.mkdir()
    template_path.write_text(TEMPLATE, encoding="utf-8")

    write_appdaemon_config(
        template_path,
        output_path,
        {
            "latitude": 50.0,
            "longitude": 20.0,
            "elevation": 200,
            "time_zone": "Europe/Warsaw",
        },
    )

    assert output_path.is_file()
    assert "latitude: 50.0" in output_path.read_text(encoding="utf-8")


def test_fetch_core_config_with_retry_waits_then_returns(monkeypatch, capsys) -> None:
    payload = {
        "latitude": 50.0,
        "longitude": 20.0,
        "elevation": 200,
        "time_zone": "Europe/Warsaw",
    }
    outcomes = iter([OSError("not ready"), payload])
    delays: list[float] = []

    def fake_fetch_core_config(_url: str, _token: str) -> dict[str, object]:
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(
        build_appdaemon_config,
        "fetch_core_config",
        fake_fetch_core_config,
    )
    monkeypatch.setattr(build_appdaemon_config.time, "sleep", delays.append)

    result = fetch_core_config_with_retry(
        build_appdaemon_config.CORE_CONFIG_URL,
        "test-token",
        attempts=2,
        retry_delay=0.25,
    )

    assert result == payload
    assert delays == [0.25]
    assert "Waiting for Home Assistant Core configuration" in capsys.readouterr().out


def test_fetch_core_config_with_retry_rejects_incomplete_response(monkeypatch) -> None:
    monkeypatch.setattr(
        build_appdaemon_config,
        "fetch_core_config",
        lambda _url, _token: {"latitude": 50.0},
    )

    with pytest.raises(RuntimeError, match="after 1 attempts") as error:
        fetch_core_config_with_retry(
            build_appdaemon_config.CORE_CONFIG_URL,
            "test-token",
            attempts=1,
            retry_delay=0.0,
        )

    assert isinstance(error.value.__cause__, ValueError)
    assert "longitude" in str(error.value.__cause__)


def test_main_writes_runtime_config(monkeypatch, tmp_path) -> None:
    template_path = tmp_path / "appdaemon.template.yaml"
    output_path = tmp_path / "appdaemon.yaml"
    template_path.write_text(TEMPLATE, encoding="utf-8")
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_appdaemon_config.py",
            "--template",
            str(template_path),
            "--output",
            str(output_path),
            "--attempts",
            "1",
            "--retry-delay",
            "0",
        ],
    )
    monkeypatch.setattr(
        build_appdaemon_config,
        "fetch_core_config_with_retry",
        lambda *_args, **_kwargs: {
            "latitude": 50.0,
            "longitude": 20.0,
            "elevation": 200,
            "time_zone": "Europe/Warsaw",
        },
    )

    build_appdaemon_config.main()

    assert output_path.is_file()
    assert "time_zone: \"Europe/Warsaw\"" in output_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("token", "extra_args", "message"),
    [
        (None, [], "SUPERVISOR_TOKEN is required"),
        ("test-token", ["--attempts", "0"], "--attempts must be at least 1"),
        (
            "test-token",
            ["--retry-delay", "-1"],
            "--retry-delay cannot be negative",
        ),
    ],
)
def test_main_rejects_invalid_runtime_options(
    monkeypatch,
    tmp_path,
    token: str | None,
    extra_args: list[str],
    message: str,
) -> None:
    if token is None:
        monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    else:
        monkeypatch.setenv("SUPERVISOR_TOKEN", token)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_appdaemon_config.py",
            "--template",
            str(tmp_path / "template.yaml"),
            "--output",
            str(tmp_path / "appdaemon.yaml"),
            *extra_args,
        ],
    )

    with pytest.raises(SystemExit, match=message):
        build_appdaemon_config.main()
