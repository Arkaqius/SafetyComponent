"""Exercise the packaged HASS callback adapter using a fictional offline socket.

Set SAFETY_APPDAEMON_PYTHON to an isolated interpreter containing the packaged
runtime. The subprocess uses -I so the bundled Hass stub cannot shadow it.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
from typing import Any


class FictionalSocket:
    """Replace only network transport, retaining real service/result processing."""

    def __init__(self, plugin: Any, mode: str) -> None:
        self.plugin = plugin
        self.mode = mode
        self.requests: list[dict[str, Any]] = []
        self.release = asyncio.Event()

    async def send_json(self, request: dict[str, Any]) -> None:
        """Return a fictional HA envelope or inject a specific transport failure."""
        self.requests.append(request)
        if self.mode == "throw":
            raise RuntimeError("fictional transport failure")
        if self.mode == "never":
            await self.release.wait()
            return
        if self.mode == "timeout":
            return
        response: dict[str, Any] = {
            "id": request["id"], "type": "result",
            "success": self.mode != "failure", "result": None,
        }
        if self.mode == "failure":
            response["error"] = {"code": "fictional", "message": "rejected"}
        asyncio.get_running_loop().call_soon(
            lambda: asyncio.create_task(self.plugin.receive_result(response))
        )


async def probe_scenario(mode: str, *, use_broker: bool = False) -> dict[str, Any]:
    """Call actual HASS, Services and websocket adapters without a HA connection."""
    from appdaemon.plugins.hass.hassapi import Hass
    from appdaemon.plugins.hass.hassplugin import HassPlugin
    from appdaemon.services import Services

    logger = logging.getLogger("fictional-service-contract")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    tasks: list[Any] = []
    ad = SimpleNamespace(
        loop=asyncio.get_running_loop(), main_thread_id=threading.get_ident(),
        stopping=False,
        config=SimpleNamespace(internal_function_timeout=1, suppress_log_messages=False),
        logging=SimpleNamespace(get_child=lambda _: logger, get_error=lambda: logger,
                                separate_error_log=lambda: False),
        futures=SimpleNamespace(add_future=lambda _, task: tasks.append(task)),
    )
    plugin = object.__new__(HassPlugin)
    plugin.AD, plugin.logger, plugin.error = ad, logger, logger
    # Keep the fictional deadline above Windows' 15.625 ms monotonic clock quantum.
    plugin.config = SimpleNamespace(namespace="default", namespaces=[], ws_timeout=0.1)
    plugin.connect_event = asyncio.Event()
    if mode != "disconnected":
        plugin.connect_event.set()
    plugin.services = {"notify": {"fixture": {}}}
    plugin.id = 0
    plugin._result_futures, plugin._silent_results, plugin._request_context = {}, {}, {}
    plugin.bytes_sent = plugin.bytes_recv = plugin.requests_sent = plugin.updates_recv = 0
    plugin.ws = FictionalSocket(plugin, mode)
    ad.services = Services(ad)
    ad.services.services = {}
    ad.services.register_service("default", "notify", "fixture", plugin.call_plugin_service, silent=True)
    app = object.__new__(Hass)
    app.AD, app.logger = ad, logger
    app._config_model = SimpleNamespace(name="fictional-contract")
    app._namespace = "default"
    received: list[Any] = []
    callback_threads: list[int] = []
    owner_threads: list[int] = []
    broker: Any = None
    receiver_time = [0.0]

    if use_broker:
        # Keep only backend on sys.path; never import the bundled test Hass stub.
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from components.core.service_dispatcher import (
            Lane, ProcessLeaseRegistry, ResourceSpec, ServiceDispatcher,
        )
        app.run_every = lambda *_args, **_kwargs: "fictional-timer"
        app.cancel_timer = lambda *_args, **_kwargs: None
        broker = ServiceDispatcher(
            app, [ResourceSpec("notify/fixture", Lane.MOBILE, frozenset({"notify/fixture"}))],
            registry=ProcessLeaseRegistry(), clock=lambda: receiver_time[0],
        )
        broker.start()

    def completed(result: Any) -> None:
        received.append(result)
        callback_threads.append(threading.get_ident())

    def invoke() -> Any:
        owner_threads.append(threading.get_ident())
        if broker is not None:
            request = broker.make_intent(
                resource="notify/fixture", service="notify/fixture", payload={"message": "Fictional test"},
                tag="fictional", revision=1, deadline_at=30,
            )
            broker.enqueue(request, on_complete=lambda receipt: completed({
                "status": receipt.status.value, "deadline_missed": receipt.deadline_missed,
            }))
            broker.tick()
            return None
        return app.call_service("notify/fixture", message="Fictional test", callback=completed)

    owner_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fictional-app-owner")
    scheduled = await asyncio.get_running_loop().run_in_executor(owner_pool, invoke)
    # Wait for the finite cases; the hung fake socket is released only for cleanup.
    for _ in range(100):
        if received or (broker is not None and broker.registry.completion_count):
            break
        await asyncio.sleep(0.002)
        if mode == "never":
            break
    before_owner_drain = len(received)
    credits_before_owner_drain = broker.registry.lease_count if broker is not None else None
    if broker is not None:
        if mode == "never":
            receiver_time[0] = 30
        await asyncio.get_running_loop().run_in_executor(owner_pool, broker.tick)
    result = {
        "mode": mode, "scheduling_return": scheduled, "completion": list(received),
        "callback_on_owner": any(t == owner_threads[0] for t in callback_threads),
        "request_count": len(plugin.ws.requests),
        "before_owner_drain": before_owner_drain,
        "credits_before_owner_drain": credits_before_owner_drain,
        "lease_count": broker.registry.lease_count if broker is not None else None,
        "quarantined": broker.registry.quarantined_count if broker is not None else None,
    }
    if broker is not None:
        broker.stop()
    if mode == "never":
        plugin.ws.release.set()
        await asyncio.sleep(0.02)
    owner_pool.shutdown(wait=True)
    return result


async def probe_packaged_runtime() -> dict[str, Any]:
    """Collect facts without applying any application acceptance interpretation."""
    return {
        "version": importlib.metadata.version("appdaemon"),
        "scenarios": [await probe_scenario(mode) for mode in (
            "success", "failure", "timeout", "disconnected", "throw", "never",
        )],
        "broker_scenarios": [await probe_scenario(mode, use_broker=True) for mode in (
            "success", "failure", "timeout", "disconnected", "throw", "never",
        )],
    }


def test_actual_packaged_callback_contract() -> None:
    """Preserve the distinction between successful empty envelope and bare None."""
    import pytest

    interpreter = os.environ.get("SAFETY_APPDAEMON_PYTHON")
    if not interpreter:
        pytest.skip("Packaged runtime evidence requires SAFETY_APPDAEMON_PYTHON; stub is insufficient")
    process = subprocess.run(
        [interpreter, "-I", str(Path(__file__).resolve())],
        capture_output=True, text=True, timeout=30, check=True,
    )
    evidence = json.loads(process.stdout)
    assert evidence["version"] == "4.5.13"
    cases = {case["mode"]: case for case in evidence["scenarios"]}
    assert all(case["scheduling_return"] is None for case in cases.values())
    assert all(not case["callback_on_owner"] for case in cases.values())
    assert cases["success"]["completion"][0]["success"] is True
    assert cases["success"]["completion"][0]["result"] is None
    assert cases["failure"]["completion"][0]["success"] is False
    assert cases["timeout"]["completion"][0]["ad_status"] == "TIMEOUT"
    assert cases["disconnected"]["completion"] == cases["throw"]["completion"] == [None]
    assert cases["disconnected"]["request_count"] == 0
    assert cases["throw"]["request_count"] == 1
    assert cases["never"]["completion"] == []
    broker_cases = {case["mode"]: case for case in evidence["broker_scenarios"]}
    assert all(case["scheduling_return"] is None and case["before_owner_drain"] == 0
               and case["credits_before_owner_drain"] == 1 for case in broker_cases.values())
    assert broker_cases["success"]["completion"][0]["status"] == "accepted_by_home_assistant"
    for name in ("failure", "timeout", "disconnected", "throw"):
        assert broker_cases[name]["completion"][0]["status"] != "accepted_by_home_assistant"
        assert broker_cases[name]["lease_count"] == 0
        assert broker_cases[name]["callback_on_owner"]
    assert broker_cases["never"]["completion"] == []
    assert broker_cases["never"]["lease_count"] == broker_cases["never"]["quarantined"] == 1


if __name__ == "__main__":
    print(json.dumps(asyncio.run(probe_packaged_runtime())))
