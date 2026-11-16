"""Bounded owner admission and process-lifetime HA service completion leases."""

from __future__ import annotations

import builtins
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
import json
import math
from threading import RLock
from time import monotonic
from typing import Any
from uuid import uuid4

from components.core.lifecycle import CancellationKind, LifecycleScope

MAX_PENDING = 1024
MAX_PENDING_BYTES = 4 * 1024 * 1024
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_CREDITS = 64


class Lane(str, Enum):
    """Reserved independent adapter capacity, not household output policy."""

    MOBILE = "mobile"
    MQTT = "mqtt"
    LOCAL = "local"
    RECOVERY = "recovery"


LANE_CREDITS = {Lane.MOBILE: 60, Lane.MQTT: 1, Lane.LOCAL: 2, Lane.RECOVERY: 1}


class Admission(str, Enum):
    """Queue admission never establishes service acceptance or physical effect."""

    QUEUED = "queued"
    COALESCED = "coalesced"
    REJECTED = "rejected"
    OVERLOADED = "overloaded"


class CompletionStatus(str, Enum):
    """Transport evidence remains distinct from execution/physical confirmation."""

    ACCEPTED = "accepted_by_home_assistant"
    FAILED = "failed"
    UNKNOWN = "unknown"
    CANCELLED = "cancelled_unsent"
    DEADLINE_MISSED = "deadline_missed"


@dataclass(frozen=True)
class ResourceSpec:
    """Finite resource/service allowlist established from validated configuration."""

    key: str
    lane: Lane
    services: frozenset[str]


@dataclass(frozen=True)
class ServiceIntent:
    """Immutable serialized request carrying its original absolute deadline."""

    operation_id: str
    runtime_id: str
    generation: int
    resource: str
    service: str
    payload_json: str
    tag: str
    revision: int
    enqueued_at: float
    deadline_at: float
    incident_id: str = ""

    @property
    def payload(self) -> dict[str, Any]:
        """Copy the validated payload before handoff to the external adapter."""
        value: dict[str, Any] = json.loads(self.payload_json)
        return value

    @property
    def byte_size(self) -> int:
        """Count serialized payload and identity overhead against the queue budget."""
        return len(json.dumps(vars(self), ensure_ascii=False).encode("utf-8"))


@dataclass(frozen=True)
class ServiceCompletion:
    """Bounded immutable callback evidence, consumed only on the current owner."""

    operation_id: str
    runtime_id: str
    generation: int
    resource: str
    tag: str
    revision: int
    status: CompletionStatus
    completed_at: float
    error: str = ""
    deadline_missed: bool = False
    handed_off: bool = False


@dataclass
class _Lease:
    intent: ServiceIntent
    lane: Lane
    completion: ServiceCompletion | None = None
    quarantined: bool = False
    deadline_missed: bool = False
    handed_off: bool = False


@dataclass(frozen=True)
class MqttOfflineFence:
    """Process-owned offline barrier retained across an app's logical stop."""

    identity: str
    payload_json: str


class ProcessLeaseRegistry:
    """Retain at most 64 unresolved calls/completion credits across app reloads.

    This infrastructure stores immutable requests/results and transport ownership,
    never mutable components, managers or domain completion functions.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._leases: dict[str, _Lease] = {}
        self._operations: dict[str, str] = {}
        self._mailbox: deque[str] = deque()
        self._mqtt_fences: deque[MqttOfflineFence] = deque()
        self._mqtt_fence_failed = False

    def mqtt_offline_fence(self, payload: Mapping[str, Any]) -> MqttOfflineFence:
        """Retain a bounded immutable offline publication before stopping ingress."""
        if (set(payload) != {"topic", "payload", "retain", "qos"}
                or payload["payload"] != "offline" or payload["retain"] is not True
                or not isinstance(payload["topic"], str) or not payload["topic"]
                or payload["qos"] not in (0, 1, 2)):
            raise ValueError("Invalid MQTT offline fence")
        encoded = json.dumps(dict(payload), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ValueError("MQTT offline fence too large")
        with self._lock:
            for fence in self._mqtt_fences:
                if fence.payload_json == encoded:
                    return fence
            if len(self._mqtt_fences) >= MAX_CREDITS:
                self._mqtt_fence_failed = True
                raise ValueError("MQTT offline fence capacity exhausted")
            fence = MqttOfflineFence(uuid4().hex, encoded)
            self._mqtt_fences.append(fence)
            return fence

    def next_mqtt_fence(self) -> MqttOfflineFence | None:
        """Read only the oldest unacknowledged process publication barrier."""
        with self._lock:
            return self._mqtt_fences[0] if self._mqtt_fences else None

    def resource_busy(self, resource: str) -> bool:
        """Include unresolved and completed-but-undrained transport ownership."""
        with self._lock:
            return resource in self._leases

    def resource_quarantined(self, resource: str) -> bool:
        """Expose transport uncertainty without releasing a resource's lease."""
        with self._lock:
            lease = self._leases.get(resource)
            return lease is not None and lease.quarantined

    def acknowledge_mqtt_fence(self, identity: str) -> None:
        """Retire a barrier only after its actual explicit-success completion."""
        with self._lock:
            if self._mqtt_fences and self._mqtt_fences[0].identity == identity:
                self._mqtt_fences.popleft()

    def _mqtt_allowed(self, intent: ServiceIntent) -> bool:
        if intent.resource != "mqtt":
            return True
        if not self._mqtt_fences:
            return not self._mqtt_fence_failed
        fence = self._mqtt_fences[0]
        return (intent.tag == "mqtt-offline-fence" and intent.incident_id == fence.identity
                and intent.service == "mqtt/publish" and intent.payload_json == fence.payload_json)

    @property
    def lease_count(self) -> int:
        """Include completed-but-not-drained work in process credit accounting."""
        with self._lock:
            return len(self._leases)

    @property
    def completion_count(self) -> int:
        """Return reserved mailbox occupancy; duplicates never allocate a new slot."""
        with self._lock:
            return len(self._mailbox)

    @property
    def quarantined_count(self) -> int:
        """Count unresolved deadlines without treating timeouts as cancellation."""
        with self._lock:
            return sum(lease.quarantined for lease in self._leases.values())

    def acquire(self, intent: ServiceIntent, lane: Lane) -> bool:
        """Reserve the physical resource and mailbox credit before invoking HA."""
        with self._lock:
            if not self._mqtt_allowed(intent):
                return False
            if intent.resource in self._leases or intent.operation_id in self._operations:
                return False
            if len(self._leases) >= MAX_CREDITS:
                return False
            if sum(lease.lane == lane for lease in self._leases.values()) >= LANE_CREDITS[lane]:
                return False
            self._leases[intent.resource] = _Lease(intent, lane)
            self._operations[intent.operation_id] = intent.resource
            return True

    def complete(self, operation_id: str, response: Any, completed_at: float) -> None:
        """Normalize one callback into its already-reserved mailbox slot only."""
        with self._lock:
            resource = self._operations.get(operation_id)
            lease = self._leases.get(resource) if resource is not None else None
            if lease is None or lease.completion is not None:
                return
            try:
                if isinstance(response, Mapping) and response.get("success") is True:
                    status, error = CompletionStatus.ACCEPTED, ""
                elif isinstance(response, Mapping) and response.get("success") is False:
                    status, error = CompletionStatus.FAILED, str(response.get("error") or "service_rejected")[:512]
                elif isinstance(response, Exception):
                    status, error = CompletionStatus.FAILED, f"{type(response).__name__}: service_submission_failed"
                else:
                    status, error = CompletionStatus.UNKNOWN, "explicit_success_missing"
            except Exception:
                status, error = CompletionStatus.UNKNOWN, "completion_normalization_failed"
            request = lease.intent
            error = error.encode("utf-8")[:512].decode("utf-8", errors="ignore")
            missed = lease.deadline_missed or completed_at > request.deadline_at
            lease.deadline_missed = missed
            lease.completion = ServiceCompletion(
                request.operation_id, request.runtime_id, request.generation,
                request.resource, request.tag, request.revision, status,
                completed_at, error, missed, getattr(lease, "handed_off", True),
            )
            if (status == CompletionStatus.ACCEPTED and request.tag == "mqtt-offline-fence"
                    and self._mqtt_allowed(request)):
                self.acknowledge_mqtt_fence(request.incident_id)
            self._mailbox.append(operation_id)

    def release_unsent(self, operation_id: str) -> None:
        """Release only a reservation proven never handed to the HA adapter."""
        with self._lock:
            resource = self._operations.get(operation_id)
            lease = self._leases.get(resource) if resource is not None else None
            if lease is not None and not getattr(lease, "handed_off", True) and lease.completion is None:
                self._operations.pop(operation_id)
                self._leases.pop(lease.intent.resource)

    def mark_handoff(self, operation_id: str, clock: Callable[[], float]) -> bool:
        """Check time inside the acquired lock immediately before external handoff."""
        with self._lock:
            resource = self._operations.get(operation_id)
            lease = self._leases.get(resource) if resource is not None else None
            if lease is None:
                return False
            if not self._mqtt_allowed(lease.intent):
                return False
            now = clock()
            if not math.isfinite(now) or now >= lease.intent.deadline_at:
                return False
            lease.handed_off = True
            return True

    def expire(self, now: float) -> tuple[ServiceIntent, ...]:
        """Quarantine unresolved expired calls without releasing credit or replacement."""
        newly_expired = []
        with self._lock:
            for lease in self._leases.values():
                if lease.completion is None and now >= lease.intent.deadline_at:
                    lease.quarantined = True
                    if not lease.deadline_missed:
                        lease.deadline_missed = True
                        newly_expired.append(lease.intent)
        return tuple(newly_expired)

    def drain(self, limit: int = MAX_CREDITS) -> tuple[ServiceCompletion, ...]:
        """Release only actually completed leases, including retired generations."""
        completed = []
        with self._lock:
            for _ in range(min(limit, MAX_CREDITS)):
                if not self._mailbox:
                    break
                operation = self._mailbox.popleft()
                resource = self._operations.pop(operation)
                lease = self._leases.pop(resource)
                if lease.completion is not None:
                    completed.append(replace(
                        lease.completion, deadline_missed=lease.deadline_missed,
                    ))
        return tuple(completed)


def get_process_registry() -> ProcessLeaseRegistry:
    """Serialize singleton creation outside AppDaemon's reloadable module state."""
    # CPython's atomic setdefault publishes the sole creation lock across reloads.
    creation_lock = builtins.__dict__.setdefault("_safetycomponent_service_registry_lock", RLock())
    with creation_lock:
        existing = builtins.__dict__.get("_safetycomponent_service_registry")
        if existing is None:
            existing = ProcessLeaseRegistry()
            builtins.__dict__["_safetycomponent_service_registry"] = existing
        return existing


@dataclass
class _Pending:
    intent: ServiceIntent
    on_complete: Callable[[ServiceCompletion], None] | None
    before_dispatch: Callable[[ServiceIntent], bool] | None
    on_deadline: Callable[[ServiceCompletion], None] | None = None
    deadline_reported: bool = False


class ServiceDispatcher:
    """Fast bounded admission, independent resource handoff and owner-only drain."""

    def __init__(
        self, app: Any, resources: list[ResourceSpec], *,
        clock: Callable[[], float] = monotonic, registry: ProcessLeaseRegistry | None = None,
        runtime_id: str | None = None,
    ) -> None:
        self.resources = self._resource_catalog(resources)
        self.app = app
        self.clock = clock
        self.registry = registry if registry is not None else get_process_registry()
        self.scope = LifecycleScope("ServiceDispatcher", runtime_id=runtime_id, enabled=True)
        self._pending: dict[tuple[str, str], _Pending] = {}
        self._pending_bytes = 0
        self._inflight: dict[str, _Pending] = {}
        self._latest: dict[tuple[str, str], int] = {}
        self.deadline_misses = 0
        self.admission_failures = 0
        self.completion_failures = 0
        self.last_error: str | None = None
        self.service_failures: dict[str, str] = {}
        self.scope.declare(
            "completion_drain", CancellationKind.TIMER,
            lambda cb: app.run_every(cb, "now", 0.05, __silent=True), self.tick, app.cancel_timer,
        )

    @staticmethod
    def _resource_catalog(resources: list[ResourceSpec]) -> dict[str, ResourceSpec]:
        if len(resources) > 4096 or len({r.key for r in resources}) != len(resources):
            raise ValueError("Invalid service resource catalog")
        if any(not isinstance(resource.key, str) or not 1 <= len(resource.key) <= 255
               or resource.lane not in LANE_CREDITS or not resource.services
               or any(not isinstance(service, str) or not 1 <= len(service) <= 128
                      for service in resource.services) for resource in resources):
            raise ValueError("Invalid service resource specification")
        return {
            resource.key: ResourceSpec(resource.key, Lane(resource.lane), frozenset(resource.services))
            for resource in resources
        }

    def add_resources(self, resources: list[ResourceSpec]) -> None:
        """Add only trusted startup configuration; never replace an existing resource."""
        additions = self._resource_catalog(resources)
        if any(key in self.resources and self.resources[key] != value for key, value in additions.items()):
            raise ValueError("Cannot replace an admitted service resource")
        self.resources = self._resource_catalog(list({**self.resources, **additions}.values()))

    @property
    def pending_count(self) -> int:
        """Return unsent queue count independently of accepted/durable state."""
        return len(self._pending)

    def start(self) -> None:
        """Own a drain at least once per second without spawning service threads."""
        self.scope.start()
        self.scope.set_enabled(True)

    def stop(self) -> None:
        """Invalidate unsent work; process leases remain tracked, never cancelled."""
        self.scope.stop()
        self._pending.clear()
        self._pending_bytes = 0
        self._inflight.clear()
        self._latest.clear()

    def make_intent(
        self, *, resource: str, service: str, payload: dict[str, Any], tag: str,
        revision: int, deadline_at: float, incident_id: str = "",
    ) -> ServiceIntent:
        """Copy caller data before enqueue; malformed requests still fail admission."""
        return ServiceIntent(
            uuid4().hex, self.scope.runtime_id, self.scope.generation, resource, service,
            json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
            tag, revision, self.clock(), deadline_at, incident_id,
        )

    def enqueue(
        self, intent: ServiceIntent, *, on_complete: Callable[[ServiceCompletion], None] | None = None,
        before_dispatch: Callable[[ServiceIntent], bool] | None = None,
        on_deadline: Callable[[ServiceCompletion], None] | None = None,
    ) -> Admission:
        """Coalesce only unsent intent; never imply acceptance or replace a lease."""
        if not self._valid(intent):
            self.admission_failures += 1
            self.last_error = "invalid_service_intent"
            return Admission.REJECTED
        key = (intent.resource, intent.tag)
        if key in self._latest and intent.revision <= self._latest[key]:
            return Admission.REJECTED
        previous = self._pending.get(key)
        if previous is not None and previous.intent.incident_id == intent.incident_id:
            intent = replace(intent, enqueued_at=min(intent.enqueued_at, previous.intent.enqueued_at),
                             deadline_at=min(intent.deadline_at, previous.intent.deadline_at))
        size = self._pending_bytes - (previous.intent.byte_size if previous else 0) + intent.byte_size
        if (size > MAX_PENDING_BYTES or (previous is None and len(self._pending) >= MAX_PENDING)
                or (key not in self._latest and len(self._latest) >= MAX_PENDING)):
            self.admission_failures += 1
            self.last_error = "service_queue_overload"
            return Admission.OVERLOADED
        self._latest[key] = intent.revision
        self._pending[key] = _Pending(intent, on_complete, before_dispatch, on_deadline)
        self._pending_bytes = size
        return Admission.COALESCED if previous else Admission.QUEUED

    def _valid(self, intent: ServiceIntent) -> bool:
        try:
            return self._validate_intent(intent)
        except (ValueError, TypeError, AttributeError, RecursionError):
            return False

    def _validate_intent(self, intent: ServiceIntent) -> bool:
        resource = self.resources.get(intent.resource)
        if (not self.scope.eligible or resource is None or intent.service not in resource.services
                or intent.runtime_id != self.scope.runtime_id or intent.generation != self.scope.generation):
            return False
        if any(not isinstance(value, str) or len(value) > limit or not value
               for value, limit in ((intent.operation_id, 128), (intent.runtime_id, 128),
                                    (intent.resource, 255), (intent.service, 128), (intent.tag, 128))):
            return False
        if (not isinstance(intent.revision, int) or isinstance(intent.revision, bool)
                or not 0 <= intent.revision < 2 ** 63
                or not isinstance(intent.generation, int) or isinstance(intent.generation, bool)
                or not 0 <= intent.generation < 2 ** 63
                or not isinstance(intent.enqueued_at, (int, float)) or isinstance(intent.enqueued_at, bool)
                or not isinstance(intent.deadline_at, (int, float)) or isinstance(intent.deadline_at, bool)
                or not math.isfinite(intent.enqueued_at) or not math.isfinite(intent.deadline_at)
                or intent.deadline_at < intent.enqueued_at
                or not isinstance(intent.incident_id, str) or len(intent.incident_id) > 128
                or len(intent.payload_json.encode("utf-8")) > MAX_PAYLOAD_BYTES):
            return False
        try:
            payload = intent.payload
            json.dumps(payload, allow_nan=False)
            return isinstance(payload, dict) and not {
                "callback", "return_result", "timeout", "hass_timeout",
            }.intersection(payload)
        except (ValueError, TypeError):
            return False

    def tick(self, **_: Any) -> None:
        """Drain up to 64 completions, then admit independent eligible resources."""
        if not self.scope.eligible:
            return
        generation = self.scope.generation
        now = self.clock()
        for completion in self.registry.drain():
            if not self._owner_current(generation):
                return
            pending = self._inflight.pop(completion.operation_id, None)
            if pending is None or completion.runtime_id != self.scope.runtime_id or completion.generation != self.scope.generation:
                continue
            if completion.status == CompletionStatus.ACCEPTED:
                self.service_failures.pop(completion.resource, None)
            else:
                self.service_failures[completion.resource] = completion.error or completion.status.value
            if completion.deadline_missed and not pending.deadline_reported:
                self.deadline_misses += 1
            if self._latest.get((completion.resource, completion.tag)) == completion.revision:
                self._notify(pending, completion)
        if not self._owner_current(generation):
            return
        now = self.clock()
        for request in self.registry.expire(now):
            if not self._owner_current(generation):
                return
            pending = self._inflight.get(request.operation_id)
            if pending is not None and not pending.deadline_reported:
                pending.deadline_reported = True
                self.deadline_misses += 1
                if pending.on_deadline is not None and self.scope.eligible:
                    try:
                        pending.on_deadline(replace(
                            self._unsent(request, CompletionStatus.DEADLINE_MISSED, now), handed_off=True,
                        ))
                    except Exception as exc:
                        self.completion_failures += 1
                        self.last_error = f"deadline_observer:{type(exc).__name__}"
        self._admit_mqtt_fence()
        for key, pending in tuple(self._pending.items()):
            if not self._owner_current(generation):
                break
            request = pending.intent
            now = self.clock()
            if now >= request.deadline_at:
                self._remove_pending(key)
                self.deadline_misses += 1
                self._notify(pending, self._unsent(request, CompletionStatus.DEADLINE_MISSED, now))
                continue
            if not self.registry.acquire(request, self.resources[request.resource].lane):
                continue
            try:
                eligible = pending.before_dispatch is None or pending.before_dispatch(request)
            except Exception:
                eligible = False
            # A policy callback may stop or supersede this owner's unsent intent.
            # Never remove a replacement record or hand off a superseded clear.
            if self._pending.get(key) is not pending:
                self.registry.release_unsent(request.operation_id)
                continue
            if not self._owner_current(generation):
                self.registry.release_unsent(request.operation_id)
                return
            if not eligible:
                self.registry.release_unsent(request.operation_id)
                self._remove_pending(key)
                self._notify(pending, self._unsent(request, CompletionStatus.CANCELLED, now))
                continue
            now = self.clock()
            if now >= request.deadline_at:
                self.registry.release_unsent(request.operation_id)
                self._remove_pending(key)
                self.deadline_misses += 1
                self._notify(pending, self._unsent(request, CompletionStatus.DEADLINE_MISSED, now))
                continue
            if not self._owner_current(generation) or self._pending.get(key) is not pending:
                self.registry.release_unsent(request.operation_id)
                continue
            if not self.registry.mark_handoff(request.operation_id, self.clock):
                self.registry.release_unsent(request.operation_id)
                self._remove_pending(key)
                now = self.clock()
                status = CompletionStatus.DEADLINE_MISSED if now >= request.deadline_at else CompletionStatus.CANCELLED
                self.deadline_misses += int(status == CompletionStatus.DEADLINE_MISSED)
                self._notify(pending, self._unsent(request, status, now))
                continue
            self._remove_pending(key)
            self._inflight[request.operation_id] = pending
            # The callback captures process infrastructure and immutable identity only.
            registry, operation, clock = self.registry, request.operation_id, self.clock

            def completed(
                response: Any, operation_id: str = operation,
                completion_registry: ProcessLeaseRegistry = registry,
                completion_clock: Callable[[], float] = clock,
            ) -> None:
                completion_registry.complete(operation_id, response, completion_clock())

            try:
                self.app.call_service(request.service, callback=completed, **request.payload)
            except Exception as exc:
                registry.complete(operation, exc, clock())

    def _admit_mqtt_fence(self) -> None:
        # Offline is infrastructure-owned: stopping a projection owner must not
        # stop the barrier drain or require a new app before an idle-lane handoff.
        if "mqtt" not in self.resources or self.registry.resource_busy("mqtt"):
            return
        fence = self.registry.next_mqtt_fence()
        key = ("mqtt", "mqtt-offline-fence")
        if fence is None or key in self._pending:
            return
        request = self.make_intent(
            resource="mqtt", service="mqtt/publish", payload=json.loads(fence.payload_json),
            tag=key[1], revision=self.next_revision(*key),
            deadline_at=self.clock() + 30, incident_id=fence.identity,
        )
        self.enqueue(request)

    def _remove_pending(self, key: tuple[str, str]) -> None:
        pending = self._pending.pop(key)
        self._pending_bytes -= pending.intent.byte_size

    def _owner_current(self, generation: int) -> bool:
        return self.scope.eligible and self.scope.generation == generation

    def _notify(self, pending: _Pending, completion: ServiceCompletion) -> None:
        if not self.scope.eligible or pending.on_complete is None:
            return
        try:
            pending.on_complete(completion)
        except Exception as exc:
            self.completion_failures += 1
            self.last_error = f"owner_completion:{type(exc).__name__}"[:512]

    @staticmethod
    def _unsent(request: ServiceIntent, status: CompletionStatus, now: float) -> ServiceCompletion:
        return ServiceCompletion(request.operation_id, request.runtime_id, request.generation,
                                 request.resource, request.tag, request.revision, status, now,
                                 deadline_missed=status == CompletionStatus.DEADLINE_MISSED)

    def retire_tag(self, resource: str, tag: str) -> None:
        """Release idle receipt identity only after the domain retires that tag."""
        key = (resource, tag)
        if key not in self._pending and not any(
            pending.intent.resource == resource and pending.intent.tag == tag
            for pending in self._inflight.values()
        ):
            self._latest.pop(key, None)

    def next_revision(self, resource: str, tag: str) -> int:
        """Allocate caller revision intent from the current bounded owner receipt."""
        return self._latest.get((resource, tag), 0) + 1
