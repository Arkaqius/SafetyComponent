# Data Model: Explicit Provider Selection

## Editable source

| Entity | Fields and rules |
| --- | --- |
| ExternalSources | Required closed map: WeatherPointModel, OfficialWeatherWarnings, OutdoorAirQuality. Every value is a registered ID or explicit null. |
| ProviderParameters | Optional closed-by-registry map from provider ID to its own closed parameter object. No enabled or parameters wrapper. |
| InstallationSite | Country/timezone shared; coordinates obtained from HA. No teryt_codes. Site is required for active C-EXT selections. |
| ProviderDefinition | ID, capability, hazards, countries, data_kind, transport_kind, closed runtime/parameter models, required_when_selected and friendly metadata. |
| ResolvedBinding | Selected ID, canonical parameters, system lifecycle policy and derived enabled. No selection_origin or alias provenance. |

When the component is off, selections remain saved but no adapter is active.
Validate IDs, capabilities and supplied shapes regardless; active requiredness
and required site apply when C-EXT is on and a source is selected. If a site is
supplied, selected-country applicability is checked; missing site while disabled
does not trigger polling or require example coordinates.

Inactive known provider values remain saveable if supplied values are valid;
missing active-only fields are allowed. Unknown fields or IDs are rejected even
when inactive. Parameters cannot supply transport settings.

## AppliedSelectionSnapshot

Published at `sensor.external_source_selection` independently of C-EXT.

| Field | Rule |
| --- | --- |
| schema_version | Integer 1; unsupported/missing means unknown presentation. |
| runtime_id | Nonempty per-start ID, max 128 ASCII characters. |
| component_enabled | Boolean indicating actual compiled component activation. |
| selections | Exactly the three capability keys, each holding the fields below. |
| selections.*.provider | ID or null, from applied source. |
| selections.*.data_kind | live, synthetic, or null when provider is null. |
| selections.*.hazards | Declared hazard codes, empty only when provider is null. |

Publication is bounded to the three categories, IDs <=128 characters and existing
hazard enum. It contains no region codes, credentials or private parameter values.
Derived presentation never updates this snapshot from a browser draft.

## MonitoringCategory

| Field | Rule |
| --- | --- |
| capability | Existing capability identity. |
| selection_state | enabled, disabled, component_disabled, unknown, or test. |
| evidence_state | unknown, unsupported, awaiting_evidence, unavailable, stale, healthy_empty, active, available, or not_evaluated. |
| provider/name | Actual selected source and catalogue-friendly name; never infer selection from brand. |
| current_count | Nullable integer; null/“—” for disabled/unknown/unevaluated real coverage. |
| retained_evidence | Historical/active real evidence shown separately with provenance and validity. |
| runtime_id | Same generation as applied selection for any current evidence. |

Raw provider health remains ok/stale/unavailable/schema_error. Presentation is
derived, not another provider-health enum. A real empty official feed maps to
healthy_empty only when usable for the applied category and declared hazard.
Weather/AQ models use available, never official no-warning claims.

## SyntheticPreview

Separate `sensor.external_hazard_test_state` with schema_version 1, runtime_id,
provider, provider_name, data_kind synthetic, scenario, health, capability,
hazards, bounded observations, warnings and count. Its entity state is the raw
preview health (or awaiting_evidence before a result); timestamps are
last_success_at and last_attempt_at, with stale_after_seconds, detail_code and a
localized test_label. Scenario is null before the first result.
Maximum 64 summaries, using existing normalized observation summary limits.
No real H symptom IDs, fault IDs or recovery command/proposal fields.

## RealAssertionCheckpoint

The existing SQLite `external_hazard_assertions` record namespace stores one
closed envelope: schema_version 1 and an assertions mapping keyed by symptom_id.
Each strict record contains symptom_id (1..256 alphanumeric/underscore characters,
beginning with a letter), fault_id (ExternalWeatherExposure or
OutdoorAirQualityExposure), opening (1..128 characters), hazard, source
(1..128 characters), timezone-aware asserted_at and finite JSON context of depth
at most 8. Fault, symptom, opening and hazard identities must agree; supplied
context source/opening_id/hazard_code must agree with their record fields.
Synthetic observations never enter this namespace.
Cap the complete checkpoint at 4096 records and 1 MiB serialized UTF-8; validate
closed record fields, identities, timestamps and total size before restore/write.
Attempt an atomic checkpoint before publishing a qualified real transition.
If assertion persistence fails, retain the real assertion in memory and expose
the persistence failure; a failed clear checkpoint must withhold the clear.
Storage failure, invalid schema or limit overflow must never silently discard
danger or turn uncertain persistence into positive clear evidence.

Restore active assertions before initial real fault publication, even if their
source/component is now disabled or the opening was removed. Mark them retained
and unevaluable rather than current fresh evidence. Do not restore qualification
timers or replay notifications/recovery proposals/actions. A removed opening
remains unresolved; physical closure may clear only through a valid matching
configured contact. Missing/corrupt checkpoint with an ACTIVE evidence journal
means UNKNOWN/retained danger, never an inactive/healthy claim. Fresh installations
without previous assertion evidence begin awaiting evidence normally.

## RetainedFaultPublication

External real fault entities publish retained_assertions as complete restored
records and retained_hazard_unknown as a boolean. Restored assertions keep
active=true with raw evaluation UNEVALUABLE, independently of whether their
current source or opening exists. A qualified fresh real decision replaces that
symptom's retained presentation; a different symptom cannot clear it. When an
active journal has no matching usable assertion record, an unresolved retained
unknown contributor keeps the fault active/UNEVALUABLE and sets the boolean.

The application-level safety_coverage_state snapshot wraps the degradation
snapshot. While retained assertions or retained uncertainty remain, FULL or
PARTIAL is changed to UNKNOWN; existing DEGRADED or UNKNOWN is preserved.
Attributes are retained_external_assertion_count (total restored unresolved
records), retained_external_assertions (at most 32 records) and
retained_hazard_unknown. These attributes are optional when there is no retained
state. This wrapper does not manufacture a diagnostic failure or new clear.

Recovery restore excludes external exposure proposal IDs via
restore_excluded_symptoms: both checkpoint symptom IDs and currently configured
external weather/air-quality symptom IDs. Persisted recommendations and consent
are not replayed merely because those symptoms are restored. Normal fresh real
evidence may create a new proposal through the existing confirmation boundary.

## State transitions

- Draft selector change: update only its category; retain parameter map.
- Save: validate whole target source, then atomically replace if revision matches.
- Before restart: applied snapshot and monitoring remain unchanged.
- Startup: publish current snapshot and awaiting evidence before scheduling.
- Disable: applied disabled state mutes its real monitoring metrics; retained
  real faults/evidence do not become cleared.
- Synthetic result: update preview only; real category coverage stays unevaluable.
- Reconnect: current status requires matching runtime_id and fresh usable evidence;
  retained or previous-generation state cannot produce a healthy zero.
