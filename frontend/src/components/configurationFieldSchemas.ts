/** Editable installation fields, aligned with the version 2 source model. */
export type FieldSpec = {
  label: string;
  help?: string;
  kind: 'text' | 'number' | 'boolean' | 'select' | 'list' | 'object';
  required?: boolean;
  initial?: unknown;
  options?: Array<[string, string]>;
  fields?: Record<string, FieldSpec>;
};

const text = (label: string, required = false, help?: string): FieldSpec => ({ label, kind: 'text', required, help, initial: '' });
const number = (label: string, help?: string): FieldSpec => ({ label, kind: 'number', help, initial: 0 });
const list = (label: string, help?: string, options?: Array<[string, string]>): FieldSpec => ({
  label,
  kind: 'list',
  help,
  options,
  initial: [''],
});
const object = (label: string, fields: Record<string, FieldSpec>, initial: unknown = {}): FieldSpec => ({
  label,
  kind: 'object',
  fields,
  initial,
});
const select = (label: string, options: Array<[string, string]>, required = false): FieldSpec => ({
  label,
  kind: 'select',
  options,
  required,
  initial: options[0][0],
});
const yesNo = (label: string): FieldSpec => ({ label, kind: 'boolean', initial: true });

const targetFields = {
  target: { ...text('Stan lub atrybut', false, 'state oznacza stan encji; inaczej wpisz nazwę atrybutu.'), initial: 'state' },
};
const checks = object('Kontrole zdrowia', {
  freshness: object(
    'Aktualność danych',
    {
      timestamp_source: text('Źródło znacznika czasu', true, 'Np. last_updated lub nazwa atrybutu czasu.'),
      max_silence_seconds: { ...number('Maksymalna cisza (s)'), required: true },
    },
    { timestamp_source: '', max_silence_seconds: 60 }
  ),
  required_value: object('Wymagana wartość', targetFields),
  allowed_values: object(
    'Dozwolone wartości',
    { ...targetFields, values: { ...list('Dozwolone stany'), required: true } },
    { values: [''] }
  ),
  finite_number: object('Skończona liczba', targetFields),
  numeric_range: object('Zakres liczbowy', { ...targetFields, minimum: number('Minimum'), maximum: number('Maksimum') }, { minimum: 0 }),
  rate_of_change: object(
    'Szybkość zmian',
    {
      ...targetFields,
      window_seconds: { ...number('Okno pomiaru (s)'), required: true },
      min_samples: { ...number('Minimalna liczba próbek'), initial: 2 },
      maximum_rise_per_minute: number('Maksymalny wzrost na minutę'),
      maximum_fall_per_minute: number('Maksymalny spadek na minutę'),
    },
    { window_seconds: 60, min_samples: 2, maximum_rise_per_minute: 0 }
  ),
});

const monitorTiming = {
  failure_debounce_seconds: number('Opóźnienie wykrycia awarii (s)'),
  recovery_debounce_seconds: number('Opóźnienie potwierdzenia powrotu (s)'),
  detection_budget_seconds: { ...number('Budżet wykrycia (s)'), initial: 60 },
  checks,
};

const hazardOptions: Array<[string, string]> = [
  ['frost', 'Mróz'],
  ['wind', 'Wiatr'],
  ['rain', 'Deszcz'],
  ['storm', 'Burza'],
  ['outdoor_air_pollution', 'Zanieczyszczenie powietrza'],
];

export const registrySchemas: Record<string, Record<string, FieldSpec>> = {
  rooms: {
    area_id: text('Obszar Home Assistant', true),
    temperature_sensor: text('Czujnik temperatury', true, 'Pełny identyfikator encji, np. sensor.temperatura.'),
    window: text('Okno z listy otworów'),
    actuator: text('Osłona cover.*'),
    temperature: object('Progi temperatury tego pomieszczenia', {
      low_temperature_c: number('Minimalna temperatura (°C)'),
      high_temperature_c: number('Maksymalna temperatura (°C)'),
    }),
  },
  openings: {
    area_id: text('Obszar Home Assistant', true),
    entity_id: text('Czujnik otwarcia', true),
    friendly_name: text('Nazwa otworu', true),
    kind: select(
      'Rodzaj otworu',
      [
        ['window', 'Okno'],
        ['door', 'Drzwi'],
        ['garage_door', 'Brama garażowa'],
        ['gate', 'Brama'],
      ],
      true
    ),
    safety_door: object('Monitoring drzwi i bram', {
      timeout_seconds: { ...number('Czas otwarcia przed alarmem (s)'), initial: 120 },
      condition: object(
        'Warunek monitorowania',
        {
          entity_id: text('Encja warunku', true),
          pass_states: { ...list('Stany zezwalające'), required: true },
          blocked_states: { ...list('Stany blokujące'), required: true },
        },
        { entity_id: '', pass_states: [''], blocked_states: [''] }
      ),
    }),
    external_hazard: object('Zagrożenia zewnętrzne', {
      hazards: list('Monitorowane zagrożenia', 'Pomiń to pole, aby użyć zagrożeń systemowych.', hazardOptions),
      actuator_entity_id: text('Osłona cover.*'),
      execution_policy: select('Tryb wykonania', [
        ['manual', 'Ręczny'],
        ['user_confirmed', 'Po potwierdzeniu użytkownika'],
      ]),
      confirmation_timeout_seconds: { ...number('Czas na potwierdzenie (s)'), initial: 120 },
    }),
  },
  detectors: {
    area_id: text('Obszar Home Assistant', true),
    entity_id: text('Encja detektora', true),
    friendly_name: text('Nazwa detektora', true),
    hazard: select(
      'Wykrywane zagrożenie',
      [
        ['smoke', 'Dym'],
        ['flammable_gas', 'Gaz palny'],
        ['carbon_monoxide', 'Tlenek węgla'],
      ],
      true
    ),
    profile: text('Profil systemowy', true, 'Nazwa profilu detektora z konfiguracji systemowej.'),
    gas_identity: text('Rodzaj gazu', false, 'Wymagane tylko dla detektora gazu palnego.'),
    enabled: yesNo('Włączony'),
  },
  monitored_entities: {
    entity_id: text('Monitorowana encja', true),
    description: text('Opis celu monitoringu', true),
    area_id: text('Obszar Home Assistant'),
    enabled: yesNo('Włączona'),
    ...monitorTiming,
  },
  component_overrides: monitorTiming,
};

export function initialObject(schema: Record<string, FieldSpec>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(schema)
      .filter(([, field]) => field.required)
      .map(([key, field]) => [key, structuredClone(field.initial)])
  );
}

export function updateObjectField(value: Record<string, unknown>, key: string, next: unknown): Record<string, unknown> {
  const updated = { ...value, [key]: next };
  if (key === 'hazard') {
    if (next === 'flammable_gas' && !('gas_identity' in updated)) updated.gas_identity = '';
    if (next !== 'flammable_gas') delete updated.gas_identity;
  }
  if (key === 'execution_policy') {
    if (next === 'user_confirmed' && !('actuator_entity_id' in updated)) updated.actuator_entity_id = '';
    if (next === 'manual') delete updated.actuator_entity_id;
  }
  return updated;
}
