"""Capture actual packaged HASS event delivery using fictional, offline input."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock


async def probe():
    """Replace network and final worker transport, preserving actual HA adapters."""
    from appdaemon.events import Events
    from appdaemon.plugin_management import PluginManagement
    from appdaemon.plugins.hass.hassplugin import HassPlugin
    from appdaemon.state import State

    logger = logging.getLogger("offline-indoor-contract")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    captured = []

    async def deliver(_name, job):
        captured.append(dict(event=job["event"], data=deepcopy(job["data"])))
        return True

    ad = SimpleNamespace(loop=asyncio.get_running_loop(), sched=None, http=None, apps_enabled=True,
        stopping=False, logging=SimpleNamespace(get_child=lambda _: logger),
        app_management=SimpleNamespace(objects={"fixture": SimpleNamespace(id="fixture")}, check_app_updates=AsyncMock()),
        threading=SimpleNamespace(dispatch_worker=deliver),
        callbacks=SimpleNamespace(callbacks_lock=asyncio.Lock(), callbacks={"fixture": {
            kind: dict(type="event", namespace="default", event=kind, function=lambda: None,
                       pin_app=True, pin_thread=0, kwargs={})
            for kind in ("state_changed", "plugin_started", "plugin_stopped")}}))
    ad.events = Events(ad)
    state = object.__new__(State)
    state.AD, state.logger, state.error = ad, logger, logger
    state.state = {"default": {}, "admin": {"plugin.fixture-hass": {}}}
    ad.state = state
    ad.plugins = SimpleNamespace(refresh_update_time=AsyncMock(), process_meta=Mock(),
                                  plugin_meta={}, plugin_objs={"default": {"active": False}})
    plugin = object.__new__(HassPlugin)
    plugin.AD, plugin.logger, plugin.error = ad, logger, logger
    plugin.name = "fixture-hass"
    plugin.config = SimpleNamespace(namespace="default", namespaces=[], persist_entities=False)
    plugin.ready_event = asyncio.Event()
    plugin.ready_event.set()
    plugin.first_time = True
    entity = "binary_sensor.fixture_indoor_alarm"
    at = datetime(2026, 11, 16, tzinfo=timezone.utc)

    def snapshot(value, seconds):
        stamp = (at + timedelta(seconds=seconds)).isoformat()
        return dict(entity_id=entity, state=value, last_changed=stamp, last_updated=stamp, attributes={})

    await state.set_namespace_state("default", {entity: snapshot("off", -86400)})
    initial_sync_events = len(captured)
    for index, (previous, current, old_at, new_at) in enumerate([
        ("off", "on", -86400, 0), ("on", "off", 0, 1),
        ("off", "off", 1, 1), ("off", "unknown", 1, 2), ("unknown", "off", 2, 3),
    ]):
        await plugin.receive_event(dict(event_type="state_changed", origin="LOCAL",
            time_fired=(at + timedelta(seconds=index + 10)).isoformat(), context=dict(id=f"fictional-context-{index}"),
            data=dict(entity_id=entity, old_state=snapshot(previous, old_at), new_state=snapshot(current, new_at))))
    management = object.__new__(PluginManagement)
    management.AD, management.plugin_objs = ad, ad.plugins.plugin_objs
    await management.notify_plugin_stopped(plugin.name, "default")
    await plugin.notify_plugin_started({}, {entity: snapshot("off", -86400)})
    await asyncio.sleep(0)
    return dict(runtime="AppDaemon", version=importlib.metadata.version("appdaemon"),
                network="fictional offline input", initial_sync_event_count=initial_sync_events, events=captured)


def test_packaged_indoor_event_contract():
    """A cached initial sync is not a live transition and no producer order exists."""
    import pytest

    interpreter = os.environ.get("SAFETY_APPDAEMON_PYTHON")
    if not interpreter:
        pytest.skip("Requires actual AppDaemon interpreter; bundled stub is insufficient")
    result = subprocess.run([interpreter, "-I", str(Path(__file__).resolve())], capture_output=True,
                            text=True, check=True, timeout=20)
    evidence = json.loads(result.stdout)
    fixture = json.loads((Path(__file__).parent / "fixtures" / "indoor_event_contract.json").read_text(encoding="utf-8"))
    assert evidence == fixture
    assert evidence["initial_sync_event_count"] == 0
    assert [item["event"] for item in evidence["events"]] == ["state_changed"] * 5 + ["plugin_stopped", "plugin_started"]
    assert all("producer_sequence" not in item["data"] for item in evidence["events"])


if __name__ == "__main__":
    print(json.dumps(asyncio.run(probe()), sort_keys=True))
