# Feature Specification: Complete Read-Only Heating Monitoring

**Feature Branch**: `codex/003-heating-monitoring`

**Created**: 2026-11-14

**Status**: Draft

**Input**: Implement option A: complete monitoring of the existing heating
installation, from independent room need through controller request and boiler
response to delivered room heat, without automatic device control. Close the
heating audit findings and expose qualified coverage to the operator.

## Clarifications

### Session 2026-11-14

- Q: Which heating scope should the next stage cover? -> A: Option A, complete
  monitoring of the current installation without automatic heating control.
Full monitoring means evidenced coverage of the required
heating chain; selecting a profile or receiving telemetry alone is insufficient.

## User Scenarios & Testing

### User Story 1 - Understand and qualify heating coverage (Priority: P1)

An operator can determine which parts of the installation are supervised, which
inputs/policies are needed, and why a rule cannot be admitted.

**Why this priority**: Partial telemetry must not imply that heat reaches rooms.

**Independent Test**: Compare diagnostic-only, partially qualified and fully
qualified fictional installations without changing household equipment.

**Acceptance Scenarios**:

1. **Given** availability-only boiler data and no room mappings, **When** the
   operator reviews coverage, **Then** the view identifies excluded need/request/
   delivery paths and does not claim complete protection.
2. **Given** an enabled rule lacks required fresh or independent evidence,
   **When** its profile is validated, **Then** admission fails with a corrective
   explanation rather than invented timestamps, permissions or thresholds.
3. **Given** a commissioned input/profile inventory, **When** a configuration
   draft is reviewed, **Then** qualification results distinguish proven source
   contracts from observations that still require installation evidence.

### User Story 2 - Detect failure across the heating chain (Priority: P1)

Residents receive a specific heating warning for unmet permitted room need,
missing controller request, absent boiler response or insufficient delivery.

**Why this priority**: A running controller or available sensor does not prove
effective heating.

**Independent Test**: Supply deterministic time-coherent samples for each stage
and observe the independent fault, reason and allocated deadline.

**Acceptance Scenarios**:

1. **Given** independent permitted need and no associated request, **When** the
   allowed interval expires, **Then** missing-demand evidence is reported within
   the allocated total heating-loss budget.
2. **Given** a valid request without adequate boiler or room response, **When**
   startup/inhibition allowances expire, **Then** the relevant response/output/
   delivery warning identifies its observations and affected installation/room.
3. **Given** a still-unmet need, **When** targets, phases or inhibitions change
   repeatedly, **Then** the original unresolved deadline remains effective and
   neither indefinite inhibition nor a false clear occurs.

### User Story 3 - Preserve danger during reconfiguration and failure (Priority: P1)

An existing heating incident remains visible until current positive recovery
evidence resolves its original cause, even if monitoring becomes unevaluable.

**Why this priority**: Configuration changes and storage failures are not HEAL.

**Independent Test**: Persist an alarm, remove its rule/system, restart with the
same store, and exercise storage failure using an isolated test installation.

**Acceptance Scenarios**:

1. **Given** an active incident, **When** its rule/profile/system is removed,
   **Then** the original incident remains active and unevaluable with retained
   provenance, separately from the diagnostic review/storage fault.
2. **Given** a storage write/read failure, **When** fresh positive hazard evidence
   arrives, **Then** it remains effective; failure of durable storage cannot
   silently discard it or authorize recovery.
3. **Given** retained danger, **When** the installation restarts or reconnects,
   **Then** no transient healthy state, replayed command/consent or fabricated
   observed recovery interval is produced.

### User Story 4 - Read actionable heating evidence (Priority: P2)

The operator sees why a check is active, pending, excluded or unevaluable, and
what observed recovery evidence is still required.

**Why this priority**: Qualification and commissioning must be reviewable.

**Independent Test**: Inspect desktop/mobile views with qualified, partial,
retained, failed-storage, stale and disconnected evidence.

**Acceptance Scenarios**:

1. **Given** a pending check, **When** details are opened, **Then** the effective
   target, measured value, source age, elapsed/remaining budget and inhibition
   reason are readable with units and explicit unknown values.
2. **Given** valid complete coverage, partial admission or unavailable input,
   **When** the summary updates, **Then** health, phase, coverage and active danger
   remain independent meanings derived from applied evidence.
3. **Given** an incident, **When** delivery history is opened, **Then** the view
   links its original identity to attempt outcomes and distinguishes accepted
   notification submission from confirmed receipt or physical recovery.

### Edge Cases

- Unchanged observations with new proven source times versus cached republish.
- Missing, future, regressing or replayed timestamps and partially updated frames.
- Controller-owned intent presented as independent room permission or demand.
- A reduced target that is still unmet, permission withdrawal and targets attained
  under a changed operating context.
- DHW priority, pump overrun, boiler startup, anti-cycle delay and repeated changes.
- Simultaneous quality loss and real heating failure; storage failure during SET
  or recovery; corrupt, missing or oversized retained state.
- Removed/renamed installation or room identities with unresolved incidents.
- Duplicate samples, clock discontinuity, restart during qualification/recovery.
- Optional rules not supported by a commissioned installation.
- UI reconnect with old diagnostics; missing optional evidence and keyboard use.

## Requirements

### Functional Requirements

- **FR-001**: Monitoring shall cover the permitted room-need -> controller-request
  -> boiler-response -> room-delivery chain for each explicitly admitted system
  and room, preserving existing room-temperature protection.
- **FR-002**: Rule admission shall require documented signal semantics, original
  observation time/cadence, units, circuit association and required independence.
  Availability or command confirmation shall not substitute for physical evidence.
- **FR-003**: Equipment thresholds, timing envelopes and code interpretation shall
  come from reviewed source/equipment calibration. Unproven values shall prevent
  admission instead of being replaced with arbitrary operating defaults.
- **FR-004**: The existing R01..R13 heating capabilities shall remain independently
  selectable under their evidence contracts. Excluded and optional capabilities
  shall be explicit; catalogue membership shall not establish active coverage.
- **FR-005**: Missing-demand and missing-response decisions shall preserve their
  total unresolved deadline across target/phase/inhibition changes and restart.
- **FR-006**: Heating-loss detection, decision and notification allocation shall
  fit the 30 min SG-010/012 budget, and allocated input-supervision paths shall
  fit the 60 s SG-003 budget including acquisition and scheduling allowances.
- **FR-007**: Active hazard identity, evidence, onset and unresolved timing debt
  shall survive rule/profile/system removal or incompatibility as active
  unevaluable assertions, separate from supervision diagnostics.
- **FR-008**: New fresh positive hazard evidence shall remain effective during
  persistence failure. Failed storage, missing input, removed configuration or
  stale data shall not constitute positive recovery evidence.
- **FR-009**: Recovery shall require qualified comparable evidence for the complete
  recovery interval. Downtime, acknowledgement and contact restoration alone
  shall not clear a heating incident.
- **FR-010**: Reconciliation shall precede initial healthy publication. Incident
  identity and bounded retained evidence shall remain visible without replaying
  historical actions, timers, consent or notification commands.
- **FR-011**: Health, phase, coverage, rule admission and active danger shall be
  reported separately and derived from applied qualified evidence. Complete
  coverage shall require all required chain paths and their input contracts.
- **FR-012**: Operator details shall expose bounded source age, values/units,
  targets, elapsed/remaining time, inhibition, retained provenance and outstanding
  recovery evidence; unknown values shall not appear as zero or healthy.
- **FR-013**: Configuration and monitoring shall support Polish operator flows,
  mobile/desktop accessibility and EN/PL/DE runtime meaning parity. Existing
  revision protection and separate save/application boundaries shall remain.
- **FR-014**: Heating incidents shall use existing fault, notification and manual
  recovery contracts, preserving stable identifiers and independent fault causes.
- **FR-015**: The feature shall perform no heating device control, reset, setpoint,
  pump, relay, valve, ventilation or failover command, including during restart,
  alarm qualification and recovery. Notification transport remains permitted.
- **FR-016**: Source normalization shall remain product-neutral and read-only.
  Repeated controller-derived signals shall retain their common-cause limitation.
  Equipment limits, code classification and hydraulic capabilities shall belong
  to reviewed versioned profiles, independently of installation entity names.
- **FR-017**: Runtime state and evidence shall be bounded, versioned and validated;
  loss of safety state shall expose uncertainty and shall not manufacture safety.
- **FR-018**: Full installation admission shall require a completed evidence
  inventory and acceptance record. Unsupported sources remain excluded/partial;
  selecting a broader profile shall not bypass commissioning.

### Key Entities

- **Heating installation and room**: Stable circuit/room identity and selected
  monitoring scope with reviewed bindings.
- **Qualified observation**: Semantic value, unit, original observation time,
  quality, producer evidence and independence group.
- **Reviewed rule policy**: Required evidence, calibrated thresholds, allowances,
  failure/recovery predicates and total timing allocation.
- **Unresolved heating episode**: Original target/cause, onset, incident identity
  and elapsed/remaining budget independent of current evaluability.
- **Retained assertion**: Unresolved historical danger and provenance that remains
  active when its original monitoring contract is no longer applied.
- **Coverage assessment**: Required paths, admitted/excluded rules and current
  quality, independent of boiler operating phase and active incident severity.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Every admitted rule in the validation matrix has complete evidence
  and calibration; every incomplete rule is rejected or explicitly excluded.
- **SC-002**: Every required stage of a fully admitted installation has a passing
  fault-injection/recovery acceptance scenario with bounded timing evidence.
- **SC-003**: Repeated target/phase changes cannot defer unresolved detection beyond
  its configured budget in any deterministic boundary/restart scenario.
- **SC-004**: All removed-rule/system and storage-failure scenarios retain active
  danger without an intervening healthy publication or unsupported clear.
- **SC-005**: All allocated heating-loss and supervision tests satisfy the 30 min
  and 60 s total budgets respectively, including their reserved delivery time.
- **SC-006**: Every operator state identifies missing evidence and pending/retained
  context on desktop/mobile; no disconnected or partial case implies full coverage.
- **SC-007**: All local end-to-end acceptance scenarios make zero heating actuator
  calls and preserve existing C-TEMP and unrelated component behavior.
- **SC-008**: Full operational admission requires an installation evidence record
  covering every required path; absent proof remains an explicit unmet condition.
- **SC-009**: At least two materially different equipment/source profiles shall
  demonstrate equivalent decisions for equivalent qualified facts, explicit
  exclusion of unsupported capabilities and no device-specific change to the
  common safety rules.

## Assumptions and Boundaries

- Cooling, automated mitigation, manufacturer protection, combustion certification
  and proof of complete HARA residual-risk achievement are outside this feature.
- Existing independently operating appliance protections remain required.
- Producer changes outside this repository may be needed to expose trustworthy
  per-value observation times. Their availability shall not be assumed.
- Planning and local implementation do not authorize private configuration changes,
  household drills, deployment or actuator testing.
- Requirements derive from [heating architecture](<../Heating System Monitoring - Architecture.md>),
  [SYS](<../../sys/SafetyConcept - SYS.md#86-heating-system-monitoring-component-c-hvac>)
  and [SSRD](<../../sys/SafetyComponent - SSRD.md#410-heating-system-monitoring>).
