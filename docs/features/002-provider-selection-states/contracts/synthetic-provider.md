# Contract: German Synthetic Warning Provider

## Trusted declaration and parameters

Bundle GermanyDummyWarningsApiComponent in germany_dummy_warnings/. Declare:
capability OfficialWeatherWarnings; countries {DE}; hazards {wind};
data_kind synthetic; transport_kind none. Label it “Niemcy — źródło testowe” in the
Polish catalogue, with EN/PL/DE runtime text. It is not DWD or another real authority.

Required when selected and C-EXT enabled: region_code, a synthetic region identifier
of 1..32 ASCII letters/digits/underscore/hyphen, beginning with a letter or digit.
It represents test scope, not a validated official German administrative code.
scenario is one of empty, warning, unavailable, stale (default empty).
No endpoint, access token or credential field is present.

System policy supplies scheduling (initial poll and 60-second interval) and a
180-second stale limit. No HTTP client is constructed/injected for transport none.
A controllable clock makes tests deterministic. Constructors never poll or sleep.

## Scenarios

| Scenario | Normalized preview result |
| --- | --- |
| empty | Healthy complete empty wind-warning feed; synthetic count 0. |
| warning | One active wind observation scoped to the chosen synthetic region. |
| unavailable | Unavailable health and no usable new evidence; explicit test reason. |
| stale | Stale health with synthetic expired/aged evidence outside the stale budget. |

Scenario changes apply on the normal saved-and-restarted lifecycle. No extra
live scenario-control endpoint or household action is introduced. Polling and
shutdown use existing bounded scheduling. Preview warnings have explicit
synthetic provenance and authority_confirmed false.

## Dispatch and safety isolation

Runtime uses the trusted installed definition to route:
- live adapter -> external_api_result;
- synthetic adapter -> external_api_test_result.

Validate that result identity matches the scheduled adapter. Input payloads and
observation metadata cannot reclassify a source as live. Live event consumers
reject synthetic sources defensively; preview consumers reject live or unknown
sources. Shared validation checks authority against trusted data_kind as well as
capability, rather than labelling dummy observations authoritative.

SelfDiagnostics, real provider/capability D allocations and degradation bindings
receive selected live definitions only. Synthetic results never update real
C-EXT _health/_observations, real exposure evaluations, real advice inhibition,
real notification state or recovery proposals/commands. A separate presentation
handler publishes sensor.external_hazard_test_state and a clearly marked preview
card using the current runtime_id. It is initialized even with zero live sources,
and bounded to the selected synthetic source and 64 observation summaries.

Real monitoring remains unevaluable for synthetic-only coverage. Explicit test
selection cannot clear an existing persisted real fault; reconfiguration must not
erase safety state or runtime journals. An opening-confirmed-closed real clear is
independent and is not attributed to synthetic evidence.

## Required proof

Parameter validation, source compilation, full startup, polling, dispatch,
preview, scenario health and shutdown are exercised with the normal bundled
registration. A network spy fails on every attempted request. For all four
scenarios snapshot real H/D state, coverage, notification output and recovery
proposals before/after and assert no synthetic-induced differences or household
service calls. Inject a synthetic result on the live event and a spoofed provider
identity to prove rejection at both boundaries. Preserve tests for concurrent
live sources and suppression of late results after shutdown.
