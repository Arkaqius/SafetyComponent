"""Bounded coherent MQTT projections over the process-owned service lane."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
import json
from typing import Any

from components.core.lifecycle import CancellationKind, LifecycleScope
from components.core.service_dispatcher import (
    Admission, CompletionStatus, MAX_PAYLOAD_BYTES, ServiceCompletion, ServiceDispatcher,
)

MAX_GROUPS = 4096
MAX_GROUP_BYTES = 256 * 1024
MAX_QUEUE_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class ProjectionGroup:
    """A whole immutable entity projection, including ordered topic messages."""

    entity: str
    revision: int
    messages: tuple[str, ...]
    snapshot_json: str

    @property
    def byte_size(self) -> int:
        """Count all encoded messages and cached acceptance evidence."""
        return len((self.snapshot_json + "".join(self.messages) + self.entity).encode("utf-8")) + 64


class MqttProjectionQueue:
    """Coalesce unsent groups and acknowledge only complete, explicit success.

    A partial group is uncertain. Its completion never acknowledges a newer
    desired revision, and retry reads the owner's current desired projection.
    Only one topic call is outstanding; the process broker serializes reloads.
    """

    def __init__(
        self, dispatcher: ServiceDispatcher,
        on_accepted: Callable[[ProjectionGroup], None],
        on_retry: Callable[[str], None],
    ) -> None:
        self.dispatcher = dispatcher
        self.on_accepted, self.on_retry = on_accepted, on_retry
        self.scope = LifecycleScope("mqtt_projection", enabled=True)
        self.pending: OrderedDict[str, ProjectionGroup] = OrderedDict()
        self.pending_bytes = 0
        self.active: ProjectionGroup | None = None
        self.index = 0
        self._waiting = False
        self._revision = 0
        self.desired_revisions: dict[str, int] = {}
        self.accepted_revisions: dict[str, int] = {}
        self.failures = 0
        self.last_error: str | None = None
        self.uncertain: set[str] = set()

    def start(self) -> None:
        """Own the one-second projection drain and recreate it on restart."""
        self.scope.enabled = True
        self.scope.start()
        app = self.dispatcher.app
        self.scope.declare(
            "drain", CancellationKind.TIMER,
            lambda callback: app.run_every(callback, "now", 1), self.tick, app.cancel_timer,
        )

    def stop(self) -> None:
        """Invalidate unsent groups; external in-flight effects remain tracked."""
        self.scope.stop()
        self.pending.clear()
        self.pending_bytes = 0
        self.active = None
        self._waiting = False

    def enqueue(self, entity: str, messages: list[dict[str, Any]], snapshot: dict[str, Any]) -> bool:
        """Validate bounds before admitting any part of the entity group."""
        self._revision += 1
        # A rejected newer desired projection still fences all older clear work.
        self.desired_revisions[entity] = self._revision
        try:
            encoded = tuple(json.dumps(message, ensure_ascii=False, allow_nan=False) for message in messages)
            group = ProjectionGroup(entity, self._revision, encoded,
                                    json.dumps(snapshot, ensure_ascii=False, allow_nan=False))
        except (TypeError, ValueError, RecursionError):
            return self._reject(entity, "invalid_projection")
        previous = self.pending.get(entity)
        size = self.pending_bytes - (previous.byte_size if previous else 0) + group.byte_size
        if (not messages or len(entity) > 255 or group.byte_size > MAX_GROUP_BYTES
                or any(len(message.encode("utf-8")) > MAX_PAYLOAD_BYTES for message in encoded)
                or size > MAX_QUEUE_BYTES or (previous is None and len(self.pending) >= MAX_GROUPS)):
            return self._reject(entity, "projection_overload")
        self.pending[entity] = group
        self.pending_bytes = size
        return True

    def _reject(self, entity: str, error: str) -> bool:
        self.failures += 1
        self.last_error = error
        self.uncertain.add(entity)
        return False

    def tick(self, **_: Any) -> None:
        """Admit one topic after the previous real completion has been drained."""
        if not self.scope.eligible:
            return
        fence = self.dispatcher.registry.next_mqtt_fence()
        if fence is not None:
            return
        if self._waiting:
            return
        if self.active is None:
            if not self.pending:
                return
            for entity, candidate in tuple(self.pending.items()):
                snapshot = json.loads(candidate.snapshot_json)
                barrier = snapshot.get("barrier", {})
                blocked = any(self.accepted_revisions.get(key, 0) < revision for key, revision in barrier.items())
                if snapshot.get("availability") is True and (blocked or self.uncertain - {"availability"}):
                    self.pending.move_to_end(entity)
                else:
                    self.pending.move_to_end(entity, last=False)
                    break
            else:
                return
            entity_key, self.active = self.pending.popitem(last=False)
            self.pending_bytes -= self.active.byte_size
            self.index = 0
        group = self.active
        payload = json.loads(group.messages[self.index])
        request = self.dispatcher.make_intent(
            resource="mqtt", service="mqtt/publish", payload=payload, tag="mqtt-projection",
            revision=self.dispatcher.next_revision("mqtt", "mqtt-projection"),
            deadline_at=self.dispatcher.clock() + 30,
            incident_id=f"{group.entity}:{group.revision}",
        )
        self._waiting = True

        def completed(result: ServiceCompletion) -> None:
            if self.active is not group:
                return
            if result.status != CompletionStatus.ACCEPTED or result.deadline_missed:
                self._reject(group.entity, result.status.value)
                self.active = None
                self._waiting = False
                if group.entity not in self.pending:
                    self.on_retry(group.entity)
                return
            self._waiting = False
            self.index += 1
            if self._superseded_unsafe(group):
                self.uncertain.add(group.entity)
                self.active = None
                return
            if self.index == len(group.messages):
                self.accepted_revisions[group.entity] = group.revision
                if self.desired_revisions.get(group.entity) == group.revision:
                    self.uncertain.discard(group.entity)
                self.active = None
                self.on_accepted(group)

        callback = self.scope.guard(completed)
        admission = self.dispatcher.enqueue(
            request, on_complete=callback, on_deadline=callback,
            before_dispatch=lambda _: (
                self.scope.eligible and self.active is group
                and not self._superseded_unsafe(group)
            ),
        )
        if admission not in {Admission.QUEUED, Admission.COALESCED}:
            self._waiting = False
            self._reject(group.entity, admission.value)

    def _superseded_unsafe(self, group: ProjectionGroup) -> bool:
        if self.desired_revisions.get(group.entity) == group.revision:
            return False
        latest = self.pending.get(group.entity)
        if latest is None:
            return True
        previous, desired = json.loads(group.snapshot_json), json.loads(latest.snapshot_json)
        # Context-only refresh must not starve a coherent group. A changed
        # safety state or a rejected newer projection always fences old work.
        return any(previous.get(key) != desired.get(key) for key in ("state", "has_state", "removed", "availability")) or (
            (previous.get("attributes") or {}).get("active") != (desired.get("attributes") or {}).get("active")
        )

    def retire(self, entity: str) -> None:
        """Retire idle receipt metadata only after retained deletion completes."""
        if entity not in self.pending and (self.active is None or self.active.entity != entity):
            self.desired_revisions.pop(entity, None)
            self.accepted_revisions.pop(entity, None)
            self.uncertain.discard(entity)
