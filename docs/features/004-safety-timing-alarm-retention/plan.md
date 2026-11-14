# Implementation Plan: Safety Timing and Indoor Alarm Retention

**Branch**: `codex/003-heating-monitoring` | **Date**: 2026-11-14

**Input**: [Feature specification](spec.md)

**Design completed**: 2026-11-15

## Summary

Align weather timing with the approved SYS allocation. Correct indoor recovery
so historical clear snapshots cannot erase an alarm. Restore unresolved indoor
assertions and gas restrictions independently of current detector configuration,
before initial fault/global publication.

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

## Phase 0: Research

See [research](research.md). The allocation preserves SYS, distinguishes weather
from AQ and keeps aperture qualification parallel with hazard confirmation.

## Phase 1: Design Deliverables

- [Data model](data-model.md): observations, timing episodes, assertions and checkpoint.
- [Weather timing](contracts/weather-timing.md): stage allocation and configuration validation.
- [Indoor recovery and retention](contracts/indoor-recovery-retention.md): authority,
  startup/durable ordering and operator projections.
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

When features 003 and 004 share runtime bootstrap, restore both assertion owners
before initial publication; neither owner may filter or overwrite the other's
faults. Add a combined retained-heating/indoor-gas startup regression. Backend
tests shall extend existing external hazard/runtime/notification and indoor
component/config/startup suites, plus storage, FaultManager and output policy.
Frontend tests shall cover configuration and the internal-hazard projections.

## Delivery Boundary

The requested documentation PR will contain features 003 and 004 plus associated
audit evidence. These are designs, not deployed fixes. No live operation or
constitution exception is proposed. The maintainer timing decision is recorded
in research and the contracts; implementation and deployment remain separate.
