# Safety Monitoring Responsibility Boundaries

**Document role:** Non-normative architecture note

Safety monitoring covers the complete path from a safety-relevant input to a
decision and notification. Not every part of that path can be supervised by
SafetyFunctions itself. Monitoring responsibility should remain with the layer
that can still observe and report a failure when the monitored layer is down.

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
| SafetyFunctions self-diagnostics | An application self-monitor | Configuration validation, component initialization, scheduler progress, exception counters, persistence health, queue or worker liveness, and completion of safety-evaluation cycles. |
| Platform and add-on updates | Home Assistant Supervisor, with an optional SafetyFunctions consumer | Update availability, installed and offered versions, advisory severity, information freshness, and excessive update age. Installation and restart remain outside monitoring logic. |
| Notification path | `NotificationManager` and channel-specific diagnostics | Home Assistant service acceptance, per-target attempts, retries, and observable channel errors without presenting acceptance as confirmed delivery to a physical phone. |

These monitors may use a common diagnostic state model and evidence format, but
each channel retains its own lifecycle, calibration, and fault ownership. A
Safety Component declares which channels it depends on and decides how lost
coverage affects its safety function; it does not take ownership of the
underlying broker, host, provider, or Supervisor lifecycle.

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

This note records an architectural direction only. Any adopted safety contract
must be refined in the SYS, SSRD, feature architecture, configuration, and
verification evidence before implementation is claimed.
