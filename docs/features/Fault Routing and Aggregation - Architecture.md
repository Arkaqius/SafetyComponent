# Fault Routing and Aggregation - Architecture

## Purpose and scope

This architecture defines how Boolean safety-mechanism results and diagnostic
checks become stable, independently actionable fault instances. It covers
per-subject hazard faults, Group A and Group B entity health, shared inputs,
and validation of the routing configuration. Fault state, priority, and
response policy are defined in [Fault State Policy](Fault%20State%20Policy%20-%20Architecture.md).

The requesting Safety Component owns a diagnostic fault for a dependency used
by its safety decision or recovery. Entity Monitor supplies health checks; it
does not become the owner of every dependency fault. An explicitly monitored
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
Diagnostic faults likewise aggregate only checks that describe the same
unavailable capability and scope. Independent failures must remain separately
visible in the evidence even when they share one fault instance.

### Per-door timeout

Each monitored door or gate has one `SafetyDoorOpenTimeout{DoorKey}` hazard
fault (class H, priority L2). Its stable `DoorKey` comes from configured
subject identity, not a display name. A failed timeout for one door does not
set, retain, or clear another door's fault. A door input failure instead
contributes to the scoped `SafetyDoorMonitoringUnavailable` diagnostic fault;
the timeout's last active evidence is retained until valid evaluation resumes.
No actuator response is introduced by this routing change.

### Entity and component diagnostics

| Matrix row | Fault owner and identity | Evidence and aggregation boundary | Affected hazard/capability |
| --- | --- | --- | --- |
| M11, Group A | Entity Monitor: `EntityHealth{EntityKey}` | Explicitly selected external entity checks only | None by default; declare any internal consumer explicitly |
| M12, Group B | Temperature: `TemperatureMonitoringUnavailable` | Required room temperature input and forecast computation, scoped by room and direct/forecast capability | H-TEMP for the affected capability |
| M13, Group B | Temperature recovery: `TemperatureRecoveryUnavailable` | Required recovery contact/actuator, command, and postcondition evidence | Recovery for the affected H-TEMP room/proposal only |
| M14, Group B | Safety Doors: `SafetyDoorMonitoringUnavailable` | Door/condition input checks, scoped by door | M03 `SafetyDoorOpenTimeout{DoorKey}` for that door |
| M15a, Group B | External Hazard: `ExternalOpeningMonitoringUnavailable` | Opening-contact checks, scoped by opening | H-EXT exposure evaluation for that opening |
| M15b, Group B | External Hazard recovery: `ExternalRecoveryUnavailable` | Required actuator/postcondition checks and failed command/readback | Recovery for the affected H-EXT opening/proposal only |
| M16, shared input | One declared component owner or `CommonInputUnavailable` | One common-source incident; each consumer registers its dependency | Only explicitly bound H-TEMP, H-EXT, M03, or H-HEAT capability/subject |

Class D and priority L3 apply to M11..M16. The matrix in
[Fault Handling Plan](../FAULT_HANDLING_PLAN.md) defines each row's response,
recovery, and degradation allocation. A diagnostic fault does not itself
erase the hazard condition whose evaluation or recovery is impaired.

An entity selected for Group A and consumed by Group B retains both
memberships and the stricter applicable health-check policy, but has one
diagnostic fault owner for a given failure. The configured owner maps each
check to the relevant component fault, while external-only checks may retain
their Group A fault. A shared input has one diagnostic owner and explicit
fan-out to all dependent component capabilities; it is not cloned into a
second `EntityHealth` fault or used to disable unrelated components.

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

## Identifier migration and compatibility

Replacing the shared `SafetyDoorOpenTimeout` identity with per-door identities
is an intentional contract migration. Before activation, inventory consumers
of the old Home Assistant entity ID, MQTT discovery and retained state,
notification tags, stored fault state, dashboards, and automations. Publish
the new identities and retire obsolete discovery/state deliberately; retirement
does not emit a false `CLEARED` transition or imply that an active door became
safe. Until consumers are migrated, the old entity is a read-only aggregate of
the per-door faults: it is `Set` if any door fault is set, `Cleared` only after
all door faults are cleared, and otherwise `Not_tested`. It does not trigger
notification or recovery independently. Preserve the raw fault-state codes and
all unrelated stable identifiers.

## Verification

Acceptance tests cover two doors failing independently, one door recovering
while the other remains failed, multiple Group B checks per room, mixed Group
A/B membership with one owner, one shared input affecting only declared
consumers, known but uninstalled SMs versus unknown IDs, ambiguous/missing
bindings and shadow cycles, and migration of old discovery, tags, and state.
