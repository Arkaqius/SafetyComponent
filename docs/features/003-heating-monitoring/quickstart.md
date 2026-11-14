# Validation Guide: Complete Read-Only Heating Monitoring

## Prerequisites

Use Python 3.10+, backend development requirements, Node 20 from
`frontend/.nvmrc`, frontend dependencies and Playwright Chromium. Follow
[contributor setup](../../../CONTRIBUTING.md#development-setup). Use the bundled
AppDaemon stub and fictional sources; no household configuration or actuator is
required. This document defines acceptance to implement, not a claim that the
new scenarios already pass.

## 1. Establish the current baseline

From the repository root:

```powershell
python -m ruff check backend
python -m mypy
pytest backend/tests/test_heating_monitor.py backend/tests/test_heating_rules.py backend/tests/test_heating_output.py backend/tests/test_heating_additional_rules.py
```

The audited heating baseline is 141 passing tests. Scoped mypy currently covers
13 modules; the implementation must extend scope to new typed heating modules
and changed typed boundaries. A passing baseline is not proof that the new
negative cases below are covered.

## 2. Demonstrate lifecycle regressions, then close them

Use isolated temporary SQLite stores and deterministic source/wall/monotonic
clocks in the existing suites and new planned assertion/startup test files.

| Scenario | Required outcome |
| --- | --- |
| Active R02, select R01-only profile | Original H/incident remains active UNEVALUABLE; separate review/storage D; no false initial healthy state. |
| Remove room/system or disable C-HVAC, restart | Same retained assertion visible on stable fault/global surfaces even without a current system entity. |
| Missing/corrupt checkpoint plus active journal | Explicit retained unknown danger, never journal-based HEAL or command replay. |
| Still-unmet lowered R03/R04 target | At deadline-1/exact/+1 and repeated changes, original debt remains bounded; qualified H or explicit reconciliation loss, never indefinite inhibition. |
| Failed SET persistence, R02..R11 | Fresh qualified positive danger published with persistence D; no claim of successful durability. |
| Failed durable CLEAR | H remains active; no HEAL until qualified recovery and required commit succeed. |
| Restart during recovery | Downtime contributes no observed clear coverage and does not replay a proposal/consent/action. |
| Record/byte limit and one over | At-limit valid state admitted; oversize rejected without active eviction or hidden loss. |

The R03 fixture starts with room 18 C/target 21 C and lowers target to 20 C.
The R04 fixture starts with flow 25 C/requested target 45 C and lowers target to
35 C. With a test budget 120 s and fresh samples each 5 s, neither may remain
silently `target_changed` at 205 s. These are fictional regression values, not
production calibration.

## 3. Validate admission and timing

Run schema/compiler/API tests with fictional equivalent source names. Reject
missing source times, stale/replayed/future samples, unsuitable cadence, wrong
units/equipment policy and dependent need/request evidence. Require complete
qualification matching the selected policy before broader admission.

Count both reconciliation stages. Prove actual configured SG-003 paths <=60 s
and heating-loss paths <=1800 s including reserves, startup and allowed windows.
Test a boundary allocation and one just over. R10/R11 require an independently
reviewed equipment allocation. HA submission acceptance is the transport claim.

## 4. Exercise frontend and end-to-end mocks

From `frontend/` with Node 20:

```powershell
npm test
npm run typecheck
npm run lint -- --max-warnings=0
npm run format:check
npm run build
npm run test:ui
```

Mock flows cover profile readiness, valid revisioned save, unchanged applied
monitoring until restart, 390 px/desktop evidence, keyboard use, pending budgets,
retained-only danger, storage failure, disconnect and generation mismatch.
Block non-local requests. Check EN/PL/DE key/placeholder parity and Polish help.
Record untouched global-format baseline separately; never count a failed gate
as passed or rewrite unrelated files to hide it.

## 5. Complete repository gates

From the repository root:

```powershell
pytest backend/tests
pytest backend/tests --cov=backend --cov-report=term-missing
git diff --check
```

Report exact counts/coverage/type scope, links/tables/path validation and remaining
installation gaps. Run unchanged C-TEMP, entity supervision, provider selection,
notifications, manual recovery and startup regressions. Assert zero heating
actuator/reset calls; permitted notification transport is accounted separately.

## 6. Prepare operational qualification separately

Create a sanitized manifest using the [source contract](contracts/source-admission.md).
Review producer semantics, per-value times/cadence, independent room permission,
heat request, circuit/delivery evidence and equipment limits. Missing external
producer support remains a prerequisite with excluded coverage.

Prepare a concrete private configuration proposal, timing evidence and rollback
plan. Obtain separate authorization before applying bindings, commissioning on a
live installation or deployment. Do not turn ordinary controller setpoints or
cached HA values into physical measurements to make the gate pass. Completion of
local implementation and operational full-chain admission are distinct outcomes.
