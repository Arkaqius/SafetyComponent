# Data Model: External Hazard Provider Plugins

**Date:** 2026-11-12

This design refines [the specification](spec.md) and preserves existing source
model and runtime identities. Proposed internal records do not create a new
editable installation format or persistent database schema.

## Provider definition

One registered adapter class owns one immutable definition.

| Field | Type or constraint | Meaning |
| --- | --- | --- |
| `provider_id` | Non-empty stable registry key | Existing `component_name`; raw and derived diagnostic identities must be unique. |
| `adapter_class` | `ExternalApiComponent` subtype | Reviewed bundled implementation. |
| `capability` | Existing `ProviderCapability` | Exactly one of the three existing capabilities. |
| `hazards` | Non-empty set of existing `HazardType` | Explicit coverage compatible with capability. |
| `countries` | Set of uppercase two-letter country codes | Empty means global; missing/unknown metadata never means global. |
| `config_model` | Closed provider-owned Pydantic model | System/runtime endpoint and lifecycle validation. |
| `parameter_model` | Closed provider-owned Pydantic model | Supplied editable parameter values and activation-dependent validation. |
| `required_when_enabled` | Set of declared parameter names | Activation-only requiredness, exported and enforced from the same declaration. |
| `display_name`, `description`, field labels/help | Plain text from packaged provider declarations | Polish editor metadata, never executable instructions or identity; runtime display names and coverage text have EN/PL/DE translations. |
| `legacy_parameter_paths` | Optional mapping from declared parameter names to source-path segments | Provider-owned compatibility inputs relative to `user_config`; IMGW declares `installation.site.teryt_codes`. |

Model and warning providers declare frost/wind/rain/storm subsets; AQ declares
outdoor air pollution. Open-Meteo weather retains the existing four weather
hazards, IMGW the hazards it normalizes, and AQ its current explicit index/units.
A new capability or hazard vocabulary is a separate contract change.

## Source provider selection

The existing `user_config.providers` map gains optional `parameters`. Each entry
has an optional explicit boolean `enabled`; omission must survive read/save and
must not be replaced by its displayed default. `parameters` is a closed mapping
whose fields and supplied values belong to that provider's model.

Unknown provider IDs and supplied undeclared fields fail even when disabled.
Disabled bindings may omit activation-only fields; present malformed values are
not accepted merely because the binding is disabled. Full requiredness applies
when C-EXT and the country-applicable provider are enabled.

### Effective-selection transitions

| Source choice | Country applicable | Effective result |
| --- | --- | --- |
| `enabled` omitted, packaged true | Yes | Active if C-EXT is enabled and required parameters resolve. |
| `enabled` omitted, packaged true | No | Inactive inherited default; no adapter failure. |
| Explicit true | No | Source-path validation error before persistence/activation. |
| Explicit false | Either | Inactive, retained draft values, no polling or adapter contributor. |
| Packaged default false; enabled override omitted | Yes | Inactive unless explicitly enabled. |

Parameter-only entries inherit enablement. Source-map membership alone therefore
does not establish an explicit enabled choice.

## Shared installation location

Shared data remains `country_code` and IANA `timezone`, with latitude/longitude
injected from Home Assistant Core at compilation. The source does not gain
editable latitude/longitude. The existing optional `site.teryt_codes` field
remains only as an IMGW compatibility input, not a universal regional selector.

## Resolved provider binding

The pure resolver returns a mapping keyed by stable provider ID. Each generated
binding contains the provider's validated system transport fields, effective
`enabled`, normalized editable `parameters`, and `selection_origin` (`explicit`
or `inherited`). Country applicability is used to resolve activation rather than
stored as another generated field. Source-path errors retain the appropriate
canonical or compatibility location during validation; alias provenance and
shared site data are not duplicated into each generated binding.

Provider definitions remain in the registry's class mapping. Startup snapshots
the definitions of installed active adapters for diagnostics, C-EXT, and
degradation rather than serializing classes into generated configuration.

Generated `api_components` retains its keys and effective `enabled` behavior.
Any new parameter/provenance fields are additive and are separated before the
existing transport model is validated. The installed runtime catalogue contains
only active bindings. No source normalization mutates the input document.

### IMGW parameter resolution

| Canonical field | Legacy field | Result |
| --- | --- | --- |
| Absent | Valid | Resolve from legacy; preserve source location. |
| Valid | Absent | Resolve from canonical. |
| Valid | Same normalized set | Accept; order is immaterial. |
| Supplied | Different or invalid supplied value | Reject conflict or invalid value; never choose silently. |
| Both absent | Both absent | Reject if active; allow incomplete disabled binding. |

Codes are strings; trim whitespace, require four ASCII digits, preserve leading
zeros, and reject duplicates after normalization. A supplied empty canonical list
is not treated as absent to fall back silently to a different legacy value.
Read and compilation do not migrate source. Explicit editor changes follow the
atomic alias-edit rules in [configuration-api.md](contracts/configuration-api.md).

## Provider result and accepted evidence

Keep immutable `ApiResult`, `ExternalObservation`, `Measurement`, and
`ProviderHealth` identities and existing field semantics. A result is one complete
snapshot for exactly one installed provider; its definition supplies coverage
even when it has no observations.

Before accepting a replacement, check source identity, unique observation IDs,
declared hazards, valid timezone-aware intervals, source semantics, and required
measurement names, finite values, and units. Validate official authority and
urgency against capability. Reject incomplete model snapshots and unsupported
payloads through existing `schema_error`; do not invent new raw health states.

For accepted official snapshots, an empty observation set can be healthy after
successful validation and regional filtering. Model sample timestamps remain
mandatory where required. Cached evidence retains original times. Same-ID updates
replace only that provider's prior assertion. Failed snapshots retain accepted
evidence for diagnostic context and conservative evaluation, without granting
fresh or clear status.

## Health and coverage

Provider health remains `ok`, `stale`, `unavailable`, or `schema_error`.
Before first evidence, health is absent/awaiting rather than a fabricated `ok`.
Coverage is a derived projection, separate from hazard activation and global
`FULL`, `PARTIAL`, `DEGRADED`, and `UNKNOWN` codes.

Additive capability/hazard coverage records contain `capability`, `hazard`,
selected applicable provider IDs, and a reason/status. Projection reasons are
`not_configured`, `unsupported`, `awaiting_evidence`, `unavailable`, `available`,
or `no_current_warnings`; these do not replace provider or aggregate raw states.
An available forecast does not make an unconfigured official feed healthy.

For hazard `h`, relevant providers are active applicable bindings whose declared
hazards include `h`. Any valid active assertion remains usable independently.
Data-based clearing requires a non-empty relevant set, fresh complete healthy
results from all members, no active assertion, and existing hysteresis/delay.
An unknown, pending, stale, failed, or uncovered path provides no positive clear
evidence. Positive closure of an opening follows its existing separate delay.

## Diagnostic dependency and recovery records

Retain `ExternalDataUnavailable`, `ProviderHealth{ProviderId}`, and existing
capability contributor identities. Derive their targets from installed bindings
and exact consumer hazard/opening parameters, not provider-name maps.

Provider-specific degradation targets gain an optional internal provider scope.
Capability-level targets have no single-provider scope and apply only to the
affected hazard/dependency. Existing non-provider bindings retain their current
behavior. Re-evaluation keys include provider scope so recovery of one source
cannot release a peer's pending or failed restriction for the same capability.

Diagnostic clear restores eligibility to evaluate that source. Fresh hazard
evaluation and current recovery policy are still required; it never clears a
hazard, removes another cause, or replays an actuator command.

## Configuration errors

Existing error and message fields remain. Optional `field_errors` contains bounded
records of `{path, code, message}`, where `path` is a source-relative sequence of
string keys or list indexes. Preserve alias provenance so legacy errors reference
the original source while the editor can highlight the corresponding provider
field. Do not derive structured errors by parsing exception strings.
