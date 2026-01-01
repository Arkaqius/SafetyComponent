"""Minimal stub of appdaemon Hass API for tests."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional


class DummyLogger:
    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        return None

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        return None

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        return None

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        return None

    def __call__(self, msg: str, *args: Any, **kwargs: Any) -> None:
        return None


class Hass:
    def __init__(
        self,
        ad: Optional[Any] = None,
        name: Optional[str] = None,
        logger: Optional[Any] = None,
        args: Optional[Dict[str, Any]] = None,
        config: Optional[Any] = None,
        app: Optional[Any] = None,
        global_vars: Optional[Any] = None,
    ) -> None:
        self.AD = ad
        self.name = name
        self.logger = logger or getattr(ad, "logger", DummyLogger())
        self.args = args or {}
        self.config = config
        self.app_config = app
        self.global_vars = global_vars
        self._state: dict[str, Any] = {}

        # If a mocked AppDaemon instance provides helpers, reuse them
        self.set_state = getattr(ad, "set_state", self.set_state)  # type: ignore
        self.get_state = getattr(ad, "get_state", self.get_state)  # type: ignore
        self.call_service = getattr(ad, "call_service", self.call_service)  # type: ignore
        self.run_in = getattr(ad, "run_in", self.run_in)  # type: ignore
        self.listen_state = getattr(ad, "listen_state", self.listen_state)  # type: ignore

    def log(self, msg: str, *args: Any, **kwargs: Any) -> None:
        if hasattr(self.logger, "info"):
            try:
                self.logger.info(msg, *args, **kwargs)
            except Exception:
                pass
        return None

    def set_state(self, entity_id: str, state: Any = None, attributes: Optional[dict] = None, **kwargs: Any) -> None:
        self._state[entity_id] = {"state": state, "attributes": attributes or {}}

    def get_state(self, entity_id: str, **kwargs: Any) -> Any:
        return self._state.get(entity_id, {}).get("state")

    def call_service(self, service: str, **kwargs: Any) -> None:
        return None

    def stop_app(self, name: Optional[str]) -> None:
        self._stopped = name

    def run_in(self, callback: Callable, delay: int, **kwargs: Any) -> Any:
        # In test mode, immediately execute the callback to keep behavior predictable
        return callback(**kwargs)

    def listen_state(self, callback: Callable, entity: str, **kwargs: Any) -> Any:
        # Return a dummy handle for cancellation in potential future extensions
        return (callback, entity, kwargs)

    def cancel_timer(self, handle: Any) -> None:
        return None
