"""Explicit discovery retirement preserves live topics and rejects foreign owners."""

import json

import pytest

import migrate_mqtt_retained
from retire_mqtt_discovery import DiscoveryRetirement

from .test_mqtt_retained_migration import FakeBrokerClient


@pytest.fixture
def broker(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(migrate_mqtt_retained.time, "monotonic", lambda: clock[0])
    client = FakeBrokerClient(clock)
    payload = {
        "unique_id": "safety_component_old",
        "state_topic": "safety_component/state/old",
        "json_attributes_topic": "safety_component/attributes/old",
        "device": {"identifiers": ["safety_component"]},
    }
    client.retained.update({
        "homeassistant/sensor/safety_component_old/config": json.dumps(payload).encode(),
        "homeassistant/sensor/old/config": json.dumps(payload).encode(),
        "homeassistant/sensor/safety_component_current/config": b"current",
        "safety_component/state/old": b"FAIL",
        "safety_component/attributes/old": b'{"active":true}',
    })
    return client


def test_audit_selects_only_reviewed_discovery_and_never_publishes(broker):
    original = dict(broker.retained)
    migration = DiscoveryRetirement(broker, ["sensor.old"], {}, 1, 1)
    assert migration.run("test", 1883) == set(migration.expected)
    assert not broker.published
    assert broker.retained == original
    assert all("+" not in topic and "#" not in topic for topic, _ in broker.subscriptions[0])


def test_apply_preserves_state_attributes_and_current_discovery(broker):
    migration = DiscoveryRetirement(broker, ["sensor.old"], {}, 1, 1)
    preserved = {key: value for key, value in broker.retained.items() if key not in migration.expected}
    assert migration.run("test", 1883, apply=True) == set()
    assert broker.retained == preserved
    assert set(topic for topic, *_ in broker.published) == set(migration.expected)
    assert len(broker.subscriptions) == 2


@pytest.mark.parametrize("bad_payload", [
    b"broken", b"[]", b'{"device":null}',
    json.dumps({
        "unique_id": "safety_component_old", "state_topic": "other/state/old",
        "json_attributes_topic": "safety_component/attributes/old",
        "device": {"identifiers": ["safety_component"]},
    }).encode(),
])
def test_unverified_ownership_aborts_before_any_deletion(broker, bad_payload):
    broker.retained["homeassistant/sensor/old/config"] = bad_payload
    migration = DiscoveryRetirement(broker, ["sensor.old"], {}, 1, 1)
    with pytest.raises(RuntimeError, match="unverified"):
        migration.run("test", 1883, apply=True)
    assert not broker.published


def test_deletion_denied_is_detected_by_verification(broker):
    broker.deny_delete = True
    migration = DiscoveryRetirement(broker, ["sensor.old"], {}, 1, 1)
    with pytest.raises(RuntimeError, match="remain after migration"):
        migration.run("test", 1883, apply=True)


@pytest.mark.parametrize("entities", [[], ["sensor.Old"], ["switch.old"], ["sensor.old/#"]])
def test_entity_selection_must_be_explicit_and_canonical(broker, entities):
    with pytest.raises(ValueError):
        DiscoveryRetirement(broker, entities, {}, 1, 1)
