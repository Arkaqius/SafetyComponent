# Fault degradation and coverage

## Purpose

Diagnostic (`D`) faults restrict only the installed hazard (`H`) capabilities
that depend on failed evidence or response paths. A restriction is not a hazard
fault SET/CLEAR transition. Fault evaluation status, active condition,
priority, system severity, and coverage are independent axes. This contract
refines [Fault State Policy](Fault%20State%20Policy%20-%20Architecture.md),
[Fault Routing and Aggregation](Fault%20Routing%20and%20Aggregation%20-%20Architecture.md),
and [SWR-FLT-014..019](<../sys/SafetyComponent - SSRD.md#44-fault-aggregation-and-system-state>).

## Installed binding contract

Each diagnostic contributor declares an owner, the capability and subject it
can impair, its H symptom targets, its effect (`evaluation`, `recovery`,
`notification`, `publication`, or `durability`), and the positive evidence
required to remove that restriction. A
Group A check with no internal consumer declares an intentional external-only
empty target list. An empty list is never inferred from a missing declaration.

The configuration compiler resolves every target to one installed H symptom
and its owning H fault. Missing, duplicate, ambiguous, or non-H targets are
rejected; uninstalled future catalog rows do not become runtime baseline
members. A rejected binding retains unambiguously identified installed H
targets as unresolved, blocks only their dependent actuator recovery, and
reports its configuration error. If no installed target can be resolved,
aggregate coverage remains `UNKNOWN`, but recovery of unrelated H subjects is
not blocked by a guessed scope. Independent monitors continue running.

| D source | Exact scope | Restricted capability |
| --- | --- | --- |
| Room temperature input | One room's direct and forecast H symptoms | Evaluation |
| Room derivative input | One room's forecast H symptoms | Evaluation; direct comparison remains available |
| Room window/actuator input | One room's low-temperature H recovery actions | Recovery only |
| Door contact/condition | One door's `SafetyDoorOpenTimeout{DoorKey}` | Evaluation |
| External opening contact | Installed weather/AQ exposure symptoms for that opening | Evaluation |
| External recovery actuator | Recovery actions for that opening | Recovery only |
| Provider capability | Installed weather or AQ exposure symptoms using that capability | Evaluation/advice/recovery requiring that capability |
| One provider adapter | Installed weather or AQ exposure symptoms using that adapter's evidence; consumer capability loss remains a separate cause | Evaluation for the provider-specific path only |
| App Health predicate/recovery contributor | Exact failed installed H symptom or recovery binding | Evaluation or recovery for that subject only |
| App Health delivery, local output, publication, or store | Installed H users of the failed response or durability path | Notification, publication, or durability; valid H detection continues |
| Indoor detector health | The detector's own smoke/gas/CO/water alarm symptom | Evaluation; healthy detector channels continue |
| Group A-only external entity | Intentional empty internal H target list | External automation coverage, not internal H coverage |

The installation's exact resolved bindings are authoritative over
catalog-wide shorthand such as `H-TEMP` or `H-EXT`. Shared inputs use one D
owner and a union of declared consumer targets. The compiler must not fan out
by entity domain, friendly name, component class, or fault priority.

## Cause and recovery ordering

Restrictions are keyed by D symptom, not just by aggregate D fault. Two failed
checks or providers can restrict the same H target independently. The target
is restored only after every active cause has qualified clear evidence and
the dependent H path is reevaluated. Unavailable evidence changes a cause to
unresolved; it never produces a clear. Existing active H evidence remains
active while evaluation is unavailable.

Restriction changes are applied before notification/recovery handling of the
same event. A pending recovery proposal is invalidated if a newly active or
unresolved restriction makes it ineligible. When the dependency recovers,
a fresh H evaluation and current recovery policy are required before a new
actuator proposal can be made; an old actuator command is never replayed
merely because a D fault cleared. Manual
guidance and independent valid H channels continue where their own contracts
permit them.

Provider health is partitioned by capability. Weather point data, official
warnings, and outdoor air quality each retain independent evidence. Loss of
AQ data does not disable weather exposure; loss of one weather provider does
not erase valid evidence from another. Actuator eligibility checks the current
proposal's evidence source, so valid IMGW evidence remains eligible when the
weather point model is unavailable. Consumer capability-loss and provider
adapter failures retain distinct contributors inside `ExternalDataUnavailable`.
The shared fault's activation shall not apply the union of every contributor's
restriction to a single failed source; coverage follows current contributor
evidence and consumer redundancy policy.

## Coverage and supervision

Coverage is derived from the declared installed H baseline. Its raw state is
`FULL`, `PARTIAL`, `DEGRADED`, or `UNKNOWN`, separate from the fault-severity
summary. `DEGRADED` takes precedence for known technical loss; otherwise
unresolved evidence yields `UNKNOWN`; otherwise an explicit operator or
configuration exclusion yields `PARTIAL`; otherwise coverage is `FULL`.
Active H faults can coexist with `FULL`. Excluded required capabilities remain
in the baseline and are listed with reasons. Publication includes affected H
fault, exact symptom, capability, subject, restriction effect, and each D cause.

On restart, a persisted or remembered clear is not proof of current coverage.
Required paths remain `UNKNOWN` until fresh qualified evidence arrives. The
system shall never publish a false H clear to make coverage look healthy.

`sensor.safety_coverage_state` publishes the raw state and bounded attributes
for the installed baseline, affected scopes, rejected bindings, and omission
counts. SafetyHome shows coverage separately from fault severity; an
unavailable entity or disconnected Home Assistant connection is presented as
unknown, never as full coverage.

In-process diagnostics can inspect entity input quality, provider adapters,
SM invocation results, recovery-policy decisions, persistence calls, and
transport submissions while the process executes. They cannot establish that
the process itself is alive after it stops, that initialization completed when
it never started, that MQTT publication arrived during broker failure, or that
a handset displayed a notification. Those claims require an independent
supervisor or observer with its own heartbeat/timeout and authority boundary.
