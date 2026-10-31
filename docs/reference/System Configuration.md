# System Configuration Reference

## 1. Purpose

`backend/config/system_config.yml` is the public, packaged source of policy and
installation-independent defaults. Operators do not edit it inside a released
Home Assistant App. The build compiler combines it with the private
`user_config.yml` and generates the AppDaemon runtime configuration.

The `default_` prefix identifies a system baseline that a user or asset may
refine. Fields without that prefix are fixed software policy except the explicitly
editable functional-safety calibration below, whose stable names are retained.
`default_hazards` is inherited by opening roles, which
may select their own applicable hazards; there is no installation-wide user
override for the list.

`system_config.version` and `user_config.model_version` must match. There is no
independent version in the generated `app_config` object.

Print the closed machine-readable contract without loading installation data:

```powershell
python backend/build_app_config.py --print-system-schema
```

## 2. Top-level ownership

| Path | What it controls | Why it belongs here |
| --- | --- | --- |
| `system_config.version` | Complete system/user source contract version. | Prevents compilation of incompatible public policy and private installation data. |
| `app_definition` | AppDaemon module, class, default log level, and invocation behavior. | Defines how the packaged backend is started, not household topology. |
| `validation` | Strict-key handling and Home Assistant entity checks. | Validation strength is release policy and must be applied before mechanisms start. |
| `calibration` | Safety thresholds, timing, profiles, and installation-independent defaults. | These values affect safety decisions and require review, bounds, and tests. |
| `runtime_cfg` | Fault catalog and runtime service/provider behavior. | These settings describe released software behavior rather than physical installation assets. |

Rooms, openings, detectors, monitored entities, site coordinates, notification
destinations, and Home Assistant entity IDs do not belong in this file.
Site latitude and longitude are read from current Home Assistant Core
configuration at App startup and are not persisted in `user_config.yml` either.

## 3. Application and validation

| Path | Type/default | Meaning and rationale | User override |
| --- | --- | --- | --- |
| `app_definition.module` | `SafetyFunctions` | Stable AppDaemon module entry point. | No |
| `app_definition.class` | `SafetyFunctions` | Stable AppDaemon class entry point. | No |
| `app_definition.log_level` | `ERROR` | Safe packaged fallback for local compilation. The Home Assistant App `log_level` option overrides it when generating `apps.yaml`. | HA App option |
| `app_definition.use_dictionary_unpacking` | `true` | Selects the AppDaemon callback invocation contract used by the backend. | No |
| `validation.strict_validation` | `true` | Rejects unknown configuration keys so misspellings cannot silently weaken monitoring. | No |
| `validation.validate_entity_id_syntax` | `true` | Rejects malformed Home Assistant entity IDs before startup. | No |
| `validation.validate_entity_existence` | `true` | Checks configured entities and areas against Home Assistant before mechanisms start. | No |

## 4. Calibration

### 4.1 Temperature

| Field under `calibration.temperature` | Type/default | Purpose | User override |
| --- | --- | --- | --- |
| `sm_tc_1_debounce_limit` | integer `2` | Consecutive direct-temperature evaluations required by the low/high mechanisms. | No |
| `sm_tc_1_reeval_delay_seconds` | seconds `30` | Delay between direct-temperature reevaluations. | No |
| `sm_tc_2_debounce_limit` | integer `2` | Consecutive forecast evaluations required before lifecycle change. | No |
| `sm_tc_2_reeval_delay_seconds` | seconds `30` | Delay between forecast reevaluations. | No |
| `sm_tc_2_derivative_sample_minutes` | minutes `15` | Sampling horizon used to qualify the temperature derivative. | No |
| `sm_tc_min_valid_temperature_c` | °C `-40` | Lower plausibility boundary; values outside it are not positive safety evidence. | No |
| `sm_tc_max_valid_temperature_c` | °C `80` | Upper plausibility boundary. | No |
| `sm_tc_max_abs_rate_c_per_min` | °C/min `0.25` | Rejects implausible temperature-rate evidence. | No |
| `sm_tc_max_forecast_delta_c` | °C `6` | Bounds forecast extrapolation from one observation. | No |
| `default_low_temperature_c` | °C `18` | Installation baseline for the low-temperature threshold. | `installation.component_settings.temperature.low_temperature_c`, then room override |
| `default_high_temperature_c` | °C `28` | Installation baseline for the high-temperature threshold. | `installation.component_settings.temperature.high_temperature_c`, then room override |
| `forecast_horizon_hours` | hours `2` | Fixed horizon for room forecast evaluation. | No |

The compiler preserves the existing uppercase mechanism parameter names only
inside the generated runtime payload and diagnostics. Editable calibration uses
`small_snake_case`.

### 4.2 Entity Monitor

| Field under `calibration.entity_monitor` | Type/default | Purpose | User override |
| --- | --- | --- | --- |
| `default_startup_grace_seconds` | seconds `600` | Shared startup qualification for D contributions without allocated detection budgets, except `SafetyAppHealth`; acquisition, H detection and allocated supervision retain immediate routing. | `installation.component_settings.entity_monitor.startup_grace_seconds` |
| `default_failure_debounce_seconds` | seconds `15` | Default persistence required before a dependency becomes unhealthy. | Per explicit entity or component dependency |
| `default_recovery_debounce_seconds` | seconds `60` | Default persistence required before recovery is accepted. | Legacy per-entity/dependency migration input |
| `default_evaluation_interval_seconds` | seconds `60` | Baseline ordinary freshness/debounce cadence; the monitor caps it to meet derived requirements. Short-budget dependencies retain 5-second reconciliation. | Legacy `installation.component_settings.entity_monitor.evaluation_interval_seconds`, validated and capped |
| `unhealthy_summary_limit` | integer `32` | Bounds diagnostic publication size. | No |
| `component_overrides` | mapping, empty | Reviewed calibration for stable component-owned dependency keys. | Merged with `installation.component_settings.entity_monitor.component_overrides` |

The existing startup override applies to diagnostic routing across the application,
not only to entity freshness. Its interval starts on every SafetyFunctions
initialization, including an App or Home Assistant restart. Explicit existing
overrides retain their value; `0` disables this delay. The frontend shows the
backend-confirmed startup phase and countdown throughout the interval. Deferred
D contributions remain unevaluable rather than passing; application-health
failures, valid H evidence and contributors with allocated
`detection_budget_seconds` bypass the gate. The interval shall not enlarge an
allocated supervision budget, including SG-003's 60-second path. Existing
`deferred_symptom_count` reports the number of contributors enrolled in the gate,
not the number of queued observations. Supplied startup metadata must be current
and valid to confirm completion; legacy progress reports without that metadata
remain compatible. See
[Fault Routing and Aggregation](<../features/Fault Routing and Aggregation - Architecture.md#startup-qualification>).

The shared background reader acquires temperature-owned and shared
outside-temperature dependency reports on a 120-second baseline, other ordinary
Entity Monitor reports on a 60-second baseline, and short-budget dependencies
on a 5-second baseline. Monitor requirements may shorten ordinary intervals,
with a 5-second minimum. Logical records in distinct fault families share
physical acquisition at the shortest required interval without merging faults.
The short-budget group uses an
independent worker with a 3-second response deadline; ordinary reads have a
120-second deadline. Reader evidence lasts from acquisition start through the
group interval, response deadline and a 5-second scheduling allowance for
ordinary reads. Short-budget evidence uses its group interval plus 3 seconds.
State-change listeners supplement these reads immediately. Dependency timing
uses `report_timeout_seconds` for maximum source-report age and
`failure_debounce_seconds` for confirmation. The monitor derives scheduling
within its system-owned reader bounds and detection allocation; request
deadlines remain internal HA-reader policy. Legacy nested
`checks.freshness.max_silence_seconds` is accepted as an equivalent report-age
alias, and both forms must agree when present. Successful acquisition does not
reset the age of a source report. Schema validation checks freshness plus
debounce, while the dependency
contract separately allocates transport and scheduling overhead. Temperature
inputs use live `last_reported` confirmation rather than requiring a value
change; a declared timestamp contract remains necessary to relate integration
reports to actual measurements. MQTT integrations may suppress unchanged
writes unless `force_update` is enabled, so repeated messages do not necessarily
advance `last_reported`. See the [Entity Monitor architecture](../features/Entity%20Health%20Monitoring%20-%20Architecture.md#82-optional-checks)
for source semantics and detection-budget allocation.

Room-temperature and shared outside-temperature dependencies use a 3600-second
report-silence limit, 60-second failure confirmation and a 4020-second detection
budget. The forecast-rate
dependency retains failure debounce of its derivative sampling interval plus
60 seconds and allocates that interval plus 390 seconds as its detection
budget. These dependency defaults reserve acquisition/evaluation allowance;
they do not extend the immediate hazard alarm paths.

### 4.3 Safety Door

`calibration.safety_door.default_timeout_seconds` is the system open-duration
baseline. `installation.component_settings.safety_door.timeout_seconds` overrides it for
one installation, and an opening role may override it for one door or gate.

### 4.4 External Hazard

`calibration.external_hazard.default_hazards` is the baseline hazard set for an
opening role. `actuation_mode` and `clear_delay_seconds` are fixed runtime
policy. Weather and air-quality decision thresholds use `default_` because the
private installation may refine them under
`installation.component_settings.external_hazard.weather` and
`installation.component_settings.external_hazard.outdoor_air_quality`. The
weather forecast horizon has no user override.

| System field | Unit/default | Installation override |
| --- | --- | --- |
| `weather.forecast_horizon_hours` | hours `2` | No user override |
| `weather.default_frost_watch_c` | °C `2` | `weather.frost_watch_c` |
| `weather.default_frost_warning_c` | °C `0` | `weather.frost_warning_c` |
| `weather.default_gust_watch_m_s` | m/s `15` | `weather.gust_watch_m_s` |
| `weather.default_gust_warning_m_s` | m/s `20` | `weather.gust_warning_m_s` |
| `weather.default_precipitation_warning_mm_h` | mm/h `2.5` | `weather.precipitation_warning_mm_h` |
| `weather.default_persistence_seconds` | seconds `120` | `weather.persistence_seconds` |
| `weather.default_hysteresis` | temperature `0.5`, gust `1.0` | `weather.hysteresis` |
| `outdoor_air_quality.default_standard` | `european_aqi` | `outdoor_air_quality.standard` |
| `outdoor_air_quality.default_warning_at` | index `60` | `outdoor_air_quality.warning_at` |

The former `decision_timeout_seconds` field was removed because no runtime code
consumed it. User-confirmed actuator proposals retain their separate,
per-opening `confirmation_timeout_seconds` contract.

### 4.5 Internal Environmental Hazard

`calibration.internal_environmental_hazard` owns detector profiles, alarm and
clear state semantics, health debounce, persistent-state policy, and the
maximum detector count. The private configuration selects a profile and binds
it to a detector; it cannot redefine the profile semantics.
The same system-owned binary profile can describe a water-leak sensor when its
Home Assistant wet/dry states match the profile. `WaterLeakDetected` is an L2
C-LEAK fault; merely binding the sensor never enables valve actuation.

### 4.6 Functional safety

`calibration.functional_safety` owns the sampling period, host-memory and PSI
qualification/recovery margins, CPU, disk and temperature policy, WAN outage
qualification/recovery, source freshness, backup age, the remote-battery
threshold, and detector/operational-test intervals and state stores. These are
packaged defaults and fixed runtime policy. The installation binds host memory, disk, temperature,
backup, update, and remote battery entities in `installation.functional_safety` and
reuses `notification.wan_entity` for WAN evidence. Missing bindings do not
create a positive healthy observation.
Thresholds, qualification/recovery durations, backup maximum age and test
intervals may be overridden under
`installation.component_settings.functional_safety`, using the same field names.
Omitted or null values inherit packaged values. The compiler validates the
complete merged calibration, including all recovery margins, before saving or
starting the App. Detector-test interval overrides are limited to 1–180 days.
Sampling cadence, all `*_stale_after_seconds` fields, state-file paths and fault
levels remain system-only. See the [source contract](../features/Configuration%20Model%20-%20Architecture.md#33-component-settings).
The memory thresholds are packaged defaults, not a guarantee that
256 MiB is a safe reserve for every host; review them against actual host
capacity and workload before an installation relies on L2 memory detection.

| Policy field | Packaged value | Effect |
| --- | --- | --- |
| `evaluation_interval_seconds` | 15 s | In-process host/WAN policy and progress evaluation; source acquisition is a separate 60-second background batch, not an independent watchdog. |
| `maintenance_poll_interval_seconds` | 3600 s | Battery, backup and update batch-read cadence; completed attempts and expired reader evidence trigger maintenance policy evaluation. System-only integer, at least 1 s. |
| `memory_low_available_mib` / `memory_recovery_available_mib` | 256 / 384 MiB | L2 assertion and recovery margins, requiring corroborating PSI. |
| `memory_high_psi_percent` / `memory_recovery_psi_percent` | 10% / 5% | PSI qualification and recovery margins. |
| `memory_qualification_seconds` / `memory_recovery_seconds` | 120 / 120 s | Sustained L2 assertion and distinct recovery duration. |
| `cpu_high_percent` / `cpu_recovery_percent` | 90% / 70% | L3 host CPU qualification and recovery margins. |
| `cpu_qualification_seconds` / `cpu_recovery_seconds` | 300 / 120 s | Sustained high CPU load and distinct recovery duration. |
| `disk_low_free_mib` / `disk_recovery_free_mib` | 1024 / 2048 MiB | L3 low host-disk-space threshold and positive recovery margin. |
| `host_temperature_high_c` / `host_temperature_recovery_c` | 80 / 70 °C | L3 host-temperature threshold and distinct recovery margin. |
| `resource_qualification_seconds` / `resource_recovery_seconds` | 120 / 120 s | Sustained disk/thermal qualification and recovery. |
| `backup_max_age_hours` | 48 h | Maximum age of a valid last-success backup timestamp before an L3 overdue maintenance warning. |
| `backup_stale_after_seconds` | 86400 s | Maximum observation age for an optional backup-failure source; not a substitute for backup-success age. |
| `wan_qualification_seconds` / `wan_recovery_seconds` | 60 / 60 s | Sustained L3 WAN fault and recovery. |
| `battery_low_percent` | 15% | L4 maintenance threshold per configured remote device. |
| `battery_fault_catalog_file` | `/config/appdaemon/battery_fault_catalog.json` | One-time legacy import path for active/retired battery-fault identities; SQLite retains MQTT discovery cleanup state after exclusions or removal. |
| `detector_test_interval_days` | 180 days | L3 due/failed maintenance warning per configured detector. |
| `notification_test_interval_days` | 30 days | Due date after an operator-attested notification-receipt pass. |
| `backup_restore_test_interval_days` | 180 days | Due date after an operator-attested restore pass on a separate installation, when enabled. |
| `resource_stale_after_seconds` / `wan_stale_after_seconds` | 180 / 180 s | Maximum age for accepted host and WAN evidence. |
| `update_stale_after_seconds` / `battery_stale_after_seconds` | 86400 / 86400 s | Maximum age for accepted update and battery evidence. |
| `detector_test_state_file` | `/config/appdaemon/detector_tests.json` | One-time legacy import path for operator-reported detector results stored in SQLite. |
| `periodic_test_state_file` | `/config/appdaemon/periodic_tests.json` | One-time legacy import path for SQLite operational-test attestations, separate from detector records and editable configuration. |
| `memory_fault_level` / `wan_fault_level` / `cpu_fault_level` | L2 / L3 / L3 | Fixed reviewed severities for host memory, WAN and CPU. |
| `warning_fault_level` | L3 | Fixed severity for disk, host temperature, backup, available updates and due/failed detector tests. |
| `maintenance_fault_level` | L4 | Fixed informational severity for low batteries and due/failed periodic notification-receipt or backup-restore tests. These conditions remain visible without degrading the overall system state. |

Disk and temperature baselines require review against the actual host and normal
workload; they are maintenance limits, not hardware shutdown protection. Backup
creation and a successful separate-installation restore are different evidence.
Operational-test records never trigger a notification or backup operation.

### 4.7 Heating input supervision

`calibration.heating_system_monitor` owns the generic input monitor's bounded
schedule, persistence and rule qualification. It contains no controller product
selection or device-specific entity names. `Diagnostic` remains the default R01
profile; an application upgrade does not enable additional rules.

| Field | Packaged default | Meaning | User override |
| --- | --- | --- | --- |
| `evaluation_interval_seconds` | `5` | Reconciliation cadence in seconds. | No |
| `maximum_systems` | `8` | Maximum explicitly selected heating installations. | No |
| `state_file` | `/config/appdaemon/heating_monitor_state.json` | Legacy import path for the `heating_monitor_state` store in the shared SQLite database, outside the deployed app tree. | No |
| `profiles.Diagnostic.provenance` | Input availability diagnostics; excluded from thermal and SG-003 coverage | Describes the admitted diagnostic scope, not manufacturer or thermal evidence. | No |
| `profiles.Diagnostic.enabled_rules` | `[R01]` | Input-source supervision only. Other profiles may select R02..R13 with complete reviewed policies and qualified mappings. | No |
| `profiles.Diagnostic.failure_seconds` | `5` | Qualified input failure duration before activation, subject to shared diagnostic startup qualification. | No |
| `profiles.Diagnostic.recovery_seconds` | `60` | Continuous valid input duration before clearing; missing evidence does not clear activation. | No |
| `profiles.<key>.device_fault` | Absent | R02 current-status policy; required when R02 is enabled. | No |
| `profiles.<key>.missing_demand` | Absent | R03 independent room-need/request policy; required when R03 is enabled. | No |
| `profiles.<key>.no_response` | Absent | R04 request/response and bounded inhibition policy; required when R04 is enabled. | No |
| `profiles.<key>.flow_rise` | Absent | R05 commissioned physical flow-rise windows, thresholds and timing. | No |
| `profiles.<key>.flow_tracking` | Absent | R06 commissioned flow-target bands, observed windows and timing. | No |
| `profiles.<key>.pump_response` | Absent | R07 topology-specific physical pump response and timing. | No |
| `profiles.<key>.flow_return` | Absent | R08 loaded flow/return differential bands and covered windows. | No |
| `profiles.<key>.room_delivery` | Absent | R09 room need, independently evidenced physical delivery and temperature response. | No |
| `profiles.<key>.mode_temperature` | Absent | R10 reviewed per-phase envelopes and HSM-H05 equipment response allocation. | No |
| `profiles.<key>.absolute_temperature` | Absent | R11 independent absolute flow limit and HSM-H05 equipment response allocation. | No |
| `profiles.<key>.cycling` | Absent | R12 informational CH/DHW counters and bounded physical cycle observations. | No |
| `profiles.<key>.maintenance` | Absent | R13 fresh maintenance-status policy; required when R13 is enabled. | No |

The private configuration enables `HeatingSystemMonitorComponent` and selects
`installation.heating_systems` with stable keys, friendly names and semantic
input/room bindings. A binding supplies `entity_id`, optional literal
`attribute`, `value_map`, units/conversion, required `evidence_kind` and
`independence_group`, and explicit freshness selectors where supported.
`availability_only` preserves uncertainty about original measurement age;
`source_timestamp` requires `observed_at_attribute` or
`observed_at_entity_id`. Neither source publication nor HA `last_updated` is
silently substituted for measurement time.

Each optional rule policy provides `evidence_reference`, `failure_seconds` and
`recovery_seconds`. Demand/response policies additionally declare separate need
bands or target recovery tolerance, explicit allowances, source-time skew and
a total unresolved-need budget of at most 1800 seconds. `no_response` declares
`inhibition_context: none` or `mapped_reason`; the latter requires a normalized
`inhibition_reason` (`none`, `startup`, `anti_cycle`). The component derives its
bounded expiry; a source `until` value is not assumed. Required inputs must have
original observation timestamps, appropriate physical/intent meaning and a
validated complete source-to-notification timing allocation. Unqualified
availability-only bindings cannot activate those rules.

The compiled component publishes partial coverage and explicit rule exclusions.
R01 success does not prove physical heating response or SG-003 timing
compliance. R12/R13 remain L4 maintenance information and do not restrict hazard
checks. Input maps cannot write device setpoints. State-version migration
preserves unchanged R01 incidents; new defaults do not authorize clearing old
active evidence. See the exact policy fields, bounds and
[generic input contract and example](../HEATING_MONITOR_DELIVERY.md#generic-input-contract)
and [R07..R12 policy fields](<../features/Heating Additional Rule Policies.md>)
and [installation template](../../backend/config/user_config.example.yml).

## 5. Runtime configuration

### 5.1 Faults

`runtime_cfg.faults` is the stable fault catalog. Each entry owns its operator
name, level, H/D category, related Safety Mechanism IDs, and optional shadowing.
The `category` key defaults to `H` for compatibility; diagnostic faults use
`D`. Level is validated in `1..4` and selects the notification level of the
same number. Category does not imply urgency, recovery actuation, or a
degradation target. Changing a
fault key, severity, or mechanism mapping requires coordinated requirements,
tests, UI, MQTT, and deployment changes.

### 5.2 Providers

`runtime_cfg.providers` is the only system source for external API adapters.
Each provider groups default enablement with its endpoint, polling interval,
request timeout, retry count, and staleness limit. The private
`user_config.providers.<name>.enabled` field may change enablement; it cannot
replace endpoints or transport safety bounds.

Provider configuration is intentionally separate from external-hazard decision
calibration: providers acquire evidence, while C-EXT decides what that evidence
means for the installation.

### 5.3 Notification and recovery

`runtime_cfg.notification` owns transport timeout, severity profiles, bounded
retry, delivery deadlines, level-one repetition, and persistence. Private
configuration owns only destinations, the default UI URL, optional local
annunciators, and WAN evidence.

`runtime_cfg.recovery` owns persistence for proposals, manual-work reports and
bounded action outcomes, and separate recovery timing. Installation assets and
actuation eligibility remain in the private opening/room registry; installation
configuration does not set recovery timing.

| `runtime_cfg.recovery.timing` field | Packaged default | Meaning |
| --- | --- | --- |
| `consent_timeout_seconds` | `120` seconds | Validity of a pending command-consent request. Expiry authorizes no command. |
| `effect_timeout_seconds` | `120` seconds | Observation deadline after an executed command; service acceptance is not completion. |
| `manual_task_timeout_seconds` | `null` | Optional manual-task deadline. Null leaves manual work without a command-consent deadline. |

Consent and effect durations shall be integer seconds from 15 through 86400;
a manual-task duration shall be null or an integer in the same range. Optional per-action fields
with the same names shall refine system-owned action policy, not installation
entity bindings. A non-default legacy
`RecoveryResult.confirmation_timeout_seconds` value remains a compatibility
fallback for consent/effect when the corresponding per-action field is absent;
otherwise the separate system defaults apply. Persistence settings remain
unchanged. These optional timing fields introduce no independent version in
generated runtime configuration and do not change the source-model version
contract between `system_config.version` and `user_config.model_version`.

Enabled runtime persistence uses the shared SQLite database described in
[Runtime State Storage](<../features/Runtime State Storage - Architecture.md>).
The existing state-file fields are retained as one-time JSON import paths;
notification and recovery saves use their separate store namespaces afterwards.
The database is `safety_state.sqlite3` beside `runtime_cfg.fault_evidence.state_file`,
which defaults to `/config/appdaemon/safety_state.sqlite3`. Configuration YAML,
API/MQTT JSON, and transient `/run` diagnostic JSON retain their current formats.

`runtime_cfg.fault_evidence` owns the independent fault diagnostic store. Its
`enabled` switch defaults to `true`; `state_file` is
`/config/appdaemon/fault_evidence_state.json` as a legacy import path.
`max_records: 256` limits fault
keys, `max_frame_bytes: 4096` limits the UTF-8 activation-capture fields within
one freeze frame, and `max_total_bytes: 1048576` limits the complete persisted
logical serialized snapshot, including lifecycle timestamps, counters, reason, duration and
clock uncertainty. Lifecycle fields retain their own bounded validation and do
not consume the capture byte budget. The
closed source schema requires all five fields and rejects a total limit too
small to contain one frame. Operators do not configure this policy through
private installation YAML. Setting `enabled: false` retains bounded evidence
in process memory only; it does not suppress first-activation capture.

The same `freeze_frame` object carries the capture and lifecycle fields in
MQTT and API fault records. The persisted store uses format version 2 and
migrates validated version 1 records on load, preserving their captured values
and lifecycle metadata within the original validation bounds. This changes
neither the configured content limits nor the accepted legacy state-file path.
The 1 MiB bound applies to evidence content, not the complete shared database.

### 5.4 MQTT

`runtime_cfg.mqtt` owns discovery topics, device identity, retain/QoS behavior,
heartbeat, expiry, and startup retained-state behavior. The user configuration
does not contain MQTT policy or a retired-discovery cleanup list.

## 6. Localization

Backend translations are stored in:

- `backend/components/core/locales/en.yml`;
- `backend/components/core/locales/pl.yml`;
- `backend/components/core/locales/de.yml`.

`user_config.localization.language` selects one file. Optional private
installation names live in `/config/locales/<language>.yml` in the App's
private configuration directory. This flat YAML mapping accepts only
`entity_name.<entity_id>: <display name>` entries, for example
`entity_name.sensor.safety_app_health: Safety status`. A private name takes
precedence over a packaged name. The files are never edited by the GUI and
must not be committed to the public repository.
Stable entity IDs, fault IDs, Safety Mechanism IDs, raw states, and MQTT topics
are never localized.

## 7. Generated configuration

The optional installation-owned `safety_routines` registry compiles into
`user_config.safety_routines.routines`. It introduces no packaged calibration
override or change to existing component bindings. See
[Safety Routines](../features/Safety%20Routines%20-%20Architecture.md) for the
closed schema, service limits, source-time qualification and event API.

`backend/build_app_config.py` validates both closed source models, checks their
versions, resolves them, and generates `apps.yaml`. SafetyFunctions then
validates the complete generated runtime contract before starting mechanisms.
The generated `app_config` and `user_config.safety_components` structures are
not additional editable sources. In particular, generated room, door, opening,
detector, and monitored-entity collections are created only from the private
installation registry; empty placeholder collections do not exist in
`system_config.yml`.
