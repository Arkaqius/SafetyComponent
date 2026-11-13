# Validation Guide: External Hazard Provider Plugins

**Date:** 2026-11-12

This guide defines local validation for implementation of [the plan](plan.md).
Existing regression checks establish the baseline; the acceptance scenarios
below must also pass before claiming the extension is complete. Use fixtures and
mock mode, with no live provider request, deployment, or household actuator test.

## Prerequisites

- Work from the repository root and preserve existing changes.
- Read [AGENTS.md](../../../AGENTS.md) and
  [CONTRIBUTING.md](../../../CONTRIBUTING.md).
- Use Python 3.10+ with `backend/requirements-dev.txt` installed.
- Use Node.js 20 from `frontend/.nvmrc` and installed lockfile dependencies.
  Check `node --version`; an older default runtime is not equivalent.
- For browser regressions, install the project's Playwright Chromium runtime
  using `npx playwright install chromium` from `frontend/` when needed.
- Use a temporary directory for generated configuration and synthetic state.
  Do not read or copy an installation-owned configuration or secret into fixtures.

## Documentation and active feature

From the repository root:

```powershell
python .specify/scripts/python/check_prerequisites.py --json --paths-only
git diff --check
```

Expected: the feature path resolves to
`docs/features/001-external-provider-plugins`; edited documents have no whitespace
errors. Also validate new untracked Markdown, local links/anchors, tables, source
paths, source-schema exports, and JSON/YAML examples. HARA and stable runtime IDs
must remain unchanged.

## Backend gates

```powershell
python -m ruff check backend
python -m mypy
pytest backend/tests
pytest backend/tests --cov=backend --cov-report=term-missing
```

Expected: all checks pass for the change and the configured coverage gate is
satisfied. New typed provider core modules must be included in mypy's configured
scope; report that scope accurately.

For focused development, run the existing affected suites and extend them with
the contract cases below:

```powershell
pytest backend/tests/test_external_hazard_config.py backend/tests/test_config_compiler.py backend/tests/test_user_config_api.py
pytest backend/tests/test_external_apis.py backend/tests/test_external_api_runtime.py
pytest backend/tests/test_external_hazard_component.py backend/tests/test_external_hazard_policy.py backend/tests/test_external_hazard_startup.py
pytest backend/tests/test_self_diagnostics.py backend/tests/test_degradation.py backend/tests/test_localization.py
python backend/build_app_config.py --print-user-schema
```

Schema inspection must not load a private installation or contact a provider.
After implementation, its provider entries must describe the same editable
parameters and constraints as the configuration catalogue.

## Frontend gates

From `frontend/` under Node.js 20:

```powershell
npm test
npm run typecheck
npm run lint -- --max-warnings=0
npm run format:check
npm run build
npm run test:ui
```

The browser command uses the existing Playwright mock server on local port 4175.
It must not authenticate to a household Home Assistant instance. Include new
domain/component tests in the explicit test TypeScript configuration where
needed; the existing test runner compiles before discovering tests.

The preceding specification baseline found unrelated formatting failures in 109
frontend files and a Node 18 default. Use Node 20, keep changed files formatted,
record any remaining baseline formatting failure explicitly, and do not reformat
unrelated files merely to make the repository-wide command green. These earlier
results are not a substitute for fresh implementation validation.

## Acceptance matrix

| Scenario | Local stimulus | Required observable result |
| --- | --- | --- |
| Legacy Polish installation | Existing public Polish fixture, legacy TERYT, fake HA coordinates | Same providers and stable identities; source not rewritten. |
| Canonical IMGW parameters | Provider-owned county-code field | Compiler/save/start receive the same normalized codes. |
| Duplicate alias declarations | Equal reordered sets, then conflicting sets | Equal accepted; conflict rejected before replacement or startup. |
| Disabled incomplete provider | Missing activation-only region value, then malformed supplied value | Omission allowed while inactive; malformed supplied value rejected. |
| Country and default intent | Berlin fixture with inherited IMGW default; then explicit IMGW true | Inherited source inactive; explicit incompatible selection identified as error. |
| Additional regional source | Synthetic non-PL adapter, custom parameter and packaged field | Own schemas accepted without shared provider-name maps. |
| Complete startup | Stubbed full SafetyFunctions with synthetic source | No degradation binding errors; diagnostics installed before polling. |
| Same-capability independence | Two warning adapters; fail and recover each separately | Source-specific restrictions; valid peer evidence remains usable. |
| Hazard coverage | Wind-only official feed with no current warnings | Wind feed healthy; frost receives no false coverage or clear evidence. |
| Evidence conflict | Valid active warning plus another source's clear result | Active evidence retained; no majority-vote clearing. |
| Failure after assertion | Timeout, stale, partial, malformed, then expired source data | No clear caused solely by missing or unusable input. |
| Snapshot identity and semantics | Duplicate IDs, wrong provider/hazard, wrong units, missing required model fields | Rejected through existing failure semantics; accepted evidence not falsely refreshed. |
| Empty official feed | Complete validated applicable response with zero warnings | Healthy empty only within its declared coverage; no invented source time. |
| No official source | Models selected, official warnings absent | Official feed shown not configured; independent model monitoring continues. |
| Runtime isolation | One stalled source, peer due, then shutdown | Peer runs within configured bounds; no duplicate in-flight request or post-stop dispatch. |
| Metadata-driven editor | PL and synthetic non-PL catalogues in mock mode | Only applicable fields; unknown metadata cannot grant eligibility. |
| Draft compatibility | Open legacy source, edit country/selection/TERYT, switch subpages | No dirty state on read; values retained; no accidental alias conflict. |
| Validation and revision | Invalid save/import and stale revision | Inline/general error; failed save leaves bytes/revision unchanged; conflict is 409. |
| Consent boundary | Save valid source and inspect restart behavior in mocks | Save does not activate or operate devices; restart remains separate and explicit. |
| Localized presentation | Polish editor and EN/PL/DE runtime fixtures | Friendly equivalent text; technical identities stay unchanged. |

Use existing sanitized provider payloads and the bundled AppDaemon stub. Keep the
synthetic regional adapter in test support, not the production provider catalogue.
Fake clocks and bounded wait assertions make timing/failure tests deterministic;
do not require real cloud responses or real-time household events.

## Completion evidence

Record the branch/commit, checks and counts, schema/identity compatibility,
accepted synthetic-source startup and shutdown, no unsafe clear cases, locale
parity, and any unchanged baseline failures. Confirm public configuration examples,
the printed schema, operator help, and normative contracts agree. A new live
national provider and deployment require their own scope and authorization.

The next workflow command after this design is `$speckit-tasks`.
