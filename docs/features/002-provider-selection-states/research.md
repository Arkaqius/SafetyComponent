# Research: Provider Selection and Monitoring States

**Date**: 2026-11-13. **Mode**: brownfield design, backend/frontend read-only
research. Decisions below describe the target, not deployed behavior.

## 1. One explicit choice per category

**Decision**: Require `external_sources` with the three existing capability keys
and an ID or null for each. Store values in `provider_parameters.<ProviderId>`.
Keep source model version 2 and reject old shapes.

**Rationale**: Selection becomes independent of parameter retention, country
applicability and lifecycle policy. There is no default-vs-explicit provenance.

**Alternatives considered**: Keeping per-provider enabled switches preserves the
ambiguity the user rejected; embedding all inactive providers in each category
duplicates ownership. A compatibility converter is explicitly excluded.

## 2. Remove compatibility at the boundaries

**Decision**: Remove old provider source fields, site TERYT alias, legacy path
metadata, constructor fallbacks and provenance. Update validators, examples,
schema exports, shared fixtures and tests in the same implementation.

**Rationale**: Current core/configuration.py resolves aliases and selection_origin;
frontend providerConfiguration.ts mirrors them. Both need removal to avoid two
models disguised behind one selector.

**Alternatives considered**: A new selector over legacy bindings would keep the
complexity in the backend and tests. Rewriting unrelated state migrations is
outside the user's feature scope.

## 3. Apply state is independent of save state

**Decision**: SafetyFunctions publishes a small `sensor.external_source_selection`
snapshot before polling, even when the external component is disabled. Use a
per-start `runtime_id` shared by selection, provider, aggregate and preview output.

**Rationale**: The current safety decoder filters disabled providers out using
enabled_providers. Neither absence nor saved YAML proves what the running process
has applied. Boot identity prevents retained healthy values from a previous
configuration supplying current healthy status.

**Alternatives considered**: Reading the saved API document on the monitoring page
would misreport saved-but-not-restarted changes. Deriving disabled from missing
entities confuses disabled, booting, disconnected and unknown.

## 4. Separate display state from raw health and hazard state

**Decision**: Add category presentation derived from applied selection plus fresh
matching-generation evidence. Disabled wins over old diagnostic counts; a real
active hazard remains separately visible. Disconnection/missing metadata is unknown.

**Rationale**: Current ExternalHazards headings are already generic, but healthy
counts, exposure summaries and default zero values can imply healthy monitoring.
The whole summary, cards and counters need coverage-aware presentation.

**Alternatives considered**: Only changing a badge or greying the official list
leaves green top-level summaries misleading. Renaming provider raw health states
is unnecessary.

## 5. Trusted synthetic classification

**Decision**: Declarations add `data_kind: live|synthetic` and
`transport_kind: http|none`. Route synthetic results to
`external_api_test_result` using the runtime's registered adapter identity.
Keep previews outside real health/observations, diagnostic allocations and policy.

**Rationale**: SelfDiagnostics currently consumes external_api_result before C-EXT.
An ordinary dummy result could alter D/H state before the UI ever labels it.

**Alternatives considered**: Payload-only flags can be dropped or falsified;
UI-only badges do not isolate safety effects. A second complete runtime is
unnecessary because the existing scheduler can dispatch through two typed paths.

## 6. Selectable German dummy

**Decision**: Bundle `GermanyDummyWarningsApiComponent`, country DE, wind-only,
synthetic and transport none. Parameters are a synthetic region_code and a
scenario enum: empty, warning, unavailable, stale. It has no default selection.

**Rationale**: Existing regional adapters live only in test support. They cannot
exercise the actual configuration catalogue and operator flow. A bundled dummy
tests that extension without representing a real German authority.

**Alternatives considered**: Adding a live German national integration adds an
unrequested service dependency; a UI-only mock bypasses the production plugin
boundary. A synthetic preview must never claim official authority.

## 7. Reuse bounded metadata and UI primitives

**Decision**: Metadata version 2 removes enablement defaults/legacy paths and adds
trusted classification. Keep existing schema budgets, finite scalar/string-array
validation, plain-text help, safe-key rejection and immutable draft updates.

**Rationale**: Those controls are safety/input boundaries rather than compatibility
baggage. Reuse ProviderParameterEditor for the selected source only.

**Alternatives considered**: New form frameworks or generic editable dictionaries
increase scope and weaken the declared-field boundary.

## 8. Keep unrelated source and consent rules

**Decision**: Preserve common site coordinates from HA, asset threshold precedence,
revisioned full saves, separate confirmed restart, live provider IDs and H/D raw
states where unchanged by the explicit source break. Amend SYS/SSRD and ADR.

**Rationale**: Waiving backwards compatibility does not waive positive-clear,
operator consent or real/test separation. There is no reason to rename healthy
live provider entities or modify HARA goals.

**Alternatives considered**: Broadly resetting state or identifiers would add risk
without simplifying provider selection.

## 9. Retain real assertions across selection/restart

**Decision**: Add a bounded active-real-assertion checkpoint in the existing SQLite
store, restored before FaultManager publishes initial fault states. A disabled,
removed or synthetic replacement source leaves previously asserted real hazards
active but unevaluable until a valid independent clear is available.

**Rationale**: Current cfg_parser.get_faults creates fresh fault objects;
SafetyFunctions.register_entities publishes their initially inactive state even
if the evidence journal still has an ACTIVE record. That journal freezes an early
symptom frame and cannot reconstruct all active opening/hazard contributors.
FR-010 needs an explicit restart checkpoint rather than a display-only fix.

**Alternatives considered**: Resetting faults on reconfiguration creates false
clear evidence. Replaying the old event stream can resend notifications and
commands. Restoring qualified assertions without timers or action replay is bounded
and preserves the positive-clear policy. No legacy checkpoint importer is needed.

## Evidence inventory

Reviewed source models/compiler/API, system and public user configuration,
registered adapter/runtime/C-EXT/diagnostic paths, frontend config/domain/hooks,
warning page/CSS, existing browser tests and synthetic support fixtures.
Private installation source is not modified; old sources will require manual
replacement before a separately authorized deployment. No new external technical
dependency requires online research.
