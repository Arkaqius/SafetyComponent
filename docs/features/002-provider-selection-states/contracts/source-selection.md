# Contract: Source Selection and Configuration API

## Canonical editable shape

```yaml
user_config:
  model_version: 2
  external_sources:
    WeatherPointModel: OpenMeteoWeatherApiComponent
    OfficialWeatherWarnings: ImgwWarningsApiComponent
    OutdoorAirQuality: OpenMeteoAirQualityApiComponent
  provider_parameters:
    ImgwWarningsApiComponent:
      teryt_codes: ["0000"]
```

This is a fragment of the full source; component selection, notification and
installation registry remain required as documented in the configuration
architecture. Null means explicit disabled:

```yaml
external_sources:
  WeatherPointModel: OpenMeteoWeatherApiComponent
  OfficialWeatherWarnings: null
  OutdoorAirQuality: OpenMeteoAirQualityApiComponent
```

Do not accept missing category keys, multiple selections, old user_config.providers,
source enabled switches, selection_origin, or installation.site.teryt_codes.
Do not infer a country default. Country changes revalidate instead of replacing
the source. Unknown/mismatched IDs and malformed parameter fields fail before
save or startup. Validate source and generated runtime through the same pure
resolver, without network access.

All parameter values have one owner: provider_parameters.<ID>.<field>.
IMGW retains trimmed unique four-ASCII-digit codes and leading zeros. Other
providers do not request TERYT. Retain inactive known parameter drafts;
require selected active fields and validate all supplied values.

System runtime_cfg.providers holds lifecycle/transport policy only, with no
enabled defaults. Runtime api_components may contain derived enabled flags for
lifecycle. There is no second editable selection model.

## Read-only catalogue

Keep GET /api/config and its outer envelope. Under
system_defaults.external_hazard expose provider_metadata_version 2 and
provider_plugins. Each entry declares countries, capability, hazards, display_name,
description, parameter_schema, required_when_selected, parameter_defaults,
data_kind and transport_kind. Remove enabled and legacy_parameter_paths metadata.

Registry declarations, rather than parameter input, determine data_kind and
transport_kind. Required names must exist in the closed parameter schema.
Existing bounded interpretation remains: 1 MiB catalogue, 64 providers,
64 KiB/schema, 64 properties, 128 local definitions, depth 8, reference hops 16,
1024 enum values, title/enum text 256, help 2048, pattern 256 characters.
Unsafe property/path keys remain rejected. Version 1 is not decoded as a fallback.

## Writes and errors

Keep PUT /api/config, POST /api/config/import and POST /api/config/restart-target.
Save/import errors use existing 422 error/message and bounded field_errors;
revision conflicts remain 409. Errors identify external_sources.<capability> or
provider_parameters.<ID>.<field>. Existing bounds remain 32 errors, 16 path
segments, 128 characters per string segment and 512 per field message.

Import validates and previews; it does not save or migrate. Invalid/obsolete saved
source remains readable for correction/reset, with its actual revision and
validation errors, but cannot start monitoring. This is invalid-input handling,
not a legacy editor or automatic converter. Valid reads do not dirty the draft.
No private source is rewritten on read. Restart remains a separate confirmed
operation against the saved revision; source changes are not hot-applied.

## UI

Three neutral categories, one selector each. Values are provider IDs or a disabled
sentinel mapped only to source null. Options are applicable named providers and
“Wyłączone”; no inheritance/enablement submenu. Unknown or incompatible selected
values remain visible as validation errors. The selected provider alone exposes
its declared fields. Update selection and canonical values immutably without
legacy read/write/reconciliation functions.

The public PL template selects IMGW explicitly. The public German example selects
no official-warning provider by default; a separate acceptance draft explicitly
selects the dummy. Global models are explicit choices, not inheritance defaults.
