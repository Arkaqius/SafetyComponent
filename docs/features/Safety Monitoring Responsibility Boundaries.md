# Safety Monitoring Responsibility Boundaries

**Document role:** Non-normative architecture note

Functional safety monitoring covers the complete path from a safety-relevant
input to a decision and notification. It asks whether SafetyFunctions, Home
Assistant, and their host can still provide that protection; it does not infer
that the home is safe when monitoring is lost. This refines the system-failure
hazard `HZ‑SYSTEM‑FAIL‑01` and safety goal `SG‑003` in the HARA. Not every part
of the path can be supervised by SafetyFunctions itself. Monitoring
responsibility remains with the layer that can still observe and report a
failure when the monitored layer is down.

## Diagnostic domains

The monitoring design should use separate domain monitors rather than one
central component that owns every diagnostic decision:

| Domain | Suggested owner | Diagnostic scope |
| --- | --- | --- |
| Home Assistant safety inputs | `EntityMonitorComponent` | Availability, freshness, type, finite values, plausible ranges, rate of change, and required or allowed states for inputs declared by the installation, Safety Components, or application core. |
| External data providers | Each external API adapter and its consuming Safety Component | HTTP and schema result, source and retrieval freshness, last attempt, last success, consecutive failures, and provider-independent cache health. |
| MQTT transport | A dedicated MQTT transport monitor, supported by broker and Home Assistant diagnostics | Connection and session state, observable publish failures, reconnects, queue pressure, message age, and an end-to-end or loopback heartbeat where the installation can provide one. |
| Home Assistant and AppDaemon runtime | A runtime-platform monitor plus Home Assistant Supervisor | Home Assistant connectivity, AppDaemon add-on state, application process restarts, event-loop delay, missed evaluation deadlines, and component lifecycle failures. |
| Host resources | Host/platform integrations or an external supervisor | Sustained CPU load, memory and swap pressure, disk space, host temperature and throttling, clock synchronization, and restart counters. |
| Device maintenance | A dedicated maintenance policy using Home Assistant battery entities | Battery level, source quality, and device identity. A low battery is informational while the device remains usable; loss of a safety input remains owned by its safety component or Entity Monitor. |
| SafetyFunctions self-diagnostics | An application self-monitor | Configuration validation, component initialization, scheduler progress, exception counters, persistence health, queue or worker liveness, and completion of safety-evaluation cycles. |
| Platform and add-on updates | Home Assistant Supervisor, with an optional SafetyFunctions consumer | Update availability, installed and offered versions, advisory severity, information freshness, and excessive update age. Installation and restart remain outside monitoring logic. |
| Notification path | `NotificationManager` and channel-specific diagnostics | Home Assistant service acceptance, per-target attempts, retries, and observable channel errors without presenting acceptance as confirmed delivery to a physical phone. |

These monitors may use a common diagnostic state model and evidence format, but
each channel retains its own lifecycle, calibration, and fault ownership. A
Safety Component declares which channels it depends on and decides how lost
coverage affects its safety function; it does not take ownership of the
underlying broker, host, provider, or Supervisor lifecycle.

## Functional safety model

Monitoring distinguishes three independent concepts:

1. **Observed hazard/fault:** an asserted household condition or a diagnosed
   failure with a configured notification level. `sensor.safetysystem_state`
   currently reports the highest active fault level; `no_faults` does not mean
   every safety function was evaluated successfully.
2. **Coverage:** whether each safety function had fresh, trustworthy inputs and
   completed evaluation within its budget. `unknown`, stale, malformed, and
   unavailable evidence is not a passing observation. Coverage loss can coexist
   with an asserted hazard and must not clear it.
3. **Diagnostic channel health:** whether Home Assistant, AppDaemon, MQTT, the
   notification route, and the host can carry observations and reports. A
   healthy source entity does not prove that its consumer completed a decision
   or that a message reached a physical phone.

The functional safety view should show health by domain and an overall
coverage summary, but must retain the underlying cause, source, age, last
successful evaluation, and reporting path. Aggregation cannot turn an unknown
domain into healthy. A fault level is a policy decision, not a synonym for a
health-state label.

### Relationship to Entity Monitor

`EntityMonitorComponent` remains the authority for availability, freshness,
type, and value checks of declared Home Assistant input entities. It already
provides Group A/B diagnostics and owns its existing level-3 per-entity faults.
The platform monitor must not repurpose those generic faults to express a
different severity. It should consume the entity-quality result as evidence and
own the host, runtime, network, update, and battery policy separately. A host
metric or update entity is an installation binding only when Home Assistant
cannot identify a unique suitable source; calibration, timing, and severities
belong to system configuration.

### Severity boundaries

| Condition | Safety meaning | Allocation |
| --- | --- | --- |
| Sustained insufficient memory available to Home Assistant | The host may fail to evaluate or report safety conditions | Level 2 platform-health fault, after calibrated qualification and recovery hysteresis. A high usage percentage alone is insufficient evidence of imminent exhaustion. |
| Low battery with a still-functioning device | Maintenance is needed; safety coverage has not yet been shown lost | Level 4 informational condition. Do not convert it into a level-3 Entity Monitor failure. |
| Unavailable or stale safety-device input | The dependent safety function may have lost coverage | Existing owning component or Entity Monitor fault and severity; a battery warning neither replaces nor clears it. |
| Sustained CPU, disk, swap, or thermal pressure | Possible precursor to missed deadlines | Diagnose the resource and correlate with evaluation lateness; isolated peaks are not faults. Severity and qualification are system policy. |
| Internet/WAN loss | Cloud-dependent providers and mobile delivery may be impaired while local protection remains possible | Level 3 network fault; report the network state separately from local Home Assistant health and apply Local-Only mode/notification policy. A single failed public probe does not prove all Internet connectivity is lost. |
| Update available for Home Assistant or the SafetyComponent App | Maintenance information, not evidence that the running version is malfunctioning | Level 4 informational condition per product; track installed/offered versions and age, and never install or restart automatically from this monitor. |

For memory, the level-2 rule uses **both** available memory and memory
pressure/PSI; total-used percentage alone is not a substitute. Its exact
thresholds, duration, sampling interval, and positive recovery margin must be
validated as a set against the host's actual memory size and normal workload.
If the host or Home Assistant cannot expose either required measurement, this
rule is uncovered rather than silently falling back to a one-signal alarm.
Missing or invalid telemetry means unknown coverage, not a healthy host or an
automatic level-2 memory fault. Home Assistant's System monitor integration
exposes memory, CPU, disk, and PSI metrics where supported, but its diagnostic
sensors are disabled by default; installation setup must enable and identify
the required entities. See the [System monitor integration](https://www.home-assistant.io/integrations/systemmonitor/).

For batteries, use a bounded inventory of device-associated `sensor` entities
with the battery device class and `%` units, plus `binary_sensor` entities with
the battery device class, where `on` means low. Do not scan every entity whose
name contains "battery". Retain device identity, source timestamp, quality, and
an exclusion mechanism for mains-powered or incorrectly reported entities.
If both forms belong to one device, merge them into one maintenance condition
while preserving both observations. An unavailable battery entity cannot prove
that a battery is low or full. A low battery that later causes loss of a safety
input is then reported through the separate coverage fault owned by that
input's component. See Home Assistant's [sensor](https://developers.home-assistant.io/docs/core/entity/sensor/)
and [binary sensor](https://developers.home-assistant.io/docs/core/entity/binary-sensor/)
device-class contracts.

For updates, consume Home Assistant `update` entities for Core, Operating
System, Supervisor, and the SafetyComponent App when exposed. Their state and
installed/latest-version attributes are product-specific evidence; absence of
an update entity or stale update information is unknown, not "up to date".
Version discovery must not call the update-install action. See the
[Home Assistant update entity](https://developers.home-assistant.io/blog/2022/03/20/update-entity/).

## Source and ownership boundaries

The runtime shall rely on Home Assistant's existing integrations and Supervisor
for platform telemetry rather than infer host memory or update state from the
AppDaemon container. Safety Home may suggest candidate entities using their
integration, device class, unit, and device identity; the installation confirms
the exact binding when a unique trustworthy source cannot be established.
SafetyFunctions validates state, units, timestamps, freshness, and source scope
before using them. The user configuration contains bindings, exclusions, and
optional selection; system configuration owns thresholds, debounce, fault
levels, and default diagnostic policy. An unavailable runtime source leaves its
domain uncovered without disabling unrelated safety mechanisms.

Supervisor can observe the App or Home Assistant when one process fails; an
external watchdog is required to detect complete host or Supervisor loss and
to notify outside the failed Home Assistant/MQTT path. SafetyFunctions can
publish a heartbeat while alive, but a missing heartbeat must be judged by a
separate observer. Neither an AppDaemon timer nor a frontend view is an
independent watchdog for the process that hosts it. A successful TCP check of
the Ingress frontend alone does not prove that SafetyFunctions is evaluating.

Every domain has one fault owner. Entity Monitor retains entity-quality faults;
the owning Safety Component retains loss-of-input and hazard semantics; the
platform monitor owns qualified resource, runtime, network, update, and
maintenance conditions. Other domains may cite a shared underlying failure in
their evidence without producing duplicate user alerts. Reporting failure
must not block safety evaluation or turn an active fault into a clear state.

## Verification scenarios

- Healthy telemetry, an unknown source, a stale source, wrong units, and an
  absent required source produce distinct results; none of the last four is a
  positive healthy observation.
- A transient memory dip remains diagnostic, sustained calibrated memory
  exhaustion asserts level 2, and clearing requires fresh recovery evidence.
- Low battery remains level 4 while the device works; a subsequent unavailable
  safety sensor retains both the maintenance and coverage context without a
  duplicate root-cause notification.
- A local network outage, WAN outage, cloud-provider outage, and complete Home
  Assistant loss are distinguishable to the extent their observers remain
  available. Local-Only policy does not silently disable local safety checks.
- Available and stale update data, version changes, and missing product update
entities are distinguishable. No test of observation invokes installation.
- A deliberately stalled AppDaemon evaluation is detected by an independent
  observer; self-published MQTT availability is not accepted as sole evidence
  of continued evaluation or physical-phone delivery.

## Execution and recovery allocation

| Layer | Primary responsibility |
| --- | --- |
| SafetyFunctions | Validate safety-relevant Home Assistant inputs; evaluate component and external-provider health; expose application self-diagnostics while the application is running; convert loss of required coverage into the appropriate diagnostic fault. |
| Home Assistant Supervisor and platform integrations | Manage the Home Assistant and add-on lifecycle, restart AppDaemon according to installation policy, expose host and add-on health, and report platform or add-on updates. SafetyFunctions may consume these results but should not duplicate Supervisor lifecycle ownership. |
| MQTT broker and Home Assistant MQTT integration | Operate the transport and broker service. SafetyFunctions publishes availability and heartbeat information and records observable publish failures, but broker availability alone does not prove end-to-end delivery. |
| Independent supervisor or watchdog | Detect complete loss of Home Assistant, AppDaemon, MQTT, or the host; perform an installation-approved restart or failover response; and provide an out-of-band indication when the normal Home Assistant/MQTT reporting path is unavailable. |

Host CPU load, memory pressure, disk space, temperature, clock synchronization,
and restart counters are supporting diagnostic evidence. Missed evaluation
deadlines, event-loop delay, lost heartbeats, and unavailable safety inputs are
more direct evidence that a safety function has lost coverage. Resource alarms
therefore need persistence and hysteresis rather than reacting to isolated
peaks.

## Common diagnostic rules

- Keep the actual hazard state separate from the health of the channel that
  reports it. Missing or stale data is not evidence that a hazard is clear.
- Assign one fault owner to one underlying failure. Other components may expose
  supporting diagnostics without creating duplicate faults.
- Preserve provider independence: one failed external API must not overwrite or
  suppress healthy data from another provider.
- Do not rely on an application to report its own total failure through the same
  MQTT or Home Assistant path that has failed.
- Keep monitoring separate from recovery execution. Restarts, failover, or
  other corrective actions belong to an explicitly approved Supervisor or
  installation policy.

The adopted safety contract is in
[SYS §8.8](<../sys/SafetyConcept - SYS.md#88-functional-safety-and-platform-health-monitoring-c-fsm>)
and [SSRD §4.12](<../sys/SafetyComponent - SSRD.md#412-functional-safety-and-platform-health-monitoring>).
Configuration, code, tests, and independent-watchdog evidence remain necessary
to establish which parts operate in an installation.
