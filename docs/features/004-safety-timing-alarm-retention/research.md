# Research: Safety Timing and Indoor Alarm Retention

## R1 — Weather timing allocation

**Decision**: Maintainer confirmed on 2026-11-15: 120 seconds total to warning.
Allocate 5 seconds dispatch, 75 seconds weather confirmation in parallel with
60 seconds door/gate qualification, 9 seconds scheduling/reconciliation + 1 second decision and
30 seconds notification submission/HA acceptance: 5 + max(75, 60) + 10 + 30 = 120.
The default weather persistence becomes 75 seconds; AQ retains its independent
300-second confirmation. No provider poll is needed to finish qualification.

**Rationale**: Current confirmation defaults to 300 seconds. SG-011/018 specify
120 seconds after usable input. Dispatch, qualification, aperture correlation,
decision and notification allowances must fit the agreed allocation. Physical
weather onset and provider polling are separate assurance boundaries. The existing
120-second positive-clear delay is a different parameter.

**Alternatives considered**: Exactly 120 seconds confirmation would consume the
whole budget before notification; extending SYS was rejected by the maintainer.
A single shared weather/AQ default would unnecessarily alter the AQ contract.

## R2 — New authoritative observations initiate recovery

**Decision**: Separate provenance, normalized state, source/profile identity,
receiver session and monotonic receipt time. Admit producer order/timestamps only
where a reviewed integration contract proves them. The default binary-event
profile requires a delivered current-session alarm-to-clear transition after the
accepted alarm watermark. Startup off, cached reads and attribute-only changes
cannot initiate recovery.

**Rationale**: Current `_classify` can substitute receiver time for absent source
time; `_schedule_alarm_clear` subtracts historical `last_changed` age, reducing
30 seconds to approximately one second. AppDaemon
[get_state reads its internal state](https://appdaemon.readthedocs.io/en/latest/AD_API_REFERENCE.html).
HA [state timestamps](https://www.home-assistant.io/docs/configuration/state_object/)
do not inherently prove physical measurement time. Its
[reporting semantics](https://developers.home-assistant.io/blog/2024/03/20/state_reported_timestamp/)
require specific subscriptions; ordinary callbacks cannot be assumed to supply
a producer heartbeat.

Observe the complete configured monotonic interval after acceptance. At expiry,
require the same session, incident, binding and token, uninterrupted eligible
clear evidence and still-clear readback. Reconnect, alarm, unknown/test/hush,
link loss and ordering uncertainty invalidate the interval. Readback confirms a
candidate; it never creates one. Receiver identity is not a producer epoch.

**Alternatives considered**: Cached-age subtraction, repeated off polling and
invented producer epochs are rejected as false recovery proof.

**Admission evidence**: Capture sanitized alarm/clear/same-state/initial-sync,
unknown-to-clear and reconnect callbacks on the pinned integration. Verify
[plugin lifecycle events](https://appdaemon.readthedocs.io/en/latest/APPGUIDE.html#appdaemon-events)
and actual distinguishability before source admission. Unproven continuity leaves
danger active and unverified.

## R3 — Retain assertions independently of current bindings

**Decision**: Bootstrap an owner checkpoint even when the component is disabled.
Preserve stable detector/symptom/fault/incident IDs, trusted hazard, original binding
and profile fingerprint, bounded cause/context and independent gas restriction.
Keep `internal_environment_state`; target 4096 records and 1 MiB with validated
field lengths, nesting, numbers and timestamps. Never silently evict active danger.

**Rationale**: Current restore/save iterate current detectors, losing removed
alarms and inhibition. Root journal restore covers external exposure, not every
indoor assertion. Restore trusted retained fault definitions before inactive-fault
filtering, assertions before first publication, and restrictions before output
recovery. Component initialization cannot reset them. Friendly names do not prove
replacement identity. No qualification timers, proposals or commands are restored.

**Alternatives considered**: Current-detector-only persistence and UI-only alarm
restoration leave safety policy unprotected.

## R4 — Durable CLEAR precedes HEAL

**Decision**: One bounded atomic legacy checkpoint conversion preserves true alarms
and gas latches, including orphans. Old clear timestamps remain historical only.
Positive alarm SET remains effective in memory on storage failure. CLEAR requires
durable acknowledgement before recovery publication or restriction release.

**Rationale**: Current recovery publishes clear before persistence. Missing/corrupt
state plus active journal evidence must produce unknown retained danger and a
persistence diagnostic. No implicit gas-reset mechanism is introduced.

An inactive alarm journal does not prove release of the independent gas latch.
Loss/corruption after prior ownership therefore retains unknown gas restriction.
Before source admission, commit a session-dirty marker; mark clean only after
stopping ingress and draining writes. Unclean restoration reconciles owner and
journal generations rather than trusting a durable CLEAR that may predate an
uncommitted newer SET. Never-durable details are unrecoverable and remain explicit
uncertainty. Missing files do not prove virgin installation. Regression coverage
includes these crash interleavings and corruption after alarm HEAL.

**Alternatives considered**: Clear on failed write, treating corrupt state as
empty and arbitrary active-record eviction are rejected.

## R5 — One shared lifecycle, with component-owned safety policy

**Decision**: Retain the concrete callback-based `SafetyMechanism` as the shared
execution object. Add a typed lifecycle scope and execution outcome, rather than
six new competing base classes. Constructor configuration is inert; explicit
start owns registration. Each registration has exactly one scope, cancellation
handle and runtime/generation fence. Component scopes may own a shared source
listener or sampler used by several mechanisms; do not duplicate those listeners
per mechanism. Stop invalidates generation before cancellation. Disable cancels
qualification and denies live results without clearing retained assertions.

**Rationale**: All six components already instantiate this class, but temperature
and doors use implicit listeners while heating/entity/indoor/external paths own
separate schedules. Common construction alone does not provide lifecycle safety.
`extract_entities` currently treats location strings as entities. Explicit
`monitored_entities` replaces inference; retain existing stable mechanism names,
`isEnabled` access and parameter keys through internal adapters.

Normalize eligible positive/negative, unevaluable, inhibited and disabled outcomes
at shared execution entry. Wrap the legacy decorator without adding another
debounce. Domain duration/coverage and source-authority rules remain separate.
Recovery simulation uses an explicitly side-effect-free entry: unevaluable is
not a valid negative, and simulation cannot publish, schedule or grant consent.

**Alternatives considered**: Forcing all domain timers into one symmetric debounce
would alter smoke/gas timing and erase weather/heating semantics. Leaving each
component to implement lifecycle independently preserves the audited drift.

## R6 — Commit fault state, then independently admit response consumers

**Decision**: FaultManager commits authoritative in-memory evaluation and a bounded
immutable response identity before admitting consumers. Isolate failures only at
explicit response-consumer boundaries; do not silently swallow prerequisite
validation/evaluation errors on every EventBus channel. Notification lifecycle
admission precedes recovery admission but neither waits for publication or remote
delivery. No automatic EventBus retry may replay an actuator action.

**Rationale**: Current `_set_fault` publishes MQTT before the `fault` event. The
inline fault-injection reproduction left an active fault and zero response events.
EventBus also stops at the first throwing subscriber. Failure reporting must use
bounded local diagnostics; publishing a diagnostic must not recursively fail the
original alarm or fabricate successful consumer admission.

**Alternatives considered**: Merely reversing the MQTT/event calls still leaves
response subscribers coupled. Blanket exception suppression hides lost evidence
and could weaken required routing failures. A durable cross-manager event log is
unnecessary here; uncertain restart reconciliation remains owner-specific.

## R7 — Bounded asynchronous HA service admission and root-owned completion

**Decision**: Use a service-submission adapter with AppDaemon's documented
`call_service(..., callback=...)` completion mechanism. AppDaemon 4.5.0
[documents background completion](https://appdaemon.readthedocs.io/en/4.5.0/APPGUIDE.html#returning-results).
The [application threading guide](https://appdaemon.readthedocs.io/en/4.5.0/APPGUIDE.html#appdaemon-and-threading)
also makes callback/thread ownership explicit. Completion callbacks enqueue bounded
immutable results; only the application-owned drain mutates domain state.
Keep SWR-NOT-009's prohibition on unsupported `return_result`, `timeout` and
`hass_timeout` arguments. A submission's immediate scheduling return is not its
completion result. Completion `None` retains the existing documented acceptance
meaning; it is not phone delivery proof.

**Rationale**: The current provider loops through synchronous target calls inside
NotificationManager's fault handler. A single stalled target delays recovery and
other targets. Per-target in-flight slots prevent one target consuming another's
capacity. A timed-out unresolved slot is quarantined, never replaced by another
thread or overlapping call. Late completion is fenced from newer lifecycle state.
MQTT uses a separate bounded projection lane. Notification persistence uses its
own bounded snapshot writer. No adapter is allowed to mutate FaultManager or
call another domain's response handler from a worker/completion callback.

**Admission evidence**: Declared dependency is AppDaemon >=4.5,<5; the locally
installed 4.4.2 is outside that range and is not runtime admission evidence.
Implementation must exercise the packaged supported HASS service adapter and
callback signatures in a non-household harness. Unsupported callback semantics
are an explicit integration failure, never silent synchronous fallback. No claim
is made that app-level cancellation can recall a service already handed to HA.

**Alternatives considered**: A new thread on every timeout leaks resources under
permanent hangs. A common thread pool lets stalled targets starve other outputs.
Unbounded callbacks and treating submission return as delivery success are rejected.

## R8 — Preserve durable authorization and separate publication progress

**Decision**: Keep each owner's SQLite namespace and atomic snapshot semantics.
Copy bounded notification snapshots to one writer with one coalesced pending
snapshot. Recovery command authorization still waits for its own exact durable
proposal/token generation; asynchronous diagnostic projection does not grant
permission. Publish desired and accepted MQTT progress separately internally;
failed publication cannot become an accepted cache entry or alter domain truth.

**Rationale**: Moving network calls off the response path is insufficient if
notification persistence or recovery diagnostics can still block that path.
Local output restrictions must be rechecked at dispatch and prior queued unsafe
output intent invalidated. An already-submitted service cannot be recalled; it
must not be replayed after restart or completion timeout.

**Alternatives considered**: Sharing one mutable manager state across callbacks,
marking all queued work durable, and turning isolated transport into a new
automatic-recovery authority are rejected.

## Verification Allocation

- Weather: every timing stage/boundary, repeated/failed sources, aperture
  conditions, independent clear delay and invalid timing combinations.
- Recovery: old off after fresh alarm, 29.999/30-second boundaries, startup/cached
  off, attribute-only updates, restart/reconnect at second 29, test/hush, unknown,
  link loss, ambiguous ordering and obsolete callback tokens.
- Retention: removed detector/profile, changed binding, disabled component and
  empty current list, first-publication ordering and cleared alarm with gas latch.
- Storage: legacy conversion, missing/corrupt checkpoint with active journal,
  record/byte overflow, failed SET/CLEAR and independent smoke/gas/CO/leak incidents.
- Frontend: retained/unverified and disabled-but-active projections, persistence
  uncertainty and EN/PL/DE runtime parity. All scenarios issue zero household commands.
- Shared lifecycle: all six families, explicit entity lists, repeated start/stop,
  disable during qualification, stale generations and side-effect-free simulation.
- Response isolation: MQTT exception before publication, throwing consumer,
  stalled target, bounded queue overflow, late/duplicate completion, persistence
  failure and current gas restrictions. Measure full existing deadline budgets.

## Evidence Map

- [HARA](<../../sys/SafetyConcept - HARA.md>),
  [SYS](<../../sys/SafetyConcept - SYS.md>) and
  [SSRD](<../../sys/SafetyComponent - SSRD.md>).
- [Indoor architecture](<../Internal Environmental Hazard Monitoring - Architecture.md>)
  and [external architecture](<../External Hazard Monitoring - Architecture.md>).
- [Indoor monitor](../../../backend/components/safetycomponents/internal_environmental_hazard/internal_environmental_hazard_monitor_component.py),
  [schema](../../../backend/components/safetycomponents/internal_environmental_hazard/schema.py),
  [state store](../../../backend/components/safetycomponents/internal_environmental_hazard/state_store.py),
  [bootstrap](../../../backend/SafetyFunctions.py) and
  [system configuration](../../../backend/config/system_config.yml).

These findings are design evidence, not implemented fixes. No private values or
live household tests are published.
