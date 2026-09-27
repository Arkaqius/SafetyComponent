"""Publisher metadata is isolated, bounded, cached, and fails unknown."""

import json
from unittest.mock import Mock

import pytest

from components.external_apis.stable_releases import StableReleaseProvider


@pytest.fixture(autouse=True)
def synchronous_worker(monkeypatch) -> None:
    """Run the bounded transport deterministically without real threads."""

    class Worker:
        def __init__(self, *, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr("components.external_apis.stable_releases.Thread", Worker)


@pytest.mark.parametrize("prerelease", [True, False])
def test_stable_schema_and_cache(monkeypatch, prerelease: bool) -> None:
    response = Mock()
    response.read.return_value = json.dumps(
        {"draft": False, "prerelease": prerelease, "tag_name": "v0.3.1"}
    ).encode()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    transport = Mock(return_value=response)
    monkeypatch.setattr("components.external_apis.stable_releases.urlopen", transport)
    provider = StableReleaseProvider()
    result = provider.poll()
    assert result["safety_component"]["status"] == (
        "unknown" if prerelease else "current"
    )
    assert result["safety_component"]["version"] == (None if prerelease else "v0.3.1")
    assert provider.poll() == result
    assert transport.call_count == 4


def test_transport_failure_is_unknown(monkeypatch) -> None:
    monkeypatch.setattr(
        "components.external_apis.stable_releases.urlopen",
        Mock(side_effect=OSError("offline")),
    )
    assert all(
        item["status"] == "unknown" and item["version"] is None
        for item in StableReleaseProvider().poll().values()
    )


def test_pending_worker_does_not_block_or_spawn_duplicate_fetches(monkeypatch) -> None:
    worker = Mock()
    monkeypatch.setattr("components.external_apis.stable_releases.Thread", worker)
    provider = StableReleaseProvider()
    assert all(item["status"] == "unknown" for item in provider.poll().values())
    provider.poll()
    worker.assert_called_once()
    worker.return_value.start.assert_called_once()
