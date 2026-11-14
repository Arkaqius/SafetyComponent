# Implementation Plan: External Hazard Provider Plugins

**Branch**: `open_spec_intruduction` | **Date**: 2026-11-12 | **Spec**: [spec.md](spec.md)

**Input**: [External Hazard Provider Plugins](spec.md), SYS/SSRD refinements, and
[ADR-0001](../../adr/0001-external-provider-plugins.md).

## Summary

Complete the existing bundled-provider architecture so a conforming regional
provider can traverse configuration, startup, independent polling, C-EXT,
diagnostics, degradation, and operator presentation. Retain Open-Meteo as the
default model source, select official warnings separately, and preserve source
model version 2, legacy TERYT input, and current runtime identities.

The main implementation boundary is a pure shared provider resolver. Compilation
and startup both use it, so invalid provider configuration is rejected before
save as well as before polling. Registered declarations supply parameter schemas,
capabilities, hazard coverage, country applicability, and friendly metadata.
Consumer policy uses these declarations instead of provider-name tables.

Phase 0 research and Phase 1 design are complete in the linked artifacts. This
plan defines implementation work and its evidence; it does not establish that
the extension is implemented or deployed.

## Technical Context

**Language/Version**: Python 3.10+; existing local Pydantic 2.12.5; TypeScript 5.6,
React 19, Vite 6; Node.js 20 as declared in `frontend/.nvmrc`.

**Primary Dependencies**: Existing AppDaemon 4.x, Pydantic 2.x, PyYAML 6,
standard-library HTTPS/worker infrastructure, React, and `@hakit/core`.
Reuse these dependencies; no plugin loader, form framework, or new service.

**Storage**: Existing private YAML configuration with revision-guarded atomic
replacement and ephemeral generated AppDaemon configuration. Reuse existing
runtime storage; no database migration or new persistent provider cache.

**Testing**: pytest with bundled Hass stub, sanitized provider fixtures, Node's
test runner after TypeScript compilation, and mock-only Playwright. Ruff, mypy,
ESLint, Prettier, type checks, coverage, and production build remain gates.

**Target Platform**: SafetyComponent Home Assistant App on its existing supported
architectures, plus desktop/mobile browsers through authenticated Ingress.

**Project Type**: Existing Python safety backend and React operator frontend with
a shared editable-configuration boundary.

**Performance Goals**: Preserve per-provider schedules, one in-flight request per
provider, bounded worker/result queues, and serialized EventBus delivery. Defaults
remain weather 600 s, official warnings 300 s, AQ 300 s, request timeout 10 s,
two retries, and dispatch cadence 1 s. Do not reinterpret cloud polling as a
physical-event detection-time guarantee.

**Constraints**: Preserve HARA, safety goals, policy thresholds, source model 2,
existing IDs/topics/raw states, and actuator consent. Validate without network
calls. Unknown or stale evidence cannot clear a hazard. One provider failure
cannot suppress independent valid evidence.

**Scale/Scope**: One installation location and one instance per stable provider ID;
three bundled adapters and a controlled additional non-Polish acceptance adapter.
No new live national provider, runtime package installation, multi-home feature,
or deployment is included.

## Constitution Check

*GATE: Evaluated before Phase 0 and repeated after Phase 1.*

| Principle or boundary | Before research | After design | Evidence or implementation obligation |
| --- | --- | --- | --- |
| I. Documentation before implementation | PASS | PASS | Spec, SYS, SSRD, feature architecture, and ADR precede code; HARA is unchanged. |
| II. Typed and documented Python | PASS | PASS | Typed resolver/catalogue/coverage records and public docstrings; include new typed core modules in mypy scope and extend touched boundaries. |
| III. Verification before deployment | PASS | PASS | Safety regressions and full synthetic-provider startup are release gates; local mocks precede separately authorized deployment. |
| IV. Scoped instructions/frontend stack | PASS | PASS | Root instructions and existing frontend stack retained; typed bounded metadata renderer with no new framework. |
| V. Explicit safety contracts | PASS | PASS | Additive parameters, legacy alias, stable identities, provider isolation, and conservative hazard clearing. |
| Privacy and scope | PASS | PASS | No installation secrets or live household actions; preserve existing work and current branch. |
| English/Polish/German parity | PASS | PASS | English design; Polish operator guide/UI; EN/PL/DE runtime additions checked together. |

These are design-compliance gates, not a report that future implementation tests
have passed. No constitution exceptions or unresolved design clarifications remain.

## Project Structure

### Documentation (this feature)

```text
docs/features/001-external-provider-plugins/
├── spec.md
├── checklists/requirements.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    ├── provider-interface.md
    └── configuration-api.md
```

A later `$speckit-tasks` invocation produces the task list; this planning phase
does not create it. The active path remains in `.specify/feature.json`.

### Source Code (repository root)

The implementation retains the existing layout. Entries marked new are proposed
source modules, not files produced by this planning command.

```text
backend/
├── configuration_model.py
├── system_configuration.py
├── build_app_config.py
├── user_config_api.py
├── SafetyFunctions.py
├── components/
│   ├── external_apis/
│   │   ├── core/{api_component,registry,models}.py
│   │   ├── core/configuration.py                 # new pure provider resolver
│   │   ├── imgw_warnings/{component,schema}.py
│   │   ├── open_meteo_weather/{component,schema}.py
│   │   └── open_meteo_air_quality/{component,schema}.py
│   ├── app_config_validator/app_cfg_validator.py
│   ├── core/{self_diagnostics,degradation}.py
│   └── safetycomponents/external_hazard/
│       └── external_hazard_component.py
└── tests/
frontend/
├── src/
│   ├── userConfigurationApi.ts
│   ├── domain/{providerConfiguration,safety}.ts  # providerConfiguration is new
│   ├── components/ProviderParameterEditor.tsx   # new
│   ├── pages/{Configuration,ExternalHazards}.tsx
│   └── content/configurationHelp.ts
├── tests/ui/
└── CONFIGURATION.md
```

**Structure Decision**: Extend existing provider/core seams and introduce only a
small pure resolver and dedicated frontend provider editor. Keep provider-specific
schemas and compatibility-path declarations inside each provider. No new top-level package,
remote plugin service, transport stack, authentication route, or persistence layer.

## Phase 0: Research Decisions

[research.md](research.md) records the inspected implementation and decisions:

1. One shared pure resolver at compiler/save and runtime boundaries.
2. Distinct provider-owned editable and runtime schemas with explicit-selection
   provenance retained before defaults merge.
3. Provider-declared IMGW legacy alias resolution without automatic source rewrite.
4. Registry-driven health and hazard/source-specific degradation bindings.
5. A bounded schema-derived editor using the existing configuration routes.
6. Complete snapshots, explicit coverage, and conservative multi-source clearing.

All design choices are resolved using the existing stack and approved scope.

## Phase 1: Design and Contracts

- [Data model](data-model.md): provider definitions, bindings, parameter
  validation, snapshot semantics, coverage, and diagnostic transitions.
- [Provider interface](contracts/provider-interface.md): registration, resolver,
  validation ordering, EventBus, C-EXT, and degradation contracts.
- [Configuration interface](contracts/configuration-api.md): additive metadata
  and errors, canonical parameters, alias behavior, UI edits, and existing routes.
- [Validation guide](quickstart.md): prerequisites, runnable existing checks, and
  acceptance scenarios for the implementation.

### Implementation sequence and dependency boundaries

| Order | Work package | Main outputs and acceptance |
| --- | --- | --- |
| 1 | Provider declarations and resolution | Add parameter/coverage metadata and shared resolver; dispatch system schemas by provider; resolve canonical/legacy fields and explicit selection before persistence. Unit/compiler/API regressions establish the foundation. |
| 2 | Runtime wiring and diagnostics | Pass one validated installed catalogue to startup, SelfDiagnostics, and degradation. Remove fixed provider maps while retaining fault and contributor IDs. Full startup accepts a synthetic regional adapter. Depends on 1. |
| 3 | Hazard and coverage semantics | Filter by declared hazards, validate complete snapshots, retain active evidence, gate clearing on all relevant sources, and scope recovery restrictions by provider. Preserve timing and positive opening-closure behavior. Depends on 1; integrates with 2. |
| 4 | Metadata-driven configuration and presentation | Extend existing catalogue/errors, add typed decoder and bounded editor, preserve inherited/explicit choices and legacy drafts, expose coverage, update Polish help and runtime locales. Depends on 1; can proceed alongside 2/3 against the agreed contract. |
| 5 | Cross-layer acceptance and compatibility | Exercise synthetic non-Polish source through save/import/start/dispatch/health/coverage/failure/recovery/shutdown and mock browser configuration. Refresh public examples/schema and traceability together. Depends on 2..4. |
| 6 | Delivery review | Run all applicable checks, account for baseline formatting, review stable identities and HARA, and record evidence. Deployment remains a separate authorized action. Depends on 5. |

New regression tests accompany each affected safety contract. The synthetic
adapter stays in test fixtures rather than becoming a real bundled national
service. Registration-only or isolated C-EXT tests cannot satisfy work package 5.

### Requirements and evidence allocation

| Specification requirements | Design allocation | Verification focus |
| --- | --- | --- |
| FR-001..005 | Registry, parameter models, resolver, catalogue, editor | Applicable choices, strict fields, pre-save errors, shared location. |
| FR-006..008 | Existing default adapters and normalized contract | Model/official provenance, units/time, responsibility separation. |
| FR-009..014 | Installed catalogue, diagnostics, C-EXT, degradation | Hazard-specific coverage, active-source conflicts, no false clear, independent stalled provider. |
| FR-015 | Provider-declared alias paths and source serialization | Legacy/canonical/equal/conflicting TERYT; model 2 and identity parity. |
| FR-016..017 | Existing configuration store/routes, typed errors, locales | Atomic save/revision, explicit restart, Polish UI and EN/PL/DE runtime parity. |
| FR-018..019 | Synthetic startup acceptance and release review | Complete extension path, unchanged HARA and actuator authority. |

### Verification baseline and risks

Local planning validation on 2026-11-12 verified the unchanged source baseline:
1284 backend tests, 91.75% backend coverage, and 161 frontend tests with Node 20;
Ruff, scoped mypy, frontend typecheck, lint, and build passed. Full
frontend formatting reported 109 pre-existing files. These historical results
do not prove the provider extension; implementation requires fresh acceptance.

Primary risks are losing explicit-selection provenance while serializing,
validating only at startup, alias conflicts created by UI edits, treating empty
partial feeds as safe, and broad diagnostic restrictions that block an independent
provider. Contracts and acceptance cases address each risk. No additional live
service assumptions are needed.

## Complexity Tracking

No constitution violations or additional architecture exceptions are required.
