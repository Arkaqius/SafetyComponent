# Heating monitor delivery and verification

This delivery record separates implementation and installation evidence from
the normative [heating architecture](<features/Heating System Monitoring - Architecture.md>),
[SYS C-HVAC requirements](<sys/SafetyConcept - SYS.md#86-heating-system-monitoring-component-c-hvac>)
and [software requirements](<sys/SafetyComponent - SSRD.md#410-heating-system-monitoring>).
Requirement IDs and all R01..R13 mechanism/fault identities remain unchanged.

## Initial delivery scope

This delivery provides generic input normalization and R01 input-source
diagnostics. The packaged `Diagnostic` profile selects R01; configuration
rejects enabling R02..R13. Those rules remain normative requirements and are
displayed as excluded capabilities, with no dormant thermal/device-fault
algorithms enabled by calibration alone.

The component reports partial coverage. A valid input, available entity or
cleared R01 diagnostic does not establish successful heating, independent room
need, boiler response, safe appliance temperature or SG-003 timing compliance.
The deployment retains the existing independent C-TEMP protection and performs
no heating actuator calls.

## Generic input contract

The safety engine consumes normalized inputs directly mapped from Home Assistant
device entities and attributes. It does not recognize controller products,
versions, prefixes or selectable provider integrations. The same rule receives
the same semantic value regardless of the underlying device or entity name.

Installation configuration selects sources under `installation.heating_systems`.
Each stable installation key contains `friendly_name`, `profile` (default
`Diagnostic`), `inputs` and optional `rooms`. Each room has `friendly_name` and
`inputs`; room inputs select `room_temperature`, `target_temperature` and
`heating_permitted`. Installation keys and room keys are alphanumeric, begin
with a letter and must not collide ignoring case.

Installation input roles are `source_health`, `boiler_active`, `boiler_state`,
`dhw_active`, `pump_active`, `power_percent`, `power_w`, `flow_temperature`,
`return_temperature`, `requested_flow_temperature`, `heat_request`,
`heating_permitted`, `device_status`, `maintenance_status`, `burner_starts_ch`,
`burner_starts_dhw`, `room_temperature` and `target_temperature`.

| Binding field | Meaning |
| --- | --- |
| `entity_id` | Source HA entity; no required naming pattern |
| `attribute` | Optional literal attribute name; omitted means entity state; nested/executable selectors are rejected |
| `value_map` | Explicit raw-state to normalized boolean/enumerated value mapping |
| `unit` | Source unit: `°C`, `°F`, `K`, `%`, `W`, `kW` or `count`; temperature normalization produces °C and `power_w` converts kW to W |
| `scale`, `offset` | Finite numeric conversion applied after temperature unit normalization; scale cannot be zero; not a policy threshold or executable expression |
| `observed_at_attribute`, `observed_at_entity_id` | Original observation timestamp attribute or separate entity state; both select an attribute of that separate entity when combined |
| `max_age_seconds` | Maximum original observation age for `source_timestamp`; it cannot establish measurement age for `availability_only` |
| `freshness` | `source_timestamp` for evidenced measurement freshness, or `availability_only` for source contact without measurement-freshness proof |
| `evidence_kind` | Required source role: `measurement`, `intent` or `contact` |
| `independence_group` | Required common-source identifier; equal groups cannot demonstrate independent need versus controller request |
| `shared_temperature` | Reuse an existing C-TEMP dependency without creating a separate heating-owned source dependency |

The configuration model and compiler resolve these bindings into the component's
`systems` registry. System-owned settings select evaluation cadence, bounded
installation count, persistence location and named calibration profiles. The
supported rule selection is R01 diagnostics, not a thermal safety allocation.
Mappings contain data only, with no expressions or service calls. Unmapped states,
missing attributes, non-finite conversions and unavailable sources produce
unknown/unevaluable evidence, never an implicit false, zero or healthy result.

Source role retains its physical meaning. Room-control settings and confirmed
commands do not establish boiler flow targets, burner/pump activity or delivered
heat. Publication/contact timestamps do not become measurement timestamps.
Controller-derived targets/permissions retain a common-cause limitation;
independent need-to-request coverage requires independently evidenced permission
and need. Historical `last_error` is diagnostic only, never current fault proof.
There is no `last_error` runtime role in this input schema.

Boolean roles require actual booleans after mapping. `boiler_state` maps to
`idle`, `starting`, `heating`, `dhw`, `pump_overrun`, `inhibited` or `unknown`.
`device_status` normalizes raw status to `clear` or `fault`, while
`maintenance_status` maps to `clear` or `maintenance` for diagnostics; their
device/maintenance rules remain excluded.
Timestamp evidence accepts epoch seconds (including numeric entity-state text)
between 1970 and year 9999, or timezone-aware ISO timestamps;
naive, future, stale, regressing and changed-value/same-timestamp evidence is
rejected. Numeric timestamps belong in the selector's source value, rather
than being inferred from HA `last_updated`.

A minimal installation mapping can select inputs without a controller-specific
integration contract:

```yaml
installation:
  heating_systems:
    Main:
      friendly_name: Heating system
      profile: Diagnostic
      inputs:
        boiler_active:
          entity_id: binary_sensor.example_boiler_active
          value_map: {"on": true, "off": false}
          evidence_kind: measurement
          independence_group: boiler
        flow_temperature:
          entity_id: sensor.example_boiler_telemetry
          attribute: flow_temperature
          unit: °C
          evidence_kind: measurement
          independence_group: boiler
```

These bindings default to `availability_only`. A false `boiler_active` means
the boiler is inactive, not that its input is unavailable; R01 monitors input
quality rather than whether heating is currently requested or produced.

## Delivery sequence

1. Implement generic input normalization, immutable bounded evidence and explicit
   rule admission/coverage. Add fixtures with differently named device entities
   that produce equivalent normalized results. Retain existing room-temperature
   protection and the controller's ownership of heating commands.
2. Extend configuration model 2 with explicit selected heating installations,
   input mappings and room associations. Keep rule calibration under
   `calibration.heating_system_monitor`. Installation mappings do not own
   manufacturer limits, failure qualification or recovery policy.
3. Deliver the read-only R01 foundation with explicit R02..R13 exclusions. Report
   missing independence, freshness, boiler response, thermal, code and delivery
   evidence explicitly. An empty fault list or healthy selected source must not
   be called full heating supervision. Enable no thermal rule without its
   reviewed equipment/thermal allocation.
4. Add bounded durable incident/deadline handling and shared fault publication
   with eight evaluation states, separate activation/shadowing and compatible
   notification attempts. Add EN/PL/DE operator labels and concise notifications.
5. Implement and admit further safety paths in separately validated changes
   after input-rate/freshness, independent permission, equipment-code and thermal
   allocations have their own tests and installation evidence. No guessed
   universal thermal limit substitutes for reviewed
   `HSM-H05/<EquipmentProfileKey>` evidence. Merely adding a profile cannot
   activate those excluded rules in this delivery.
6. Validate, publish the focused branch/PR and deploy the validated capability.
   Check live version, source ages, coverage, startup qualification, faults and
   logs separately; record the deployed commit and remaining exclusions.

## Timing and admission gates

A source that offers only availability cannot establish measurement freshness,
even if its entity changes periodically. Each selected safety path needs its
own demonstrated source cadence, observation semantics and complete timing
allocation. Inputs/rules lacking that evidence remain explicitly outside the
claimed safety coverage; they may support separately identified diagnostics.

For example, a 40 s source timeout plus 5 s failure qualification, 5 s evaluation
latency, 1 s decision and 30 s notification reserve gives an 81 s worst-case loss
path. It cannot claim SG-003's 60 s budget. Changing a label or allowing a larger
timeout does not meet that requirement. Likewise, availability does not establish
IR-008's 0.2 Hz boiler measurement sampling or its maximum source age.

## Acceptance evidence

| Area | Required evidence before claiming the capability |
| --- | --- |
| Input normalization | Different device/entity fixtures produce equivalent normalized evidence; state and attribute selectors; boolean/enumerated mappings; units/conversions; missing/unmapped values; future/stale/replayed timestamps; publication versus observation |
| Rule coverage | Enabled-input validation; explicit diagnostic/shadow/excluded paths; common-cause limitation; no healthy full-coverage summary for a partial installation |
| Lifecycle | Positive recovery only; no clear from missing data, mode change or restart; bounded durable incident/deadline state; current FaultManager evaluation/activation semantics |
| Safety boundary | No boiler/climate/pump/reset calls; control intent rejected as physical response; historical errors diagnostic only; existing C-TEMP and shared dependency ownership retained |
| Runtime presentation | Friendly HA names where available; localized fallback labels and reason codes in EN/PL/DE; phase, evidence quality and diagnostic coverage shown independently |
| Deployment | Narrow backup/deploy, correct running revision, post-startup source/coverage readback and logs; no household actuator routine triggered for verification |

Implementation and deployment results belong in the PR and release report.
This record does not assert that any rule or live installation has passed these
gates. English is the source language for this technical document; runtime
operator labels and messages require EN/PL/DE parity.
