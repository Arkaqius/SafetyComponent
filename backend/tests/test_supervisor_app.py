"""Only self identity can cross the Supervisor provider boundary."""

import json
from unittest.mock import MagicMock

import pytest

from components.external_apis.supervisor_app import own_app_slug


@pytest.mark.parametrize(
    "slug", ["local_safety_component_dev", "abc_safety_component", "../core", None]
)
def test_self_identity_is_bounded_and_redacted(monkeypatch, slug) -> None:
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-only-token")
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = json.dumps(
        {"result": "ok", "data": {"slug": slug, "options": {"secret": "not-public"}}}
    ).encode()
    transport = MagicMock(return_value=response)
    monkeypatch.setattr("components.external_apis.supervisor_app.urlopen", transport)
    if slug is None or slug == "../core":
        with pytest.raises(RuntimeError, match="identity is unavailable"):
            own_app_slug()
    else:
        assert own_app_slug() == slug
    request = transport.call_args.args[0]
    assert request.full_url == "http://supervisor/addons/self/info"
    assert request.get_method() == "GET"
    assert response.read.call_args.args == (64 * 1024 + 1,)


def test_no_supervisor_token_has_no_transport_call(monkeypatch) -> None:
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    transport = MagicMock()
    monkeypatch.setattr("components.external_apis.supervisor_app.urlopen", transport)
    with pytest.raises(RuntimeError):
        own_app_slug()
    transport.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [b"[]", b"not-json", b"x" * (64 * 1024 + 1)],
    ids=["array", "invalid-json", "oversized"],
)
def test_malformed_or_oversized_identity_is_unavailable(
    monkeypatch, body: bytes
) -> None:
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-only-token")
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = body
    monkeypatch.setattr(
        "components.external_apis.supervisor_app.urlopen",
        MagicMock(return_value=response),
    )
    with pytest.raises(RuntimeError) as error:
        own_app_slug()
    assert str(error.value) == "Supervisor app identity is unavailable"


def test_transport_errors_never_expose_credentials(monkeypatch) -> None:
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-only-token")
    monkeypatch.setattr(
        "components.external_apis.supervisor_app.urlopen",
        MagicMock(side_effect=OSError("test-only-token")),
    )
    with pytest.raises(RuntimeError) as error:
        own_app_slug()
    assert "test-only-token" not in str(error.value)
