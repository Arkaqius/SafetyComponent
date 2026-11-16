"""Exercise the packaged HASS callback adapter using a fictional offline socket.

Set SAFETY_APPDAEMON_PYTHON to an isolated interpreter containing the packaged
runtime. The subprocess uses -I so the bundled Hass stub cannot shadow it.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import subprocess
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


async def probe_scenario(mode: str) -> dict[str, Any]:
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
    plugin.config = SimpleNamespace(namespace="default", namespaces=[], ws_timeout=0.01)
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

    def completed(result: Any) -> None:
        received.append(result)
        callback_threads.append(threading.get_ident())

    def invoke() -> Any:
        owner_threads.append(threading.get_ident())
        return app.call_service("notify/fixture", message="Fictional test", callback=completed)

    scheduled = await asyncio.to_thread(invoke)
    # Wait for the finite cases; the hung fake socket is released only for cleanup.
    for _ in range(100):
        if received:
            break
        await asyncio.sleep(0.002)
        if mode == "never":
            break
    result = {
        "mode": mode, "scheduling_return": scheduled, "completion": list(received),
        "callback_on_owner": any(t == owner_threads[0] for t in callback_threads),
        "request_count": len(plugin.ws.requests),
    }
    if mode == "never":
        plugin.ws.release.set()
        await asyncio.sleep(0.02)
    return result


async def probe_packaged_runtime() -> dict[str, Any]:
    """Collect facts without applying any application acceptance interpretation."""
    return {
        "version": importlib.metadata.version("appdaemon"),
        "scenarios": [await probe_scenario(mode) for mode in (
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


if __name__ == "__main__":
    print(json.dumps(asyncio.run(probe_packaged_runtime())))
