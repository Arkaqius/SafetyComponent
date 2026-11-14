import { MOCK_MODE } from './config';
import {
  decodeProviderCatalogue,
  decodeProviderFieldErrors,
  validateProviderDraft,
  type ProviderFieldError,
} from './domain/providerConfiguration';

export type ConfigurationMap = Record<string, unknown>;

export interface UserConfigurationDocument {
  user_config: ConfigurationMap;
  template_user_config?: ConfigurationMap;
  system_defaults?: ConfigurationMap;
  revision: string;
  restart_required: boolean;
  setup_required: boolean;
  validation_error?: string | null;
}

interface ApiErrorBody {
  error?: string;
  message?: string;
  field_errors?: unknown;
}

export class ConfigurationApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number,
    public readonly fieldErrors: ProviderFieldError[] = []
  ) {
    super(message);
    this.name = 'ConfigurationApiError';
  }
}

declare global {
  interface Window {
    __safetyHomeConfigurationSeed?: unknown;
    __safetyHomeConfigurationMock?: {
      snapshot(): UserConfigurationDocument;
      replace(document: UserConfigurationDocument): void;
      failNext(error: { error: string; message: string; field_errors?: unknown; status?: number }): void;
    };
  }
}

const emptyParameters = { type: 'object', additionalProperties: false, properties: {} };
const mockProviderDefinitions = {
  OpenMeteoWeatherApiComponent: {
    data_kind: 'live',
    transport_kind: 'http',
    countries: [],
    capability: 'WeatherPointModel',
    hazards: ['frost', 'wind', 'rain', 'storm'],
    display_name: 'Pogoda Open-Meteo',
    description: 'Model pogody dla współrzędnych Home Assistant.',
    parameter_schema: emptyParameters,
    required_when_selected: [],
    parameter_defaults: {},
  },
  OpenMeteoAirQualityApiComponent: {
    data_kind: 'live',
    transport_kind: 'http',
    countries: [],
    capability: 'OutdoorAirQuality',
    hazards: ['outdoor_air_pollution'],
    display_name: 'Jakość powietrza Open-Meteo',
    description: 'Model jakości powietrza.',
    parameter_schema: emptyParameters,
    required_when_selected: [],
    parameter_defaults: {},
  },
  ImgwWarningsApiComponent: {
    data_kind: 'live',
    transport_kind: 'http',
    countries: ['PL'],
    capability: 'OfficialWeatherWarnings',
    hazards: ['frost', 'wind', 'rain', 'storm'],
    display_name: 'Ostrzeżenia IMGW',
    description: 'Ostrzeżenia urzędowe dla wybranych powiatów.',
    parameter_schema: {
      type: 'object',
      additionalProperties: false,
      properties: {
        teryt_codes: {
          type: 'array',
          title: 'Kody TERYT',
          description: 'Czterocyfrowe kody powiatów, jeden w wierszu.',
          items: { type: 'string', pattern: '^[0-9]{4}$' },
          minItems: 1,
          maxItems: 10000,
          uniqueItems: true,
        },
      },
    },
    required_when_selected: ['teryt_codes'],
    parameter_defaults: {},
  },
  GermanyDummyWarningsApiComponent: {
    data_kind: 'synthetic',
    transport_kind: 'none',
    countries: ['DE'],
    capability: 'OfficialWeatherWarnings',
    hazards: ['wind'],
    display_name: 'Niemcy — źródło testowe',
    description: 'Kontrolowane źródło regionalne trybu demonstracyjnego.',
    parameter_schema: {
      type: 'object',
      additionalProperties: false,
      properties: {
        region_code: {
          type: 'string',
          title: 'Kod regionu',
          description: 'Identyfikator regionu testowego.',
          minLength: 1,
          maxLength: 32,
          pattern: '^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$',
        },
        scenario: { type: 'string', title: 'Scenariusz testowy', enum: ['empty', 'warning', 'unavailable', 'stale'], default: 'empty' },
      },
    },
    required_when_selected: ['region_code'],
    parameter_defaults: { scenario: 'empty' },
  },
};

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
    localization: { language: 'pl' },
    notification: {
      mobile: { services: ['notify/all_phones'], default_url: '/' },
      local: {},
      wan_entity: null,
    },
    external_sources: {
      WeatherPointModel: 'OpenMeteoWeatherApiComponent',
      OfficialWeatherWarnings: 'ImgwWarningsApiComponent',
      OutdoorAirQuality: 'OpenMeteoAirQualityApiComponent',
    },
    provider_parameters: { ImgwWarningsApiComponent: { teryt_codes: ['0000'] } },
    installation: {
      site: {
        timezone: 'Europe/Warsaw',
        country_code: 'PL',
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
    detector_profiles: ['home_assistant_binary_alarm'],
    temperature: { default_low_temperature_c: 18, default_high_temperature_c: 28 },
    safety_door: { default_timeout_seconds: 120 },
    entity_monitor: { default_startup_grace_seconds: 600, default_evaluation_interval_seconds: 5 },
    external_hazard: {
      provider_metadata_version: 2,
      provider_plugins: mockProviderDefinitions,
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

let nextMockError: { error: string; message: string; field_errors?: unknown; status?: number } | undefined;
if (MOCK_MODE && typeof window !== 'undefined') {
  const seed = window.__safetyHomeConfigurationSeed as UserConfigurationDocument | undefined;
  if (seed && typeof seed.revision === 'string' && seed.user_config && typeof seed.user_config === 'object')
    mockDocument = structuredClone(seed);
  window.__safetyHomeConfigurationMock = {
    snapshot: () => structuredClone(mockDocument),
    replace: document => {
      mockDocument = structuredClone(document);
    },
    failNext: error => {
      nextMockError = error;
    },
  };
}

const mockTemplate = structuredClone(mockDocument.user_config);

export async function loadUserConfiguration(): Promise<UserConfigurationDocument> {
  if (MOCK_MODE) return { ...structuredClone(mockDocument), template_user_config: structuredClone(mockTemplate) };
  return requestConfiguration(CONFIG_ENDPOINT, { cache: 'no-store' });
}

export async function saveUserConfiguration(userConfig: ConfigurationMap, revision: string): Promise<UserConfigurationDocument> {
  if (MOCK_MODE) {
    if (nextMockError) {
      const failure = nextMockError;
      nextMockError = undefined;
      throw new ConfigurationApiError(
        failure.message,
        failure.error,
        failure.status ?? 422,
        decodeProviderFieldErrors(failure.field_errors)
      );
    }
    if (revision !== mockDocument.revision)
      throw new ConfigurationApiError('Konfiguracja zmieniła się w innej sesji. Wczytaj ją ponownie.', 'revision_conflict', 409);
    const catalogue = decodeProviderCatalogue(mockDocument.system_defaults?.external_hazard ?? {});
    const installation = userConfig.installation as ConfigurationMap | undefined;
    const site = installation?.site as ConfigurationMap | undefined;
    const fieldErrors = validateProviderDraft(catalogue, userConfig, typeof site?.country_code === 'string' ? site.country_code : '');
    if (fieldErrors.length) throw new ConfigurationApiError('Sprawdź parametry źródeł danych.', 'invalid_configuration', 422, fieldErrors);
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
    throw new ConfigurationApiError(
      body.message || body.error || `Błąd importu konfiguracji (${response.status})`,
      body.error ?? 'invalid_configuration',
      response.status,
      decodeProviderFieldErrors(body.field_errors)
    );
  }
  if (!body.user_config || typeof body.user_config !== 'object' || Array.isArray(body.user_config)) {
    throw new Error('Plik nie zawiera poprawnej sekcji user_config');
  }
  return body.user_config as ConfigurationMap;
}

export async function prepareConfigurationRestart(revision: string): Promise<string> {
  if (MOCK_MODE) throw new Error('Restart jest dostępny tylko w zainstalowanej aplikacji HA.');
  const response = await fetch('api/config/restart-target', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirmed: true, revision }),
  });
  const body = (await response.json().catch(() => ({}))) as { app_slug?: unknown } & ApiErrorBody;
  if (!response.ok) {
    const message =
      body.error === 'revision_conflict'
        ? 'Konfiguracja zmieniła się w innej sesji. Wczytaj ją ponownie przed restartem.'
        : body.error === 'invalid_saved_configuration'
          ? 'Zapisany config nie przeszedł walidacji. Popraw go przed restartem.'
          : 'Nie można przygotować restartu. Sprawdź połączenie z Supervisor i logi aplikacji.';
    throw new Error(message);
  }
  if (typeof body.app_slug !== 'string') throw new Error('Brak identyfikatora aplikacji.');
  return body.app_slug;
}

async function requestConfiguration(url: string, init: RequestInit): Promise<UserConfigurationDocument> {
  const response = await fetch(url, init);
  const body = (await response.json().catch(() => ({}))) as UserConfigurationDocument & ApiErrorBody;
  if (!response.ok) {
    throw new ConfigurationApiError(
      body.message || body.error || `Błąd API konfiguracji (${response.status})`,
      body.error ?? 'configuration_error',
      response.status,
      decodeProviderFieldErrors(body.field_errors)
    );
  }
  if (!body.user_config || typeof body.revision !== 'string') {
    throw new Error('API zwróciło nieprawidłowy dokument konfiguracji');
  }
  return body;
}
