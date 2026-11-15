# Contract: Fault Response and Publication Isolation

## Commit and Admission

FaultManager applies valid evidence to authoritative in-memory fault state before
response admission. Create one immutable internal `FaultResponseEvent` containing
runtime, incident, transition revision/event ID, fault/symptom identities, state,
severity and bounded allowlisted context. Keep existing external IDs and adapt
existing handler arguments at a single boundary; transport workers never receive
mutable fault/component objects.

Admit NotificationManager lifecycle changes before RecoveryManager policy work,
without waiting for MQTT, persistence or remote service completion. A consumer
exception is caught at its registered isolated response boundary, recorded locally
and does not stop remaining eligible consumers. Other EventBus channels retain
their explicit prerequisite/failure semantics. Expose failed consumer admission;
do not record it as successful notification or automatically replay a command.
Preserve per-incident order and revision; consumer deduplication is generation-
scoped and bounded by the configured fault catalog and current incidents.

Failure reporting uses bounded counters and latest local error, not a recursively
published fault event. Authoritative state remains available even while diagnostics
cannot reach HA. Local admission and decision must fit the existing decision
allocation, including the weather `T_ext_decision <= 1 s` budget.

## Asynchronous Service Adapter

Use supported AppDaemon `call_service(..., callback=...)` background completion,
with no `return_result`, `timeout` or `hass_timeout` arguments. Validate the actual
packaged >=4.5,<5 HASS adapter in a non-household integration harness. Unsupported
completion semantics fail admission explicitly; no silent blocking fallback.

Separate service lanes by target/resource: each configured mobile target has one
in-flight lease; MQTT has its own projection lane; local electrical outputs and
recovery commands serialize per affected physical resource. A stalled mobile
target cannot consume another target's lease. Submission callbacks only append
immutable completion to a bounded mailbox. The owner-thread drain checks runtime,
operation, incident revision and authorization identities before applying results.
Acquire/register the lease and its completion credit before invoking AppDaemon;
the test adapter may complete synchronously. Normalize completion/error fields to
at most 4 KiB per record. A fast callback cannot race an absent lease or create an
extra in-flight operation.
Immediate scheduling return is not delivery acceptance; completion follows the
existing AppDaemon acceptance interpretation and never proves phone delivery.

Retain unresolved leases in a lock-protected process-lifetime infrastructure
registry across AppDaemon app reloads. Store no mutable domain state there. All
registry creation and access must be serialized; AppDaemon `global_vars` alone
is not a locking primitive. Expiring an application deadline quarantines its
unresolved lease; it does not cancel HA work or authorize an overlapping replacement.
Do not create a new worker/thread per timeout. Release the lease only on actual
completion or proven process reset. An obsolete completion may release its old
lease, but may not update the new domain outcome or replay an action.

An already-submitted physical command cannot be recalled. A timed-out command
remains execution-unknown until its reviewed physical postcondition/reconciliation
resolves it; never retry a physical command automatically because a callback was
lost. A currently queued local-output intent must pass latest gas/output policy
immediately before dispatch. Stop invalidates unsent intents and preserves
restrictions without sending an off/reset command.

## Resource Bounds and Overload

Each configured target has one in-flight and one latest unsent intent per active
tag; quiet context changes coalesce without downgrading an undelivered new alert.
Keep lifecycle/control changes (clear, acknowledge, shadow, urgency change) ordered
by revision. Only one serialized service call per resource is in flight; do not
send an old clear after a newer SET. Target quarantine leaves pending uncertainty
visible; a same-target alert may be delayed, while other targets remain independent.

The per-application pending-intent limit is 1024 records / 4 MiB total, with 64 KiB
maximum per immutable service payload. These are infrastructure limits validated
before enqueue, not new installation configuration fields. Completion mailboxes
reserve one slot per admitted in-flight lease, so a result cannot be dropped merely
because pending intents are full. Drain at most 64 completions per scheduler tick;
the owned drain runs at least once per second within the assigned scheduling
budget. Per-target leases are bounded by the finite validated target/resource
catalog; arbitrary events cannot create new service resources.

The process broker has 64 total lease/completion credits: reserve capacity for
one MQTT lane, two local-output resources and one recovery-command resource;
remaining credits serve mobile targets. Credits stay held until the owner drains
completion, not merely until a callback enqueues it. The completion mailbox is
therefore at most 64 records, even under rapid completion/reuse. A retired resource
with unresolved work still consumes its credit; an idle retired resource may be
removed. Repeated configuration changes/reloads cannot accumulate unbounded
leases. Capacity exhaustion exposes unavailable delivery capacity rather than
creating new workers or calling a synchronous fallback. Other available reserved
adapter lanes remain independent. These process limits include all generations.

Overflow rejects or coalesces unsent work explicitly, retains authoritative danger
and records affected delivery/publication uncertainty. Never silently evict an
unresolved domain assertion or label an unattempted alert delivered. Existing
L1/L2/L3 deadlines include queueing, scheduling and submission, not a fresh allowance
after dequeue. Overload is failure evidence, not a claim of meeting all deadlines.

## Publication and Persistence

Keep MqttEntityManager's public register/publish calls and stable topics; calls
update desired projection and enqueue without blocking response processing.
Track desired and accepted revisions separately. For each entity, discovery
precedes its attributes/state publication; coalesce only whole coherent unsent
projection groups, including lifecycle and active attributes. Retained discovery,
transient state, heartbeat and explicit retired-entity cleanup keep their contracts.
Availability online is queued only after its required startup publication barrier;
an old runtime cannot publish online/state after its offline fence. MQTT blockage
does not prevent alarm evaluation or available non-MQTT responses.

The offline fence is an ordered publication barrier, not the instant of logical
stop. An already-handed-off MQTT call cannot be cancelled by an app generation
check. Publish the offline barrier only after that call's actual completion;
while its lease is quarantined, remote offline publication is unconfirmed and
configured expiry remains an independent liveness limit. Old/new runtime traffic
must never bypass that outstanding lease. Tests distinguish no new obsolete
submission/owner mutation from external effects already in flight; they must not
claim that logical stop guarantees immediate remote offline state.

Bound pending MQTT projection to 4096 entity groups / 8 MiB and 256 KiB per group.
Overflow exposes publication uncertainty; domain state is never evicted. Cache
acknowledgement follows actual publication completion; retries use desired current
projection, not a historical heartbeat snapshot. MQTT service completion is not
proof that every subscriber received the state.

Multi-topic MQTT publication is not atomic. Preserve the existing publication
state/attribute cross-check and expose publication revision where needed;
consumers must show uncertainty for mismatched snapshots rather than infer clear.
A late acceptance may be recorded as historical evidence but shall not erase a
deadline miss, renew an expired deadline or restore superseded content.

Notification persistence snapshots are immutable and use one writer with one
coalesced pending generation in the existing namespace. Failed writes report
durability uncertainty without suppressing current danger or other adapters.
Recovery authorization remains stricter: proposal/token consumption must be
durably acknowledged for the exact current generation before any command handoff.
At actual queued-command dispatch, the RecoveryManager owner must revalidate
current incident, resource, consent/token expiry, restrictions, output eligibility
and physical postcondition policy after exact durable acknowledgement and before
handoff to AppDaemon. A valid decision made at enqueue is insufficient. A failed
check cancels unsent intent without consuming a fresh execution permission;
reconciliation cannot replay a previously handed-off command.
No worker completion may bypass policy, consent expiry or a new restriction.
Keep existing per-owner payload limits and atomic store semantics; shared SQLite
does not imply a cross-manager transaction. Do not claim a snapshot durable on enqueue.

## Verification and Traceability

FR-016..018/023; SC-007/008/010 -> SWR-FLT-026/027, SWR-NOT-012/017,
SWR-MQTT-007 and existing recovery authorization requirements.

Test MQTT failure before/after activation, throwing first consumer, one permanently
stalled target with healthy independent targets, notification/persistence failure,
repeated reload with a quarantined lease, duplicate/late completion, superseding
SET/clear/acknowledgement, resource/byte bounds and gas restriction before queued
local dispatch. Assert no action duplication, no accepted-state cache on scheduling
return, no blocking fault admission and no unsupported AppDaemon service arguments.
All service calls are simulated; no household action is needed for verification.
