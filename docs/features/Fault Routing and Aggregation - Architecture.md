# Fault Routing and Aggregation - Architecture

## Purpose and scope

This architecture defines how Boolean safety-mechanism results and diagnostic
checks become stable, independently actionable fault instances. It covers
per-subject hazard faults, Group A and Group B entity health, shared inputs,
and validation of the routing configuration. Fault state, priority, and
response policy are defined in [Fault State Policy](Fault%20State%20Policy%20-%20Architecture.md).

Safety Components declare their input dependencies, checks, and consumer
bindings. Entity Monitor routes temperature, safety-door, external-opening,
and shared-input failures into one `InputMonitoringUnavailable` D/L3 fault.
Recovery dependencies retain their separate diagnostic faults. An explicitly monitored
external entity with no internal consumer remains an Entity Monitor Group A
fault.

## Binding model

An installed safety mechanism exposes a stable family ID, a subject key when
its result is subject-specific, and one or more Boolean contributors. Routing
maps `(SM family ID, subject key, contributor key)` to exactly one fault
instance and owner. Several contributors may feed the same instance. The
subject key must be preserved through symptom creation, aggregation, active
condition, notifications, and clearing. A family-level `related_sms` match
alone is insufficient to route two doors to distinct faults.

For a hazard fault, one failed contributor sets the instance; it clears only
when all required contributors for that same subject provide valid clear
evidence. Unavailable or unevaluable evidence never clears an active hazard.
Diagnostic faults may aggregate checks for multiple inputs or providers.
Independent failures and their capability and subject scopes must remain separately
visible in the evidence even when they share one fault instance.

### Per-door timeout

Each monitored door or gate has one `SafetyDoorOpenTimeout{DoorKey}` hazard
fault (class H, priority L2). Its stable `DoorKey` comes from configured
subject identity, not a display name. A failed timeout for one door does not
set, retain, or clear another door's fault. A door input failure instead
contributes to `InputMonitoringUnavailable` with that door's explicit scope;
the timeout's last active evidence is retained until valid evaluation resumes.
No actuator response is introduced by this routing change.

### Entity and component diagnostics

| Matrix row | Fault owner and identity | Evidence and aggregation boundary | Affected hazard/capability |
| --- | --- | --- | --- |
| M11, Group A | Entity Monitor: `EntityHealth{EntityKey}` | Explicitly selected external entity checks only | None by default; declare any internal consumer explicitly |
| M12, Group B | Entity Monitor: `InputMonitoringUnavailable` | Required room temperature input and forecast computation, scoped by room and direct/forecast capability | H-TEMP for the affected capability |
| M13, Group B | Temperature recovery: `TemperatureRecoveryUnavailable` | Required recovery contact/actuator, command, and postcondition evidence | Recovery for the affected H-TEMP room/proposal only |
| M14, Group B | Entity Monitor: `InputMonitoringUnavailable` | Door/condition input checks, scoped by door | M03 `SafetyDoorOpenTimeout{DoorKey}` for that door |
| M15a, Group B | Entity Monitor: `InputMonitoringUnavailable` | Opening-contact checks, scoped by opening | H-EXT exposure evaluation for that opening |
| M15b, Group B | External Hazard recovery: `ExternalRecoveryUnavailable` | Required actuator/postcondition checks and failed command/readback | Recovery for the affected H-EXT opening/proposal only |
| M16, shared input | Entity Monitor: `InputMonitoringUnavailable` | One common-source incident; each consumer registers its dependency | Only explicitly bound H-TEMP, H-EXT, M03, or H-HEAT capability/subject |

Class D and priority L3 apply to M11..M16. The matrix in
[Fault Handling Plan](../FAULT_HANDLING_PLAN.md) defines each row's response,
recovery, and degradation allocation. A diagnostic fault does not itself
erase the hazard condition whose evaluation or recovery is impaired.

M13 and M15b retain a separate `RecoveryCommand` contribution for a rejected
Home Assistant service command or a missed physical postcondition. RecoveryManager
persists the outstanding failure and sends its exact H symptom/actuator pair to
Entity Monitor. A successful service call is not positive repair evidence;
clearing requires the configured contact or actuator-state postcondition.
Availability checks continue independently, and failure does not trigger
automatic command replay.

An entity selected for Group A and consumed by Group B retains both
memberships and the stricter applicable health-check policy within its logical
record, with one diagnostic fault owner per contribution. The configured owner maps each
check to the relevant component fault, while external-only checks may retain
their Group A fault. A shared input has one diagnostic owner and explicit
fan-out to all dependent component capabilities; it is not cloned into a
second `EntityHealth` fault or used to disable unrelated components.

The same physical entity may serve separate diagnostic roles. Input checks
merge under `InputMonitoringUnavailable`, while recovery, detector and
application-health families retain their own logical records and fault names.
For example, a window contact used for exposure assessment and a temperature
recovery postcondition does not collapse the two fault families. Its HA report
is acquired once at the shortest cadence required by either record. An explicit
Group A membership attaches once, preferring the input record when present.

`InputMonitoringUnavailable` preserves each entity, consumer, failed check,
last report, reason, and affected H subject. Clearing one contributor cannot
clear another failed or unevaluable contributor. Fault-level aggregation shall
not widen a contributor's coverage restriction to every input consumer.

Provider adapter failures and required external-capability failures likewise
contribute to one `ExternalDataUnavailable` D/L3 fault. Provider identity and
capability identity remain separate evidence dimensions. The consumer's
redundancy policy determines capability coverage, so one failed provider does
not imply loss of an independently supplied capability.

## Configuration validation

Startup validation resolves bindings against installed components, configured
subjects, declared checks, and the known SM catalogue. Startup fails for a
missing or ambiguous owner, a missing subject, duplicate instance identity,
an unresolved contributor, or a shadow target that is absent, self-referential,
or cyclic. An unknown SM ID is a configuration error. A known mechanism that
belongs to an optional component not installed in this deployment is distinct
from an unknown ID and is not treated as a live contributor.

Validation must prove that each installed Boolean result has one fault route
or an explicit diagnostic-only exemption. Routing may not infer an owner from
entity domain, display name, or iteration order. Invalid configuration is
reported before monitoring and responses start.

## Breaking identifier change

The input merge retires `TemperatureMonitoringUnavailable`,
`SafetyDoorMonitoringUnavailable`, `ExternalOpeningMonitoringUnavailable`, and
`CommonInputUnavailable` in favor of `InputMonitoringUnavailable`. The external
merge retires `ExternalHazardDataUnavailable` and per-provider
`ExternalProviderUnavailable...` faults in favor of `ExternalDataUnavailable`.
There is one current fault entity per merged group; no aggregate alias is
published. Contributor identities and raw provider/entity health diagnostics
remain stable. Retire obsolete discovery and retained topics without inventing
recovery evidence; rebuild current fault state from current contributors.
Consumers of the retired fault entity IDs must migrate to the new identities.

Replacing the shared `SafetyDoorOpenTimeout` identity with per-door identities
is an intentional breaking change. The shared fault and its Home Assistant
entity are removed; no aggregate alias is published. Retire obsolete MQTT
discovery and retained state without emitting a false recovery transition.
Dashboards, automations and other consumers must use the per-door identities.
Old notification tags and stored fault state are not mapped to a new door
because their subject cannot be established reliably.

## Verification

Acceptance tests cover two doors failing independently, one door recovering
while the other remains failed, multiple Group B checks per room, mixed Group
A/B membership with one owner, one shared input affecting only declared
consumers, known but uninstalled SMs versus unknown IDs, ambiguous/missing
bindings and shadow cycles, and removal of obsolete discovery and state.
