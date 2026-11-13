# Research: External Hazard Provider Plugins

**Date:** 2026-11-12

**Scope:** Phase 0 decisions for [the implementation plan](plan.md). This is a
planning record of implementation evidence and design choices, separate from
normative SYS/SSRD requirements.

## 1. Reuse the existing provider boundary

**Decision:** Extend the explicit bundled registry and existing adapters. Keep
Open-Meteo behind the same internal contract while retaining its default role.

**Rationale:** The registry, `ExternalApiComponent`, `ApiResult`, serialized
`external_api_result`, and capability-based C-EXT already exist. A second plugin
loader or special model-provider path would duplicate lifecycle and error rules.
An additional real national service is outside this feature's agreed scope.

**Alternatives considered:** Runtime entry-point installation; a new provider
service; bypassing adapters for globally available sources. All add scope without
solving configuration and diagnostic coupling.

**Evidence:** `backend/components/external_apis/core/registry.py`,
`api_component.py`, `models.py`, and `api_runtime.py` within that same directory;
the explicit imports in `backend/components/external_apis/__init__.py`.

## 2. Validate at compilation and startup

**Decision:** Introduce a pure shared provider resolver in the external API core.
Call it from compilation and reuse its rules at `AppCfgValidator` startup.
Do not make source validation depend on live HTTP or Hass calls.

**Rationale:** `compile_config()` validates source models but provider runtime and
site validation currently occurs in `_validate_api_components()` at startup.
`UserConfigStore.save()` and import validate through compilation. Leaving these
paths separate can allow an invalid provider configuration to be saved first.

**Alternatives considered:** Validate only in `SafetyFunctions`; invoke the
entire application validator from the source store; duplicate provider rules in
the API handler. A focused resolver avoids a broad lifecycle dependency and
keeps save/import/compiler/startup behavior equivalent.

**Evidence:** `backend/build_app_config.py`,
`backend/components/app_config_validator/app_cfg_validator.py`, and
`backend/user_config_api.py` save/import/restart validation paths.

## 3. Separate editable parameters from transport configuration

**Decision:** Each provider supplies a closed editable parameter model and its
existing runtime/transport model. The packaged provider map dispatches by registry
ID; the common `ProviderRuntimeSource` may remain a reusable base, not a closed
universal schema. Parameter metadata defines activation-dependent requiredness.

**Rationale:** User `ProviderSelection` currently accepts only `enabled` and the
system map accepts one fixed lifecycle schema. New regional fields and
provider-specific system fields need validation by their owners. Unknown fields
always fail; disabled bindings may omit activation-only parameters, but supplied
values must still be structurally valid.

**Alternatives considered:** Unvalidated free-form dictionaries; putting every
regional field on the common site; duplicating a per-provider union in shared
configuration code. Registry dispatch preserves isolation and closed schemas.

**Evidence:** `backend/configuration_model.py`, `backend/system_configuration.py`,
and the existing provider `schema.py` files.

## 4. Preserve explicit-selection provenance

**Decision:** Resolve applicability before defaults obscure whether `enabled`
was supplied. Retain omission when serializing source; carry effective activation
and selection provenance through the generated binding as additive internal data.

**Rationale:** Explicit true outside country coverage is an error, inherited true
outside coverage is inactive, and explicit false is inactive. The current merge
loses that distinction. A read or unchanged save must not materialize overrides.

**Alternatives considered:** Treat every merged true as explicit; silently
disable all incompatible choices; infer intent from provider-map presence alone.
The last alternative fails for parameter-only bindings inheriting enablement.

**Evidence:** `compile_user_config_v2()` uses `exclude_unset=True` before
`deep_merge`; the save path also excludes unset fields. Pydantic tracks explicitly
supplied fields through `model_fields_set` and preserves omission with
`exclude_unset`. [Pydantic 2.12 serialization](https://docs.pydantic.dev/2.12/concepts/serialization/)

## 5. Resolve legacy TERYT inside IMGW

**Decision:** Add an IMGW-owned pure parameter-resolution hook. Accept the shared
site alias and canonical parameter; normalize code strings, reject duplicates,
compare simultaneous declarations as sets, and reject disagreement. Do not
rewrite source on read or compilation.

**Rationale:** Generic resolution must not encode Polish field names. Existing
source format and generated identities remain compatible. UI edits must avoid
creating a stale second declaration when a legacy file is displayed.

**Alternatives considered:** Remove the alias; prefer canonical values silently;
require manual migration; copy aliases into source on every read. Each either
breaks compatibility or hides a configuration conflict.

**Evidence:** `InstallationSite`, runtime `SiteConfig`, and
`backend/components/external_apis/imgw_warnings/component.py`.

## 6. Publish one schema-derived catalogue

**Decision:** Export provider-specific parameter schemas and field metadata from
the same definitions used by validation. Preserve existing `provider_plugins`
entries and their `countries`/`enabled` fields. Deterministically inline bounded
provider-local schema definitions so exported schemas are self-contained and
cannot collide; never cache a catalogue across registry changes.

**Rationale:** The existing exported schema lists allowed provider IDs but not
each provider's different parameters. Pydantic supports validation-mode JSON
Schema and field metadata; use those facilities instead of parallel hand-written
frontend rules. [Pydantic 2.12 JSON Schema](https://docs.pydantic.dev/2.12/concepts/json_schema/)

**Alternatives considered:** A new metadata endpoint; a hardcoded provider form
per country; a frontend-only schema. The existing authenticated configuration
response is the smallest compatible interface.

## 7. Keep UI interpretation bounded and typed

**Decision:** Add a typed catalogue decoder and a dedicated provider parameter
editor reusing existing field primitives. Support closed flat parameter objects,
scalars, enums, and bounded string arrays with documented constraints. Reject
unknown metadata rather than interpreting it as global applicability.

**Rationale:** The current editor hides explicitly incompatible choices and treats
unknown IDs as unrestricted. Its general object renderer also contains household
conditionals. A bounded provider renderer avoids importing those assumptions or
building a general-purpose JSON Schema application.

**Alternatives considered:** A new form framework; arbitrary recursive schema
execution; extending every household-specific conditional in the existing editor.
Server validation remains authoritative for cross-field and plugin-specific rules.

Metadata version 1 uses fixed export/decoder size, depth, reference, field, and
text budgets specified in the configuration contract. These bound interpretation
without changing existing source-model parameter limits. Oversized metadata is
an explicit error, not permission to discard saved values or infer eligibility.

**Evidence:** `frontend/src/pages/Configuration.tsx`,
`frontend/src/components/ConfigurationObjectEditor.tsx`, and
`frontend/src/userConfigurationApi.ts`.

## 8. Resolve diagnostics by installed source and hazard

**Decision:** Pass the validated installed-provider catalogue into SelfDiagnostics,
C-EXT, and degradation compilation. Scope provider restrictions to both provider
identity and supported hazard; retain separate capability-level contributors.

**Rationale:** SelfDiagnostics rejects names outside `PROVIDER_FAULTS` and
degradation maps each capability to one hardcoded provider. A synthetic provider
can pass compilation while full startup still fails. Multiple providers with the
same capability also require source-specific recovery and re-evaluation state.

**Alternatives considered:** Append each future provider to global maps; clear
all capability restrictions when one source recovers; infer coverage from class
names. These violate the extension and independent-evidence contracts.

**Evidence:** `backend/components/core/self_diagnostics.py`,
`backend/components/core/degradation.py`, and `backend/SafetyFunctions.py`.

## 9. Treat snapshots and empty feeds explicitly

**Decision:** Keep `ApiResult` as a complete snapshot and validate it against the
installed provider definition before replacing accepted evidence. Retain source
and validity times, declared hazard coverage, and model/official semantics. Empty
official feeds can establish absence only for their confirmed coverage; model
snapshots must contain the measurements required by their declared coverage.

**Rationale:** A common capability does not imply support for every hazard. An
empty wind-only feed is unrelated to frost. A failed, partial, expired, or
malformed snapshot cannot become positive clear evidence. An empty official feed
uses retrieval freshness without inventing a source observation timestamp.

**Alternatives considered:** Empty observations always mean safe; every weather
provider covers every weather hazard; let later policy discover malformed fields.
All risk broadening clear evidence beyond the provider's contract.

## 10. Prove the entire extension path with controlled sources

**Decision:** Extend full startup integration with a synthetic non-Polish adapter,
independent scheduling, diagnostic/degradation checks, and mock frontend metadata.
Use local fixtures; preserve the existing transport and deployment boundaries.

**Rationale:** Existing tests cover a synthetic provider's compilation and C-EXT
handling separately. They do not prove full startup and source-specific coverage.
The prior local baseline passed all runtime checks except repository-wide
frontend formatting; that is evidence of existing behavior, not the extension.

**Alternatives considered:** Test only the registry; use a real household or a new
live national endpoint for acceptance. Controlled fixtures are deterministic and
exercise failures without introducing an unrelated integration or actuator risk.

## Resolution status

All research decisions needed for Phase 1 are resolved. The design remains within
the accepted specification and ADR. Concrete APIs, models, validation ordering,
and acceptance details are in [data-model.md](data-model.md),
[contracts/provider-interface.md](contracts/provider-interface.md), and
[contracts/configuration-api.md](contracts/configuration-api.md).
