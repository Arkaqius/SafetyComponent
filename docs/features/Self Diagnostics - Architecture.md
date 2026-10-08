# Self-diagnostics and independent supervision

## Purpose and ownership

Provider adapters own polling, schema validation, freshness, normalized results,
and raw provider-health telemetry. `SelfDiagnosticsComponent` converts each
installed adapter's current health to its own L3 diagnostic (`D`) fault. The
consumer's `ExternalHazardDataUnavailable` is separate: it describes loss of a
required household capability after redundancy policy, not the failure of one
adapter. A failed weather provider must not disable independent IMGW or outdoor
air-quality evidence. See [External Hazard Monitoring](External%20Hazard%20Monitoring%20-%20Architecture.md)
and [Fault Degradation and Coverage](Fault%20Degradation%20and%20Coverage%20-%20Architecture.md).

`SafetyAppHealth` is one L2 diagnostic fault with distinct contributors for
startup, MQTT publication, mobile delivery, local outputs, persistence,
evaluation, and recovery dispatch. A contributor is `SET` only on current
qualified failure; a successful attempt on the same path and operation clears
that contributor.
Historical error counters, user-declined recovery, and intentional local-output
inhibition are not failure evidence. Multiple stores or output vectors retain
independent contributions, so one successful path cannot clear another failed
path. A local-output contributor is installed only when a local output is
configured; an absent optional vector does not make coverage unknown. Existing
`sensor.safety_app_health`, delivery health, and per-provider
health entities retain detail and are not replaced by fault state.

## Routing and restrictions

| Contributor | Fault and priority | Restriction target | Clear evidence |
| --- | --- | --- | --- |
| Each installed provider adapter | Own `ExternalProviderUnavailable{Provider}`, D/L3 | Installed weather or AQ H symptoms using that provider's capability | Fresh `OK` adapter result |
| Core startup/process | `SafetyAppHealth`, D/L2 | Installed H evaluation; process outage also needs external observation | Core managers and fault routes initialized |
| MQTT publication | `SafetyAppHealth`, D/L2 | H publication/UI freshness, not independent detection | Observed publication and fresh heartbeat |
| Mobile delivery | `SafetyAppHealth`, D/L2 | L1-L3 notification path only | Accepted target submission or restored confirmed transport; not handset receipt |
| Local annunciator | `SafetyAppHealth`, D/L2 | Eligible L1-L2 local notification vector only | Successful attempted output command |
| Notification/recovery/detector state stores | `SafetyAppHealth`, D/L2, one contributor per store | L1-L3 notification durability, configured H recovery durability, or installed indoor-detector H durability, respectively | Successful retry of the failed load or save operation on the same store; a save cannot clear a failed restore |
| Periodic and detector-test attestation stores | `SafetyAppHealth`, D/L2, one contributor per store | Intentional external-only maintenance evidence; no invented H actuator restriction | Successful retry of the same load/save operation |
| Fault evidence store | `SafetyAppHealth`, D/L2, independent `fault_evidence_state` contributor | Diagnostic-evidence durability for installed H faults; valid detection and recovery continue | Successful retry of the failed load/save operation or successful capture after a capacity failure; success of one operation cannot clear another failed operation |
| H predicate invocation | `SafetyAppHealth`, D/L2 | Exact H symptom whose invocation throws | Successful invocation of the same predicate; missing input remains separately unevaluable |
| Recovery dispatcher | `SafetyAppHealth`, D/L2 | Exact H recovery binding | Successful invocation of that path after dispatcher readiness |

The level selects notification defaults; neither D category nor level grants an
actuator action. Degradation bindings resolve to installed H symptom identities
and carry `evaluation`, `recovery`, `notification`, `publication`, or `durability`
effect. Only evaluation and recovery effects block dependent actuator proposals.
The other effects remain visible in coverage without treating valid H detection
as failed. Recovery remains subject to a fresh H evaluation after an evaluation
restriction clears. An unavailable D observation does not clear an active fault.

## Health-signal allocation contract

| Signal class | Fault owner or explicit exemption |
| --- | --- |
| Entity Monitor Group A/B input checks | `EntityHealth{EntityKey}` for external-only Group A, or requesting component's D fault for Group B; Group C is passive inventory and creates no fault. |
| Temperature, door, external-opening, and recovery dependencies | `TemperatureMonitoringUnavailable`, `TemperatureRecoveryUnavailable`, `SafetyDoorMonitoringUnavailable`, `ExternalOpeningMonitoringUnavailable`, or `ExternalRecoveryUnavailable` with exact subject bindings. |
| Indoor detector trouble/unavailable and persisted alarm state | `InternalEnvironmentalDetectorUnavailable` for detector input; `SafetyAppHealth` detector-store contributor for durability. |
| External provider adapter health and consumer capability health | Per-provider `ExternalProviderUnavailable{Provider}`; `ExternalHazardDataUnavailable` only after consumer redundancy policy. |
| Notification delivery, local output commands, notification/recovery stores, SM invocation, and recovery dispatch | `SafetyAppHealth` contributors, retaining raw health entities and logs. |
| Functional Safety Monitor source faults, periodic tests, detector tests, and battery exclusions | Their individual D faults; operator attestations are evidence, not implicit positive checks. Their storage failures have separate App Health contributors. |
| Bounded freeze-frame capture and persistence | `SafetyAppHealth` fault-evidence-store contributor for capacity or durability loss; no additional H fault and no clearing of active H evidence. |
| MQTT heartbeat and process/startup absence | In-process `SafetyAppHealth` publication contribution when observable; HA-hosted independent observer for the outage itself. |
| Derivative Monitor numerical outputs and evaluation-progress timestamps | Measurement and progress evidence consumed by the owning H or component D mechanisms; no second fault for the helper. |
| SafetyHome request-local validation errors and diagnostic snapshot export | Request response or debug projection only; not a safety capability loss by themselves. |

## Independent observer boundary

An AppDaemon process cannot attest its own continued execution, startup before
its managers exist, or broker delivery while MQTT is unavailable. An observer
outside AppDaemon shall check the `sensor.safety_app_health` heartbeat and raw
state and raise a separately owned Home Assistant notification when the state
is missing, unhealthy, or stale. The optional
[Home Assistant automation example](../../backend/config/ha_supervisor_automation.example.yml)
uses a fixed notification ID, so repeated checks update one alert and recovery
dismisses it. It does not call a household actuator or infer a fault CLEAR from
a retained MQTT value. The example requires installation and validation in the
target Home Assistant configuration; merely storing it in this repository does
not activate supervision. It requires MQTT heartbeat publishing to remain
enabled, with MQTT sensor `expire_after` greater than the heartbeat interval.
HA's MQTT entity becomes unavailable when the configured expiry elapses; the
observer treats both absence and that unavailable state as unhealthy.

Home Assistant is independent of AppDaemon but shares the host and may share
the broker/network. This observer can report AppDaemon or broker loss while HA
still runs; it cannot report HA/host power loss, HA service failure, or handset
receipt. Those need a separate host and transport. During an AppDaemon/MQTT
outage the in-process D fault cannot be published, so the independent alert is
the authoritative outage indication. On return, current D evidence must be
reevaluated; a missed heartbeat is not retroactively converted into a false H
clear.
