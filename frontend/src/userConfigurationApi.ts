import { MOCK_MODE } from './config';

export type ConfigurationMap = Record<string, unknown>;

export interface UserConfigurationDocument {
  user_config: ConfigurationMap;
  system_defaults?: ConfigurationMap;
  revision: string;
  restart_required: boolean;
  setup_required: boolean;
  validation_error?: string | null;
}

interface ApiErrorBody {
  error?: string;
  message?: string;
}

const CONFIG_ENDPOINT = 'api/config';
let mockDocument: UserConfigurationDocument = {
  revision: 'absent',
  restart_required: false,
  setup_required: true,
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
        timezone: 'Europe/Warsaw',
        country_code: 'PL',
        teryt_codes: ['0000'],
      },
      common_entities: { outside_temp: 'sensor.outdoor_temperature' },
      component_settings: {
        temperature: {},
        safety_door: {},
        external_hazard: {},
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
  system_defaults: {
    temperature: { default_low_temperature_c: 18, default_high_temperature_c: 28 },
    safety_door: { default_timeout_seconds: 120 },
    entity_monitor: { default_startup_grace_seconds: 60, default_evaluation_interval_seconds: 5 },
    external_hazard: {
      weather: {
        default_frost_watch_c: 2,
        default_frost_warning_c: 0,
        default_gust_watch_m_s: 15,
        default_gust_warning_m_s: 20,
        default_precipitation_warning_mm_h: 2.5,
        default_persistence_seconds: 120,
      },
      outdoor_air_quality: { default_warning_at: 60 },
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
      system_defaults: mockDocument.system_defaults,
      revision: `mock-${Date.now()}`,
      restart_required: true,
      setup_required: false,
    };
    return structuredClone(mockDocument);
  }
  return requestConfiguration(CONFIG_ENDPOINT, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_config: userConfig, revision }),
  });
}

export async function importUserConfiguration(source: string): Promise<ConfigurationMap> {
  if (MOCK_MODE) throw new Error('Import YAML jest dostępny w zainstalowanej aplikacji.');
  const response = await fetch('api/config/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ yaml: source }),
  });
  const body = (await response.json().catch(() => ({}))) as { user_config?: unknown } & ApiErrorBody;
  if (!response.ok) {
    throw new Error(body.message || body.error || `Błąd importu konfiguracji (${response.status})`);
  }
  if (!body.user_config || typeof body.user_config !== 'object' || Array.isArray(body.user_config)) {
    throw new Error('Plik nie zawiera poprawnej sekcji user_config');
  }
  return body.user_config as ConfigurationMap;
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
