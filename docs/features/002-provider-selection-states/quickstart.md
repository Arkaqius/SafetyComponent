# Validation Guide: Provider Selection and Monitoring States

## Prerequisites

Use the existing checkout and dependencies from [CONTRIBUTING.md](../../../CONTRIBUTING.md).
Use Python 3.10+ and Node 20 from frontend/.nvmrc. Current local Node 18 must not be
used for frontend acceptance; use nvm or the isolated Node 20 invocation below.
No live Home Assistant access or actuator permission is needed for these tests.

This guide defines feature acceptance to execute after implementation. Passing
unchanged baseline suites does not prove these new outcomes.

## Backend gates (repository root)

```powershell
python -m ruff check backend
python -m mypy
pytest backend/tests
pytest backend/tests --cov=backend --cov-report=term-missing
git diff --check
```

The current mypy baseline lists eight files. Implementation must add all new typed
dummy and applied-state modules, retain existing scope and report the final list.
Coverage must remain at least the configured 90%; do not weaken it to add a dummy.

## Frontend gates (frontend directory, Node 20)

```powershell
npm test
npm run typecheck
npm run lint -- --max-warnings=0
npm run format:check
npm run format:check:changed
npm run build
npm run test:ui
```

When Node 20 is not on PATH, prefix each invocation with
`npm exec --yes --package=node@20 --`. Record whole-repository formatting failures
separately from changed-file checks and never reformat unrelated files.

For manual mock inspection:

```powershell
npm run dev:mock -- --host 127.0.0.1
```

Use the printed local URL, configuration and external-hazard routes. All browser
automation must block non-local requests. Synthetic fixtures contain no private
location, credential or live endpoint dependency.

## Scenarios and required observations

| Scenario | Action | Expected proof |
| --- | --- | --- |
| Polish source | Select IMGW, valid TERYT, save/reopen | Neutral category, only its fields, clean reopened draft. |
| Disabled | Select Wyłączone and apply in a controlled runtime | Grey section/cards and — counts, never a healthy zero. |
| German dummy | Select test provider and region | Test markers, no TERYT, no network. |
| Four scenarios | Apply empty/warning/unavailable/stale separately | Repeatable separate previews, no real H/D/coverage/notification/recovery effect. |
| Inactive values | Switch plugin/off and reselect | Draft values restored; only chosen fields shown. |
| Obsolete source | Submit old provider enabled/legacy site TERYT forms | Identified validation errors, saved bytes/revision unchanged. |
| Invalid choice | Unknown ID, wrong capability or country | Explicit errors; no inferred provider. |
| Apply boundary | Edit, save without restart, then restart stub | Monitoring tracks applied snapshot only, generation changes at startup. |
| Retained evidence | Reuse previous boot's healthy states | No healthy current claim without matching runtime_id. |
| Component off | Start with C-EXT disabled | Selection snapshot still published, monitoring muted, no polling. |
| Active real hazard | Disable/fail its source or select dummy | No fabricated clear; independent physical closure remains valid. |
| Restart active real hazard | Assert, persist, disable component/source or select dummy, restart | Assertion restored before initial publication; no HEAL/inactive, action or notification replay. |
| Retained presentation | Inspect real fault and global coverage after restart | Fault active/UNEVALUABLE with retained_assertions or retained_hazard_unknown; global coverage never FULL/PARTIAL solely because the live path is absent. |
| Persisted recommendation | Restart with an old external exposure proposal and retained assertion | Old proposal/consent is excluded from restore; only newly qualified real evidence can create a new recommendation. |
| Damaged assertion state | Corrupt/remove checkpoint with ACTIVE evidence journal, overflow bounds or fail storage | Explicit uncertainty/persistence failure, never a healthy clear or silently lost assertion. |
| Concurrent live data | Dummy plus real model sources | Model evidence remains usable and unchanged by preview scenario. |
| Metadata/input budgets | At-limit/one-over schema and errors | Bounded decoder remains strict with no v1/alias fallback. |
| Mobile/accessibility | 390 px, keyboard and screen reader labels | No overflow; disabled/test status is textual, not colour-only. |

## Expected test surfaces

Extend the existing compiler/configuration/API/provider/registry/runtime/startup,
C-EXT/degradation/localization tests rather than retaining obsolete compatibility
expectations. Add focused dummy and selection publisher modules/tests. Update the
shared sanitized provider_contract.json and both language consumers together.

Frontend acceptance includes providerConfiguration, ProviderParameterEditor,
safety projection, connection invalidation, provider-configuration.spec.ts,
external-provider-coverage.spec.ts and existing contextual-help/draft cases.

Verify schemas from `python backend/build_app_config.py --print-user-schema`
against the new examples, metadata v2 and strict old-shape rejection.

## Documentation and delivery checks

Validate relative links, anchors, tables, source/schema examples, requirement
allocation and EN/PL/DE key/meaning parity. Confirm HARA unchanged. Report branch,
commit if created, exact tests/coverage/type scope, formatting baseline and gaps.

No deployment, private configuration replacement, push or household action is
authorized by this guide. A future deployment requires a target-model installation
file and separate explicit approval; no compatibility migration tool is supplied.
