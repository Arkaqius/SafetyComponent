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
