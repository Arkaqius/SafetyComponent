# System Configuration Reference

## 1. Purpose

`backend/config/system_config.yml` is the public, packaged source of policy and
installation-independent defaults. Operators do not edit it inside a released
Home Assistant App. The build compiler combines it with the private
`user_config.yml` and generates the AppDaemon runtime configuration.

The `default_` prefix identifies a system baseline that a user or asset may
refine. Fields without that prefix are fixed software policy for the released
system configuration. `default_hazards` is inherited by opening roles, which
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
| `default_startup_grace_seconds` | seconds `60` | Prevents startup transients from immediately becoming dependency faults. | `installation.component_settings.entity_monitor.startup_grace_seconds` |
| `default_failure_debounce_seconds` | seconds `15` | Default persistence required before a dependency becomes unhealthy. | Per explicit entity or component dependency |
| `default_recovery_debounce_seconds` | seconds `60` | Default persistence required before recovery is accepted. | Per explicit entity or component dependency |
| `default_evaluation_interval_seconds` | seconds `5` | Baseline periodic evaluation cadence. | `installation.component_settings.entity_monitor.evaluation_interval_seconds` |
| `unhealthy_summary_limit` | integer `32` | Bounds diagnostic publication size. | No |
| `component_overrides` | mapping, empty | Reviewed calibration for stable component-owned dependency keys. | Merged with `installation.component_settings.entity_monitor.component_overrides` |

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

### 4.6 Functional safety

`calibration.functional_safety` owns the sampling period, host-memory and PSI
qualification/recovery margins, CPU, disk and temperature policy, WAN outage
qualification/recovery, source freshness, backup age, the remote-battery
threshold, and detector/operational-test intervals and state stores. These are
packaged policy values. The installation binds host memory, disk, temperature,
backup, update, and remote battery entities in `installation.functional_safety` and
reuses `notification.wan_entity` for WAN evidence. Missing bindings do not
create a positive healthy observation.
The memory thresholds are packaged defaults, not a guarantee that
256 MiB is a safe reserve for every host; review them against actual host
capacity and workload before an installation relies on L2 memory detection.

| Policy field | Packaged value | Effect |
| --- | --- | --- |
| `evaluation_interval_seconds` | 15 s | Periodic in-process sample; not an independent watchdog. |
| `memory_low_available_mib` / `memory_recovery_available_mib` | 256 / 384 MiB | L2 assertion and recovery margins, requiring corroborating PSI. |
| `memory_high_psi_percent` / `memory_recovery_psi_percent` | 10% / 5% | PSI qualification and recovery margins. |
| `memory_qualification_seconds` / `memory_recovery_seconds` | 120 / 120 s | Sustained L2 assertion and distinct recovery duration. |
| `cpu_high_percent` / `cpu_recovery_percent` | 90% / 70% | L4 host CPU qualification and recovery margins. |
| `cpu_qualification_seconds` / `cpu_recovery_seconds` | 300 / 120 s | Sustained high CPU load and distinct recovery duration. |
| `disk_low_free_mib` / `disk_recovery_free_mib` | 1024 / 2048 MiB | L4 low host-disk-space threshold and positive recovery margin. |
| `host_temperature_high_c` / `host_temperature_recovery_c` | 80 / 70 °C | L4 host-temperature threshold and distinct recovery margin. |
| `resource_qualification_seconds` / `resource_recovery_seconds` | 120 / 120 s | Sustained disk/thermal qualification and recovery. |
| `backup_max_age_hours` | 48 h | Maximum age of a valid last-success backup timestamp before L4 overdue maintenance. |
| `backup_stale_after_seconds` | 86400 s | Maximum observation age for an optional backup-failure source; not a substitute for backup-success age. |
| `wan_qualification_seconds` / `wan_recovery_seconds` | 60 / 60 s | Sustained L3 WAN fault and recovery. |
| `battery_low_percent` | 15% | L4 maintenance threshold per configured remote device. |
| `detector_test_interval_days` | 180 days | L4 due/failed maintenance condition per configured detector. |
| `notification_test_interval_days` | 30 days | Due date after an operator-attested notification-receipt pass. |
| `backup_restore_test_interval_days` | 180 days | Due date after an operator-attested restore pass on a separate installation, when enabled. |
| `resource_stale_after_seconds` / `wan_stale_after_seconds` | 180 / 180 s | Maximum age for accepted host and WAN evidence. |
| `update_stale_after_seconds` / `battery_stale_after_seconds` | 86400 / 86400 s | Maximum age for accepted update and battery evidence. |
| `detector_test_state_file` | `/config/appdaemon/detector_tests.json` | Durable operator-reported test results. |
| `periodic_test_state_file` | `/config/appdaemon/periodic_tests.json` | Durable operational-test attestations, separate from detector records and editable configuration. |
| `memory_fault_level` / `wan_fault_level` / `cpu_fault_level` / `maintenance_fault_level` | L2 / L3 / L4 / L4 | Fixed reviewed severities for host memory, WAN, CPU, and maintenance. |

Disk and temperature baselines require review against the actual host and normal
workload; they are maintenance limits, not hardware shutdown protection. Backup
creation and a successful separate-installation restore are different evidence.
Operational-test records never trigger a notification or backup operation.

## 5. Runtime configuration

### 5.1 Faults

`runtime_cfg.faults` is the stable fault catalog. Each entry owns its operator
name, level, related Safety Mechanism IDs, and optional shadowing. Changing a
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

`runtime_cfg.recovery` owns persistence for proposed and confirmed recovery
actions. Installation assets and actuation eligibility remain in the private
opening/room registry.

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

`backend/build_app_config.py` validates both closed source models, checks their
versions, resolves them, and generates `apps.yaml`. SafetyFunctions then
validates the complete generated runtime contract before starting mechanisms.
The generated `app_config` and `user_config.safety_components` structures are
not additional editable sources. In particular, generated room, door, opening,
detector, and monitored-entity collections are created only from the private
installation registry; empty placeholder collections do not exist in
`system_config.yml`.
