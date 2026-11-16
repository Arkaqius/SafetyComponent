# Feature Specification: Safety Timing and Indoor Alarm Retention

**Feature Branch**: `codex/004-safety-timing-alarm-retention`

**Created**: 2026-11-14

**Status**: Specified

**Updated**: 2026-11-15

**Input**: Plan feature 004 to reconcile external weather timing with the SYS
120-second requirement and correct two critical indoor-alarm defects: historical
clear evidence and loss of active danger/gas inhibition after configuration removal.
Include the backend architecture fixes for shared mechanism lifecycle, explicit
monitored inputs and isolation between alarm processing, recovery, notifications
and diagnostic publication.

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

### User Story 4 - Receive warnings despite an independent delivery failure (Priority: P1)

Residents retain alarm protection and available response guidance when diagnostic
publication or one notification channel fails or takes too long.

**Why this priority**: An independent display or delivery failure must not conceal
danger or prevent another available warning path.

**Independent Test**: Inject publication failure, a failing response consumer and
a stalled notification target during a fresh alarm; observe the remaining paths.

**Acceptance Scenarios**:

1. **Given** a qualified alarm, **When** diagnostic publication fails, **Then**
   activation remains committed and notification/recovery handling is admitted
   without waiting for publication repair; publication failure remains observable.
2. **Given** multiple notification targets and recovery guidance, **When** one
   target stalls, **Then** independent targets and recovery processing continue
   within their applicable allocations without granting new execution permission.
3. **Given** multiple response consumers, **When** one fails, **Then** the remaining
   eligible consumers still receive the event, with failure reported separately
   and no duplicate logical response or false successful delivery.

### User Story 5 - Preserve consistent monitoring across lifecycle changes (Priority: P2)

Operators receive consistent monitoring when mechanisms are started, disabled,
stopped or restarted, without duplicate listeners or actions from an old runtime.

**Why this priority**: Infrastructure differences must not change the meaning of
an alarm or allow a previous monitoring session to act after shutdown.

**Independent Test**: Exercise lifecycle transitions for temperature, doors,
entity health, heating, indoor alarms and external hazards with delayed callbacks.

**Acceptance Scenarios**:

1. **Given** a monitoring mechanism, **When** start/stop is repeated, **Then** each
   configured input has only its intended subscriptions, stop is idempotent and
   callbacks from the stopped session cannot alter state or trigger responses.
2. **Given** a disabled mechanism with active danger, **When** a late callback or
   timer fires, **Then** no new qualification, clear or action is authorized;
   existing danger and restrictions remain until their valid resolution.
3. **Given** descriptive location and policy text alongside configured inputs,
   **When** monitoring starts, **Then** only explicitly declared inputs are observed;
   changing display text does not add or change monitored entities.

### Edge Cases

- Initial state read versus a current source transition; attribute-only updates.
- Old/future/regressing timestamps, repeated sequence and unknown source epoch.
- Off at startup after an earlier alarm; source/receiver restart during recovery.
- Alarm -> test/hush -> off and profile-specific permissible clear transitions.
- Device/source loss while HA retains an off value; unproven heartbeat semantics.
- Removed detector/profile/component, renamed key or reused identity for new equipment.
- Persistence failure during SET or CLEAR, corrupt/oversized state and late callbacks.
- Simultaneous gas, CO, smoke, leak and weather events; multiple contributors.
- Diagnostic publication failure before and after activation; one consumer throws.
- A stalled notification target alongside a healthy target; bounded overload and
  obsolete transport completion after an incident or runtime changes.
- Repeated start/stop, stop during evaluation, late listeners/timers and disable
  during recovery; descriptive text that resembles an entity identifier.

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
- **FR-016**: Qualified fault activation and admission to notification/recovery
  handling shall not depend on successful diagnostic publication. A publication
  failure shall remain observable without suppressing danger or fabricating clear.
- **FR-017**: Failure of one response consumer shall not prevent delivery to other
  eligible consumers; logical event order and incident identity shall be preserved
  and retries shall not duplicate logical fault transitions or authorized actions.
- **FR-018**: A slow, failed or unavailable notification target shall not delay
  fault processing, recovery policy or another independent delivery adapter beyond
  their existing timing allocations. Queueing and overload shall be bounded and
  explicitly reported; elapsed deadlines shall not become successful delivery.
- **FR-019**: All six installed safety-component families shall use the shared
  SafetyMechanism lifecycle contract for start, enable/disable, stop, ownership of
  subscriptions/timers and rejection of callbacks from obsolete sessions.
- **FR-020**: Disabling or stopping evaluation shall cancel pending qualification
  and prevent obsolete results from changing safety state, while preserving active
  assertions and independent restrictions. Repeated stop shall be harmless.
- **FR-021**: Mechanisms shall monitor only explicitly declared entity inputs;
  descriptive text, location and policy values shall not implicitly create inputs.
- **FR-022**: Shared execution shall distinguish valid positive, valid negative,
  unevaluable, inhibited and disabled outcomes, with consistent error reporting;
  unknown/failed execution shall never be converted into negative clear evidence.
- **FR-023**: Shared infrastructure shall preserve component-specific assertion,
  recovery and timing rules without adding a generic alarm debounce or granting
  new actuator permission. Fault aggregation, recovery authorization, notification
  delivery and diagnostic publication shall retain separate responsibilities.

### Key Entities

- Weather response allocation and qualified hazard/opening episode.
- Profile-defined observation authority, source order and receiver continuity.
- Newly observed clear qualification with monotonic onset and callback token.
- Retained indoor assertion, incident cause, clear watermark and gas inhibition.
- Bounded owner checkpoint and applied current/retained diagnostic projection.
- Shared monitoring lifecycle, explicit input binding and session-owned callback.
- Qualified fault event, independent response consumer and delivery outcome.

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
- **SC-007**: In every diagnostic-publication and response-consumer fault-injection
  case, committed danger remains active, all independent eligible consumers receive
  the event, and no logical transition or authorized action is duplicated.
- **SC-008**: With one stalled notification target, healthy targets and recovery
  processing meet their existing allocated deadlines; failure/overload is visible
  and no stalled attempt is reported as successful delivery.
- **SC-009**: For all six component families, repeated lifecycle operations leave
  no owned subscriptions or qualification timers after stop, obsolete callbacks
  produce zero state/action changes, and metadata-only edits add zero inputs.
- **SC-010**: Every shared execution failure/unevaluable case preserves prior
  active danger; all existing positive-alarm and domain timing requirements remain
  satisfied without additional debounce from infrastructure reuse.

## Assumptions and Boundaries

- Producer semantics require evidence; absent trustworthy clear ordering/continuity
  leaves the incident unverified and active rather than inventing a clear.
- HARA goals and SG-006/007/008 alarm latency are not relaxed to fix recovery.
- Heating changes belong to feature 003. Broader HARA gaps remain separately scoped.
- Shared lifecycle corrections include heating infrastructure integration but do
  not expand the thermal functionality of feature 003. Domain evaluation may use
  distinct scheduling strategies under the same lifecycle and outcome contract.
- Current recovery permissions, service allowlists, confirmation semantics and
  notification acceptance meanings remain unchanged. Independent processing is
  not permission to ignore output restrictions or execute a recovery command.
- This specification/plan does not authorize implementation, live detector tests,
  private configuration application or deployment.
