# Implementation Plan: Complete Read-Only Heating Monitoring

**Branch**: `codex/003-heating-monitoring` | **Date**: 2026-11-14 | **Spec**: [spec.md](spec.md)

**Input**: Approved option A, recorded in the feature specification.

## Summary

Complete evidence-based room need -> controller request -> boiler response ->
room delivery monitoring using existing R01..R13 kernels. Correct retained-alarm
loss, target-change deadline bypass and persistence-failure suppression before
admitting broader profiles. Complete configuration guidance and readable frontend
diagnostics. Cooling, automatic heating control and failover remain out of scope.

## Technical Context

**Language/Version**: Python 3.10+ source, Python 3.12 App image; strict TypeScript,
React 19, Node 20 from `frontend/.nvmrc`.

**Primary Dependencies**: Existing AppDaemon, Pydantic 2, PyYAML, SQLite,
React/Vite, @hakit/core and shared notification/recovery services. No new device
integration framework, control API or database service.

**Storage**: Existing private installation YAML/revisioned configuration API,
existing heating runtime checkpoint and a bounded assertion ledger in the same
SQLite database. Preserve source model 2 and stable runtime identifiers.

**Testing**: pytest/AppDaemon stub, Ruff, expanded scoped mypy, frontend unit and
component tests, typecheck, ESLint, Prettier, build and mock desktop/mobile
Playwright. Use deterministic clocks and injected stores, not live household tests.

**Target Platform**: Home Assistant App/AppDaemon and authenticated Ingress UI.

**Project Type**: Brownfield Python backend and React frontend feature.

**Performance Goals**: Allocated source supervision <=60 s; unresolved heating loss
<=1800 s including age, allowances, windows, two reconciliation stages,
qualification, decision and notification reserve. A viable 5 s-cadence example is
10 s source age + 5 s confirmation + 2 x 5 s evaluation + 1 s decision + 30 s HA
acceptance reserve = 56 s. A source unable to meet its contract receives no SG-003
safety credit. Equipment thermal limits retain separately reviewed allocations.

**Constraints**: No boiler reset, setpoint, climate, pump, relay or valve calls.
No fabricated original timestamps, source independence or manufacturer limits.
Storage uncertainty cannot suppress new positive danger or establish recovery.
HA notification acceptance is not proof of phone receipt or physical recovery.

**Scale/Scope**: Existing default 8 systems, ceiling 16 systems, 32 rooms/system,
32 installation inputs and 13 rule kinds. Maximum current latches: 16 x
(32 x 2 + 11) = 1200. The new ledger permits 4096 current/retained records and
1 MiB serialized UTF-8. Admission must validate its worst-case record/byte budget;
runtime overflow never evicts unresolved danger and raises persistence failure.

## Constitution Check

**Pre-research: PASS. Post-design: PASS for planning.**

| Principle | Design evidence |
| --- | --- |
| I Documentation first | Spec and contracts precede code. Reconcile affected heating SYS/SSRD/architecture before runtime edits; no deployed-completion or certification claim. |
| II Typed Python | Preserve the 13-module mypy baseline; add all new typed heating modules and changed heating boundaries as their types are completed. No weakened checks or whole-backend typing claim. |
| III Verification | Regression-first lifecycle/deadline/storage tests, full gates and zero heating actuator calls. Installation edits/deployment require separate authorization. |
| IV Frontend standards | Reuse React/TypeScript/Vite and Node 20; Polish operator flows, EN/PL/DE runtime parity and mock browser acceptance. |
| V Safety contracts | Stable fault/symptom/MQTT identities and source model remain; retained H is independent of current selection; positive-clear and consent boundaries remain. |

Operational admission is a separate acceptance gate. The current seven
availability-only inputs, missing room/request bindings and unreviewed policies
cannot establish full coverage. Missing producer/equipment facts are explicitly
defined commissioning prerequisites, not unresolved architecture decisions or
permission to invent values. No constitution exception is requested.

## Project Structure

### Documentation (this feature)

```text
docs/features/003-heating-monitoring/
  spec.md
  plan.md
  research.md
  data-model.md
  quickstart.md
  contracts/{source-admission,lifecycle-and-timing,operator-diagnostics}.md
  checklists/requirements.md
```

`tasks.md` is produced by the subsequent `$speckit-tasks` step, not this plan.
The earlier audit and T058..T062 in feature 002 remain unchanged.

### Source Code (repository root)

```text
backend/
  SafetyFunctions.py
  {configuration_model,build_app_config,system_configuration,user_config_api}.py
  config/{system_config,user_config.example}.yml
  components/safetycomponents/heating/
    heating_system_monitor_component.py
    {schema,inputs,engine,rules,state}.py
    {output,distribution,thermal,cycling,windows}.py
    assertion_store.py                         # new bounded ledger
  components/core/{sqlite_state_store,degradation}.py
  components/faults_manager/fault_manager.py
  components/recovery_manager/recovery_manager.py
  components/core/locales/{en,pl,de}.yml
  tests/test_heating_{monitor,rules,output,additional_rules}.py
  tests/test_heating_assertions.py              # new regression target
  tests/test_heating_startup.py                 # new full-path stub target
frontend/
  src/pages/{Heating,Configuration}.tsx
  src/domain/{heating,safety}.ts
  src/components/configurationFieldSchemas.ts
  src/content/configurationHelp.ts
  src/userConfigurationApi.ts
  src/dev/mockData.ts
  tests/ui/heating.spec.ts                     # new focused mock flow
```

**Structure Decision**: Extend current ownership and persistence/fault/frontend
seams. No second heating engine or coupling to controller internals. New files
above are design targets, not implemented-file claims.

## Phase 0: Research

[research.md](research.md) resolves ownership, admission, storage asymmetry,
deadline semantics, timing and coverage decisions from code/tests and read-only
installation evidence. Manufacturer values/private bindings remain commissioning
deliverables; this design does not depend on fabricated source capabilities.

## Phase 1: Design and Contracts

- [Data model](data-model.md): observations, commissioning, episodes, assertions,
  coverage and state transitions.
- [Source admission](contracts/source-admission.md): provenance, independence,
  calibration, compatibility and profile readiness.
- [Lifecycle and timing](contracts/lifecycle-and-timing.md): trusted ledger,
  startup ordering, incident identity, deadlines and persistence failure.
- [Operator diagnostics](contracts/operator-diagnostics.md): applied MQTT/UI truth,
  bounded readable evidence and configuration save/application boundaries.
- [Quickstart](quickstart.md): executable local validation and commissioning gates.

### Sequence for task generation

1. Reconcile heating requirements/architecture and create no-actuation fixtures;
   write failing orphan, lowered-target and failed-store regressions.
2. Add typed bounded ledger/coordinator; restore danger before initial publication
   even with C-HVAC disabled. Preserve valid older checkpoint evidence idempotently.
3. Fix R03/R04 deadline paths and nonthermal positive SET during failed storage;
   prove positive recovery and notification identity remain intact.
4. Implement commissioning/admission evidence validation and profile readiness,
   reusing current normalization and rule kernels.
5. Derive current/retained per-path coverage; publish structured timing/recovery
   evidence and conservative global coverage.
6. Complete configuration/Heating UI, help, localization and mock acceptance.
7. Run full regression gates, then prepare a sanitized commissioning record and
   concrete installation proposal for separately authorized review.

Trace tasks/tests to FR-001..018, SC-001..009 and US1..4; preserve
SWR-HSM-001..026. Audit sources: T058 retained assertions, T059 deadlines, T060
storage asymmetry, T061 commissioning, T062 diagnostics/UI. Unrelated indoor
alarm and weather-budget findings remain outside this feature and prevent a
claim of complete system HARA assurance.

Portability acceptance uses at least two materially different equipment/source
profiles, not only renamed entities. Profile-specific codes, units, operating
limits and unavailable capabilities shall vary while common rule semantics stay
unchanged. Junkers Cerapur is an installation qualification case, not a condition
embedded in the engine. No unverified real manufacturer limits enter fixtures.

## Complexity Tracking

The owner ledger is necessary because a disabled component cannot restore its
own H. Runtime sample/deadline state and authoritative active-assertion state have
different retention/startup duties, defined in the lifecycle contract. Neither
notification history nor a review D replaces retained H.

## Planning Verification

The current unchanged application baseline passed Ruff, mypy for 13 modules,
1440 backend tests, 188 frontend tests, typecheck, zero-warning lint and production
build using Node 20.20.2. Global Prettier reports the same 98 untouched baseline
files; no frontend source was edited. These results do not prove the new feature
or eliminate the reproduced heating defects.

Document validation checked 10 Markdown files, 62 local links/anchors, seven
tables and the 16/16 specification checklist. No unresolved template markers
remain. HARA/SYS/SSRD and the previous audit are unchanged; their affected heating
contracts must be reconciled before implementation. Technical documentation is
English; Polish operator flow and EN/PL/DE runtime parity are specified for the
implementation, with no translation keys changed by this planning pass.

No extension hooks are configured. No code implementation, installation edit,
commit, push, deployment or household action was performed. The next command is
`$speckit-tasks` for this feature.
