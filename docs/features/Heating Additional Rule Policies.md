# Heating distribution, temperature and cycling policies

This reference defines the generic R07..R12 admission contract under the
[heating architecture](<Heating System Monitoring - Architecture.md>).
System-owned policies require reviewed source and installation evidence;
selecting a policy does not prove that the installation has been commissioned.
There are no universal operating thresholds. Inputs remain literal entity or
attribute mappings, independent of controller products.

## Common qualification and source evidence

Every policy declares `evidence_reference`, `failure_seconds` and
`recovery_seconds`. Required physical values are `measurement` evidence;
targets, permission and explicit inhibition context are `intent`. Required
observations have original timestamps, bounded age and coherence. Publication
time, a gateway heartbeat or command acknowledgement alone does not establish
a fresh physical measurement. Unavailable evidence never becomes false or zero.
The [input provenance guide](<Heating Input Provenance.md>) describes how to
verify upstream timestamps and physical meanings before policy admission.

Windowed distribution/room policies additionally declare
`startup_allowance_seconds`, `maximum_inhibition_seconds`,
`maximum_unresolved_seconds`, `maximum_input_skew_seconds`,
`inhibition_context` (`none` or `mapped_reason`),
`observation_window_seconds`, `minimum_sample_count` and
`maximum_sample_gap_seconds`. Their complete timing allocation includes source
age, startup/inhibition, covered window and gap, the greater of physical/R01
failure qualification, evaluation and decision/notification reserves within
the commissioned unresolved-need budget, at most 1800 seconds. Sample count,
source/runtime span and gaps must all qualify. Cached observations cannot
advance a window or failure/recovery duration. Startup or missing coverage
after an expired budget remains quality loss, not fabricated mechanical failure.

## R07 pump relationship

`pump_response` requires physical `boiler_active`, `dhw_active` and
`pump_active`. It declares `hydraulic_reference`,
`topology_requires_pump: true`, `startup_allowance_seconds`,
`maximum_unresolved_seconds` and `maximum_input_skew_seconds`.
An observed CH burner with its topology-required pump off fails after startup
and qualification. A valid CH burner/pump relationship must persist for
recovery. Burner shutdown or DHW transition alone is not HEAL. A phase change
can restart a physical startup interval but cannot renew unresolved need.

## R08 loaded flow/return behavior

`flow_return` requires CH burner/pump/DHW context, `flow_temperature`,
`return_temperature` and its declared `load_role` (`power_percent` or `power_w`).
It declares `hydraulic_reference`, `minimum_load`,
`minimum_flow_temperature_c`, `failure_delta_k`, `recovery_delta_k`,
`inverted_failure_k` and `inverted_recovery_k` in addition to the common window
fields. Recovery bands are strictly narrower than their failure boundaries.
The observed differential is flow minus return. Excess and inversion are
separate persistent predicates; disjoint causes cannot share failure duration.
Only a sufficiently loaded, operating CH/pump interval qualifies. Idle, low
load or missing data does not clear an active distribution condition.

## R09 room delivery

`room_delivery` requires plant CH/pump/DHW context and each room's
`room_temperature`, effective `target_temperature`, `heating_permitted` and
`heat_delivery_active`. The last signal represents an independently evidenced
physical attempt through that room's heat path; a controller decision or plant
burner alone cannot establish it. The policy declares `delivery_reference`,
`need_on_margin_k`, `need_off_margin_k`, `minimum_cooling_k`,
`recovery_rise_k`, `target_stability_tolerance_k` and
`room_inhibition_context` (`none` or `mapped`). Mapped context requires a room
`room_inhibited` intent input. Need-on is strictly wider than need-off.
Cooling beyond the calibrated threshold during a covered delivery attempt
fails. Adequate rise or sustained achievement of the original target qualifies
recovery. Thermal inertia and ventilation are part of commissioning. Target
reduction, permission withdrawal or inhibition cannot heal the original need.

## R10/R11 thermal response allocation

Both policies require an `allocation` with `allocation_key` in the form
`HSM-H05/<EquipmentProfileKey>`, `manufacturer_reference`,
`hydraulic_reference`, `maximum_response_seconds`,
`detection_budget_seconds`, `decision_budget_seconds` and
`notification_budget_seconds`. Declared portions fit the total response bound;
source age plus evaluation/failure qualification fits detection. Decision and
notification portions must cover the application/transport budgets. This is a
reviewed equipment bound; neither 120 seconds nor 1800 seconds is inherited as
an appliance limit.

`mode_temperature` declares `maximum_input_skew_seconds` and `envelopes` for
`idle`, `starting`, `heating`, `dhw` and `pump_overrun`. Each envelope has
`operating_maximum_c`, `native_hysteresis_k`, `measurement_tolerance_k` and
`recovery_margin_k`. The failure threshold is the operating maximum plus native
hysteresis and measurement tolerance; the clear boundary is strictly lower.
Fresh physical boiler/DHW/pump context and current request classify the phase.
Unknown phase does not authorize applying a CH envelope during DHW.

`absolute_temperature` requires fresh `flow_temperature` alone and declares
`absolute_limit_c`, `measurement_tolerance_k` and `recovery_margin_k`. Its
alarm boundary is the absolute limit minus measurement uncertainty, never a
relaxation above the reviewed manufacturer limit. Its
validity is independent of request, DHW and startup. Valid positive thermal
evidence remains actionable during persistence failure or unrelated diagnostic
loss; uncertain time/storage cannot prove HEAL. R01's aggregate restriction
does not disable this independent temperature predicate. Its own missing
temperature remains unevaluable. Active R10/R11 recovery retains the original
stricter clear reference across phase changes and restart. Limits fit the
normalizer's physical range, so range validation cannot mask the alarm.

## R12 cycling information

`cycling` is L4 and has external-only diagnostic scope. It requires qualified
`burner_starts_ch`, `burner_starts_dhw`, `boiler_active` and `dhw_active`.
The burner input observes operation across both modes. The policy declares
`counter_reference`, `maximum_input_skew_seconds`,
`observation_window_seconds` (at most 3600), `minimum_sample_count`,
`maximum_sample_gap_seconds`, `maximum_counter_gap_seconds`,
`maximum_starts_ch`, `maximum_starts_dhw`, `recovery_starts_ch`,
`recovery_starts_dhw`, `short_cycle_seconds`, `minimum_short_cycles`,
`recovery_short_cycles` and `minimum_recovery_cycles`.

CH/DHW counters and physical transitions retain separate original-time
coverage. Rates use their actual covered counter span, normalized to the
declared observation window. A short cycle is counted only when its upper
duration bound is below the threshold; a positively long recovery cycle needs
its lower duration bound at or above that threshold. Sampled transition times
are intervals, not exact switching instants. Missing/ambiguous transitions,
counter reset/wrap and restart rebuild baselines without inventing starts or
zero-start recovery. Affected CH/DHW causes survive restart. An idle-only
window cannot heal a previously active cycling condition; recovery requires
comparable observed cycles, explained counter increments and narrower limits.
An unclassified cycle cannot count as positively healthy. Incomplete history is shown
as unavailable cycling assessment, without manufacturing a heating hazard.

## Configuration and delivery

The private installation selects policies and maps their required inputs.
The packaged `Diagnostic` profile remains R01-only. Stable rule, symptom,
fault and MQTT identities remain those in the main architecture. No rule
commands a boiler, pump, valve, reset or household routine. English is the
technical source language; runtime reasons require EN/PL/DE parity and the
operator configuration guide remains Polish.
