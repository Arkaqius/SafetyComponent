# Fault state and priority policy

This contract separates a Boolean Safety Mechanism (SM) predicate from the
fault that interprets its evidence and owns handling policy. It is derived from
[SYS section 8.1](<../sys/SafetyConcept - SYS.md#81-component-model--aggregation-rules>)
and [SWR-FLT-008..012 and 024..025](<../sys/SafetyComponent - SSRD.md#44-fault-aggregation-and-system-state>).
The [fault-handling plan](../FAULT_HANDLING_PLAN.md) records allocations and
separate delivery tasks.

## Boundaries and identity

An SM answers one Boolean question: `true` means the named violation is present
for eligible inputs; `false` means it is absent. The fault owns input bindings,
qualification, aggregation, priority, category and response policy. A missing or
invalid input, failed invocation or disabled check is not `false`. It is reported
to fault handling as unavailable evidence. `Symptom` IDs identify contributors;
they do not define a separate fault lifecycle or priority.

Each fault has category `H` (hazard/equipment condition) or `D` (diagnostic
capability failure), and exactly one priority `level` from 1 through 4. Category
does not imply urgency. Fault IDs, `related_sms` and MQTT entity IDs are
technical contracts, except for the explicit per-door fault identity change in
[Fault Routing and Aggregation](Fault%20Routing%20and%20Aggregation%20-%20Architecture.md).

## Evaluation and activation

The evaluation status is one of `NOT_EVALUATED`, `PASS`, `PENDING_FAILURE`,
`FAIL`, `PENDING_RECOVERY`, `UNEVALUABLE`, `INHIBITED` or `DISABLED`. The active
condition, active contributors, `shadowed_by` owners and latch are separate
axes; neither a display label nor a missing observation releases activation.

| Evidence and policy | Status | Active condition |
| --- | --- | --- |
| No completed evaluation | `NOT_EVALUATED` | Preserve any restored activation. |
| Valid failure, still qualifying | `PENDING_FAILURE` | Do not activate a new condition yet. |
| Qualified failure | `FAIL` | Assert or retain activation. |
| Valid recovery, still qualifying | `PENDING_RECOVERY` | Retain activation. |
| Recovery qualified | `PASS` | Release an auto-healing fault; latch policy can retain activation. |
| Required evidence invalid or execution failed | `UNEVALUABLE` | Preserve prior activation. |
| Authorized temporary inhibition | `INHIBITED` | Preserve evidence and apply response-specific rules. |
| Explicit disablement | `DISABLED` | Preserve evidence and any latch. |

For an OR-aggregated fault, one valid `true` remains actionable when another
contributor is unevaluable. An active fault clears only after every required
contributor provides valid `false` and recovery qualification completes. A
failed evaluation interrupts recovery qualification. Fault-owned timers measure
duration; they are not a failure-detection counter, DTC maturity bit or fault
episode. Qualification configuration remains fault-specific.

Explicit shadow relations suppress redundant notification and withdraw the
shadowed fault's recovery proposal. They do not erase its activation, evidence,
severity or technical restrictions. The fault may have several shadow owners;
it is re-presented only after the final owner clears. A SHADOWED response event
must refer to the shadowed fault's contributor, not the shadowing fault's
contributor.

## Priority and responses

The existing fault `level` is also its notification level; there is no second
severity scale. These defaults do not authorize actuation or select a
degradation target.

| Level | Default delivery | Submission deadline | Latch / operator control default |
| --- | --- | --- | --- |
| L1 | Urgent mobile, eligible local alarm/light, HAZARD card; bounded repeats | 10 s | Latch required; ordinary inhibit/disable denied. |
| L2 | High-priority mobile, eligible light, HAZARD card | 30 s | No latch; control only by explicit allowlist. |
| L3 | Mobile warning, WARNING card | 30 s | No latch; control only by explicit allowlist. |
| L4 | Dashboard INFO only | Best effort | No latch; control only by explicit allowlist. |

The [mobile delivery contract](<Mobile Notification Delivery - Architecture.md>)
owns transport retries, ACK and platform-specific profiles. Explicit fault
configuration owns recovery prerequisites, degradation targets, shadowing and
any permitted operator controls. Failure of notification or persistence never
blocks detection or technical restrictions.

## Published contract

Each fault MQTT state is exactly one of the eight evaluation status codes above.
The attributes `active` (Boolean), `shadowed_by` (list of fault IDs), and
`latched` (Boolean) expose independent axes. `FAIL` and `active` can coexist
with nonempty `shadowed_by`; `UNEVALUABLE` can coexist with `active: true`.
System severity counts active faults even when shadowed. Notification history
uses transition/response event codes `SET`, `CLEARED`, `SHADOWED` and `TEST`;
these are not fault MQTT states. Consumers must not infer activation or
shadowing from the evaluation status alone.

## Diagnostic evidence

Each fault retains one versioned `freeze_frame` object combining first-activation
evidence with bounded lifecycle metadata. The captured evidence contains only
selected contributor context, subject, fault priority
and category, safety-relevant configuration fields and their SHA-256
fingerprint, selected source value/timestamp/age/quality, and active restriction causes.
Temperature predicates supply their sampled value, modeled forecast where
applicable, threshold and unit directly; a separately read Home Assistant
timestamp is marked as readback rather than claimed to be the predicate's
timestamp. Arbitrary entity attributes, payload objects, recommendation text,
credentials and secret-like values are excluded. A missing or invalid source
timestamp is explicitly uncertain; it is not treated as a fresh sample.

The captured evidence is immutable while the fault remains active, including when
another symptom joins, a shadow owner changes, or notification content is
quietly refreshed. Valid recovery retains that frame for diagnosis. The next
activation replaces it and increments the activation count. A restart that
restores an active record does not increment the count on the first repeated
SET; a valid PASS must be observed before a later activation is new.

The same object contains `first_failure_at`, `last_failure_at`,
`last_valid_pass_at`, `activation_count`, `last_reason`,
`active_duration_seconds`, and `clock_uncertain` alongside the captured fields.
These lifecycle fields can update on valid clear or restart without rewriting
the activation evidence. Live duration uses a monotonic process clock. An active
record restored after a
restart sets `clock_uncertain: true` and leaves duration unknown; elapsed time
across downtime is never inferred from wall-clock subtraction. UTC timestamps
are diagnostic chronology, not qualification timers.

MQTT fault attributes and API fault records shall expose only `freeze_frame`
for this evidence and metadata. The frontend shall show them in one **Freeze
frame** section. The atomic store uses format version 2; loading a validated
version 1 record combines its existing capture and lifecycle metadata into the
same object before publication. Migration preserves the captured values and
activation count within the original capture and lifecycle validation bounds
and does not create a new activation.

`runtime_cfg.fault_evidence` limits the independent atomic JSON store to 256
fault records, 4096 UTF-8 bytes for the activation-capture fields of each frame,
and 1 MiB for the complete persisted JSON, including lifecycle fields. Lifecycle
fields retain their own bounded validation and do not consume the capture byte
budget. Combining them in one object does not tighten the original capture
limit or discard previously valid legacy data. Capacity evicts the oldest
inactive record by last activation time, never an active record. If all
records are active, the new capture is dropped and App Health reports durability
loss; an older cleared frame must not be presented as evidence for that new
activation. Detection, notification, recovery and degradation continue. A cleared
record may be evicted when the total bound is otherwise exceeded. The store is
separate from notification delivery history. No periodic, recovery, or
significant-change snapshots and no episode objects are created.
The in-memory frame is available to fault publication immediately; atomic disk
replacement is scheduled after the current response dispatch. Failed writes
assert the independent App Health persistence contributor and retry no more
often than every 60 seconds, with one final attempt on orderly shutdown.
