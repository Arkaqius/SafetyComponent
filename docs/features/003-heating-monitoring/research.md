# Research: Complete Read-Only Heating Monitoring

## Baseline

All R01..R13 have actual predicates across the existing heating modules; 141
focused heating tests passed in the audit. The reviewed installation selects
Diagnostic/R01, seven availability-only bindings, no original measurement-time
selectors, no rooms and no heat-request input. Inline checks reproduced orphaned
R02 loss and indefinite R03/R04 `target_changed` after deadline expiry. Inspection
found the storage-error gate suppressing nonthermal positive results.

## D1. Existing read-only engine

**Decision**: Reuse the kernels and semantic bindings; close lifecycle, admission
and presentation gaps. Option A excludes cooling and automatic mitigation.

**Rationale**: Operating capability depends on source qualification and reviewed
policies, not catalogue membership alone.

**Alternatives considered**: Boiler-specific rewrite, Diagnostic as thermal
coverage, or adding control to compensate for absent observations.

## D2. Configuration-independent retained danger

**Decision**: SafetyFunctions loads a strict owner assertion ledger from the
existing SQLite database and reconciles it with FaultManager before initial
fault/system publication, even with C-HVAC disabled or removed. The component
uses that coordinator, not a second authority.

**Rationale**: Current restore can reject removed bindings before retaining H;
FaultManager only has explicit independent startup restore for external exposure.

**Alternatives considered**: Review D only, component-only restoration, journal
replay. Each loses hazard authority or replays historical effects.

## D3. Bounded storage and old state

**Decision**: Ledger version 1, 4096 records and 1 MiB UTF-8. Validate configured
worst-case cardinality/bytes before admission. Resolve fault/severity from trusted
`heating/engine.py::RULES`. Store bounded cause/recovery context and fingerprints,
not raw configuration or rolling samples. Overflow cannot evict unresolved H.

**Rationale**: Current maximum is 1200 rule latches; retained orphans require a
separate bounded allowance. Record count and byte limits both apply.

**Alternatives considered**: Unbounded snapshots, dropping oldest active records,
duplicating raw device payloads.

Keep valid heating runtime-state versions 1/2 readable and bootstrap active
records idempotently. Missing/corrupt/incompatible state with active journal
evidence yields retained unknown danger. Old samples and downtime never become
new observed recovery coverage.

The new namespace is `heating_assertions`; `heating_monitor_state` retains its
existing runtime role. Use one bounded writer with at most one in-flight and one
coalesced pending ledger generation, and serialize SET/CLEAR acknowledgements.
Callback threads perform no unbounded storage waits. Normal SET publication may
await commit only within its validated decision/reconciliation allowance; timeout
publishes positive H plus persistence D without claiming durability. CLEAR requires
an acknowledged matching generation and revalidated recovery. Account the actual
writer/ack stage in timing validation rather than adding hidden latency.

## D4. Deadline preservation

**Decision**: Preserve original onset and elapsed debt. Evaluate a lowered but
still-unmet qualified target against that deadline. If evidence is no longer
comparable, report coverage/reconciliation loss by the deadline without inventing
mechanical failure. Lowering a target alone cannot HEAL existing H.

**Rationale**: Early returns before urgency currently permit expired episodes to
remain inhibited without a quality escalation.

**Alternatives considered**: Renew onset, clear on target reduction, or leave
unbounded `target_changed` inhibition.

## D5. Storage failure asymmetry

**Decision**: Qualified fresh positive H remains effective in memory/publication
when checkpointing fails, alongside a persistence D. Durable recovery must commit
before HEAL. Restart with untrusted state retains uncertainty; no claim that
uncommitted observations are durable.

**Rationale**: R10/R11 already preserve positive danger; the same principle applies
to other qualified hazards while keeping each rule's evidence requirements.

**Alternatives considered**: Suppress all results during failed storage, clear
anyway, or substitute a D for an observed H.

## D6. Commissioned source and equipment evidence

**Decision**: Use a sanitized manifest matching signal semantics, producer and
equipment references, original timestamp/cadence, topology, independence and
reviewed policies. Keep unsupported rules excluded. Commission one current
installation through product-neutral contracts and fictional validation fixtures.

**Rationale**: Entity names, free-text independence groups and HA write timestamps
are not proof. Equipment limits cannot come from arbitrary test values.

**Alternatives considered**: Stamp cached values with now, auto-enable all rules,
invent limits, recognize a controller by its entity prefix.

Producer changes outside this repository are explicit commissioning dependencies.
Absent capabilities have a defined outcome: excluded coverage and a recorded
prerequisite, not full admission. There is no unresolved architectural choice.

The evidence record lives in optional per-installation `qualification` alongside
bindings; system-owned policy/calibration remains in its existing profiles. Its
exact fields and bounds are fixed in the source-admission contract. Readiness is
derived, and a matching reference still requires actual runtime evidence and the
commissioning acceptance record; no editable true/false certification flag exists.

## D7. Complete timing allocation

**Decision**: Count source age, qualification, two evaluation stages, decision and
notification reserve. The plan's 56 s example fits SG-003; heating-loss paths stay
within 1800 s including bounded allowances. Equipment thermal allocations remain
independent. HA acceptance proves neither phone delivery nor physical recovery.

**Rationale**: Counting only one reconciliation stage understates the real path.

**Alternatives considered**: A universal 30 min timeout or renewed debt on restart.

## D8. Evidence-based operator coverage

**Decision**: Separate health, phase, required-path coverage, optional exclusions
and retained danger. Publish structured bounded timing/recovery details; complete
Polish configuration/Heating views with runtime EN/PL/DE parity.

**Rationale**: Constant partial/degraded summaries cannot distinguish a
commissioned chain from diagnostic-only monitoring.

**Alternatives considered**: Green status from numeric inputs, full coverage from
selection alone, hiding old faults when the source contract is removed.
