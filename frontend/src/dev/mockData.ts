import { type EntityMap, type EntitySnapshot } from '../domain/safety';

export const MOCK_STARTED_AT = Date.now();
const timestamp = (minutesAgo: number): string => new Date(MOCK_STARTED_AT - minutesAgo * 60_000).toISOString();

function entity(state: string, friendlyName: string, attributes: Record<string, unknown> = {}, minutesAgo = 1): EntitySnapshot {
  return {
    state,
    attributes: {
      friendly_name: friendlyName,
      ...attributes,
    },
    last_changed: timestamp(minutesAgo),
    last_updated: timestamp(minutesAgo),
  };
}

/** Deterministic entity contract used only by the local visual demo. */
export const MOCK_ENTITIES: EntityMap = {
  'sensor.notification_history': entity('3', 'Historia powiadomień', {
    version: 1,
    limit: 100,
    entries: [
      {
        id: 'demo-healed',
        tag: 'demo-temperature',
        kind: 'resolved',
        fault_state: 'CLEARED',
        level: 2,
        title: 'Zagrożenie minęło',
        message: 'Temperatura w biurze wróciła do bezpiecznego zakresu.\nLokalizacja: Biuro',
        text_truncated: false,
        created_at: timestamp(2),
        attempted_at: timestamp(2),
        attempt: 1,
        service: 'notify/safety_recipients',
        result: 'accepted_by_home_assistant',
        deadline_missed: false,
      },
      {
        id: 'demo-active',
        tag: 'demo-temperature',
        kind: 'new',
        fault_state: 'SET',
        level: 2,
        title: 'Wykryto zagrożenie',
        message: 'Temperatura w biurze wymaga uwagi.\nLokalizacja: Biuro\nZaobserwowana wartość: 29 °C',
        text_truncated: false,
        created_at: timestamp(20),
        attempted_at: timestamp(20),
        attempt: 1,
        service: 'notify/safety_recipients',
        result: 'accepted_by_home_assistant',
        deadline_missed: false,
      },
      {
        id: 'demo-failed',
        tag: 'demo-door',
        kind: 'new',
        fault_state: 'SET',
        level: 3,
        title: 'Sprawdź drzwi',
        message: 'Drzwi do garażu są otwarte zbyt długo.',
        text_truncated: false,
        created_at: timestamp(40),
        attempted_at: timestamp(39),
        attempt: 1,
        service: 'notify/safety_recipients',
        result: 'failed',
        deadline_missed: true,
      },
    ],
  }),
  'sensor.notification_delivery_health': entity('healthy', 'Stan dostarczania powiadomień', {
    acknowledged_tags: [],
  }),
  'sensor.safety_app_health': entity('running', 'Safety app health', {}, 1),
  'sensor.internal_environment_summary': entity('healthy', 'Monitoring zagrożeń wewnętrznych', {
    monitored_detectors: 2,
    active_hazards: 0,
    unavailable_detectors: 0,
    gas_switching_inhibited: false,
  }),
  'sensor.internal_environment_bathroom_flammable_gas': entity('healthy', 'Czujnik gazu w łazience', {
    area_id: 'bathroom',
    area_name: 'Łazienka',
    source_entity_id: 'binary_sensor.example_utility_gas_alarm',
    hazard: 'flammable_gas',
    gas_identity: 'flammable_gas_unspecified',
    current_state: 'off',
    classification: 'clear',
    alarm_active: false,
    health_fault_active: false,
    gas_switching_inhibited: false,
    last_observed_at: timestamp(1),
  }),
  'sensor.internal_environment_bathroom_carbon_monoxide': entity('healthy', 'Czujnik tlenku węgla w łazience', {
    area_id: 'bathroom',
    area_name: 'Łazienka',
    source_entity_id: 'binary_sensor.example_utility_co_alarm',
    hazard: 'carbon_monoxide',
    current_state: 'off',
    classification: 'clear',
    alarm_active: false,
    health_fault_active: false,
    gas_switching_inhibited: false,
    last_observed_at: timestamp(1),
  }),
  'binary_sensor.example_utility_gas_alarm': entity('off', 'Przykładowy czujnik gazu'),
  'binary_sensor.example_utility_co_alarm': entity('off', 'Przykładowy czujnik CO'),
  'binary_sensor.example_garage_gate': entity('on', 'Przykładowa brama garażowa', {}, 1),
  'binary_sensor.example_driveway_gate': entity('off', 'Przykładowa brama wjazdowa', {}, 2),
  'binary_sensor.example_patio_door': entity('on', 'Przykładowe drzwi tarasowe', {}, 1),
  'binary_sensor.example_garage_door': entity('off', 'Przykładowe drzwi garażowe', {}, 2),
  'sensor.example_occupancy': entity('occupied', 'Przykładowa obecność', {}, 1),
  'sensor.safetysystem_state': entity(
    'hazard',
    'Stan systemu bezpieczeństwa',
    {
      fault_count: 1,
      highest_fault_level: 2,
      state_label: 'Zagrożenie',
    },
    3
  ),
  'sensor.external_hazard_state': entity(
    'warning',
    'Zagrożenia zewnętrzne',
    {
      active_hazards: ['niebezpieczny wiatr'],
      affected_openings: ['Brama garażowa'],
      providers: {
        OpenMeteoWeatherApiComponent: 'ok',
        ImgwWarningsApiComponent: 'ok',
        OpenMeteoAirQualityApiComponent: 'ok',
      },
      enabled_providers: ['OpenMeteoWeatherApiComponent', 'ImgwWarningsApiComponent', 'OpenMeteoAirQualityApiComponent'],
      advice_inhibition: [
        {
          reason: 'wind',
          source: 'OpenMeteoWeatherApiComponent',
          valid_until: timestamp(-120),
        },
      ],
      last_evaluated_at: timestamp(0),
      actuation_mode: 'manual_and_user_confirmed',
      active_symptom_count: 1,
    },
    0
  ),
  'sensor.external_provider_open_meteo_weather': entity('ok', 'Dane pogodowe Open-Meteo', {
    provider: 'OpenMeteoWeatherApiComponent',
    last_attempt_at: timestamp(0),
    last_success_at: timestamp(0),
    consecutive_failures: 0,
    detail_code: null,
    observation_count: 4,
    observations: [
      { id: 'weather-frost', hazard_type: 'frost', provider_level: 'safe', observed_at: timestamp(0), valid_to: timestamp(-60) },
      { id: 'weather-wind', hazard_type: 'wind', provider_level: 'warning', observed_at: timestamp(0), valid_to: timestamp(-60) },
      { id: 'weather-rain', hazard_type: 'rain', provider_level: 'safe', observed_at: timestamp(0), valid_to: timestamp(-60) },
      { id: 'weather-storm', hazard_type: 'storm', provider_level: 'safe', observed_at: timestamp(0), valid_to: timestamp(-60) },
    ],
  }),
  'sensor.external_provider_imgw_warnings': entity('ok', 'Ostrzeżenia IMGW', {
    provider: 'ImgwWarningsApiComponent',
    last_attempt_at: timestamp(1),
    last_success_at: timestamp(1),
    consecutive_failures: 0,
    detail_code: null,
    observation_count: 1,
    observations: [
      {
        id: 'imgw-local-storm',
        hazard_type: 'official_warning',
        provider_level: '2',
        observed_at: timestamp(1),
        valid_to: timestamp(-180),
      },
    ],
    warning_count: 1,
    warnings: [
      {
        id: 'imgw-local-storm',
        event_name: 'Burze',
        degree: '2',
        probability: '80',
        valid_from: timestamp(30),
        valid_to: timestamp(-180),
        published_at: timestamp(10),
        regions: ['0000'],
        content: 'Prognozowane są burze, którym miejscami będą towarzyszyć silne opady deszczu.',
        comment: '',
        office: 'IMGW-PIB',
        locally_applicable: true,
      },
    ],
  }),
  'sensor.external_provider_open_meteo_air_quality': entity('ok', 'Jakość powietrza Open-Meteo', {
    provider: 'OpenMeteoAirQualityApiComponent',
    last_attempt_at: timestamp(4),
    last_success_at: timestamp(4),
    consecutive_failures: 0,
    detail_code: null,
    observation_count: 1,
    observations: [
      {
        id: 'open-meteo-air-quality',
        hazard_type: 'outdoor_air_pollution',
        provider_level: 'safe',
        observed_at: timestamp(4),
        valid_to: timestamp(-60),
        display_value: '31',
        display_unit: '',
      },
    ],
  }),
  'sensor.fault_riskytemperature': entity(
    'Set',
    'Fault: Risky temperature',
    {
      description: 'Temperatura przekroczyła bezpieczny zakres.',
      level: 'level_2',
      location: 'Office',
      notification_tag: 'demo-active-temperature',
    },
    4
  ),
  'sensor.fault_riskytemperatureforecast': entity(
    'Shadowed',
    'Fault: Risky temperature forecast',
    {
      description: 'Trend temperatury wskazuje na możliwe przekroczenie zakresu.',
      level: 'level_3',
      location: 'Office, Livingroom',
    },
    7
  ),
  'sensor.recovery_manipulatewindowbedroom': entity('DO_NOT_PERFORM', 'Recovery ManipulateWindowBedroom', {}, 22),
  'sensor.recovery_manipulatewindowentrance': entity('DO_NOT_PERFORM', 'Recovery ManipulateWindowEntrance', {}, 23),
  'sensor.recovery_manipulatewindowgarage': entity('DO_NOT_PERFORM', 'Recovery ManipulateWindowGarage', {}, 24),
  'sensor.recovery_manipulatewindowkidsroom': entity('DO_NOT_PERFORM', 'Recovery ManipulateWindowKidsroom', {}, 25),
  'sensor.recovery_manipulatewindowkitchen': entity('DO_NOT_PERFORM', 'Recovery ManipulateWindowKitchen', {}, 26),
  'sensor.recovery_manipulatewindowlivingroom': entity('DO_NOT_PERFORM', 'Recovery ManipulateWindowLivingroom', {}, 27),
  'sensor.recovery_manipulatewindowoffice': entity(
    'TO_PERFORM',
    'Recovery ManipulateWindowOffice',
    {
      description: 'Sprawdź źródło ciepła i przewietrz pomieszczenie.',
    },
    5
  ),
  'sensor.recovery_manipulatewindowupperbathroom': entity('DO_NOT_PERFORM', 'Recovery ManipulateWindowUpperbathroom', {}, 29),
  'sensor.safety_door_garagegate': entity(
    'active',
    'Safety Door: ExampleGarageGate',
    {
      description: 'Configured door open-timeout monitor.',
      door_name: 'ExampleGarageGate',
      door_state: 'open',
      source_entity: 'binary_sensor.example_garage_gate',
      timeout_seconds: 120,
      open_duration_seconds: 185,
      remaining_seconds: 0,
      opened_at: timestamp(4),
    },
    1
  ),
  'sensor.safety_door_externalgate': entity(
    'inactive',
    'Safety Door: ExampleDrivewayGate',
    {
      description: 'Configured door open-timeout monitor.',
      door_name: 'ExampleDrivewayGate',
      door_state: 'closed',
      source_entity: 'binary_sensor.example_driveway_gate',
      timeout_seconds: 120,
      open_duration_seconds: 0,
      remaining_seconds: 120,
      opened_at: null,
    },
    2
  ),
  'sensor.safety_door_livingroomterracedoor': entity(
    'blocked',
    'Safety Door: ExamplePatioDoor',
    {
      description: 'Configured door open-timeout monitor.',
      door_name: 'ExamplePatioDoor',
      door_state: 'open',
      source_entity: 'binary_sensor.example_patio_door',
      timeout_seconds: 120,
      open_duration_seconds: 0,
      remaining_seconds: 120,
      opened_at: null,
      condition_entity: 'sensor.example_occupancy',
      condition_state: 'occupied',
      condition_result: 'blocked',
      condition_pass_states: ['empty'],
      condition_blocked_states: ['occupied'],
    },
    1
  ),
  'sensor.safety_door_garagedoor': entity(
    'inactive',
    'Safety Door: ExampleGarageDoor',
    {
      description: 'Configured door open-timeout monitor.',
      door_name: 'ExampleGarageDoor',
      door_state: 'closed',
      source_entity: 'binary_sensor.example_garage_door',
      timeout_seconds: 120,
      open_duration_seconds: 0,
      remaining_seconds: 120,
      opened_at: null,
    },
    2
  ),
};

const temperatureSpecs: Array<
  [entityId: string, friendlyName: string, value: number, rate: number, acceleration: number, lowThreshold: number, highThreshold: number]
> = [
  ['sensor.example_bedroom_temperature', 'Example bedroom temperature', 21.6, 0.001, 0, 18, 28],
  ['sensor.example_entry_temperature', 'Example entry temperature', 20.8, -0.012, -0.001, 18, 28],
  ['sensor.example_garage_temperature', 'Example garage temperature', 17.2, 0.008, 0, 10, 28],
  ['sensor.example_guest_room_temperature', 'Example guest-room temperature', 22.1, 0.003, 0, 18, 28],
  ['sensor.example_living_room_temperature', 'Example living-room temperature', 22.8, 0.011, 0.001, 18, 28],
  ['sensor.example_office_temperature', 'Example office temperature', 27.4, 0.086, 0.004, 18, 28],
  ['sensor.example_heating_temperature', 'Example heating-circuit temperature', 22.5, 0.002, 0, 18, 28],
  ['sensor.example_utility_temperature', 'Example utility-room temperature', 23.3, -0.006, 0, 18, 28],
];

for (const [entityId, friendlyName, value, rate, acceleration, lowThreshold, highThreshold] of temperatureSpecs) {
  MOCK_ENTITIES[entityId] = entity(String(value), friendlyName, {
    device_class: 'temperature',
    state_class: 'measurement',
    unit_of_measurement: '°C',
  });
  MOCK_ENTITIES[`${entityId}_rate`] = entity(String(rate), `${friendlyName} rate`, {
    attribution: 'Data provided by SafetyFunction',
    unit_of_measurement: '°C/min',
  });
  MOCK_ENTITIES[`${entityId}_rateofrate`] = entity(String(acceleration), `${friendlyName} rate of rate`, {
    attribution: 'Data provided by SafetyFunction',
    unit_of_measurement: '°C/min²',
  });
  MOCK_ENTITIES[`${entityId}_low_threshold`] = entity(String(lowThreshold), `${friendlyName} low threshold`, {
    source_entity: entityId,
    threshold_type: 'low',
    unit_of_measurement: '°C',
  });
  MOCK_ENTITIES[`${entityId}_high_threshold`] = entity(String(highThreshold), `${friendlyName} high threshold`, {
    source_entity: entityId,
    threshold_type: 'high',
    unit_of_measurement: '°C',
  });
}

MOCK_ENTITIES['sensor.entity_monitor_summary'] = entity('stale', 'Monitorowane encje', {
  total: 3,
  healthy: 2,
  degraded: 0,
  stale: 1,
  unavailable: 0,
  unhealthy_entities: [
    {
      entity_id: 'sensor.example_office_temperature',
      entity_key: 'TemperatureOffice',
      friendly_name: 'Temperatura biura',
      health: 'stale',
      failed_checks: ['freshness'],
    },
  ],
});

for (const [key, sourceEntity, name, health, areaName, owner] of [
  ['temperature_office', 'sensor.example_office_temperature', 'Temperatura biura', 'stale', 'Biuro', 'TemperatureComponent'],
  ['safety_door_garage_gate', 'binary_sensor.example_garage_gate', 'Brama garażowa', 'healthy', 'Garaż', 'SafetyDoorsComponent'],
  ['common_outside_temp', 'sensor.example_outdoor_temperature', 'Temperatura zewnętrzna', 'healthy', undefined, 'SafetyFunctions'],
] as const) {
  const source = MOCK_ENTITIES[sourceEntity] ?? entity('7.2', name);
  MOCK_ENTITIES[sourceEntity] = source;
  MOCK_ENTITIES[`sensor.entity_health_${key}`] = entity(health, name, {
    entity_id: sourceEntity,
    entity_key: key,
    friendly_name: name,
    current_state: source.state,
    source_groups: ['component'],
    owners: [owner],
    purposes: ['Źródło danych funkcji bezpieczeństwa'],
    fault_owner: 'entity_monitor',
    fault_name: `EntityHealth${key}`,
    area_name: areaName,
    last_changed: source.last_changed,
    last_updated: source.last_updated,
    failure_debounce_seconds: 15,
    recovery_debounce_seconds: 60,
    checks: [
      {
        check: 'availability',
        result: 'passed',
        reason: 'entity_available',
        observed_value: source.state,
        evaluated_at: timestamp(0),
        calibration: {},
      },
      ...(health === 'stale'
        ? [
            {
              check: 'freshness',
              result: 'failed',
              reason: 'freshness_expired',
              observed_value: 3720,
              evaluated_at: timestamp(0),
              calibration: { timestamp_source: 'last_updated', max_silence_seconds: 3600 },
            },
          ]
        : []),
    ],
  });
}
