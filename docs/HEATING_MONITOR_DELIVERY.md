# Heating monitor delivery and verification

This delivery record separates implementation and installation evidence from
the normative [heating architecture](<features/Heating System Monitoring - Architecture.md>),
[SYS C-HVAC requirements](<sys/SafetyConcept - SYS.md#86-heating-system-monitoring-component-c-hvac>)
and [software requirements](<sys/SafetyComponent - SSRD.md#410-heating-system-monitoring>).
Requirement IDs and all R01..R13 mechanism/fault identities remain unchanged.

## Delivery scope

The initial deployment established generic input normalization and R01
input-source diagnostics. This stage extends the rule contract to R02 current
device faults, R03 missing heating requests, R04 missing boiler responses,
R05 flow rise, R06 target tracking and R13 maintenance indications. R07..R12 remain excluded and their activation is
rejected. The packaged `Diagnostic` profile continues to select only R01;
upgrading the application does not enable another rule or change installation
bindings.

The component reports partial coverage. A valid input, available entity or
cleared R01 diagnostic does not establish successful heating, independent room
need, boiler response, safe appliance temperature or SG-003 timing compliance.
Each additional rule needs its own policy and qualified inputs before admission.
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
`burner_starts_dhw`, `room_temperature`, `target_temperature` and
`inhibition_reason`.

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
admitted rule set is R01/R02/R03/R04/R05/R06/R13. Rule selection alone does not establish
an input, independence, operating-condition or timing contract.
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
`maintenance_status` maps to `clear` or `maintenance`. These are current
indications with a reviewed meaning, not interpretations inferred from entity
names. `inhibition_reason` maps to `none`, `startup` or `anti_cycle` when the
selected response policy declares `inhibition_context: mapped_reason`.
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

A current-status binding can be added under `inputs` without selecting a device
integration. This fictional example assumes that the entity supplies an original
`observed_at` timestamp and can meet the declared ten-second age; those facts
must be verified for the real source:

```yaml
device_status:
  entity_id: sensor.example_boiler_status
  value_map: {"normal": "clear", "alarm": "fault"}
  evidence_kind: measurement
  independence_group: boiler
  freshness: source_timestamp
  observed_at_attribute: observed_at
  max_age_seconds: 10
```

The binding alone does not activate R02. With the unchanged `Diagnostic`
profile, a correctly mapped `fault` value is available data; R01 is not an
assessment of that device condition. A selected reviewed `device_fault` policy
supplies the separate failure/recovery contract.

### Rule policies and required evidence

System-owned profile fields `device_fault`, `missing_demand`, `no_response` and
`maintenance` hold the optional rule policies. Every profile includes R01
exactly once. A selected rule requires its matching policy; a policy for an
unselected rule is rejected. Every such policy has `evidence_reference`, `failure_seconds`
and `recovery_seconds`. The reference identifies reviewed source meanings and
calibration evidence; it does not identify an integration to load. Code/status
references also identify the applicability and version of the configured
current-status mapping. An arbitrary nonempty reference is not evidence that
the source or installation passed commissioning.

| Rule / policy field | Required normalized inputs | Failure and positive recovery |
| --- | --- | --- |
| R02 / `device_fault` | `device_status` as fresh measurement evidence | Explicit current `fault`; recovery requires fresh explicit `clear`. Unknown, unmapped and historical indications are not a passing result. |
| R03 / `missing_demand` | Room `room_temperature`, effective `target_temperature`, independently evidenced `heating_permitted`, and the associated installation/circuit `heat_request` | Independently evaluated permitted need without a request beyond its allowance. Recovery requires a valid request for persisting need or positively attained room target; removal of permission/request alone is not HEAL. |
| R04 / `no_response` | `heat_request`, `boiler_active`, `dhw_active`, `flow_temperature`, `requested_flow_temperature`; `inhibition_reason` when declared | Unsatisfied request without eligible CH response after bounded startup/inhibition. Recovery requires qualified CH response or an attained target during an eligible issued request. A generic burner indication during DHW is not CH response. |
| R13 / `maintenance` | `maintenance_status` as fresh measurement evidence | Explicit current `maintenance`; recovery requires fresh explicit `clear`. This is L4 maintenance information, separate from loss of heating. |

All selected safety-rule inputs use `freshness: source_timestamp` with their
appropriate `evidence_kind`: physical temperatures, current device statuses and
boiler/DHW operation are `measurement`; requests, current targets and permission
are `intent`. Availability/publication/contact alone cannot qualify them.
Every required source must meet its declared age and the rule's coherence
limit. R03 room-temperature/target/permission evidence must be independent of
the controller request being checked, with distinct `independence_group` declarations and the
reviewed `independent_need_reference`; the declarations do not themselves prove
physical independence.

| Additional policy field | Contract |
| --- | --- |
| `missing_demand.need_on_margin_k` | Positive target-minus-room margin that activates need; greater than the release margin |
| `missing_demand.need_off_margin_k` | Nonnegative narrower release margin used to qualify positive target attainment |
| `missing_demand.request_allowance_seconds` | Maximum eligible need-without-request allowance within the total unresolved-need allocation |
| `missing_demand.maximum_unresolved_seconds` | Total persistent need budget, at most 1800 seconds |
| `missing_demand.maximum_input_skew_seconds` | Maximum permitted difference between required source observation times |
| `missing_demand.independent_need_reference` | Reviewed evidence for independent target/permission semantics and their circuit association |
| `no_response.startup_allowance_seconds` | Bounded eligible startup allowance; not renewed by a target/phase change or restart |
| `no_response.maximum_inhibition_seconds` | Bound on a continuous permitted inhibition, subject also to the total need deadline |
| `no_response.maximum_unresolved_seconds` | Total persistent response/need budget, at most 1800 seconds |
| `no_response.target_recovery_margin_k` | Nonnegative tolerance for positively attained requested flow temperature during eligible recovery |
| `no_response.maximum_input_skew_seconds` | Maximum permitted difference between required source observation times |
| `no_response.inhibition_context` | Explicit `none` or `mapped_reason`; the latter requires a configured `inhibition_reason` input |

`inhibition_context: none` declares no additional permitted inhibition beyond
the policy's bounded startup and mandatory DHW handling. An unknown inhibition
does not grant an unlimited exception or prove recovery. The component derives
an inhibition expiry from its first continuous indication and the configured
bound; this contract does not require or claim a source-provided `until` value.
DHW priority, repeated reasons and phase changes remain inside the same durable
unresolved-need budget. They cannot each grant a new full allowance.

When required observations disappear, dependent checks become unevaluable and
retain any active symptom. The total need deadline continues; unavailable time
does not become successful operation or invented mechanical-failure samples.
A fresh active boiler response does not become a no-response fault merely
because another performance deadline elapsed. A lowered target after request
withdrawal is not positive recovery evidence.

### Flow-output policies and observed windows

Optional system-owned policies `flow_rise` (R05) and `flow_tracking` (R06)
consume the same fresh physical/intent inputs as R04. Eligible operation requires
an issued CH request, operating boiler, DHW inactive, a comparable stable target
and no mapped inhibition. Burner-off behavior is not an insufficient-output
measurement. A lowered target cannot clear the original condition.

Both policies explicitly declare `evidence_reference`, `failure_seconds`,
`recovery_seconds`, `startup_allowance_seconds`, `maximum_inhibition_seconds`,
`maximum_unresolved_seconds`, `maximum_input_skew_seconds`, `inhibition_context`,
`observation_window_seconds`, `minimum_sample_count`, `maximum_sample_gap_seconds`
and `target_stability_tolerance_k`. No operating threshold is supplied by default.

| Policy-specific field | Meaning |
| --- | --- |
| `flow_rise.minimum_target_deficit_k` | Positive deficit required to start a rise-failure window |
| `flow_rise.minimum_rise_k` | Positive minimum endpoint temperature rise over the covered window |
| `flow_rise.recovery_rise_k` | Adequate endpoint rise; strictly greater than the failing-rise boundary |
| `flow_rise.target_recovery_margin_k` | Nonnegative target-attainment tolerance, strictly below the activation deficit, in eligible CH operation |
| `flow_tracking.failure_deficit_k` | Positive deficit exceeded by every sample in a failing tracking window |
| `flow_tracking.recovery_deficit_k` | Nonnegative narrower deficit band for positive recovery |

Only distinct original flow timestamps add samples. Each window must meet the
full observed span and minimum count, with no source-time or runtime gap above
the configured limit. The bounded buffer retains the anchor needed to cover
the window. R05 compares its latest and anchor temperatures; R06 checks the
observed deficits throughout the covered window. Failure/recovery qualification
then accrues only between distinct eligible source observations. A cached value
cannot advance qualification merely because the evaluation timer ran again.

Missing data, clock discontinuities, target changes outside tolerance, phase
changes and restart discard measurement/qualification windows. Durable need
onset, consumed total budget, active conditions and aggregate incident identity
remain. Initial startup/sample collection is explicit; insufficient eligible
coverage at the reserved deadline becomes R01 quality loss, not fabricated
thermal failure. Inhibition beyond its commissioned allowance likewise loses
coverage. Timing admission allocates source age, sequential startup/inhibition,
window plus a maximum sample gap, the greater of output/R01 failure duration, evaluation and
decision/notification reserves inside the total budget of at most 1800 seconds.

R05/R06 share `HeatingInsufficientOutput` L3. Its UUID remains open while any
contributor is active or still lacks positive clear evidence. Restart reasserts
the last recorded contributor of such an unresolved aggregate without creating
a new incident. Only a complete positive group recovery retires the UUID.
An evaluation cycle commits its complete contributor state before publishing
SET/CLEAR transitions. Unavailable/pending contributors invalidate older results
before any clear is published; current SETs precede current CLEARs. A failed
durable clear commit preserves activation in both fault events and the public
installation sensor. Freeze-frame evidence retains a bounded window summary:
anchor/latest observation times and temperatures, sample counts, source/runtime
spans and gaps, target, measured rise and deficit range.

### Restart and compatibility

Elapsed budgets use monotonic runtime; R01..R04 qualification uses observed
runtime intervals, while R05/R06 qualification is bounded by both distinct
source-observation and runtime spans. State version 2
retains rule/room need onset, consumed/remaining budget, inhibition onset and
the existing active latches and shared incident UUIDs. Nonnegative, known UTC
downtime is reconciled into the remaining total budget after restart; it does
not count as valid failure/recovery observations. Clock discontinuities produce
quality loss without manufacturing a physical no-response condition or a fresh
full allowance.

Migration from version 1 is admitted only when its saved legacy configuration
projection matches unchanged R01 bindings and qualification policy. It preserves
R01 activation and incident identities. Version 1 did not record constituent
cause identities, so its aggregate pending failure duration is not reused to
qualify a potentially different source; current causes qualify from fresh
observations. Version 2 retains independent source failure durations. Adding inactive policy
defaults or admitting a new rule must not make unchanged R01 evidence disappear.
Removed or materially changed
active contracts require explicit reconciliation; incompatible state must not
be replaced by an empty healthy snapshot. Positive recovery remains subject to
durable-write success and every contributing symptom's clear evidence.

## Delivery sequence

1. Implement generic input normalization, immutable bounded evidence and explicit
   rule admission/coverage. Add fixtures with differently named device entities
   that produce equivalent normalized results. Retain existing room-temperature
   protection and the controller's ownership of heating commands.
2. Extend configuration model 2 with explicit selected heating installations,
   input mappings and room associations. Keep rule calibration under
   `calibration.heating_system_monitor`. Installation mappings do not own
   manufacturer limits, failure qualification or recovery policy.
3. Retain the read-only R01 foundation and admit R02/R03/R04/R05/R06/R13 only with their
   complete policy/input contracts. Keep R07..R12 rejected. Report
   missing independence, freshness, boiler response, thermal, code and delivery
   evidence explicitly. An empty fault list or healthy selected source must not
   be called full heating supervision. Enable no thermal rule without its
   reviewed equipment/thermal allocation.
4. Add bounded durable incident/deadline handling and shared fault publication
   with eight evaluation states, separate activation/shadowing and compatible
   notification attempts. Add EN/PL/DE operator labels and concise notifications.
5. Implement and admit the remaining safety paths in separately validated changes
   after input-rate/freshness, independent permission, equipment-code and thermal
   allocations have their own tests and installation evidence. No guessed
   universal thermal limit substitutes for reviewed
   `HSM-H05/<EquipmentProfileKey>` evidence. Merely adding a profile cannot
   activate the excluded R07..R12 rules in this delivery.
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

For stage-2 admission, each need/response allocation includes maximum source
age, its applicable startup/request/inhibition allowance, failure qualification,
two sequential reconciliation intervals, 1 second for decision and 30 seconds
for notification acceptance. The complete allocation must fit the selected
`maximum_unresolved_seconds` and the 1800-second heating-loss limit. Concurrent
source stages are bounded once by their maximum; overlapping allowances cannot
be counted twice or renewed through transitions. The same conservative
required-source-loss calculation must fit 60 seconds when C-HVAC owns that
source's allocated coverage path. Larger permissible measurement age does not
override a shorter safety deadline.

R03 allocates `request_allowance_seconds`. R04 conservatively allocates
`startup_allowance_seconds + maximum_inhibition_seconds`, because a DHW or
anti-cycle interval can follow startup. Repeated inhibition remains bounded by
the original total episode deadline; it does not grant another copy of either
allowance. A deadline decision still requires current valid failure evidence
and reserves its remaining decision/notification time. Actual CH response or
missing observations must not be converted into no-response failure merely
because a deadline expired.

These are admission bounds, not universal appliance calibration. This document
provides no active demand/response profile with guessed operating values;
installation evidence and deterministic boundary tests are required before a
profile is selected. R13's L4 status does not inherit a thermal protection
guarantee or enable heating control.

## Acceptance evidence

| Area | Required evidence before claiming the capability |
| --- | --- |
| Input normalization | Different device/entity fixtures produce equivalent normalized evidence; state and attribute selectors; boolean/enumerated mappings; units/conversions; missing/unmapped values; future/stale/replayed timestamps; publication versus observation |
| Rule coverage | Enabled-input validation; explicit diagnostic/shadow/excluded paths; common-cause limitation; no healthy full-coverage summary for a partial installation |
| Lifecycle | Positive recovery only; no clear from missing data, request withdrawal, target reduction, mode change or restart; bounded durable incident/deadline state; current FaultManager evaluation/activation semantics |
| Demand/response | Independent permitted need, separate activation/release bands, coherent targets, achieved target, actual CH response, bounded startup/DHW/anti-cycle, repeated inhibition, exact total-deadline boundaries |
| Migration and clocks | Version-1 R01 preservation, additive admission, changed active contract reconciliation, repeated restart, downtime without successful samples, rollback/forward clock changes and failed HEAL commit |
| Safety boundary | No boiler/climate/pump/reset calls; control intent rejected as physical response; historical errors diagnostic only; existing C-TEMP and shared dependency ownership retained |
| Runtime presentation | Friendly HA names where available; localized fallback labels and reason codes in EN/PL/DE; phase, evidence quality and diagnostic coverage shown independently |
| Deployment | Narrow backup/deploy, correct running revision, post-startup source/coverage readback and logs; no household actuator routine triggered for verification |

Implementation and deployment results belong in the PR and release report.
This record does not assert that any rule or live installation has passed these
gates. English is the source language for this technical document; runtime
operator labels and messages require EN/PL/DE parity.
