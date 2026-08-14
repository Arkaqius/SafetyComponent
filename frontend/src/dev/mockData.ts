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
  'sensor.safety_app_health': entity('running', 'Safety app health', {}, 1),
  'binary_sensor.garage_gatedoorlow_contact_contact': entity('on', 'Brama garażowa', {}, 1),
  'binary_sensor.frontyard_externalgate_contact_contact': entity('off', 'Brama zewnętrzna', {}, 2),
  'binary_sensor.livingroom_door_contact_contact': entity('on', 'Drzwi tarasowe w salonie', {}, 1),
  'binary_sensor.garage_door_contact_contact': entity('off', 'Drzwi do garażu', {}, 2),
  'sensor.home_monitor_occupancy': entity('occupied', 'Obecność w domu', {}, 1),
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
        regions: ['1219'],
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
    'Safety Door: GarageGate',
    {
      description: 'Configured door open-timeout monitor.',
      door_name: 'GarageGate',
      door_state: 'open',
      source_entity: 'binary_sensor.garage_gatedoorlow_contact_contact',
      timeout_seconds: 120,
      open_duration_seconds: 185,
      remaining_seconds: 0,
      opened_at: timestamp(4),
    },
    1
  ),
  'sensor.safety_door_externalgate': entity(
    'inactive',
    'Safety Door: ExternalGate',
    {
      description: 'Configured door open-timeout monitor.',
      door_name: 'ExternalGate',
      door_state: 'closed',
      source_entity: 'binary_sensor.frontyard_externalgate_contact_contact',
      timeout_seconds: 120,
      open_duration_seconds: 0,
      remaining_seconds: 120,
      opened_at: null,
    },
    2
  ),
  'sensor.safety_door_livingroomterracedoor': entity(
    'blocked',
    'Safety Door: LivingRoomTerraceDoor',
    {
      description: 'Configured door open-timeout monitor.',
      door_name: 'LivingRoomTerraceDoor',
      door_state: 'open',
      source_entity: 'binary_sensor.livingroom_door_contact_contact',
      timeout_seconds: 120,
      open_duration_seconds: 0,
      remaining_seconds: 120,
      opened_at: null,
      condition_entity: 'sensor.home_monitor_occupancy',
      condition_state: 'occupied',
      condition_result: 'blocked',
      condition_pass_states: ['empty'],
      condition_blocked_states: ['occupied'],
    },
    1
  ),
  'sensor.safety_door_garagedoor': entity(
    'inactive',
    'Safety Door: GarageDoor',
    {
      description: 'Configured door open-timeout monitor.',
      door_name: 'GarageDoor',
      door_state: 'closed',
      source_entity: 'binary_sensor.garage_door_contact_contact',
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
  ['sensor.bedroom_climatesensor_temperature', 'Bedroom ClimateSensor temperature', 21.6, 0.001, 0, 18, 28],
  ['sensor.entrance_climatesensor_temperature', 'Entrance ClimateSensor temperature', 20.8, -0.012, -0.001, 18, 28],
  ['sensor.garage_climatesensor_temperature', 'Garage ClimateSensor temperature', 17.2, 0.008, 0, 10, 28],
  ['sensor.kidsroom_climatesensor_temperature', 'Kidsroom ClimateSensor temperature', 22.1, 0.003, 0, 18, 28],
  ['sensor.livingroom_climatesensor_temperature', 'Livingroom ClimateSensor temperature', 22.8, 0.011, 0.001, 18, 28],
  ['sensor.office_climatesensor_temperature', 'Office ClimateSensor temperature', 27.4, 0.086, 0.004, 18, 28],
  ['sensor.thermostat_hc1_current_room_temperature_2', 'Heating circuit temperature', 22.5, 0.002, 0, 18, 28],
  ['sensor.upperbathroom_climatesensor_temperature', 'Upper bathroom ClimateSensor temperature', 23.3, -0.006, 0, 18, 28],
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
      entity_id: 'sensor.office_climatesensor_temperature',
      entity_key: 'TemperatureOffice',
      friendly_name: 'Temperatura biura',
      health: 'stale',
      failed_checks: ['freshness'],
    },
  ],
});

for (const [key, sourceEntity, name, health, areaName, owner] of [
  ['temperature_office', 'sensor.office_climatesensor_temperature', 'Temperatura biura', 'stale', 'Biuro', 'TemperatureComponent'],
  [
    'safety_door_garage_gate',
    'binary_sensor.garage_gatedoorlow_contact_contact',
    'Brama garażowa',
    'healthy',
    'Garaż',
    'SafetyDoorsComponent',
  ],
  ['common_outside_temp', 'sensor.dom_temperature', 'Temperatura zewnętrzna', 'healthy', undefined, 'SafetyFunctions'],
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
