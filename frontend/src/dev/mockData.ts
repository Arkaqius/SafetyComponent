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
  'sensor.safetysystem_state': entity(
    '2',
    'SafetySystem state',
    {
      fault_count: 1,
      highest_fault_level: 2,
    },
    3
  ),
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
    'inactive',
    'Safety Door: LivingRoomTerraceDoor',
    {
      description: 'Configured door open-timeout monitor.',
      door_name: 'LivingRoomTerraceDoor',
      door_state: 'open',
      source_entity: 'binary_sensor.livingroom_door_contact_contact',
      timeout_seconds: 120,
      open_duration_seconds: 35,
      remaining_seconds: 85,
      opened_at: timestamp(0.6),
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

const temperatureSpecs: Array<[entityId: string, friendlyName: string, value: number, rate: number, acceleration: number]> = [
  ['sensor.bedroom_climatesensor_temperature', 'Bedroom ClimateSensor temperature', 21.6, 0.001, 0],
  ['sensor.entrance_climatesensor_temperature', 'Entrance ClimateSensor temperature', 20.8, -0.012, -0.001],
  ['sensor.garage_climatesensor_temperature', 'Garage ClimateSensor temperature', 17.2, 0.008, 0],
  ['sensor.kidsroom_climatesensor_temperature', 'Kidsroom ClimateSensor temperature', 22.1, 0.003, 0],
  ['sensor.livingroom_climatesensor_temperature', 'Livingroom ClimateSensor temperature', 22.8, 0.011, 0.001],
  ['sensor.office_climatesensor_temperature', 'Office ClimateSensor temperature', 27.4, 0.086, 0.004],
  ['sensor.thermostat_hc1_current_room_temperature_2', 'Heating circuit temperature', 22.5, 0.002, 0],
  ['sensor.upperbathroom_climatesensor_temperature', 'Upper bathroom ClimateSensor temperature', 23.3, -0.006, 0],
];

for (const [entityId, friendlyName, value, rate, acceleration] of temperatureSpecs) {
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
}
