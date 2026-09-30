# Fault state and priority policy

This contract separates a Boolean Safety Mechanism (SM) predicate from the
fault that interprets its evidence and owns handling policy. It is derived from
[SYS section 8.1](<../sys/SafetyConcept - SYS.md#81-component-model--aggregation-rules>)
and [SWR-FLT-008..012](<../sys/SafetyComponent - SSRD.md#44-fault-aggregation-and-system-state>).
The [fault-handling plan](../FAULT_HANDLING_PLAN.md) records allocations and
separate delivery tasks.

## Boundaries and identity

An SM answers one Boolean question: `true` means the named violation is present
for eligible inputs; `false` means it is absent. The fault owns input bindings,
qualification, aggregation, priority, category and response policy. A missing or
invalid input, failed invocation or disabled check is not `false`. It is reported
to fault handling as unavailable evidence. The existing `Symptom` IDs remain
stable contributor identities during migration; they do not define a separate
target lifecycle or priority.

Each fault has category `H` (hazard/equipment condition) or `D` (diagnostic
capability failure), and exactly one priority `level` from 1 through 4. Category
does not imply urgency. Fault IDs, `related_sms`, MQTT entity IDs and raw state
codes are stable contracts.

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
it is re-presented only after the final owner clears. A SHADOWED event must refer
to the shadowed fault's contributor, not the shadowing fault's contributor.

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

## Compatibility during migration

The legacy `FaultState` and MQTT values (`Set`, `Shadowed`, `Cleared`,
`Not_tested`) remain unchanged. Notification history continues to use `SET`,
`CLEARED`, `SHADOWED` and `TEST`. The richer evaluation model is additive; no
existing Home Assistant automation or frontend reader must reinterpret its
raw state. A still-active shadowed fault continues to count toward system
severity. Changes to the raw contract require a separate versioned migration
and consumer audit.

The legacy adapter currently receives only qualified symptom transitions, not
all negative predicate results. It binds contributors when an event or explicit
unavailability arrives. Accordingly the fault-owned evaluation model can
protect known unavailable inputs, but complete required-binding recovery
evidence is a migration gate before retiring legacy qualification. This gap is
tracked in the fault-handling plan, not encoded as a weaker safety requirement.
