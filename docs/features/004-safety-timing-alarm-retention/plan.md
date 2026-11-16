# Implementation Plan: Safety Timing and Indoor Alarm Retention

**Branch**: `codex/004-safety-timing-alarm-retention` | **Date**: 2026-11-14

**Input**: [Feature specification](spec.md)

**Design completed**: 2026-11-15

## Summary

Align weather timing with the approved SYS allocation. Correct indoor recovery
so historical clear snapshots cannot erase an alarm. Restore unresolved indoor
assertions and gas restrictions independently of current detector configuration,
before initial fault/global publication.
Unify lifecycle and execution outcomes through the existing shared
`SafetyMechanism`, explicit input declarations and owned cancellation scopes.
Separate fault-response admission from diagnostic publication and asynchronous
service completion, so a failed or stalled adapter cannot block independent paths.

## Technical Context

**Language/Version**: Python 3.10+; TypeScript/React, repository Node version.
**Primary Dependencies**: AppDaemon HASS, FaultManager, SQLite, MQTT, React/Vite.
**Storage**: Existing `internal_environment_state` namespace with an atomic,
versioned checkpoint independent of current configuration.
**Testing**: pytest with AppDaemon stub, fake clock and storage failures; frontend
component tests and mock Playwright.
**Target Platform**: Home Assistant/AppDaemon and browser.
**Project Type**: Existing backend/frontend application.
**Performance Goals**: Preserve positive indoor alarm latency (SG-006/007/008);
default recovery requires 30 newly observed seconds. Weather warning response
is at most 120 seconds total: 5 dispatch + max(75 weather, 60 door) + 9 reconciliation + 1 decision
+ 30 notification seconds. Windows have no additional opening delay. AQ timing
remains independent.
**Constraints**: Stable IDs, typed/documented code, no household commands or replay.
All domain state mutation remains on its application owner callback. HA service
I/O uses the supported completion-callback adapter, not additional worker threads.
Process-lifetime resource leases survive app reload; deadlines are not cancellation.
**Scale/Scope**: Current detector admission default 64 / maximum 256; retained
checkpoint design target 4096 records and 1 MiB; no silent active-record eviction.

## Constitution Check

| Gate | Assessment |
| --- | --- |
| Documentation first | Specification and research precede code. |
| Typed Python | Hints, docstrings, Ruff and explicit mypy scope required. |
| Verification | Deterministic regressions and full applicable backend/frontend checks; no live household test. |
| Scoped standards | Existing layout, Polish UI and EN/PL/DE runtime parity. |
| Safety contracts | Stable identities; cached/unavailable data cannot prove recovery. |
| Clarification | PASS: maintainer approved 120 seconds total on 2026-11-15. |
| Isolation | PASS by design: authoritative fault state and isolated ordered consumer admission precede remote completion; no worker mutates domain state. |
| Bounded resources | PASS by design: explicit pending byte/count limits, 64 process-wide lease/completion credits and no replacement for an unresolved timed-out call. |

## Phase 0: Research

See [research](research.md). The allocation preserves SYS, distinguishes weather
from AQ and keeps aperture qualification parallel with hazard confirmation.
Research R5..R8 resolves shared execution, service callback admission, process
lease lifetime and durability/publication ordering. The declared supported
AppDaemon >=4.5,<5 callback contract requires packaged-runtime integration evidence
before implementation acceptance; the local installed 4.4.2 is not that evidence.

## Phase 1: Design Deliverables

- [Data model](data-model.md): observations, timing episodes, assertions and checkpoint.
- [Weather timing](contracts/weather-timing.md): stage allocation and configuration validation.
- [Indoor recovery and retention](contracts/indoor-recovery-retention.md): authority,
  startup/durable ordering and operator projections.
- [Shared mechanism lifecycle](contracts/shared-mechanism-lifecycle.md): all six
  families, explicit inputs, typed outcomes, simulation and cancellation ownership.
- [Response isolation](contracts/response-isolation.md): authoritative fault events,
  independent consumers, bounded service completion, MQTT and snapshot writers.
- [Quickstart](quickstart.md): deterministic validation and required checks.

Post-design constitution review passes: no exception, stable identities, bounded
storage and payloads, no inferred source freshness, complete test allocation and
no household actions. Generate implementation tasks separately.

## Intended Change Surface

- External hazard component and affected configuration validation: weather
  qualification and response allocation, independent of positive-clear delay.
- Internal environmental hazard component/schema/state store: typed observations,
  monotonic session/incident tokens and configuration-independent assertions.
- `backend/SafetyFunctions.py`: owner bootstrap, retained fault catalog and gas
  restrictions before initial fault/global publication, even when disabled.
- FaultManager, shared diagnostics and output policy: retained assertions,
  independent gas latch and conservative storage-failure handling.
- `backend/components/safetycomponents/core/safety_mechanism.py` and
  `backend/components/safetycomponents/core/safety_component.py`: shared lifecycle
  and result normalization, explicit listeners and wrapped legacy decorator.
- New typed `backend/components/core/lifecycle.py` and
  `backend/components/core/service_dispatcher.py`: resource scopes and bounded
  process lease/submission/completion infrastructure. Keep these modules small;
  they own no household safety policy.
- `backend/components/core/event_bus.py`: scope-owned unsubscribe handles and
  explicit response-consumer failure isolation without weakening prerequisite events.
- `backend/components/faults_manager/fault_manager.py`,
  `backend/components/core/types_common.py`, and new typed
  `backend/components/core/response_events.py`: immutable response identity,
  commit-before-projection and existing handler compatibility adapters.
- `backend/components/core/mqtt_entity_manager.py`: ordered desired/accepted
  projection, heartbeat, startup/termination barriers and generation fencing.
- NotificationManager, MobilePushProvider, LocalAnnunciator and RecoveryManager:
  fast lifecycle admission, immutable asynchronous work, root-only completion,
  scope-owned shutdown and durable authorization before command dispatch.
- All six domain component adapters: adopt shared scopes/results while keeping
  existing assertion/recovery kernels and sampler/source-session semantics.
- `frontend/src/pages/InternalHazards.tsx` and shared projections/translations:
  retained/unverified danger remains visible when current monitoring is disabled.
- Backend/frontend tests: timing, old clear, interrupted recovery, removed detector,
  disabled component, checkpoint failure and zero-command regressions.
- SYS/SSRD and architecture: requirement-to-test allocation synchronized before
  implementation. Heating remains feature 003; broader HARA gaps remain separate.

Configuration implementation shall update `backend/config/system_config.yml`,
`backend/config/user_config.example.yml`, `backend/configuration_model.py`,
`backend/build_app_config.py` and the external-hazard schema together. Weather
overrides above the response bound require explicit installation correction;
the independent AQ field shall be accepted and compiled consistently. Frontend
configuration metadata/validation shall expose the same limits.

## Requirement and Verification Allocation

| Feature scope | Normative allocation | Required evidence |
| --- | --- | --- |
| FR-001..003; SC-001 | SG-011/018; SYS-SR-EXT-010/041/051; SWR-EXT-004/006 and notification deadlines | Full 120 s pipeline, weather 75 s, parallel door 60 s, decision <=1 s, invalid overrides, independent AQ/clear defaults |
| FR-004..007; SC-002/003 | SWR-IEHM-014/018 | Source profile fixtures; old/off-at-startup/replay and complete 30 s interval; interrupted sessions and stale tokens |
| FR-008..012; SC-004/005 | SWR-IEHM-007/013/017/022 | Immediate positive alarm despite storage failure; durable CLEAR; orphan/disabled startup, journal fallback and gas latch |
| FR-013; SC-004/005 | SWR-IEHM-019/023 | Bounded diagnostic projection, retained active frontend, EN/PL/DE meaning parity |
| FR-014/015; SC-006 | SWR-IEHM-025 and existing component isolation | Zero command/replay spies; unrelated heating/C-TEMP/AQ/fault behavior preserved |
| FR-016/017; SC-007 | SWR-FLT-026/027; SWR-MQTT-007 | MQTT exception cannot prevent fault response; throwing first consumer does not skip others; ordered revisions and deduplication |
| FR-018; SC-008 | SWR-NOT-012/017 | Stalled target, independent healthy targets, persistence/local adapter failure, explicit overload/deadline failure and callback admission/completion separation |
| FR-019..022; SC-009/010 | SWR-SM-001..006 | Six-family lifecycle matrix, explicit inputs, generation checks, result quality and side-effect-free simulation |
| FR-023; SC-006/010 | Existing recovery authorization; SWR-SM-001/004; SWR-FLT-026 | No new command permission, exact durable consent before dispatch, unchanged per-domain timing and independent manager ownership |

When features 003 and 004 share runtime bootstrap, restore both assertion owners
before initial publication; neither owner may filter or overwrite the other's
faults. Add a combined retained-heating/indoor-gas startup regression. Backend
tests shall extend existing external hazard/runtime/notification and indoor
component/config/startup suites, plus storage, FaultManager and output policy.
Frontend tests shall cover configuration and the internal-hazard projections.

## Implementation Sequence and Dependency Gates

1. **Contract/regression foundation**: add deterministic reproductions for MQTT
   failure before fault events, throwing first consumer, stalled target and
   implicit location listener. Add fictional six-family lifecycle fixtures and
   source-admission/clock/storage harnesses. Synchronize source-language architecture
   references and public configuration examples before runtime changes.
2. **Shared lifecycle**: implement typed scopes/results and explicit input binding;
   migrate all six families with shared-parent listener ownership. Normalize legacy
   decorator and direct paths, including read-only recovery simulation. Require
   unchanged positive alarm and domain timing behavior before further integration.
3. **Response boundaries**: implement immutable fault identity and isolated response
   admission, preserving notification-before-recovery admission. Register scope-owned
   subscriptions and local diagnostic failure handling. Prove MQTT exception cannot
   block notification/recovery even before asynchronous publication integration.
4. **Isolated I/O**: implement process broker, reserved credits, completion mailbox
   and supported HA callback adapter. Adapt notification targets, local outputs,
   MQTT desired/accepted projections and snapshot writers. Keep recovery consent/
   command persistence ordering. Prove stalled target, repeated reload, overflow,
   duplicate/late completion and explicit Boolean `success: true` acceptance.
5. **Weather timing**: separate AQ policy and apply 75 s weather confirmation,
   concurrent 60 s opening and unchanged positive-clear delay. Validate all timing
   overrides against the full 120 s pipeline with the real in-process dispatcher.
6. **Indoor recovery/retention**: implement new-source clear authority and complete
   intervals; owner checkpoint conversion, dirty-session recovery, trusted orphan
   catalog and gas restrictions before publication/response startup. Storage write
   acknowledgement and scope generation both gate CLEAR; test their races together.
7. **Operator/evidence integration**: update bounded current/retained projections
   and frontend configuration/indoor diagnostics; preserve EN/PL/DE runtime parity.
   Run full requirement-to-regression mapping and cross-feature startup checks.

Steps 5 and 6 use the shared foundations and may be developed separately after
their gates pass; their final startup/timing acceptance remains integrated. Feature
003's heating functionality is separate: 004 changes its common adapter/lifecycle
but does not implement missing heating rules. Generate concrete task IDs in the
subsequent tasks workflow, not in this plan.

## Validation and Admission Gates

The [quickstart](quickstart.md) defines executable scenario intent and repository
commands. New typed modules must enter `mypy.ini`; extend the check to the shared
mechanism/lifecycle boundaries converted here and report exactly which legacy
manager glue remains outside scope. Do not hide new failures with weaker flags.

Require callback-contract integration evidence for the supported packaged AppDaemon
HASS adapter, including immediate callback, failure result, no-result completion
and never-completing service. Use a non-household harness; no physical detector or
actuator stimulation is needed. Deadline success requires measured full stages;
1 Hz scheduling alone does not prove a maximum delay under load.

The existing Mobile Notification Delivery and Runtime State Storage architecture
descriptions carry the corresponding admission/completion and durable-generation
requirements. Keep their examples and verification mapping synchronized during
implementation, including desired/accepted publication distinctions.
Public IDs and local output permissions are preserved; HA acceptance requires an
explicit successful completion envelope. Queue admission
never becomes proof of phone delivery, physical postcondition or durable storage.

Post-design constitution gate: all FR-001..023 and SC-001..010 have contract/test
allocation; no exception or unresolved design choice remains. Runtime admission
evidence and implementation checks are required deliverables, not assumptions
that the planned fixes already work.

## Delivery Boundary

The [implementation task list](tasks.md) allocates all five stories, common
foundation and final cross-cutting acceptance in dependency order. Its unchecked
items describe required work, not completed implementation.

Feature 004 includes its original timing/indoor fixes and the shared lifecycle/
manager-isolation extension in one coordinated implementation scope. Feature 003
retains its separate heating functionality. These are designs, not deployed fixes.
No live operation or constitution exception is proposed. The maintainer timing
decision is recorded in research and contracts; tasks, implementation, publication
and deployment remain separate workflows.
