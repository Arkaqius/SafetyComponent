# Contract: Provider Configuration and Operator Interface

**Date:** 2026-11-12

**Requirements:** FR-001..005/011/015..018; SWR-EXT-019..021/025..027.

## Existing routes and envelopes

Keep the authenticated Ingress and loopback configuration server boundary.
No authentication, nginx, unrelated gateway, or actuator endpoint is added.

| Route | Request | Preserved response or behavior |
| --- | --- | --- |
| `GET /api/config` | None | Existing source/template/defaults/revision/setup/restart fields and optional validation error. Read does not write or migrate. |
| `PUT /api/config` | `{user_config, revision}` | Saved source, new revision, `restart_required: true`, `setup_required: false`; validated atomic replacement. |
| `POST /api/config/import` | `{yaml}` | Validated `user_config` draft only; no persistence or activation. |
| `POST /api/config/restart-target` | `{confirmed: true, revision}` | Existing own-App `{app_slug}`; separate authenticated HA admin action performs restart. |

Unknown provider IDs or keys, invalid selected parameters, alias conflicts, and
explicit enabled incompatible-country choices must fail compiler validation
before save replacement or successful import. Keep revision checks before and
after candidate validation, file mode preservation, and same-directory atomic
replacement. A failed save leaves bytes, revision, and running configuration
unchanged. No external HTTP request is made by provider validation.

An invalid saved source must remain readable for correction through the existing
`validation_error` path. Catalogue generation depends on registered definitions
and packaged defaults, not on the invalid source passing active-provider
resolution. Reading it must not rewrite it or prevent the editor displaying the
original values alongside errors.

## Editable source extension

```yaml
user_config:
  model_version: 2
  providers:
    ImgwWarningsApiComponent:
      enabled: true
      parameters:
        teryt_codes: ["0000"]
  installation:
    site:
      country_code: PL
      timezone: Europe/Warsaw
```

This fragment describes the additive provider fields; the complete installation
still requires the existing root fields. Coordinates come from Home Assistant.
Editable entries accept only `enabled` and declared `parameters`. Endpoints,
timeout/retry/staleness bounds, and executable plugin code are not editable here.
Existing enablement-only entries and the legacy site TERYT alias remain valid.
Provider omission means inherited defaults, not explicit enablement.

## Additive provider catalogue

Retain `system_defaults.external_hazard.provider_plugins`, keyed by stable
provider ID, and existing `countries` and `enabled` fields. Add the following
fields per entry. Add `provider_metadata_version: 1` beside that map to identify
the bounded metadata vocabulary without changing source model version 2.

| Field | Meaning |
| --- | --- |
| `countries` | Existing applicability set; an explicit empty array means global. |
| `enabled` | Existing packaged default, distinct from an operator override. |
| `capability`, `hazards` | Existing capability code and non-empty supported hazard list. |
| `display_name`, `description` | Friendly plain text; Polish editor text, stable ID separate. |
| `parameter_schema` | Closed validation-mode object schema with controlled local definitions. |
| `required_when_enabled` | Declared activation-only required parameter names. |
| `parameter_defaults` | Non-secret provider-owned editable defaults; never transport policy. |
| `legacy_parameter_paths` | Optional provider-owned mapping from a declared parameter to a compatibility path relative to `user_config`; IMGW declares `teryt_codes` at `installation.site.teryt_codes`. |

Schema field titles/help are localized presentation data derived from packaged
plugin metadata. Use the same definitions for catalogue export, the root
`--print-user-schema` result, and server parameter validation. Root JSON Schema
must describe each known provider's closed parameter object, not just permitted
provider keys. Inline controlled provider-local definitions into self-contained
schemas so embedding one provider cannot collide with another provider's names.

### Bounded editor schema vocabulary

Support a closed flat object of string, boolean, finite number/integer, string
enum, or bounded string-array fields. Support required/default, nullable optional
fields, string length/pattern, numeric bounds, and array item/count constraints.
Normalize only controlled local references to these shapes; reject cycles,
external references, unsupported unions/nesting, and executable annotations.
Plugin cross-field validation remains authoritative on the server.

The decoder must distinguish missing/unknown metadata from an explicit global
country set. Unknown version or unsupported field schema cannot authorize
activation or silently drop saved values. Retain the source for correction,
show an identified metadata error, and permit explicit disable/remove actions;
do not render an arbitrary plugin as a generic editable dictionary.

Use fixed, shared export/decoder budgets for metadata version 1:

| Metadata budget | Maximum |
| --- | --- |
| Complete provider catalogue JSON, encoded as UTF-8 | 1 MiB |
| Registered provider entries in the editor catalogue | 64 |
| One parameter schema, encoded as UTF-8 | 64 KiB |
| Parameter properties per provider | 64 |
| Local schema definitions per provider | 128 |
| Schema structural nesting depth | 8 |
| Local-reference hops during normalization | 16; reject cycles |
| String-enum choices per field | 1024 |
| Field/provider display title and enum-label length | 256 characters |
| Help/description length | 2048 characters |
| Pattern text length | 256 characters |

These are catalogue interpretation limits, not a new source-format migration or
a replacement for plugin-owned parameter constraints. Exceeding a budget produces
an identified metadata error; preserve the source and do not truncate values or
silently grant eligibility. Backend export and frontend decoding use equivalent
constants with conformance tests at each boundary and one over the limit. Treat
patterns as bounded validation data; reject unsupported patterns and do not
evaluate arbitrary executable expressions.

## Validation error extension

Preserve HTTP 422 `invalid_configuration` and its existing `message`. Add a
bounded optional `field_errors` array:

```json
{
  "error": "invalid_configuration",
  "message": "Provider configuration is invalid",
  "field_errors": [
    {
      "path": ["user_config", "providers", "ImgwWarningsApiComponent", "parameters", "teryt_codes"],
      "code": "required_when_enabled",
      "message": "Podaj kody powiatów dla wybranego źródła ostrzeżeń."
    }
  ]
}
```

Paths contain string keys or integer indexes. Codes classify missing fields,
unknown fields, invalid values, incompatible country, or alias conflict. Messages
are plain text and bounded; do not expose secrets or raw provider payloads.
Limit the optional array to 32 errors, each path to 16 segments, each string
segment to 128 characters, and each field message to 512 characters. Omitted
additional details remain represented by the existing general error summary;
truncation must never turn invalid configuration into a successful response.
Retain source paths for legacy errors and associate them with the displayed
provider field. Structured errors come from validation records, not parsed
exception strings. Clients still support servers returning only `error/message`.

Keep HTTP 409 `revision_conflict`, restart errors `invalid_saved_configuration`
and `restart_unavailable`, and existing successful envelopes unchanged. Invalid
save/import retains the browser draft; revision conflict requires a fresh read
and deliberate reconciliation rather than silently overwriting.

## Operator draft and compatibility behavior

- Decode metadata in a typed frontend domain module; use a dedicated parameter
  editor with existing input primitives. Maintain one complete source draft
  across configuration subpages.
- Merely displaying a packaged default must not insert an explicit `enabled`.
  Offer inherited, explicit enabled, and explicit disabled intent without losing
  the distinction in serialization.
- Show applicable providers and any explicit saved/draft entries, including
  incompatible or unknown entries as errors. Country changes preserve values
  and require revalidation rather than hiding or replacing the selection.
- Disabling retains parameter values and permits missing activation-only fields;
  it does not turn malformed supplied values into a valid draft.
- On legacy-only IMGW input, project TERYT into the provider field for display
  without modifying source or marking the form dirty. An explicit value edit
  updates the existing alias when it is the sole source location. New entries
  write canonical parameters. For equal simultaneous forms, an explicit edit
  updates both in one draft operation. For conflicting simultaneous forms,
  show both values and require a deliberate reconcile action before save.
- Display inline field errors and the general error summary. Labels and keyboard
  focus work in desktop and narrow/mobile layouts. Provider metadata is text,
  never HTML or executable expressions.
- Preserve official-warning presentation by capability, including unconfigured,
  unavailable, healthy empty, and active cases. Add supported-hazard/coverage
  context without inferring official authority from a provider name.

Update the existing mock configuration to supply complete metadata and a
controlled non-Polish fixture. Update Polish configuration help/guide during
implementation, and maintain EN/PL/DE parity for new runtime provider/health and
coverage text. Existing technical identities and CSS implementation names need
no unrelated rename.

## Contract verification

Backend API tests verify metadata/schema agreement, invalid-save unchanged bytes,
legacy round-trip, structured 422 fallback, revision 409, import without save,
and restart separation. Frontend domain/component/browser tests verify bounded
decoding, inherited intent, country changes, unknown schema, alias edits, inline
errors, retained drafts, accessibility, and mock-only provider presentation.
