# Safety Monitoring Responsibility Boundaries

**Document role:** Non-normative architecture note

Functional safety monitoring covers the observable path from a safety-relevant
input through each component's completed decision to notification and, where
applicable, confirmed recovery effect. It does not infer that the home is safe
when monitoring is lost. Complete loss of the host or Home Assistant cannot be
diagnosed by the failed application itself. This refines the system-failure
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
| Host resources while the application runs | Home Assistant host/platform integrations | Sustained CPU load, memory and swap pressure, disk space, host temperature and throttling, and restart counters. This does not detect total host or power loss. |
| Device maintenance | A dedicated maintenance policy using Home Assistant battery entities and detector test records | Remote-device battery level, source quality, and device identity; due dates and results of smoke, gas, and CO detector tests. A low battery is informational while the device remains usable; loss of a safety input remains owned by its safety component or Entity Monitor. |
| SafetyFunctions self-diagnostics | Each Safety Component plus an aggregate application view | Configuration validity, component initialization, last completed evaluation, expected deadline, result, and missed deadline count per enabled component. Event-driven components also declare their input-health supervision contract; an idle period is not itself a missed evaluation. The aggregate cannot mark all components healthy from one heartbeat. |
| Platform and add-on updates | Home Assistant Supervisor, with an optional SafetyFunctions consumer | Update availability, installed and offered versions, advisory severity, information freshness, and excessive update age. Installation and restart remain outside monitoring logic. |
| Notification and recovery paths | `NotificationManager` and `RecoveryManager`, aggregated by C-FSM | Home Assistant service acceptance, per-target attempts, retries, queue health, observable channel errors, actuator command, and owning component's postcondition evidence. Acceptance is neither physical-phone delivery nor achieved actuator effect. |
| Backup maintenance | C-FSM using Home Assistant Backup evidence | Age of the last successful backup and an optional current failure source; a successful backup does not prove that it can be restored. |
| Periodic operational tests | An authenticated operator with durable maintenance records | Explicit outcomes of notification-receipt tests and optional backup-restore tests on a separate installation; recording an outcome executes neither a test nor a restore. |

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

The functional safety view should show one row per enabled component and an
overall coverage summary, retaining the underlying cause, source, age, last
completed evaluation, deadline, and reporting path. A component with no
completed cycle is not healthy. Aggregation cannot turn an unknown domain into
healthy. A fault level is a policy decision, not a synonym for a health-state
label.

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
| Sustained low free disk space or high host temperature | Maintenance precursor, not proof of a missed safety decision | Level 4 after independent qualification; fresh recovery samples and separate recovery margins are required. |
| Backup too old, confirmed backup failure, or due/failed periodic operational test | Maintenance evidence is insufficient or requires attention | Level 4; backup creation, restore, notification receipt, and safety-function coverage remain distinct. |

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

For remote-device batteries, use a bounded inventory of device-associated `sensor` entities
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

Battery discovery reads the Home Assistant entity and device registries together
with current states. Only enabled, device-associated entities matching these
device-class and unit contracts are candidates. Candidates are grouped by the
Home Assistant device registry ID, not by display name or entity-name patterns.
Automatic monitoring is enabled by default; installation-owned device exclusions
remove a whole discovered device, including matching manual bindings, from monitoring. Existing explicit
`remote_batteries` bindings remain supported and take precedence for their
entities so automatic discovery does not create a second maintenance condition.

Safety Home fetches the inventory through authenticated `GET /api/batteries`
and displays device names, readings, source quality, and a monitoring switch.
Changing a switch edits the configuration draft only. Saving and restarting the
App applies the exclusion. The running backend discovers its inventory at
startup; refreshing the editor does not dynamically add devices to that running
inventory. Newly discovered devices enter monitoring after an App restart.
Discovery failure is unknown diagnostic coverage, not a healthy empty inventory.

For updates, consume Home Assistant `update` entities for Core, Operating
System, Supervisor, and the SafetyComponent App when exposed. Their state and
installed/latest-version attributes are product-specific evidence; absence of
an update entity or stale update information is unknown, not "up to date".
Version discovery must not call the update-install action. See the
[Home Assistant update entity](https://developers.home-assistant.io/blog/2022/03/20/update-entity/).

Smoke, flammable-gas, and carbon-monoxide detector test schedules are
maintenance evidence, not hazard-clear evidence. A valid test may come from a
device-reported test result or an explicit operator attestation containing the
detector identity, outcome, and time. A quiet detector, acknowledgement of a
reminder, or a frontend button press without a recorded outcome cannot count as
a passed test. An overdue or failed test must not silence a live alarm.

### Host storage, temperature, and backup maintenance

Free-disk-space and host-temperature bindings measure the Home Assistant host,
not an unrelated container. Disk values must use compatible storage units and
temperature values must use compatible temperature units. Numeric plausibility,
freshness, sustained qualification, and separate recovery margins apply before
changing the L4 maintenance fault. Missing, stale, or wrong-unit input is unknown
coverage and cannot positively clear an active condition.

Backup monitoring reads the timestamp of the last successful Home Assistant
backup and, optionally, a binary problem entity reporting a current backup
failure. An old, valid success timestamp is overdue evidence, not malformed data.
A future, invalid, unavailable, or transport-failed timestamp is unknown rather
than evidence of a current backup. A configured failure source must provide
fresh valid evidence; stale or unavailable failure input cannot prove success.
The monitor never creates, deletes, downloads, or restores backups.

### Periodic notification and restore tests

Notification delivery tests require the operator to verify actual receipt at
the intended destination. Home Assistant service acceptance, a queue entry, or
a normal channel-health state cannot substitute for this confirmation. The
editor enables notification tests by default; backup-restore tests are optional
and disabled by default. Test intervals remain system policy.

The health page records an explicit passed or failed operator attestation for
`notification_delivery` or `backup_restore`. An untested enabled item is due;
a recorded pass is current until its due date, then overdue; a recorded failure
remains failed until superseded by a valid result. Unreadable durable history is
unknown, not a new pass. Due, overdue, and failed items are L4 maintenance
conditions. Recording a result does not send a message, activate a siren,
operate household equipment, or restore Home Assistant.

A backup restore test must use a separate test installation. Its pass means the
operator actually verified that restore; it is not inferred from backup creation
and does not authorize restoring the live home. Detector diagnostics such as
tamper, internal failures, and end-of-life, and heating-system service remain
outside this extension. Existing detector-test and battery monitoring contracts
are unchanged.

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

Installation bindings are grouped under `installation.functional_safety`:
`host_memory.available_entity` and `host_memory.psi_entity`, optional
`host_cpu_entity`, `host_disk_free_entity`, `host_temperature_entity`, optional
`backup.last_success_entity` and `backup.failure_entity`, `periodic_tests`
selection, product-specific
`updates` entities, a `battery_monitoring` selection policy, and an optional
manual `remote_batteries` registry. `battery_monitoring.enabled` defaults to
`true`; `battery_monitoring.excluded_devices` contains Home Assistant device
registry IDs and defaults to an empty list. Discovered runtime keys use
`Battery<hex>` derived from device identity; renaming a device or entity does not
change its exclusion or create a new maintenance identity.
The existing `notification.wan_entity` is shared with the notification route.
The packaged `calibration.functional_safety` owns the numeric policy and
durable detector and operational-test schedules. Device entries may be disabled without changing
the safety-input fault owned by their component.

SafetyFunctions can observe host resource pressure while it runs, but it cannot
detect or report its own complete loss, Home Assistant loss, or host power loss
through the same failed path. Such coverage requires an independent observer
and reporting path. Without one, the installation must present this as an
uncovered boundary. Neither an AppDaemon timer nor a frontend view is an
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
- Percentage and low-battery entities on the same device produce one condition;
  manual and automatic bindings do not double-monitor the same entities.
  Exclusion survives device/entity renaming, and failed discovery remains
  distinguishable from a successful inventory with no matching devices.
- A local network outage, WAN outage, cloud-provider outage, and complete Home
  Assistant loss are distinguishable to the extent their observers remain
  available. Local-Only policy does not silently disable local safety checks.
- Available and stale update data, version changes, and missing product update
entities are distinguishable. No test of observation invokes installation.
- A deliberately stalled component is overdue even if other components and
  the MQTT heartbeat continue. In-process checks do not claim coverage after
  complete application loss.
- Notification acceptance, recipient delivery, recovery command, and verified
  effect remain separate states. No verification scenario actuates equipment.
- A missing, due, failed, and operator-attested detector test remain distinct;
  an active detector alarm is unaffected by test maintenance state.
- Disk and thermal peaks remain diagnostic; sustained qualified conditions
  assert L4, and missing or invalid observations cannot clear them.
- An old valid backup timestamp, a future timestamp, stale failure evidence,
  and unavailable backup transport are distinguishable. No observation creates
  or restores a backup.
- No record, a recorded pass, an expired pass, a failure, and unreadable
  operational-test history remain distinct. A successful HA notification call
  does not complete a recipient-receipt test. No test-result action sends a
  notification, activates a siren, or restores the live installation.

## Execution and recovery allocation

| Layer | Primary responsibility |
| --- | --- |
| SafetyFunctions | Validate safety-relevant Home Assistant inputs; evaluate component and external-provider health; expose application self-diagnostics while the application is running; convert loss of required coverage into the appropriate diagnostic fault. |
| Home Assistant Supervisor and platform integrations | Manage the Home Assistant and add-on lifecycle, restart AppDaemon according to installation policy, expose host and add-on health, and report platform or add-on updates. SafetyFunctions may consume these results but should not duplicate Supervisor lifecycle ownership. |
| MQTT broker and Home Assistant MQTT integration | Operate the transport and broker service. SafetyFunctions publishes availability and heartbeat information and records observable publish failures, but broker availability alone does not prove end-to-end delivery. |
| Independent supervisor or watchdog, when installed | Detect complete loss of Home Assistant, AppDaemon, MQTT, or the host and provide an out-of-band indication. Without this separate path, complete-loss detection is explicitly uncovered. |

Host CPU load, memory pressure, disk space, temperature, and restart counters
are supporting diagnostic evidence while the application runs. Missed evaluation
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
