# Configuration Model Architecture

## 1. Purpose

SafetyComponent separates reusable safety policy from the physical Home
Assistant installation. Configuration model version 2 declares each physical
asset once and compiles that registry into the existing component bindings.
The generated runtime contract remains compatible with the SafetyFunctions
components and is not edited directly.

## 2. Sources and precedence

Configuration is resolved in three ordered layers:

1. `system_config.yml` provides packaged policy, calibration, profiles,
   provider lifecycle, fault definitions, and component defaults that do not
   depend on one installation.
2. `user_config.yml` `installation.defaults` optionally overrides a packaged
   default for the whole installation.
3. A room, opening, detector, or monitored entity may refine the applicable
   value for that asset.

Later layers replace only values they explicitly define. Omitted values inherit
the preceding layer. Lists are replaced as complete values; mappings are merged
recursively. Stable fault keys, Safety Mechanism IDs, MQTT topics, raw states,
and runtime component identifiers are never derived from display names.

### 2.1 System-owned contract

`system_config.yml` is immutable inside a released App image. Its sections are:

The complete field-level rationale and override map is maintained in the
[System Configuration reference](<../reference/System Configuration.md>).

| Section | Ownership |
| --- | --- |
| `app_definition` | AppDaemon module, class, logging baseline, and invocation behavior. |
| `system_config.version` | Exact system and editable source-model version accepted by the compiler. |
| `validation` | Strict unknown-key handling plus startup entity syntax and existence validation. |
| `calibration.temperature` | Temperature mechanism calibration and installation-independent room defaults. |
| `calibration.entity_monitor` | Default timing, bounded publication, and component dependency overrides. |
| `calibration.safety_door` | Installation-independent open-timeout default. |
| `calibration.external_hazard` | Opening hazard defaults and default weather/air-quality decision thresholds. |
| `calibration.internal_environmental_hazard` | Detector profiles, health timing, persistence, and capacity. |
| `runtime_cfg.faults` | Stable fault catalog, levels, shadowing, and Safety Mechanism mappings. |
| `runtime_cfg.providers` | Supported provider enablement, endpoints, polling, timeouts, retries, and staleness. |
| `runtime_cfg.notification` | Delivery profiles, retries, deadlines, repeat behavior, diagnostics, and persistence. |
| `runtime_cfg.recovery` | Recovery persistence and execution defaults. |
| `runtime_cfg.mqtt` | Discovery, topics, availability, retain/QoS, heartbeat, expiry, and the empty cleanup baseline. |

Packaged text is loaded from `backend/components/core/locales/<language>.yml`,
not from `system_config.yml`. Empty installation collections such as rooms,
openings, detectors, and explicit monitored entities are not system defaults;
the compiler creates them only from the installation registry.

Installation-specific entity IDs, areas, site applicability, notification
destinations, and physical assets are prohibited from the system source.

## 3. Installation registry

The private `user_config.yml` selects enabled components, notification
destinations, language, and one normalized `installation` registry:

```yaml
user_config:
  model_version: 2
  components_enabled:
    TemperatureComponent: true
    SafetyDoorsComponent: false
    ExternalHazardComponent: true
    EntityMonitorComponent: true
    InternalEnvironmentalHazardMonitorComponent: false

  localization:
    language: en

  notification:
    mobile:
      services: [notify/mobile_app_example_phone]
      default_url: /

  installation:
    site:
      latitude: 50.0
      longitude: 20.0
      timezone: Europe/Warsaw
      country_code: PL
      teryt_codes: ["0000"]
    common_entities:
      outside_temp: sensor.outdoor_temperature
    defaults:
      temperature:
        high_temperature_c: 27.0

    rooms:
      LivingRoom:
        area_id: living_room
        temperature_sensor: sensor.living_room_temperature
        window: LivingRoomWindow

    openings:
      LivingRoomWindow:
        area_id: living_room
        entity_id: binary_sensor.living_room_window
        friendly_name: Living room window
        kind: window
        external_hazard: {}

    detectors: {}
    monitored_entities: {}
```

Registry keys use stable PascalCase identifiers. A room references an opening
by its registry key, so the same physical binary sensor can supply both the
temperature room binding and an external-hazard role without repeating its
entity ID. An opening may additionally declare a `safety_door` role. Detectors
and explicit Entity Monitor dependencies are declared under `detectors` and
`monitored_entities`.

Presence of an opening role enables that role for the opening. Absence removes
the opening from the corresponding generated component collection; deleting an
installation asset must not cause an example or system-owned asset to appear.

### 3.1 Complete editable root contract

Unknown keys are rejected. The complete editable `user_config` root is:

| Field | Required | Contract |
| --- | --- | --- |
| `model_version` | Yes | Integer `2`; no other or missing version is accepted. |
| `components_enabled` | Yes | Contains exactly the five supported component keys, each with a boolean value, and enables at least one component. |
| `localization` | No | `language` is `en`, `pl`, or `de`; `entity_names` maps valid entity IDs to non-empty display names. Defaults to English with no overrides. |
| `notification` | Yes | Installation-owned notification destinations described below. Retry, delivery, profile, persistence, and detail policy remain system-owned. |
| `providers` | No | Contains only the three supported provider keys, each with `enabled: true/false`; omitted providers inherit enabled system defaults. |
| `mqtt` | No | Contains only installation-specific `legacy_discovery_entity_ids`; all transport and publication policy remains system-owned. |
| `installation` | Yes | Physical installation registry described below. |

The five required `components_enabled` keys are
`TemperatureComponent`, `SafetyDoorsComponent`, `ExternalHazardComponent`,
`EntityMonitorComponent`, and
`InternalEnvironmentalHazardMonitorComponent`.

`notification` accepts:

| Field | Required | Contract |
| --- | --- | --- |
| `mobile.services` | Yes | Non-empty, deduplicated list of explicit `notify/<service>` names; ambiguous `notify/notify` is rejected. |
| `mobile.default_url` | No | Home Assistant-relative path beginning with one `/`; default `/`. |
| `local.light_entity` | No | Valid Home Assistant entity ID for an approved local light output. |
| `local.alarm_entity` | No | Valid Home Assistant entity ID for an approved local alarm output. |
| `wan_entity` | No | Valid Home Assistant entity ID used as WAN reachability evidence, or `null`. |

`providers` accepts only `OpenMeteoWeatherApiComponent`,
`ImgwWarningsApiComponent`, and `OpenMeteoAirQualityApiComponent`. Their URLs,
polling, timeouts, retry bounds, staleness, and schemas remain in
`system_config.yml`.

`mqtt.legacy_discovery_entity_ids` is an optional, deduplicated list of
lowercase `sensor.*` entity IDs previously published by this installation.
The MQTT manager clears their retained discovery topics at startup. This list
does not enable legacy configuration-model parsing and may be emptied after the
installation has completed and verified the cleanup.

### 3.2 Installation root

| Field | Required | Contract |
| --- | --- | --- |
| `site` | When External Hazard is enabled | Latitude `[-90, 90]`, longitude `[-180, 180]`, valid IANA `timezone`, two-letter `country_code`, and a non-empty unique list of four-digit `teryt_codes`. |
| `common_entities` | No | Map of stable semantic keys to Home Assistant entity IDs. |
| `defaults` | No | Installation-wide overrides for temperature, safety doors, external hazards, and Entity Monitor dependencies. |
| `rooms` | No | Stable room registry used to generate Temperature bindings. |
| `openings` | No | Stable physical opening registry used by room, Safety Doors, and External Hazard bindings. |
| `detectors` | No | Internal environmental detector registry. |
| `monitored_entities` | No | Explicit installation-owned Entity Monitor dependencies. |

Keys in `rooms`, `openings`, `detectors`, and `monitored_entities` use
`^[A-Z][A-Za-z0-9]*$`. They are technical identities, not translated names.

### 3.3 Installation defaults

| Path | Fields and constraints |
| --- | --- |
| `defaults.temperature` | Optional `low_temperature_c`, `high_temperature_c`, and positive `forecast_horizon_hours`. Resolved low must remain below resolved high. |
| `defaults.safety_door` | Optional positive `timeout_seconds`. |
| `defaults.external_hazard` | Optional non-empty unique `hazards` list plus weather and outdoor-air-quality overrides. Omitted values inherit the corresponding `default_*` system calibration. |
| `defaults.entity_monitor` | Optional `startup_grace_seconds`, positive `evaluation_interval_seconds`, and component override map keyed by stable dependency ID. Each component override may refine debounce, detection budget, and checks. |

### 3.4 Rooms and openings

Each room accepts:

| Field | Required | Contract |
| --- | --- | --- |
| `area_id` | Yes | Non-empty Home Assistant area ID. |
| `temperature_sensor` | Yes | Temperature entity ID; syntax and existence are checked at startup. |
| `window` | No | Stable key of one opening in the same `area_id`. One opening cannot be assigned to two rooms. |
| `actuator` | No | `cover.*` entity accepted by the existing Temperature safe-actuation contract. |
| `temperature` | No | Per-room temperature fields from section 3.3; these override installation and system defaults. |

Each opening accepts `area_id`, `entity_id`, `friendly_name`, and `kind`.
`kind` is one of `window`, `door`, `garage_door`, or `gate`. It may then carry
either or both roles:

| Role | Fields and constraints |
| --- | --- |
| `safety_door` | Optional positive `timeout_seconds`; optional `condition` with `entity_id`, non-empty unique `pass_states`, and non-empty unique `blocked_states`. Pass and blocked states must be disjoint. |
| `external_hazard` | Optional non-empty unique `hazards`; `execution_policy` is `manual` or `user_confirmed`; optional `actuator_entity_id`; `confirmation_timeout_seconds` is 15–600, default 120. Manual roles cannot define an actuator. User-confirmed execution is limited to a `garage_door` or `gate` with a `cover.*` actuator. |

An omitted role means that the opening is not generated for that component.
An opening may still exist only as a room's temperature window.

### 3.5 Detectors and explicit monitored entities

Each detector accepts:

| Field | Required | Contract |
| --- | --- | --- |
| `area_id`, `entity_id`, `friendly_name`, `profile` | Yes | Non-empty binding values. The profile must exist in the system-owned detector profiles. |
| `hazard` | Yes | `smoke`, `flammable_gas`, or `carbon_monoxide`. |
| `gas_identity` | Conditional | Required only for `flammable_gas`; forbidden for other hazards. |
| `enabled` | No | Boolean, default `true`; disabled detectors are omitted from runtime. |

Each `monitored_entities` entry accepts `entity_id`, optional `area_id`,
non-empty `description`, optional `enabled`, non-negative
`failure_debounce_seconds` and `recovery_debounce_seconds`, positive
`detection_budget_seconds`, and `checks`:

| Check | Contract |
| --- | --- |
| `freshness` | Non-empty `timestamp_source` and positive `max_silence_seconds`. |
| `required_value` | Optional non-empty `target`; default `state`. |
| `allowed_values` | Non-empty unique normalized `values` and optional `target`. |
| `finite_number` | Optional `target`; the resolved value must be finite. |
| `numeric_range` | Optional `target` and at least one of `minimum` or `maximum`; minimum cannot exceed maximum. |
| `rate_of_change` | Positive `window_seconds`, `min_samples >= 2`, and at least one non-negative rise/fall-per-minute limit. |

Entity Monitor rejects any debounce/freshness combination that exceeds the
configured detection budget.

## 4. Generated component bindings

`backend/build_app_config.py` validates the source model and generates the
existing runtime namespace:

| Installation source | Generated runtime binding |
| --- | --- |
| `rooms` | `TemperatureComponent.rooms` |
| `openings.*.safety_door` | `SafetyDoorsComponent.doors` |
| `openings.*.external_hazard` | `ExternalHazardComponent.openings` |
| `detectors` | `InternalEnvironmentalHazardMonitorComponent.detectors` |
| `monitored_entities` | `EntityMonitorComponent.explicit_entities` |

System-owned detector profiles, persistence limits, provider policy, MQTT
behavior, health calibration, and fault definitions are added during
compilation. The compiler does not copy `model_version`, `installation`, or
installation defaults into the runtime output. SafetyFunctions therefore sees
the same validated component contract as before configuration model version 2.

## 5. Validation boundaries

Compilation fails before AppDaemon starts when:

- the source model version is unsupported;
- a root or nested key is unknown;
- component enablement does not explicitly cover all supported components;
- a registry key is not a stable PascalCase identifier;
- a room references an unknown opening;
- one opening is assigned as the temperature window of multiple rooms;
- a referenced room and opening disagree on `area_id`;
- an external-hazard opening has neither asset-specific nor inherited hazards;
- a source file contains generated-only `safety_components` bindings.

The generated configuration then passes the existing component schemas and
Home Assistant startup validation. Those checks continue to validate entity
syntax and existence, areas, component policy, detection budgets, thresholds,
and safe actuation constraints.

## 6. Schema inspection and version policy

Configuration model version 2 is the only accepted editable source format.
Missing versions, model version 1, and unknown future versions fail before
AppDaemon starts. Generated component keys, entity IDs, MQTT identities,
persistence files, fault keys, and safety behavior remain separate runtime
contracts.

Print the machine-readable JSON Schema without reading an installation file:

```powershell
python backend/build_app_config.py --print-user-schema
```

Validate and compile a reviewed source file with:

```powershell
python backend/build_app_config.py --user <user.yml> --output <apps.yaml>
python backend/build_app_config.py --user <user.yml> --output <apps.yaml> --check
```

The Pydantic source model, generated JSON Schema, public example, architecture
reference, compiler tests, and runtime component validators collectively define
the executable contract. The source model rejects unknown keys; the runtime
validators additionally verify Home Assistant entity existence and resolved
component safety constraints.

## 7. Ownership and confidentiality

The public repository contains `system_config.yml` and
`user_config.example.yml`. A real `user_config.yml` remains private because it
contains household topology, entity IDs, notification destinations, and site
data. Generated `app_cfg.yaml` or `apps.yaml` is ephemeral and shall not become
an additional editable source of truth.

## 8. Operator editing boundary

Safety Home provides an authenticated Ingress page for editing the private
`user_config.yml`. The page covers the editable root fields and the complete
`installation` registry. It never reads, returns, or writes
`system_config.yml`; packaged policy remains a reviewed source-code and release
artifact.

When the installation file does not exist, the API returns the public example
as an unsaved draft with an `absent` revision. SafetyFunctions waits while the
operator fills the editor or imports an existing version 2 YAML file. Import
validates and previews the source without persisting it. The first successful
save creates `/config/user_config.yml`; a subsequent App restart compiles and
starts SafetyFunctions.

The local configuration API accepts a complete `user_config` object together
with the revision that was read by the browser. Before replacing the file it:

1. rejects a stale revision so two browser sessions cannot silently overwrite
   one another;
2. validates the complete version 2 source model;
3. compiles the candidate together with the packaged system configuration;
4. atomically replaces `/config/user_config.yml` only after those checks pass.

Saving does not apply a partial configuration to a running SafetyFunctions
instance. The operator restarts the Home Assistant App, and the normal startup
compiler recreates `apps.yaml` before AppDaemon starts. Entity existence and
other checks requiring a live Home Assistant connection remain part of
SafetyFunctions initialization.
