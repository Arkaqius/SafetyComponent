# Contract: Bundled External Provider Interface

**Date:** 2026-11-12

**Requirements:** FR-001..004/006..015/018..019; SWR-EXT-018..027.

This is an implementation design for the existing internal interface. It keeps
the current capability vocabulary, source model 2, EventBus event, provider IDs,
faults, entities, topics, and raw states.

## Registration and catalogue

Retain `register_api_component` and explicit bundled imports. Extend declarations
with `parameter_model`, `required_when_enabled`, non-empty `hazards`, and friendly
presentation metadata while retaining `component_name`, `config_model`,
`capability`, and `countries`. Models must reject undeclared fields.

Registration validates declaration shape, unique raw and derived diagnostic IDs, capability/hazard
compatibility, declared required parameter names, and supported presentation
metadata. Generated JSON Schema deterministically inlines controlled local
definitions into self-contained provider schemas; no external schema reference
is fetched. New registration must not depend on
SelfDiagnostics or C-EXT importing a provider-specific class.

Contributor names and MQTT entity slugs shall retain the existing derivation
rules and be checked independently for collisions before activation. Distinct raw
names such as `Foo` and `FooApiComponent` shall be rejected when either derived
identity collides. `FooBar` and `FooApiComponentBar` also collide in their MQTT
slug despite different contributor names. Existing provider identities remain
unchanged.

The common infrastructure may enforce shared transport bounds, but the provider's
own model validates its complete packaged schema. A synthetic provider may add a
system-owned field without modifying a universal provider record.

## Pure configuration resolution

Add a shared external-core configuration module with purpose-oriented docstrings
and typed interfaces. The public operations have these responsibilities:

| Operation | Inputs | Output and failure behavior |
| --- | --- | --- |
| Resolve source bindings | Registered definitions, packaged provider settings, source-selection mappings, shared site, C-EXT enabled flag | Normalized generated binding mappings or structured source-path errors; no I/O. |
| Validate generated bindings | Same definitions/policy plus generated effective bindings and provenance | Equivalent active parameters and transport constraints; no polling. |
| Resolve provider parameters | Provider-owned raw parameters, shared site compatibility inputs, active flag | Normalized parameters or plugin-scoped errors; no source mutation. |
| Export catalogue/schema | Registered definitions and packaged defaults | Closed per-provider source schema and bounded editor metadata. |

Compilation must invoke source resolution before returning an accepted result.
Save, import, compiler check, and restart validation thereby reject invalid
provider choices before replacement or activation. Startup reuses the same
resolver rules rather than maintaining a second implementation.

### Resolution ordering

1. Validate the source model version and known provider IDs/entry keys.
2. Validate each packaged provider through its registered transport model.
3. Capture whether each source `enabled` field was explicitly supplied before
   merging defaults. Parameter-only entries do not imply explicit enablement.
4. Resolve country applicability and effective C-EXT/provider activation.
   Reject explicit true outside coverage; inherited incompatible defaults stay
   inactive. A disabled C-EXT does not require a fabricated active site.
5. Validate supplied editable keys/types/constraints without yet requiring
   missing activation-only fields. Unknown fields always fail.
6. Resolve compatibility paths declared by the provider, including the IMGW alias
   and conflict rejection. Then enforce activation-only requiredness against the
   resolved parameters for applicable active providers. A valid legacy-only
   binding must not fail because its canonical field was initially absent.
7. Produce generated bindings; startup snapshots active provider definitions
   from the registry for installed consumers. Do not
   instantiate adapters or issue network requests during these steps.

Generated `api_components.<id>` retains existing effective `enabled` and transport
fields. Add `parameters` and an internal `selection_origin` of `explicit` or
`inherited` where needed. Remove internal fields before invoking a provider's
transport-only model. Pre-extension generated bindings without provenance retain
legacy startup applicability handling; newly compiled editable sources always
receive the stricter explicit-selection rule. Neither internal provenance nor
resolved defaults are written back into editable source.

IMGW resolution accepts canonical `parameters.teryt_codes` and legacy
`installation.site.teryt_codes`; normalization/equivalence rules are defined in
[the data model](../data-model.md#imgw-parameter-resolution). The generic compiler
does not compare or interpret TERYT itself.

## Construction, polling, and dispatch

Retain the existing injected HTTPS transport and constructor boundary. Add
normalized parameters as an optional keyword argument or equivalent typed binding
input, preserving current constructor callers during transition. Site context
contains shared location; IMGW declares its old alias through
`legacy_parameter_paths`, which the shared resolver reads without provider-name
branches.

No constructor performs polling. Preserve one in-flight call per provider,
independent schedules/caches/counters, bounded workers and results, system-owned
timeouts/retries, and deterministic shutdown. Source/metadata validators do not
fetch schemas, resolve regions online, or poll providers.

The existing event remains:

```text
event: external_api_result
argument: result: ApiResult
producer: ExternalApiRuntime serialized drain
consumers: provider-health diagnostics and ExternalHazardComponent
```

Validate normalized results before publishing a successful snapshot so diagnostics
and C-EXT agree on health. Check provider identity, observation uniqueness,
declared hazards, temporal intervals, provenance, complete required measurement
sets, finite values, and expected units. A malformed replacement becomes the
existing `schema_error`, retaining previous accepted evidence without refreshing
its timestamps. A failed poll does not publish a synthetic healthy empty feed.

`ApiResult` remains a complete snapshot, not a delta. An official-warning plugin
must positively validate the complete feed before returning a healthy empty set.
An empty/partial model result cannot stand in for missing measurements. Late or
cached observations preserve source validity; a future warning is not yet active.

## C-EXT evidence and diagnostic allocation

Use the installed catalogue to select providers by capability **and declared
hazard**. Keep the existing model/opening qualification timers and policy
thresholds. Any valid active applicable source supports its own evidence even
if a peer is unhealthy. Data-based clear requires every relevant selected source
to be fresh, healthy, and sufficiently complete, and none to sustain the hazard.
Expiry removes an assertion but cannot turn a failed refresh into absence.
Confirmed physical closure remains the separate existing exposure-clear path.

Allocate each installed adapter to `ExternalDataUnavailable` through the common
diagnostic contract. Preserve existing contributor naming. No fixed provider-ID
allowlist or capability-to-single-provider map remains in shared diagnostics,
C-EXT, or degradation compilation. Capability-loss contributors remain distinct
from adapter-health contributors.

Degradation compilation receives the same installed catalogue. Match exact
consumer symptoms by hazard/opening, add optional internal provider scope to
provider-specific targets, and retain generic capability restrictions separately.
Re-evaluation tracking includes that scope. When recovery policy names evidence
from provider B, a provider-A-only failure cannot invalidate B; a failed shared
dependency or unresolved binding still applies conservatively. Missing/unknown
evidence-source identity must never bypass a restriction.

Keep existing external aggregate/provider raw states and attributes. Add declared
`hazards` to provider diagnostics and additive `coverage_details` on the existing
aggregate entity. Each coverage detail identifies capability, hazard, selected
providers, and its derived status/reason as defined in the data model. These
projections do not alter the global coverage state vocabulary or grant safety
credit to an unconfigured official-warning feed.

## Conformance acceptance

A controlled additional provider uses a country other than PL, a custom regional
parameter, a provider-specific packaged field, and a subset such as wind-only.
It must traverse compiler, save/import validation, complete startup, scheduling,
EventBus, C-EXT, diagnostics, coverage, recovery scoping, and shutdown without
provider-name edits outside its definition/registration.

Acceptance includes two providers of the same capability, failures before/after
active evidence, healthy empty versus malformed/partial feeds, missing source
times, unsupported hazards, alias conflicts, disabled incomplete bindings,
country transitions, identity regression, and no actuator calls. See
[the validation guide](../quickstart.md).
