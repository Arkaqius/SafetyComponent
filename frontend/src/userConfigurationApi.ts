import { MOCK_MODE } from './config';

export type ConfigurationMap = Record<string, unknown>;

export interface UserConfigurationDocument {
  user_config: ConfigurationMap;
  revision: string;
  restart_required: boolean;
}

interface ApiErrorBody {
  error?: string;
  message?: string;
}

const CONFIG_ENDPOINT = 'api/config';
let mockDocument: UserConfigurationDocument = {
  revision: 'mock-1',
  restart_required: false,
  user_config: {
    model_version: 2,
    components_enabled: {
      TemperatureComponent: true,
      SafetyDoorsComponent: true,
      ExternalHazardComponent: true,
      EntityMonitorComponent: true,
      InternalEnvironmentalHazardMonitorComponent: true,
    },
    localization: { language: 'pl', entity_names: {} },
    notification: {
      mobile: { services: ['notify/all_phones'], default_url: '/' },
      local: {},
      wan_entity: null,
    },
    providers: {
      OpenMeteoWeatherApiComponent: { enabled: true },
      ImgwWarningsApiComponent: { enabled: true },
      OpenMeteoAirQualityApiComponent: { enabled: true },
    },
    mqtt: { legacy_discovery_entity_ids: [] },
    installation: {
      site: {
        latitude: 50,
        longitude: 20,
        timezone: 'Europe/Warsaw',
        country_code: 'PL',
        teryt_codes: ['0000'],
      },
      common_entities: { outside_temp: 'sensor.outdoor_temperature' },
      defaults: {
        temperature: { low_temperature_c: 18, high_temperature_c: 28, forecast_horizon_hours: 2 },
        safety_door: { timeout_seconds: 120 },
        external_hazard: { hazards: ['frost', 'wind', 'rain', 'storm', 'outdoor_air_pollution'] },
        entity_monitor: {},
      },
      rooms: {
        LivingRoom: {
          area_id: 'living_room',
          temperature_sensor: 'sensor.living_room_temperature',
          window: 'LivingRoomWindow',
        },
      },
      openings: {
        LivingRoomWindow: {
          area_id: 'living_room',
          entity_id: 'binary_sensor.living_room_window',
          friendly_name: 'Okno w salonie',
          kind: 'window',
          external_hazard: {},
        },
      },
      detectors: {},
      monitored_entities: {},
    },
  },
};

export async function loadUserConfiguration(): Promise<UserConfigurationDocument> {
  if (MOCK_MODE) return structuredClone(mockDocument);
  return requestConfiguration(CONFIG_ENDPOINT, { cache: 'no-store' });
}

export async function saveUserConfiguration(userConfig: ConfigurationMap, revision: string): Promise<UserConfigurationDocument> {
  if (MOCK_MODE) {
    mockDocument = {
      user_config: structuredClone(userConfig),
      revision: `mock-${Date.now()}`,
      restart_required: true,
    };
    return structuredClone(mockDocument);
  }
  return requestConfiguration(CONFIG_ENDPOINT, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_config: userConfig, revision }),
  });
}

async function requestConfiguration(url: string, init: RequestInit): Promise<UserConfigurationDocument> {
  const response = await fetch(url, init);
  const body = (await response.json().catch(() => ({}))) as UserConfigurationDocument & ApiErrorBody;
  if (!response.ok) {
    throw new Error(body.message || body.error || `Błąd API konfiguracji (${response.status})`);
  }
  if (!body.user_config || typeof body.revision !== 'string') {
    throw new Error('API zwróciło nieprawidłowy dokument konfiguracji');
  }
  return body;
}
