# Feature Specification: Safety Timing and Indoor Alarm Retention

**Feature Branch**: `codex/003-heating-monitoring`

**Created**: 2026-11-14

**Status**: Specified

**Input**: Plan feature 004 to reconcile external weather timing with the SYS
120-second requirement and correct two critical indoor-alarm defects: historical
clear evidence and loss of active danger/gas inhibition after configuration removal.

## Clarifications

### Session 2026-11-15

- Q: Does 120 seconds mean total warning response or confirmation alone?
  A: Total to warning, preserving SYS. Confirmation must leave room for dispatch,
  scheduling, decision and notification.

## User Scenarios & Testing

### User Story 1 - Receive weather warnings within the agreed budget (Priority: P1)

An operator receives timely, consistently qualified weather-exposure warnings
from configured model and authoritative sources.

**Why this priority**: A configured confirmation interval cannot conceal failure
to meet the applicable system response requirement.

**Independent Test**: Drive a deterministic source -> qualification -> opening
correlation -> fault -> notification-submission flow at timing boundaries.

**Acceptance Scenarios**:

1. **Given** usable applicable weather evidence and a qualifying open aperture,
   **When** the agreed response boundary is reached, **Then** the bounded decision
   and notification outcome satisfies the approved SYS allocation.
2. **Given** repeated model/official observations or source failure, **When** the
   qualification interval is evaluated, **Then** fresh continuity, interruption
   reset, authoritative validity and positive-clear rules remain effective.
3. **Given** an invalid timing combination, **When** configuration is validated,
   **Then** it is rejected with the affected budget/stage identified rather than
   silently weakening the system deadline.

### User Story 2 - Clear alarms only from new authoritative evidence (Priority: P1)

Residents retain a smoke, gas, CO or leak alarm until an approved current-source
clear contract has been continuously observed for its complete recovery interval.

**Why this priority**: Cached historical off states are not recovery evidence.

**Independent Test**: Assert a fresh alarm, then present an older off snapshot,
replayed event and interrupted recovery before a valid current clear sequence.

**Acceptance Scenarios**:

1. **Given** a fresh alarm, **When** an off snapshot predating the alarm is read,
   **Then** no clear qualification or HEAL is authorized.
2. **Given** an accepted authoritative current clear transition, **When** the
   validated interval elapses without a gap/alarm/session discontinuity, **Then**
   positive recovery is eligible; previous cached age or downtime contributes zero.
3. **Given** a clear in progress, **When** reconnect, test/hush, unavailable input,
   source-order uncertainty or a new alarm occurs, **Then** qualification is
   invalidated and obsolete callbacks cannot clear the active incident.

### User Story 3 - Retain alarm and gas inhibition after removal (Priority: P1)

An active incident and its gas switching inhibition remain effective even when
its detector, profile or component is disabled or removed.

**Why this priority**: Configuration removal cannot erase a real unresolved hazard.

**Independent Test**: Persist gas alarm/inhibition, restart with only CO configured
or with the component disabled, and inspect the very first fault/global output.

**Acceptance Scenarios**:

1. **Given** active gas danger, **When** its detector is removed, **Then** the same
   active unevaluable incident and inhibition remain independently of current bindings.
2. **Given** retained danger, **When** state is restored or rewritten, **Then**
   original identity/cause and unconfirmed recovery remain; saving current detectors
   does not delete orphan assertions.
3. **Given** missing/corrupt state with active journal evidence, **When** startup
   reconciles, **Then** explicit unknown danger and persistence uncertainty replace
   a fabricated healthy state without replaying commands or notifications.

### Edge Cases

- Initial state read versus a current source transition; attribute-only updates.
- Old/future/regressing timestamps, repeated sequence and unknown source epoch.
- Off at startup after an earlier alarm; source/receiver restart during recovery.
- Alarm -> test/hush -> off and profile-specific permissible clear transitions.
- Device/source loss while HA retains an off value; unproven heartbeat semantics.
- Removed detector/profile/component, renamed key or reused identity for new equipment.
- Persistence failure during SET or CLEAR, corrupt/oversized state and late callbacks.
- Simultaneous gas, CO, smoke, leak and weather events; multiple contributors.

## Requirements

### Functional Requirements

- **FR-001**: Weather warning response shall complete within 120 seconds total
  from usable applicable input with the relevant aperture observed open. The
  allocation shall include dispatch, parallel hazard/opening qualification,
  decision and notification; the confirmation interval shall not consume the
  whole response budget.
- **FR-002**: Weather qualification shall preserve fresh source continuity,
  authoritative validity, stable identifiers, aperture conditions and no false
  clear during stale/failed input. Indoor alarm timing shall remain independent.
- **FR-003**: Timing validation shall account for acquisition/dispatch, qualification,
  decision and notification allowance, with deterministic boundary acceptance.
- **FR-004**: Historical, initial, retained, replayed, attribute-only or unordered
  clear observations shall not establish authoritative recovery.
- **FR-005**: An accepted clear shall start a new monotonic recovery interval in
  the current verified source/session contract; the complete configured interval
  shall be newly observed. Cached age and downtime shall contribute no duration.
- **FR-006**: Source order/epoch and clear watermarks shall be established only from
  a reviewed producer/profile contract. Local receipt/session identity shall not
  be misrepresented as original measurement time or a producer epoch.
- **FR-007**: Clear eligibility shall reset on alarm, test/hush, unavailability,
  unconfirmed source continuity, reconnect or ordering uncertainty. Old callbacks
  shall be rejected by current session/incident/qualification identity.
- **FR-008**: Current positive smoke/gas/CO/leak alarm evidence shall remain effective
  independently of failed clear qualification or storage; existing severities and
  hazard-specific guidance shall remain separate.
- **FR-009**: Active symptom/incident identity, cause and gas inhibition shall survive
  detector/profile/component removal as retained active unevaluable state.
- **FR-010**: Owner-level restoration shall reconcile retained assertions before
  initial fault/global publication even when no indoor component is instantiated.
- **FR-011**: Bounded atomic state shall preserve unresolved orphan records and
  authoritative clear ordering; corrupt/missing state with active journal evidence
  shall expose unknown active danger and a distinct persistence diagnostic.
- **FR-012**: Positive recovery and gas-inhibition release shall require their own
  validated current evidence and necessary durable commit; acknowledgement or
  removal is not release permission.
- **FR-013**: Operator surfaces shall distinguish current/retained/unverified alarm,
  recovery wait, source-quality loss and persistence uncertainty with Polish UI and
  equivalent EN/PL/DE runtime labels.
- **FR-014**: Restart/reconnect shall not replay timers, proposals, consent,
  notification commands or household actuator operations.
- **FR-015**: The feature shall preserve independent heating/C-TEMP/provider
  behavior and stable fault/entity/topic/state identities; it shall add no actuator
  control, general indoor AQ engine or unrelated HARA functionality.

### Key Entities

- Weather response allocation and qualified hazard/opening episode.
- Profile-defined observation authority, source order and receiver continuity.
- Newly observed clear qualification with monotonic onset and callback token.
- Retained indoor assertion, incident cause, clear watermark and gas inhibition.
- Bounded owner checkpoint and applied current/retained diagnostic projection.

## Success Criteria

- **SC-001**: Every weather timing boundary test satisfies the approved allocation
  without hidden uncounted stages or a changed SYS requirement by implication.
- **SC-002**: No historical/replayed/off-at-startup case clears a current alarm.
- **SC-003**: A default 30-second clear interval receives 30 seconds of new qualified
  observation; its final boundary and all interruption cases behave deterministically.
- **SC-004**: Every detector/profile/component-removal restart case preserves active
  incident identity and gas inhibition before the first publication.
- **SC-005**: Failed/missing/corrupt persistence never manufactures clear or release;
  genuine positive alarm evidence and uncertainty remain visible.
- **SC-006**: All local acceptance flows issue zero household actuator commands,
  preserve unrelated faults and do not replay historical notification commands.

## Assumptions and Boundaries

- Producer semantics require evidence; absent trustworthy clear ordering/continuity
  leaves the incident unverified and active rather than inventing a clear.
- HARA goals and SG-006/007/008 alarm latency are not relaxed to fix recovery.
- Heating changes belong to feature 003. Broader HARA gaps remain separately scoped.
- This specification/plan does not authorize implementation, live detector tests,
  private configuration application or deployment.
