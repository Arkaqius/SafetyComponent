"""Explicit input bindings and owned lifecycle for callback-based mechanisms."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from components.core.lifecycle import CancellationKind, LifecycleScope
from components.core.types_common import ExecutionOutcome


class SafetyMechanism:
    """Record configuration inertly; start and enable evaluation independently."""

    def __init__(
        self, hass_app: Any, callback: Callable[..., Any], name: str,
        isEnabled: bool, *, monitored_entities: Iterable[str] = (),
        scope: LifecycleScope | None = None, **kwargs: Any,
    ) -> None:
        self.hass_app = hass_app
        self.callback = callback
        self.name = name
        self.entities = list(dict.fromkeys(monitored_entities))
        self.sm_args: dict[str, Any] = kwargs
        self.scope = scope or LifecycleScope(name, enabled=isEnabled)
        self.scope.set_enabled(isEnabled)
        self.last_outcome: ExecutionOutcome | None = None
        self.on_invalidate: Callable[[], None] | None = None
        for entity in self.entities:
            self.scope.declare(
                f"state:{entity}", CancellationKind.STATE,
                self._listen_entity(entity),
                self.entity_changed, self.hass_app.cancel_listen_state,
            )

    def _listen_entity(self, entity: str) -> Callable[[Callable[..., Any]], Any]:
        def register(callback: Callable[..., Any]) -> Any:
            return self.hass_app.listen_state(callback, entity)
        return register

    @property
    def isEnabled(self) -> bool:
        """Expose legacy enable access through lifecycle eligibility."""
        return self.scope.enabled

    @isEnabled.setter
    def isEnabled(self, enabled: bool) -> None:
        invalidating = self.scope.enabled and not enabled
        self.scope.set_enabled(enabled)
        if invalidating and self.on_invalidate is not None:
            self.on_invalidate()

    def start(self) -> None:
        """Register explicit inputs once, without changing enabled intent."""
        self.scope.start()

    def stop(self) -> None:
        """Fence and cancel work without clearing domain danger."""
        self.scope.stop()
        if self.on_invalidate is not None:
            self.on_invalidate()

    def setup_listeners(self) -> None:
        """Retain the legacy registration entry point as idempotent start."""
        self.start()

    def run_in(
        self, channel: str, callback: Callable[..., Any], delay: float, **kwargs: Any,
    ) -> Any:
        """Own a replaceable qualification timer under a domain channel."""
        return self.scope.schedule(
            channel, lambda cb: self.hass_app.run_in(cb, delay, **kwargs),
            callback, self.hass_app.cancel_timer,
        )

    def entity_changed(self, entity: str, *args: Any, **kwargs: Any) -> None:
        """Admit only a current eligible callback; domain owns evaluation telemetry."""
        if self.scope.eligible:
            if getattr(self.callback, "manages_evaluation", False):
                self.callback(self)
                return
            recorder = getattr(getattr(self.callback, "__self__", None), "record_evaluation", None)
            success = False
            try:
                self.callback(self)
                success = True
            finally:
                if callable(recorder):
                    recorder(success=success)

    def disable_sm(self, sm_name: str) -> None:
        """Retain legacy disable without granting clear permission."""
        self.isEnabled = False
