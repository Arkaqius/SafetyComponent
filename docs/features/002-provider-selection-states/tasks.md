# Tasks: Provider Selection and Monitoring States

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md),
[data-model.md](data-model.md), [source contract](contracts/source-selection.md),
[presentation contract](contracts/monitoring-presentation.md),
[synthetic contract](contracts/synthetic-provider.md), [quickstart.md](quickstart.md).

**Tests**: Required by FR-016 and the constitution. Add regressions first, show
their intended failure, then implement. Existing compatibility expectations are
replaced, not retained as alternative behavior.

**Format**: `- [X] Tnnn [P?] [USn?] Description with paths`.
[P] permits separate-file parallel work only after the stated prerequisites;
it never authorizes concurrent edits to the same file. Paths are repository-relative.

## Phase 1: Setup

- [X] T001 Confirm branch, checklist, baseline, existing changes and applicable instructions in `AGENTS.md`, `CONTRIBUTING.md` and `docs/features/002-provider-selection-states/plan.md`; verify Git/Docker/frontend ignore rules without unrelated cleanup; record evidence here.
- [X] T002 Establish controlled target-source fixtures and a no-network assertion harness in `backend/tests/provider_plugin_support.py` and `backend/tests/fixtures/external_apis/`, preserving user changes and private configuration.

## Phase 2: Foundation

Complete foundation before story production edits; independent story tests may
be authored against the fixed contracts while foundation work runs.

- [X] T003 [P] Add strict category/source/obsolete-shape regressions in `backend/tests/test_external_provider_configuration.py`, `backend/tests/test_config_compiler.py` and `backend/tests/test_external_hazard_config.py`: “Required closed map: WeatherPointModel, OfficialWeatherWarnings, OutdoorAirQuality. Every value is a registered ID or explicit null”; inactive supplied fields remain validated, active-only requiredness and site checks apply before save/startup without I/O.
- [X] T004 [P] Extend `backend/tests/test_external_provider_registry.py` and `backend/tests/test_external_apis.py` for trusted “data_kind live|synthetic”, “transport_kind http|none”, required_when_selected, closed schemas, authority semantics and canonical-only construction.
- [X] T005 Replace optional provider enablement/inheritance/aliases with external_sources and provider_parameters in `backend/configuration_model.py`, `backend/system_configuration.py`, `backend/build_app_config.py` and `backend/components/external_apis/core/configuration.py`; keep model_version 2 but accept only target shape, remove packaged enabled defaults and derived provenance.
- [X] T006 Update declarations, registry and constructor in `backend/components/external_apis/core/{registry,api_component,models}.py` and bundled adapter modules; remove legacy paths/site fallbacks and require canonical parameters, preserving complete-result/finite-unit/time validation.
- [X] T007 Reuse strict resolution in `backend/components/app_config_validator/app_cfg_validator.py`; derive runtime enabled flags only from category choices and component activation, with no old-binding fallback.
- [X] T008 Update `backend/config/system_config.yml`, `backend/config/user_config.example.yml`, `docs/examples/example_house_user_config.yml`, `docs/examples/berlin_user_config.yml` and `backend/tests/fixtures/external_apis/provider_contract.json`; remove `backend/tests/fixtures/external_apis/legacy_user_config.yml` and replace obsolete fixture/test expectations throughout affected backend tests.
- [X] T009 Extend `mypy.ini` for new typed modules as introduced and make foundation compiler/registry/provider tests, Ruff and the current typed scope pass without weakened checks.

## Phase 3: US1 - Choose a source and its parameters (P1, configuration MVP)

**Independent test**: Polish IMGW and German choices, disabled selection, conditional
fields, retained valid drafts and save/reopen through authenticated revisioned flows.

- [X] T010 [P] [US1] Extend `backend/tests/test_user_config_api.py` and `backend/tests/test_external_provider_conformance.py` for metadata v2, strict source paths, unchanged bytes/revision on invalid import/save, readable invalid source and 409/422 behavior.
- [X] T011 [P] [US1] Replace intent/alias tests in `frontend/src/domain/providerConfiguration.test.ts` with category choice, immutable parameter retention, missing/invalid choices and no metadata-v1 fallback; retain at-limit/one-over schema and error budget tests.
- [X] T012 [P] [US1] Update `frontend/src/components/ProviderParameterEditor.test.tsx` and `frontend/tests/ui/provider-configuration.spec.ts` for selected fields only, saved clean drafts, invalid country/IDs, disabled retention, field errors, keyboard navigation and 390 px layout.
- [X] T013 [US1] Export catalogue version 2 in `backend/user_config_api.py` and `backend/components/external_apis/core/configuration.py`: remove enabled/legacy paths, add trusted kind fields and required_when_selected; preserve “1 MiB”, “64 providers”, “64 KiB/schema”, “64 properties”, “128 local definitions”, “depth 8”, “reference hops 16”, “1024 enum values”, “256” title/enum/pattern and “2048” help limits.
- [X] T014 [US1] Replace source/metadata/immutable helpers in `frontend/src/domain/providerConfiguration.ts`; remove ProviderIntent/legacy paths/reconciliation and keep bounded safe-key validation, “32 errors”, “16 path segments”, “128 characters per string segment” and “512 per field message”.
- [X] T015 [US1] Update typed client and development fixtures in `frontend/src/userConfigurationApi.ts` and `frontend/src/dev/mockData.ts` for target shape and metadata v2, retaining revisioned full saves and separate confirmed restart.
- [X] T016 [US1] Replace per-provider intent controls with three provider-or-disabled selectors in `frontend/src/pages/Configuration.tsx`; render `frontend/src/components/ProviderParameterEditor.tsx` only for the chosen provider, retaining parameter drafts without inferring a source.
- [X] T017 [US1] Replace legacy/intent explanations in `frontend/CONFIGURATION.md` and `frontend/src/content/configurationHelp.ts` with Polish category selection, parameter requirements and save/apply distinction.
- [X] T018 [US1] Execute US1 API/domain/component/browser acceptance and reconcile the shared fixture in `backend/tests/test_external_provider_conformance.py` and `frontend/src/domain/providerConfiguration.test.ts`; record results here.

## Phase 4: US2 - Recognize disabled and unavailable monitoring (P1)

**Independent test**: Applied configuration versus unsaved/saved-unapplied drafts;
disabled/unknown/failed/stale/healthy-empty/live warning views; retained real danger
through source/component disable and restart without false clear or action replay.

- [X] T019 [P] [US2] Add `backend/tests/test_external_source_selection.py` and extend `backend/tests/test_external_hazard_startup.py` for publishing with C-EXT off/all categories null, before polling; “schema_version 1”, “runtime_id max 128 ASCII characters” and exactly three capability entries.
- [X] T020 [P] [US2] Add `backend/tests/test_external_assertion_store.py` for closed checkpoints, atomic assertion/clear, “4096 records”, “1 MiB serialized UTF-8”, corruption/missing-active-journal/overflow/storage failure and retained removed-source/opening cases.
- [X] T021 [P] [US2] Extend `frontend/src/domain/safety.test.ts` and `frontend/tests/ui/external-provider-coverage.spec.ts` for authoritative applied truth, generation mismatch, disconnect, muted disabled cards/headline/counters, healthy scoped zero and retained active warnings.
- [X] T022 [US2] Implement typed `backend/components/external_apis/core/selection_state.py` and wire `backend/SafetyFunctions.py` to publish independent applied selection before polling, with per-start runtime_id and no private parameter values.
- [X] T023 [US2] Implement typed bounded `backend/components/safetycomponents/external_hazard/assertion_store.py` using `backend/components/core/sqlite_state_store.py`; persist real assertions before publication, reject corruption/limits and expose persistence uncertainty without dropping danger.
- [X] T024 [US2] Wire checkpoint restore before initial FaultManager/MQTT state in `backend/SafetyFunctions.py` and `backend/components/faults_manager/fault_manager.py`; retain active unevaluable real assertions even when C-EXT/source/opening is disabled or removed, without restoring timers or replaying notifications/proposals/commands.
- [X] T025 [US2] Update `backend/components/safetycomponents/external_hazard/external_hazard_component.py` to propagate runtime_id, separate disabled/current/retained context, preserve all-source positive clear and valid matching physical-closure clear, and connect real assertion writes.
- [X] T026 [US2] Decode category selection and evidence in `frontend/src/domain/safety.ts` and connection invalidation in `frontend/src/hooks/useSafetyEntities.ts`; no draft/API/old snapshot substitute, nullable counts for unknown/disabled states, no green all-disabled safety claim.
- [X] T027 [US2] Update `frontend/src/pages/ExternalHazards.tsx`, `frontend/src/styles/index.css` and `frontend/src/domain/monitoringHelp.ts`: neutral category/CSS naming, muted text/icon states and — counts across summary/cards/coverage, while retaining real active danger separately.
- [X] T028 [US2] Add restart acceptance in `backend/tests/test_external_hazard_startup.py` and `backend/tests/test_fault_manager.py`: SET/persist/disable-or-test-selection/restart restores before initial publication; damaged/missing checkpoint with active journal never emits false HEAL/inactive/healthy or replays actions.
- [X] T029 [US2] Run US2 backend/frontend/browser and unchanged positive-clear/hysteresis/qualification regressions; record proofs in `docs/features/002-provider-selection-states/tasks.md`.

## Phase 5: US3 - Exercise a German test source (P2)

**Independent test**: Explicit DE dummy selection through configuration, startup,
four no-network scenarios, isolated preview and shutdown with no effect on real
H/D, coverage, advice, notifications, proposals or household commands.

- [X] T030 [P] [US3] Add `backend/tests/test_germany_dummy_warnings.py` for DE/wind-only synthetic declaration, “region_code 1..32 ASCII letters/digits/underscore/hyphen, beginning with a letter or digit”, scenarios “empty, warning, unavailable, stale”, injected clock, no constructor I/O and no HTTP client.
- [X] T031 [P] [US3] Extend `backend/tests/test_external_api_runtime.py`, `backend/tests/test_self_diagnostics.py` and `backend/tests/test_degradation.py` for trusted live/test routing, spoofed result identity rejection, independent schedules/shutdown and zero synthetic real-diagnostic/coverage influence.
- [X] T032 [US3] Add `backend/components/external_apis/germany_dummy_warnings/{__init__,component,schema}.py` and bundled registration; use transport none, “60-second interval”, “180-second stale limit”, authority_confirmed false and no implicit activation.
- [X] T033 [US3] Update `backend/components/external_apis/core/api_runtime.py` and `backend/SafetyFunctions.py` for trusted definition-based external_api_result versus external_api_test_result dispatch and no-network construction, excluding synthetic from real diagnostics and degradation definitions.
- [X] T034 [US3] Add a defensive separate preview handler in `backend/components/safetycomponents/external_hazard/external_hazard_component.py` publishing `sensor.external_hazard_test_state`, “schema_version 1”, matching runtime_id and “Maximum 64 summaries”; do not insert test results in real caches, H/D, advice or recovery paths.
- [X] T035 [US3] Present conspicuous synthetic source/status/count/warning markers and separate preview in `frontend/src/domain/safety.ts`, `frontend/src/pages/ExternalHazards.tsx` and mock fixtures; do not flatten dummy warnings into real warning/exposure totals.
- [X] T036 [US3] Extend `frontend/tests/ui/provider-configuration.spec.ts` and `frontend/tests/ui/external-provider-coverage.spec.ts` for DE choice and all four scenarios with blocked non-local requests, no TERYT and no real healthy-coverage claim.
- [X] T037 [US3] Add full-path synthetic isolation and restart acceptance in `backend/tests/test_external_hazard_startup.py`, update shared `backend/tests/fixtures/external_apis/provider_contract.json`, and prove all four scenarios leave real state/actions unchanged.

## Phase 6: Polish and final verification

- [X] T038 [P] Complete EN/PL/DE selection, disabled, test and retention labels in `backend/components/core/locales/{en,pl,de}.yml`; extend `backend/tests/test_localization.py` for key/placeholder parity.
- [X] T039 Review typed boundaries/public docstrings and final module scope in `mypy.ini`, `backend/components/external_apis/core/` and the new dummy/assertion modules; retain existing checks and readable safety logic.
- [X] T040 Reconcile implemented contracts, examples and requirements in `docs/features/002-provider-selection-states/`, architecture, SYS/SSRD and `README.md`; validate links/tables/paths/commands and HARA unchanged using technical-documentation.
- [X] T041 Run full backend Ruff/mypy/pytest/coverage commands from `docs/features/002-provider-selection-states/quickstart.md`; record exact counts, coverage, final typed scope and regressions here.
- [X] T042 Run full Node 20 frontend tests/typecheck/zero-warning lint/format/build/mock Playwright gates from `frontend/package.json`; check whole-feature files and record existing repository formatting baseline separately here.
- [X] T043 Review removal/isolation/retention correctness against `docs/features/002-provider-selection-states/spec.md` SC-001..007; fix actionable findings and rerun affected checks without unrelated refactors.
- [X] T044 Record completed criteria, branch/commit when created, language parity, validation and remaining gaps in `docs/features/002-provider-selection-states/tasks.md`; preserve preexisting documentation edits and keep delivery separate from household actuator actions.

## Dependencies and execution order

Setup -> foundation -> US1 / US2 -> US3 -> final gates.
US1 and US2 can develop in different files after foundation is green. US3 fixture
and dummy tests can be authored early, but production integration follows its
foundation and US2 isolation/retention seams. A failed sequential gate blocks
dependent production work until fixed.

- US1 parallel example: T010 backend API tests and T011/T012 frontend tests use
  separate files. T013 API exporter and T014 domain implementation follow foundation.
- US2 parallel example: T019 selection tests, T020 checkpoint tests and T021 UI
  projection tests are independent. T023 store implementation can proceed while
  T026 frontend decoding uses the fixed contract; root coordinates shared C-EXT
  and SafetyFunctions wiring.
- US3 parallel example: T030 dummy tests and T031 runtime tests are different-file
  work; T032 precedes T033/T034, then frontend integration T035/T036.

File ownership must be explicit when delegating. Shared integration files are
edited sequentially; agents do not edit task markers or another owner's files.

## Strategy and scope

Configuration MVP is US1 with foundation; it is a local demonstration, not a
deployable safety completion. Complete US2/US3 and full gates for delivery.
TDD applies to all changed safety contracts. Keep existing APIs, safety consent
and current raw health states except the explicitly approved configuration break.
No backwards-compatibility helper or private installation rewrite is required.

## Requirement coverage

| Requirements | Tasks |
| --- | --- |
| FR-001..005, FR-014; SC-001/002/006/007 | T003..018, T027, T040 |
| FR-006..010; SC-003/004 | T010, T019..029 |
| FR-011..013; SC-005 | T030..037 |
| FR-015/016 | T012, T018, T021, T028..044 |

## Execution evidence

Add actual red/green and final verification evidence as work completes. The
planning baseline is 1359 backend tests (91.91%), 184 frontend tests and 122 browser
cases; those are not feature completion evidence. Existing full-format baseline
is 102 files. No extension hooks are currently configured.

- Setup: current branch open_spec_intruduction, preexisting design changes retained;
  checklist 16/16; Git/Docker/frontend ignores verified, no unrelated cleanup.
- Foundation red/green: strict source/resolver tests failed under the old model,
  then passed with required category choices, canonical parameters and metadata v2.
  Config/API/registry/compiler/adapters: 149 scoped tests passed; three public
  examples compile and validate. The central fixture now has explicit null choices.
- Applied selection/dummy/runtime/C-EXT/diagnostics: 147 scoped tests passed,
  including all four synthetic scenarios, trusted routing, spoofing rejection,
  zero network access, separate bounded preview and live/synthetic shutdown safety.
- Assertion store tests began with missing module, then passed roundtrip,
  write-failure, corruption, identity coherence and exact UTF-8/record bounds.
  Restart integration covers disabled component, disabled sources, dummy selection,
  removed opening, corrupt and missing checkpoint. No false initial PASS/inactive/
  no_faults or replayed real proposal; persistence failure may raise its own new D
  warning. Global coverage retains unresolved danger even outside current H scope.
- Latest complete interim backend run: 1404 passed, before additional assertion
  identity and restart edge cases. Final full gates remain required below.

### Final verification (2026-11-14)

- T001..T044 complete. Backend: Ruff passed; mypy passed for 13 modules;
  full pytest 1426 passed; full coverage run 1426 passed, 91.88% (90% minimum).
- Frontend on Node 20: 188 unit/component tests and 126 desktop/mobile mock
  Playwright cases passed; typecheck, zero-warning lint, build and changed-file
  formatting passed. All feature TS/TSX files were explicitly checked. Global
  formatting reports 98 untouched baseline files; none belongs to this change.
- Safety review covered SC-001..007: explicit category choices and conditional
  parameters; neutral disabled/unknown presentation; generation/disconnection
  invalidation; durable real danger across seven restart modes; exact record/byte
  bounds and corruption; all four no-network dummy scenarios and trusted routing.
  Additional regressions cover invalid-startup snapshot invalidation, cleared
  retained records, aged health and malformed warning payloads.
- Documentation review: source examples compile; changed links, anchors and tables
  checked; English source and Polish operator guidance updated; 28 runtime locale
  keys checked across EN/PL/DE; HARA unchanged. No extension hooks are configured.
- Branch: open_spec_intruduction. The delivery commit contains this evidence;
  its hash is available in Git and PR #48 without a self-referential commit hash.
- Later user instruction explicitly authorizes PR publication and deployment.
  Installation configuration is prepared separately with validated explicit
  choices, preserving existing provider activation and household policies.
  Private configuration, generated output and deployment backups remain ignored.
- No remaining feature implementation gap. Live deployment verification is
  recorded separately after installation; no household actuator tests are used.

## Phase 7: Convergence

### Scope and assessment boundary

The user requested a system-wide assessment of HARA safety goals. This explicitly
extends this review beyond the provider-selection feature. The original spec,
plan, completed tasks and execution evidence above remain unchanged. Provider
selection completion is not evidence that all system safety goals are achieved.
Cross-component tasks below require separately scoped requirements and plans
before implementation; their placement here does not authorize new actuators,
installation changes, live tests or deployment.

Assessment sources: `docs/sys/SafetyConcept - HARA.md` sections 1.3.1..1.3.17,
1.6 and 2; `docs/sys/SafetyConcept - SYS.md` section 6 and component allocations;
`docs/sys/SafetyComponent - SSRD.md`; the feature spec/plan/tasks; Constitution
I..V; current code, tests, packaged configuration and read-only private installation
configuration. No branch comparison or delivery-history claim was used as proof.

Inventory: 19 SGs across 17 HARA areas; feature FR-001..016, SC-001..007,
21 acceptance scenarios, eight implementation-sequence decisions and T001..T044;
five constitution principles. The findings below comprise five missing, five
partial and three contradicting obligations: three CRITICAL and ten HIGH.

### HARA goal coverage

These are software/installation evidence assessments, not certification or proof
of residual risk. A supported mechanism does not establish its physical response,
notification delivery or safe-state effectiveness in the installation.

| Goal | Current assessment | Evidence or unmet obligation |
| --- | --- | --- |
| SG-001 cold exposure | Partial | Temperature thresholds, plausibility and warnings exist; complete timing and separately assessed fallback/safe-state evidence are absent. |
| SG-002 cold prediction | Partial | Forecast code exists; the default derivative window is 15 min versus a 10 min goal, and forecast input supervision declares a 1290 s budget. |
| SG-003 system/input failure | Partial | Entity health, diagnostics and degradation exist; several declared budgets exceed 60 s and complete host/power loss lacks independent observer evidence. |
| SG-004 heat exposure | Partial | Direct/forecast heat warnings exist; aggregate timing validation and the allocated emergency-cooling/ventilation safe-state evidence are incomplete. |
| SG-005 indoor air quality | Missing | Indoor PM/exposure evaluation required by SWR-IEHM-008..011/015/016 is absent; outdoor AQI is a different hazard. |
| SG-006 smoke/fire | Partial | Binary alarm handling exists, but the common clear/restore defects apply and the reviewed installation has no configured smoke detector. |
| SG-007 flammable gas | Partial, unsafe clear/restore | Distinct alarm and switching inhibition exist, but historical clear and configuration removal can defeat them. |
| SG-008 CO | Partial, unsafe clear/restore | Independent binary CO detection exists; the common clear/restore defects and complete 10 s response assurance remain. |
| SG-009 water leak | Partial, unsafe clear/restore | Independent L2 leak alarms exist; common clear/restore defects and 60 s installation assurance remain. No unallocated automatic valve action is assumed mandatory. |
| SG-010 HVAC failure | Partial | Heating monitoring and budget validators exist; cooling is outside that component and the installed profile is Diagnostic only. |
| SG-011 rain/storm ingress | Contradicting timing | Current hazard persistence is 300 s, exceeding the SYS 120 s budget after usable input before notification latency. |
| SG-012 heating/cooling loss | Partial | Heating warnings/manual guidance exist; broader cooling, backup/failover allocation and installation proof remain. |
| SG-013 electrical protection | Missing | No allocated RCD testing/reminders or electrical-protection/wet-zone supervision implementation was found. |
| SG-014 AV privacy | Missing | No privacy/masking/quiet-hours enforcement or unexpected AV access detection implementation was found. |
| SG-015 unauthorized access | Missing intrusion function | Door-duration monitoring exists; occupancy-conditioned unexpected entry/movement and lock-integrity functions do not. |
| SG-016 cybersecurity | Partial | Ingress restriction, validation, revision protection and actor context exist; full role authorization, configuration authenticity, compromise detection and security audit assurance do not. |
| SG-017 frost through openings | Software mechanisms supported; system proof incomplete | Current/forecast frost, aperture correlation, warning context and conservative recovery exist; complete installation timing/safe-state evidence remains. |
| SG-018 damaging wind | Contradicting timing | Current hazard persistence is 300 s, exceeding the SYS 120 s budget after usable input. |
| SG-019 outdoor pollution | Software mechanisms supported; system proof incomplete | AQI exposure and conflicting-opening-advice inhibition exist; complete installation response evidence remains. |

### Reproducible evidence and limits

- Existing targeted backend groups passed: 205 provider/configuration/retention
  tests; 207 indoor/heating/temperature tests; 169 supervision/doors/notification/
  recovery tests. Groups overlap and must not be summed as a unique suite count.
  Current frontend unit/component tests passed 188/188 on Node 20.
- An inline, deterministic check using existing indoor test helpers asserted a
  fresh gas alarm, then supplied `off` with HA timestamps one day before the
  alarm. `_schedule_alarm_clear` scheduled 1 s and `_alarm_clear_elapsed` cleared
  the alarm. Historical timestamps supplied the supposed observed clear interval.
- A separate in-memory checkpoint check restored an active gas detector with
  switching inhibition into a configuration containing only CO. The gas runtime
  and output inhibition disappeared; the next save removed the gas checkpoint.
- The installed configuration enables all six available safety components, but
  has one gas detector, one CO detector, three leak detectors and no smoke detector.
  Its heating profile is Diagnostic, enabling input diagnostics rather than the
  thermal protection rules. Names, bindings and private values are not reproduced.
- Passing existing tests does not cover the two executable negative cases above
  or prove complete HARA response budgets. No household routine, alarm injection,
  actuator operation or installation modification was performed for this audit.

### Remaining work

- [ ] T045 CRITICAL Reject stale, cached and out-of-order indoor clear evidence in `backend/components/safetycomponents/internal_environmental_hazard/internal_environmental_hazard_monitor_component.py` and its schema/state contracts; require an authoritative source order/epoch after the alarm and a complete newly observed clear interval across restart/reconnect, with regressions for historical `off`, missing timestamps and source gaps, per Constitution V and SWR-IEHM-014/017/018 (contradicts).
- [ ] T046 CRITICAL Retain unresolved indoor alarm identity, source context and gas switching inhibition when a detector is removed or disabled; update indoor state storage, restore, inactive-fault publication and bounded retained-state presentation so configuration removal cannot erase active danger, with removed-detector/restart and damaged-state regressions, per Constitution V and SWR-IEHM-014/017/018/022 (contradicts).
- [ ] T047 CRITICAL Resolve the safety-impact decision between the user-approved 300 s external debounce and the still-normative 120 s SG-011/018 deadline in SYS section 6 and external architecture section 9; preserve the user's requested behavior pending an explicit reviewed decision, avoid silently weakening a safety goal or reverting debounce, synchronize requirements/configuration/notification-budget allocation and add deadline acceptance tests after the decision, per Constitution I, FR-014, plan: preserve safety contracts, SG-011/018 and SWR-EXT-006 (contradicts).
- [ ] T048 HIGH Separate external-provider liveness supervision from hazard polling/data lifetime in `backend/components/external_apis/core/api_runtime.py`, `backend/components/core/self_diagnostics.py` and system timing configuration; allocate and verify the SG-003 60 s path for silent failure, worker loss, startup and recovery without synthetic coverage or stale positive clears, per SG-003, FR-008..010 and T031/T033 (partial).
- [ ] T049 HIGH Reconcile temperature and forecast timing contracts before changing algorithms: distinguish slow measurement/contact freshness from fault-detection liveness, address the 15 min derivative warm-up and 1290/4020 s declared budgets, and add aggregate budget validation and startup/steady-state/restart regressions in temperature schemas, dependencies and tests, per SG-001..004 and the SYS temperature/supervision allocations (partial).
- [ ] T050 HIGH Create a separately scoped indoor-AQ spec/plan and implement the allocated PM/exposure measurements, bounded observation windows, freshness, recovery and concurrent-hazard advice restrictions with contract tests; do not substitute outdoor AQI or invent detector thresholds, per SG-005, SYS-SR-IEHM-006/007/012 and SWR-IEHM-008..011/015/016 (missing).
- [ ] T051 HIGH Define separately scoped heating/cooling and backup/failover coverage with installation-approved safe responses, account for the Diagnostic-only deployed heating profile, and specify the calibrated inputs/profile and 30 min end-to-end acceptance evidence needed for thermal supervision; do not enable unvalidated thermal rules or actuators automatically, per SG-010/012 and SYS-SR-HSM-012 (partial).
- [ ] T052 HIGH Prepare a separate reviewed electrical-protection feature defining RCD maintenance/test evidence, protection-health ownership, reminders and any separately assessed wet-zone response, then implement and verify its allocated 24 h contract without unauthorized electrical actuation, per HARA 1.3.7 and SG-013 (missing).
- [ ] T053 HIGH Prepare a separate reviewed privacy feature defining AV state/quiet-hours/masking eligibility, unexpected-access evidence, authorized enforcement and a 60 s response test, then implement that allocation without silently changing camera/microphone controls, per HARA 1.3.13 and SG-014 (missing).
- [ ] T054 HIGH Prepare a separate reviewed security-monitoring feature for occupancy-conditioned unexpected entry/movement, armed/lock-state evidence and 30 s warning/escalation acceptance; preserve the existing door-duration function and require explicit authorization for any securing action, per HARA 1.3.1 and SG-015 (missing).
- [ ] T055 HIGH Complete a separately scoped threat and authorization model for safety configuration/control, per-actor role checks, configuration authenticity/integrity, security auditing and compromise detection/response; implement and negatively test the approved controls while preserving existing Ingress restrictions, per HARA 1.3.2 and SG-016 (partial).
- [ ] T056 HIGH Specify and verify independent observation of complete safety-host/process/power loss and installation resilience, including alert routing and explicit external assumptions; in-process diagnostics alone shall not establish continued coverage or recovery, per HARA 1.3.11 and SG-003 (missing).
- [ ] T057 HIGH Establish a per-goal HARA assurance matrix linking all 19 SGs to software tests, enabled installation inputs, approved safe responses and measured sensor-to-decision-to-notification timing; explicitly record absent smoke coverage, Diagnostic-only heating, autonomous device protection and conditional actuator allocations, and obtain separate authorization before commissioning/drills or claiming residual-risk goals achieved, per HARA 1.6, SG-001..019 and Constitution I/III (partial).

## Phase 8: Convergence

### Heating deep review and clarification boundary

This phase refines the user-requested heating assessment and the broad T051
finding; it does not replace Phase 7 or authorize heating control. Sources are
the current heating architecture, SYS-SR-HSM-001..018, SWR-HSM-001..026,
SG-003/010/012, code, existing tests and read-only installation configuration.
The active Spec Kit feature remains provider selection; there is no separate
heating `spec.md`/`plan.md`/`tasks.md` set. The heating scope clarification is
pending user input and shall not be inserted into the unrelated provider spec.
Create the separately scoped heating artifacts before implementing broader
commissioning, cooling or backup/failover work.

Inventory: 13 heating rules, 26 SWR-HSM requirements, 18 SYS-SR-HSM requirements,
five constitution principles and eight architecture decisions: read-only input
boundary, admission/provenance, independent need, phase eligibility, bounded
timing, durable recovery, fault/notification integration and operator diagnostics.
Five actionable findings: three contradicts, two partial, zero missing and zero
unrequested; one CRITICAL, three HIGH and one MEDIUM. These refine implementation
and deployment readiness; they are not a percentage-complete estimate.

### Implemented rule kernels versus installed coverage

| Rules | Implemented behavior | Installed admission |
| --- | --- | --- |
| R01 | Input quality and source-supervision predicate, per-cause failure/recovery qualification | Selected by Diagnostic; the configured bindings provide availability-only evidence. |
| R02 | Current mapped boiler/device fault classification | Excluded; no commissioned device-fault policy selected. |
| R03 | Independent permitted room need versus controller heat request | Excluded; no rooms/heat-request binding; deadline defect H2 also applies. |
| R04 | Issued heat request versus eligible boiler response, including startup/DHW/inhibition | Excluded; no heat-request binding or commissioned response policy; deadline defect H2 also applies. |
| R05/R06 | Qualified flow-temperature rise and tracking windows, sample/gap checks and recovery bands | Excluded; availability-only thermal bindings are not admissible source-fresh samples. |
| R07/R08/R09 | Pump/topology checks, flow-return differential and room-delivery trends | Excluded; qualified topology/load/room evidence and policies are not commissioned. |
| R10/R11 | Mode-specific and manufacturer-absolute temperature limits, with independent thermal-positive handling | Excluded; reviewed equipment envelopes and source-fresh thermal evidence are not selected. |
| R12 | Mode-specific cycling/counter windows, reset/replay handling and recovery | Excluded; commissioned counters/windows/policy are not selected. |
| R13 | Current mapped maintenance indication and explicit recovery | Excluded; no commissioned maintenance policy selected. |

Actual implementations are in the heating component and `rules.py`, `output.py`,
`distribution.py`, `thermal.py`, `cycling.py`, `inputs.py`, `schema.py` and
`state.py`. All 13 rule IDs have executable predicates; catalogue membership alone
was not used as evidence. Existing heating monitor/rule/output/additional-rule
tests passed 141/141. No application file or installed configuration was changed.

The reviewed installation enables C-HVAC for one system with profile Diagnostic,
zero assigned rooms and seven bindings: boiler activity, DHW activity, pump
activity, flow/return temperatures, power percentage and requested flow target.
All seven use `availability_only` without an original measurement-time selector.
There is no `heat_request` binding or independent room-need/permission input.
This establishes partial telemetry diagnostics, not proof that requested heat
reaches rooms. The separate C-TEMP room-temperature protection remains distinct.

Cooling, automatic setpoint/control actions and backup/failover are outside the
existing read-only heating component. Their absence is a broader SG-012 allocation
gap already captured by T051, rather than evidence that the 13 heating kernels
are stubs or an authorization to add actuator commands.

### New concrete evidence

- H1: An inline temporary-store check activated R02, then restored the same
  installation under an R01-only profile. `_restore` raised
  `removed heating contract requires review`, but no retained active R02 latch or
  R02 binding remained. A D/review indication does not retain the original H.
- H2: Inline checks with fresh observations every 5 s first established R03 need
  at room 18 C/target 21 C without request and R04 request at flow 25 C/target
  45 C without response. Reducing targets to 20 C and 35 C left both unmet.
  At 205 s, with a 120 s unresolved budget, both returned `target_changed`,
  `violation=None`, `quality_cause=None`, `remaining_seconds=0`. Early returns in
  `rules.py` precede the urgency checks, permitting indefinite INHIBITED status
  without the original heating fault or an R01 quality escalation.
- H3: After evaluation, the storage-error gate in
  `backend/components/safetycomponents/heating/heating_system_monitor_component.py`
  replaces non-R01 results with unknown/storage-unavailable, except positive
  R10/R11. Fresh nonthermal fault evidence can therefore be suppressed by a
  persistence failure. This is a code-inspection finding requiring a regression
  and explicit failure-policy resolution, not a claim of a live failure.
- H5: The same component publishes `coverage: partial` and degraded state for
  any non-all-unavailable snapshot without deriving complete admitted-path
  coverage. `frontend/src/domain/heating.ts` and `frontend/src/pages/Heating.tsx`
  project basic labels/values/reasons, but not complete observation ages,
  elapsed/remaining budgets or rule recovery evidence in the readable view.

### Remaining work

- [ ] T058 CRITICAL Preserve and reconcile orphaned active heating symptoms, incident identity and evidence when a rule/profile/system binding is removed or incompatible; keep the original H visible and unevaluable independently of the persistence/review D indication, including FaultManager/MQTT startup integration, with R02-disable and installation-removal regressions, per Constitution V, SWR-HSM-019/020 and H1 (contradicts).
- [ ] T059 HIGH Enforce the retained unresolved-need deadline for R03/R04 when the target is lowered but the need remains unmet; resolve target-comparison ineligibility without indefinite inhibition or silent loss of escalation, preserving positive-clear and legitimate permission/target semantics, with repeated-target-change, restart and deadline tests in the heating rule/component suites, per SWR-HSM-007/018, heating architecture section 5 and H2 (contradicts).
- [ ] T060 HIGH Resolve the heating persistence-failure policy so storage failure cannot suppress newly confirmed nonthermal hazard evidence while preserving active assertions and preventing unsupported recovery; keep storage uncertainty as its own D contribution and add deterministic failure-path tests for R02..R09 alongside R10/R11, per SWR-HSM-026 and H3 (contradicts).
- [ ] T061 HIGH Define the selected heating commissioning scope in its own spec/plan, then qualify the actual source semantics, original timestamps/cadence, independent permission/room need, heat-request and room/circuit associations needed by each admitted rule; supply reviewed equipment/timing policies and acceptance evidence before selecting broader profiles, retain explicit excluded coverage where evidence is absent, and do not enable rules or edit installation bindings without separate authorization, per T051/T057, SWR-HSM-004/005/024 and H4 (partial).
- [ ] T062 MEDIUM Derive heating health and coverage from qualified admitted paths and exclusions instead of constant partial/degraded summaries, and complete bounded readable MQTT/SafetyHome details for observation age, pending elapsed/remaining budgets, inhibition and positive-recovery evidence; retain diagnostic-only and disconnected uncertainty, EN/PL/DE parity and desktop/mobile tests, per SWR-HSM-023/024, heating architecture sections 3.4/9 and H5 (partial).
