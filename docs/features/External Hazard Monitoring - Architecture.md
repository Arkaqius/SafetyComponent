# External Hazard Monitoring - Feature Architecture

**Safety component:** `ExternalHazardComponent`

**System component ID:** `C-EXT`

## 1. Decisions already fixed

The following decisions are requirements, not open design options:

1. The monitored radiation type is **ionizing radiation**, not UV or solar
   irradiance.
2. The feature monitors, diagnoses, and warns. It shall not close a window or
   door, operate a gate, lock anything, change HVAC, or control ventilation.
3. Every external API has a separate API Component with its own configuration,
   schema validation, polling lifecycle, cache, health, and tests.
4. Provider-specific code does not create Safety System symptoms or faults.
   Household safety policy belongs to `ExternalHazardComponent`.
5. Raw radiation measurements and official radiological messages are different
   input classes and shall never be presented as equivalent.

## 2. Goals

The system shall:

- monitor frost, wind/gusts, rain/storm, outdoor air pollution, and ionizing
  radiation from external data sources;
- monitor configured Home Assistant window and external-door contacts;
- detect when an active external hazard is relevant to an open aperture;
- warn with friendly area/opening names, source, value, validity, freshness,
  and a manual recommendation;
- warn about an official ionizing-radiation event even when all apertures are
  closed;
- expose independent health for every external provider;
- preserve multiple simultaneous hazards and openings in one fault context;
- inhibit contradictory manual recommendations to open windows while external
  conditions make that advice unsafe;
- provide deterministic evidence suitable for unit and integration tests.

## 3. Out of scope

- Automatic closure or locking.
- Ventilation, HVAC, blind, purifier, siren, or gate control.
- Radiation shielding or dosimetry advice.
- Medical interpretation of radiation or air-quality exposure.
- Treating forecast model output as a local physical sensor.
- Treating a single raw radiation station threshold crossing as a confirmed
  radiological emergency.
- Scraping human-facing HTML as if it were a supported API contract.
- Combining all providers into one large client class.

## 4. Source strategy

| API Component | Provider/API | Purpose | Polling interval | Authority |
| --- | --- | --- | --- | --- |
| `OpenMeteoWeatherApiComponent` | Open-Meteo `/v1/forecast` | Current/model temperature, frost forecast, precipitation, weather code, wind and gusts | 10 min | Forecast/model input |
| `ImgwWarningsApiComponent` | IMGW `/api/data/warningsmeteo` | Official Polish weather warnings filtered by TERYT | 5 min | Authoritative weather warning |
| `GiosAirQualityApiComponent` | GIOŚ PJP API v1 | Nearest/configured station measurements and Polish AQ information | 15 min | Authoritative measurement source |
| `OpenMeteoAirQualityApiComponent` | Open-Meteo `/v1/air-quality` | CAMS forecast, European AQI and pollutant forecast | 30 min | Forecast/model input |
| `PaaRadiationApiComponent` | Official PAA radiation monitoring API | Official status/messages and station dose-rate data | 5 min | Authoritative only for official PAA status/messages |

Provider references:

- Open-Meteo weather: <https://open-meteo.com/en/docs>
- Open-Meteo air quality: <https://open-meteo.com/en/docs/air-quality-api>
- Open-Meteo non-commercial terms: <https://open-meteo.com/en/terms>
- IMGW current warnings JSON:
  <https://danepubliczne.imgw.pl/api/data/warningsmeteo>
- IMGW public-data terms:
  <https://danepubliczne.imgw.pl/pl/datastore?product=Mapa+synoptyczna>
- GIOŚ Swagger: <https://api.gios.gov.pl/pjp-api/swagger-ui/index.html>
- PAA official radiation map information:
  <https://www.gov.pl/web/paa/nowa-mapa-radiacyjna-polski-panstwowej-agencji-atomistyki>

### 4.1 PAA radiation data contract

`PaaRadiationApiComponent` shall consume the official PAA machine-readable
radiation source. The provider contract shall identify endpoint ownership,
payload schema, timestamps, update cadence, units, message validity and
withdrawal semantics. The component shall preserve official authority messages
and station dose-rate measurements as distinct result types.

If another radiation provider is added, it shall use a separate API Component
instead of provider-conditional code inside `PaaRadiationApiComponent`.

## 5. Logical architecture

```text
                    External API worker boundary

 OpenMeteoWeatherApiComponent ----+
 ImgwWarningsApiComponent --------+
 GiosAirQualityApiComponent ------+--> ExternalApiRuntime
 OpenMeteoAirQualityApiComponent -+      - bounded worker pool
 PaaRadiationApiComponent --------+      - one in-flight call/provider
                                         - result queue
                                         - serialized dispatch
                                                   |
                         external_observation / external_provider_health
                                                   |
                                                   v
 Home Assistant contacts ------------> ExternalHazardComponent (C-EXT)
                                       - validates freshness/validity
                                       - applies household policy
                                       - correlates openings
                                       - aggregates hazard context
                                       - maintains advice inhibition
                                                   |
                                                   | symptom events
                                                   v
 EventBus --> FaultManager --> NotificationManager --> HA/MQTT notification
                   |
                   +--> MQTT fault/system state and evidence

 C-EXT has no edge to RecoveryManager actuator execution.
```

## 6. Code placement

Target code structure:

```text
backend/components/external_apis/
  __init__.py
  core/
    __init__.py
    api_component.py
    api_runtime.py
    http_json_client.py
    models.py
    registry.py
  open_meteo_weather/
    __init__.py
    component.py
    schema.py
  imgw_warnings/
    __init__.py
    component.py
    schema.py
  gios_air_quality/
    __init__.py
    component.py
    schema.py
  open_meteo_air_quality/
    __init__.py
    component.py
    schema.py
  paa_radiation/
    __init__.py
    component.py
    schema.py

backend/components/safetycomponents/external_hazard/
  __init__.py
  external_hazard_component.py
  policy.py
  schema.py
```

Tests mirror this structure under `backend/tests/` and store sanitized provider
payloads under `backend/tests/fixtures/external_apis/<provider>/`.

### 6.1 Integration changes to the current application core

`SafetyFunctions` will retain the current Safety Component registry and add a
separate API Component registry:

- `self.api_modules` stores API Component instances;
- `self.sm_modules` continues to store only Safety Components;
- `user_config.api_components` is validated independently from
  `user_config.safety_components`;
- the EventBus is the only provider-to-C-EXT data path, so the existing
  four-argument `SafetyComponent` constructor does not need provider-specific
  dependencies;
- explicit imports register each API Component in the API registry, matching the
  existing Safety Component registration pattern;
- `SafetyFunctions.terminate()` stops the external runtime before publishing
  application availability offline.

`AppCfgValidator` will add schemas for `user_config.site`,
`user_config.api_components`, and `ExternalHazardComponent`. Its entity and area
collection will include every configured opening. Enabling C-EXT while a
required API Component or site field is absent is a startup configuration error.

## 7. Component roles

### 7.1 `ExternalApiComponent`

This is a protocol/base contract for remote API adapters. It is deliberately
not a subclass of `SafetyComponent`.

Required operations:

```python
class ExternalApiComponent(Protocol):
    component_name: str

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def request_poll(self) -> None: ...
    def normalize(self, payload: object, retrieved_at: datetime) -> ApiResult: ...
```

Each implementation owns:

- endpoint paths and provider query parameters;
- exact response schema and provider enum mapping;
- provider-specific time parsing and original units;
- location/station/TERYT selection appropriate to that provider;
- its last valid normalized result;
- last attempt/success and consecutive failure count;
- schema error, stale, and unavailable state;
- provider contract fixtures.

It does not own:

- household thresholds;
- Home Assistant opening states;
- fault severity;
- notification wording;
- cross-provider conflict resolution;
- recovery or actuation.

### 7.2 `ExternalApiRuntime`

Direct network calls shall not execute on the Safety System decision callback.
The runtime provides:

- an explicit bounded worker pool sized so one stalled provider cannot starve
  the other enabled providers;
- at most one in-flight request per provider;
- request timeout and response-size limits;
- a thread-safe result queue;
- a short AppDaemon timer that drains results and publishes EventBus events from
  the serialized application context;
- cancellation/no-resubmit behavior during shutdown;
- no polling from constructors.

The shared runtime and HTTP transport are infrastructure, not a combined API
component. Provider caches, schedules, schemas, and health remain independent.

### 7.3 `OpenMeteoWeatherApiComponent`

Requested fields shall be limited to those used by policy:

- current: `temperature_2m`, `apparent_temperature`, `precipitation`, `rain`,
  `weather_code`, `wind_speed_10m`, `wind_gusts_10m`;
- hourly for at least 12 hours: temperature, precipitation probability,
  precipitation/rain, weather code, wind speed, and gusts;
- timezone and coordinates shall be explicit.

It emits model values and validity timestamps. It shall never use words such as
"local sensor detected" for these values.

### 7.4 `ImgwWarningsApiComponent`

The IMGW component maps:

- `id` -> stable provider observation ID;
- `nazwa_zdarzenia` -> normalized hazard type while preserving original text;
- `stopien` -> provider warning degree, not directly a Safety System level;
- `prawdopodobienstwo` -> provider probability;
- `obowiazuje_od`, `obowiazuje_do`, `opublikowano` -> source times;
- `teryt` -> applicable configured administrative areas;
- `tresc`, `komentarz`, `biuro` -> sanitized authority context.

Warnings not matching configured TERYT codes are discarded before dispatch.
An updated warning with the same ID replaces the previous provider observation.

### 7.5 `GiosAirQualityApiComponent`

The GIOŚ component shall use only the current versioned API contract. It owns
station discovery/selection and sensor IDs. It returns station measurements and
named GIOŚ index information without translating them into Open-Meteo/European
AQI semantics.

Selection policy:

1. Prefer explicitly configured station IDs.
2. Otherwise select the nearest station that supplies required pollutants.
3. Expose distance and missing pollutants.
4. Never silently switch station without publishing the new station ID.

### 7.6 `OpenMeteoAirQualityApiComponent`

This component returns CAMS model/forecast values separately from GIOŚ
measurements. Initial fields:

- `european_aqi` and contributing sub-indices;
- PM2.5, PM10, NO2, O3, and SO2;
- current/model value plus at least 12 hours of forecast;
- grid coordinates, model/source time, validity, and retrieval time.

The component does not decide whether forecast or station measurement wins.

### 7.7 `PaaRadiationApiComponent`

The component shall preserve two result types:

- `official_message`: authority status/message with publication and validity;
- `dose_rate_measurement`: station value, station ID/location, timestamp, and
  original unit.

Unit normalization shall support nSv/h and µSv/h. The component shall not embed
a universal emergency threshold. It shall mark official confirmation only when
the source contract explicitly identifies an official authority status/message.

### 7.8 `ExternalHazardComponent`

`ExternalHazardComponent` is registered through the existing Safety Component
registry and integrates with `EventBus`, `FaultManager`, `NotificationManager`,
`MqttEntityManager`, and Home Assistant state listeners.

It owns:

- the latest valid normalized observation set;
- provider validity and capability availability;
- configurable hazard thresholds and hysteresis;
- contact state and area/friendly-name resolution;
- cross-provider evaluation;
- prefault and fault context;
- notification context and manual recommended action;
- an advice-inhibition snapshot used by recovery/advisory presentation.

It does not perform HTTP or parse provider payloads.

## 8. Normalized data model

Provider output uses immutable typed objects. Suggested minimum model:

```python
@dataclass(frozen=True)
class ExternalObservation:
    provider: str
    observation_id: str
    hazard_type: HazardType
    provider_level: str | None
    values: Mapping[str, Measurement]
    observed_at: datetime | None
    valid_from: datetime
    valid_to: datetime
    retrieved_at: datetime
    region_codes: tuple[str, ...]
    confidence: float | None
    authority_confirmed: bool
    source_reference: str

@dataclass(frozen=True)
class ProviderHealth:
    provider: str
    state: ProviderHealthState  # ok/stale/unavailable/schema_error
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    consecutive_failures: int
    detail_code: str | None
```

All datetimes are timezone-aware UTC internally. Original source strings may be
retained only in diagnostic/evidence context.

## 9. Decision model

The Safety Component evaluates external hazard state separately from household
exposure.

Cloud timing is measured from receipt of a usable, source-dated input. The
system does not claim that a 5- or 10-minute polling service detects a physical event
within 120 seconds of its occurrence. The 120-second decision goal begins when
the applicable normalized observation is delivered to C-EXT. Achieving a true
physical-event FTTI of 120 seconds would require a reviewed local rain/wind or
other direct sensor path.

| Hazard | Hazard evidence | Exposure condition | System response |
| --- | --- | --- | --- |
| Frost | Current or forecast external temperature crosses configured policy | Relevant opening is open | Warn with opening and temperature/forecast context |
| Wind | Gust threshold or applicable IMGW warning | Relevant opening is open | Warn with opening, gust or warning degree |
| Rain/storm | Precipitation policy or applicable IMGW warning | Relevant opening is open | Warn with opening and validity/source |
| Outdoor pollution | Configured measured/forecast AQ policy | Relevant opening is open | Warn and inhibit advice to open external openings |
| Official radiation event | PAA official status/message | None; applies to household | L2 warning, official guidance, list open apertures as context |
| Radiation measurement anomaly | Baseline/persistence/corroboration policy | None | Separate unconfirmed L3 warning; never official-alert wording |

### 9.1 Multiple providers

- IMGW warning validity is authoritative for the warning itself.
- Open-Meteo weather supplies point-model detail and forecast but does not
  replace an IMGW warning.
- GIOŚ station measurement and Open-Meteo AQ forecast are shown separately.
- Conservative AQ policy may warn if either a fresh current measurement or a
  configured high-confidence forecast exceeds policy.
- Disagreement is evidence, not a parser error; both inputs remain visible.
- Individual provider failure degrades only capabilities that require it.

### 9.2 Clearing

An active condition clears only when one of these is true:

- the affected opening is positively observed closed and the clear delay passes;
- a provider observation reaches its authoritative expiry/withdrawal and no
  other valid observation sustains the condition;
- fresh valid evidence remains below the policy threshold for the configured
  hysteresis/clear period.

Timeout, HTTP failure, parse failure, and stale data do not constitute clearing
evidence.

## 10. Fault and notification model

Stable technical faults:

| Fault ID | Default level | Trigger |
| --- | --- | --- |
| `ExternalWeatherExposure` | 2 or 3 by reviewed policy | One or more open apertures exposed to rain/storm/frost/wind |
| `OutdoorAirQualityExposure` | 3 | One or more open apertures during unacceptable outdoor AQ |
| `IonizingRadiationAlert` | 2 | Official PAA radiological warning/status |
| `RadiationDataAnomaly` | 3 | Optional corroborated raw measurement anomaly, explicitly unconfirmed |
| `ExternalHazardDataUnavailable` | 3 | All required providers for an enabled capability stale/unavailable |

`FaultManager` aggregates all active symptoms. Same-tag notifications are
refreshed as hazards or openings change. User-facing content uses Home Assistant
friendly names and resolved area names; entity IDs remain diagnostic attributes.

Required notification context:

- friendly hazard label;
- confirmed/unconfirmed label for radiation;
- affected opening and area names where applicable;
- observed or forecast values and units;
- threshold or authority warning degree;
- source and publication/sample time;
- validity and freshness;
- manual recommendation;
- authoritative link/reference for radiation.

No notification action button may call an actuator service.

## 11. Advice conflict handling

Temperature or indoor-AQ logic can recommend opening windows.
That recommendation is unsafe during outdoor pollution, damaging wind, storm,
or a radiological sheltering instruction.

Implementation shall introduce a narrow `RecoveryPolicyEvaluator` interface.
`ExternalHazardComponent` provides an evaluator snapshot such as:

```text
inhibited_action: open_external_opening
reason: outdoor_air_pollution
valid_until: 2026-08-03T18:00:00Z
source: GIOS/OpenMeteoAirQuality
```

`RecoveryManager` consults registered evaluators before showing manual advice
or executing an action. This filters contradictory advice; C-EXT itself
registers no executable recovery actions.

## 12. Configuration architecture

Global policy and per-home binding remain separate.

```yaml
app_config:
  external_hazard_policy:
    notification_only: true
    weather:
      frost_watch_c: 2.0
      frost_warning_c: 0.0
      gust_watch_m_s: 15.0
      gust_warning_m_s: 20.0
    outdoor_air_quality:
      standard: european_aqi
      warning_at: 60
      conservative_source_policy: any_fresh_source
    radiation:
      official_alert_required_for_confirmed_fault: true
      raw_anomaly_enabled: false

user_config:
  site:
    latitude: 00.0000
    longitude: 00.0000
    timezone: Europe/Warsaw
    teryt_codes:
      - "0000"

  api_components:
    OpenMeteoWeatherApiComponent:
      enabled: true
      poll_interval_seconds: 600
    ImgwWarningsApiComponent:
      enabled: true
      poll_interval_seconds: 300
    GiosAirQualityApiComponent:
      enabled: true
      station_ids: []
      poll_interval_seconds: 900
    OpenMeteoAirQualityApiComponent:
      enabled: true
      poll_interval_seconds: 1800
    PaaRadiationApiComponent:
      enabled: true
      poll_interval_seconds: 300

  safety_components:
    ExternalHazardComponent:
      openings:
        OfficeWindow:
          area_id: office
          entity_id: binary_sensor.office_window_contact_contact
          kind: window
          hazards: [frost, wind, rain, storm, outdoor_air_pollution]
```

Base URLs, request timeouts, retry ceilings, and stale defaults belong to global
application policy unless an approved test environment overrides them. Entity
IDs, location, TERYT codes, and selected stations are installation-specific.

## 13. Startup and shutdown sequence

1. Validate global policy, site, every API Component schema, and every opening.
2. Resolve all `area_id` values and validate Home Assistant entities.
3. Instantiate API Components without network activity.
4. Instantiate C-EXT and collect its symptom definitions.
5. Create FaultManager, NotificationManager, and diagnostics.
6. Subscribe EventBus handlers in deterministic order.
7. Register MQTT provider and aggregate hazard entities.
8. Start the external runtime and submit an immediate poll for each enabled
   provider.
9. Start periodic provider schedules only after the immediate poll is accepted.
10. On shutdown, stop new submissions, cancel queued work, drain/discard results
    safely, cancel timers/listeners, and publish provider availability offline.

No provider may perform a request during schema validation or construction.

## 14. Reliability and security

- TLS verification is mandatory.
- Base URLs are configuration-validated against approved HTTPS hosts.
- Redirects to unapproved hosts are rejected.
- Response bytes, JSON depth, list length, and string length are bounded.
- Remote text is data: it is sanitized and never evaluated as HTML, Jinja, YAML,
  Python, or a Home Assistant service name.
- HTTP 429/5xx uses bounded backoff without changing hazard state to clear.
- Provider credentials use platform secrets and are
  excluded from logs/evidence.
- Every provider has one in-flight call maximum.
- A slow provider cannot exhaust all workers.
- The app publishes provider health even when hazard evaluation is unavailable.
- Free APIs are treated as best-effort inputs with no assumed uptime SLA.

## 15. Test architecture

### 15.1 API contract tests

Each API Component requires fixtures for:

- normal data;
- empty/no-warning response;
- multiple simultaneous warnings or stations;
- duplicate and updated IDs;
- stale timestamps;
- missing required fields/units;
- unknown enum/event values;
- malformed JSON and oversized response;
- provider withdrawal/expiry;
- HTTP timeout, 429, 4xx, and 5xx.

### 15.2 Safety-policy tests

- Hazard active + opening open -> symptom set.
- Hazard active + opening closed -> no exposure symptom.
- One of several openings closes -> fault remains with reduced context.
- Forecast is labeled forecast.
- IMGW warning outside configured TERYT -> ignored.
- GIOŚ measurement/Open-Meteo forecast disagreement -> configured policy and
  both sources visible.
- Official radiation message -> confirmed L2 warning regardless of contacts.
- Raw radiation anomaly -> never `IonizingRadiationAlert`.
- Provider timeout while fault active -> fault is not cleared.
- External pollution -> open-window advice inhibited.
- Every external-hazard scenario -> zero actuator service calls.

### 15.3 Integration tests

- API Components schedule independently.
- A stalled provider does not block another provider or HA state listeners.
- Results are dispatched serially through EventBus.
- Fault aggregation and same-tag notification refresh preserve all active
  hazards/openings.
- Provider health and aggregate hazard MQTT entities publish correct freshness.
- Startup immediate polls occur only after manager/event wiring.
- Shutdown leaves no active polling timer or worker submission.

## 16. Implementation sequence

1. Common immutable models, provider registry, runtime, and HTTP transport.
2. `OpenMeteoWeatherApiComponent` plus contract tests.
3. `ImgwWarningsApiComponent` plus TERYT tests.
4. `GiosAirQualityApiComponent` plus station-selection tests.
5. `OpenMeteoAirQualityApiComponent` plus forecast tests.
6. `ExternalHazardComponent` weather/AQ decision logic and contact correlation.
7. Faults, MQTT diagnostics, localized notification context, and advice guard.
8. Full negative-actuation and failure-injection suite.
9. `PaaRadiationApiComponent`, radiation policy, and radiation-specific contract
   tests.

## 17. Required project configuration

The following values shall be defined for the target installation:

1. The windows and external doors belonging to the opening registry.
2. Frost, gust, AQI, hysteresis, freshness, and stale thresholds.
3. The air-quality disagreement policy.
4. Default fault notification levels.
5. Provider station identifiers and regional codes where required.
6. The notification-only boundary: no actuator calls under any condition.
