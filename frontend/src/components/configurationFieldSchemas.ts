/** Editable installation fields, aligned with the version 2 source model. */
export type FieldSpec = {
  label: string;
  help?: string;
  kind: 'text' | 'entity' | 'number' | 'boolean' | 'select' | 'list' | 'object' | 'registry' | 'object_list';
  domains?: string[];
  required?: boolean;
  includeOnCreate?: boolean;
  hidden?: boolean;
  initial?: unknown;
  options?: Array<[string, string]>;
  fields?: Record<string, FieldSpec>;
};

const text = (label: string, required = false, help?: string): FieldSpec => ({ label, kind: 'text', required, help, initial: '' });
const entity = (label: string, required = false, domains: string[] = [], help?: string): FieldSpec => ({
  ...text(label, required, help),
  kind: 'entity',
  domains,
});
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
      timestamp_source: text(
        'Źródło znacznika czasu',
        true,
        'Wiarygodny raport źródła, np. last_reported lub uzgodniony atrybut czasu. Sam odczyt HA nie odnawia świeżości.'
      ),
      max_silence_seconds: { ...number('Maksymalny wiek raportu (stare ustawienie)'), hidden: true },
    },
    { timestamp_source: '' }
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
  report_timeout_seconds: {
    ...number(
      'Maksymalny wiek raportu (s)',
      'Wymaga kontroli aktualności ze źródłem znacznika czasu. Nie jest limitem oczekiwania na odpowiedź HA.'
    ),
    initial: 3600,
  },
  failure_debounce_seconds: number(
    'Czas potwierdzenia awarii (s)',
    'Jak długo problem musi trwać przed zgłoszeniem. Częstotliwość kontroli jest dobierana automatycznie.'
  ),
  recovery_debounce_seconds: { ...number('Potwierdzenie powrotu (stare ustawienie)'), hidden: true },
  detection_budget_seconds: { ...number('Budżet wykrycia (stare ustawienie)'), hidden: true },
  checks,
};

const hazardOptions: Array<[string, string]> = [
  ['frost', 'Mróz'],
  ['wind', 'Wiatr'],
  ['rain', 'Deszcz'],
  ['storm', 'Burza'],
  ['outdoor_air_pollution', 'Zanieczyszczenie powietrza'],
];

const routineReading: Record<string, FieldSpec> = {
  entity_id: entity('Źródło odczytu', true),
  attribute: text('Atrybut wartości (opcjonalny, dla kontroli stanu)'),
  observed_at_entity_id: entity(
    'Encja czasu obserwacji',
    false,
    [],
    'Stan tej encji musi być oryginalnym czasem obserwacji: ISO 8601 ze strefą albo liczbowy Unix w sekundach. Wybierz encję albo atrybut, nie oba. Czas HA i samo last_seen urządzenia nie wystarczają.'
  ),
  observed_at_attribute: text(
    'Atrybut czasu obserwacji',
    false,
    'Rzeczywisty atrybut oryginalnego czasu obserwacji na encji wartości. Wpisanie observed_at nie tworzy atrybutu; brak czasu daje „Nie można ocenić”. Wybierz atrybut albo encję czasu.'
  ),
  max_age_seconds: { ...number('Maksymalny wiek obserwacji (s)'), initial: 300 },
};

export const routineCheckSchema: Record<string, FieldSpec> = {
  name: text('Nazwa kontroli', true),
  ...routineReading,
  kind: select(
    'Rodzaj kontroli',
    [
      ['state', 'Oczekiwany stan'],
      ['numeric_range', 'Zakres liczbowy'],
    ],
    true
  ),
  expected_states: { ...list('Oczekiwane stany', 'Dokładne stany HA, np. off dla zamkniętego kontaktronu.'), includeOnCreate: true },
  minimum: number('Wartość minimalna', 'Granica włącznie: odczyt może być równy minimum.'),
  maximum: number(
    'Wartość maksymalna',
    'Granica włącznie: 500 dopuszcza 500 W. Dla limitu poniżej 500 W przy rozdzielczości 0,1 W wybierz 499.9.'
  ),
  unit: text('Jednostka', false, 'Dokładna jednostka źródła, np. W. Kontrola liczbowa wymaga jednostki i przynajmniej jednego progu.'),
  condition: object(
    'Warunek zastosowania',
    {
      ...routineReading,
      pass_states: { ...list('Stany włączające kontrolę'), required: true },
      skip_states: { ...list('Stany pomijające kontrolę'), required: true },
    },
    { entity_id: '', pass_states: [''], skip_states: [''] }
  ),
};

export const registrySchemas: Record<string, Record<string, FieldSpec>> = {
  safety_routines: {
    name: text('Nazwa scenariusza', true),
    enabled: { ...yesNo('Scenariusz włączony'), initial: false, includeOnCreate: true },
    delay_seconds: number('Opóźnienie rozpoczęcia (s)', '0–600 s; np. 120 s na wyjście lub rutynę wieczorną. Dotyczy też „Sprawdź teraz”.'),
    observation_seconds: number(
      'Okno obserwacji (s)',
      '0 s: jedna ocena po opóźnieniu. Do 300 s: próbki co 5 s i na końcu; problem lub brak danych pozostaje w raporcie.'
    ),
    checks: { label: 'Sprawdzenia', kind: 'registry', fields: routineCheckSchema, initial: {}, required: true },
    triggers: {
      label: 'Automatyczne wyzwalacze',
      kind: 'object_list',
      initial: [],
      fields: {
        kind: select(
          'Rodzaj wyzwalacza',
          [
            ['event', 'Zdarzenie HA'],
            ['state', 'Zmiana stanu'],
          ],
          true
        ),
        event: { ...text('Nazwa zdarzenia'), includeOnCreate: true },
        entity_id: entity(
          'Encja wyzwalacza',
          false,
          [],
          'Np. sensor.home_monitor_occupancy przy wyjściu lub sensor.home_monitor_activity przed snem. Sprawdź encję w swojej instalacji.'
        ),
        from_state: text('Stan początkowy', false, 'Wyjście: occupied; sen: awake. Restart nie zastępuje zmiany stanu.'),
        to_state: text(
          'Stan docelowy',
          false,
          'Wyjście: empty; sen: asleep, nie sleep. Wymagana jest pełna zmiana od stanu początkowego do docelowego.'
        ),
      },
    },
  },
  rooms: {
    area_id: text('Obszar Home Assistant', true),
    temperature_sensor: entity('Czujnik temperatury', true, ['sensor'], 'Pełny identyfikator encji, np. sensor.temperatura.'),
    window: text('Okno z listy otworów'),
    actuator: entity('Osłona cover.*', false, ['cover']),
    temperature: object('Progi temperatury tego pomieszczenia', {
      low_temperature_c: number('Minimalna temperatura (°C)'),
      high_temperature_c: number('Maksymalna temperatura (°C)'),
    }),
  },
  openings: {
    area_id: text('Obszar Home Assistant', true),
    entity_id: entity('Czujnik otwarcia', true, ['binary_sensor', 'cover']),
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
          entity_id: entity('Encja warunku', true),
          pass_states: { ...list('Stany zezwalające'), required: true },
          blocked_states: { ...list('Stany blokujące'), required: true },
        },
        { entity_id: '', pass_states: [''], blocked_states: [''] }
      ),
    }),
    external_hazard: object('Zagrożenia zewnętrzne', {
      hazards: list('Monitorowane zagrożenia', 'Pomiń to pole, aby użyć zagrożeń systemowych.', hazardOptions),
      actuator_entity_id: entity('Osłona cover.*', false, ['cover']),
      execution_policy: select('Tryb wykonania', [
        ['manual', 'Ręczny'],
        ['user_confirmed', 'Po potwierdzeniu użytkownika'],
      ]),
      confirmation_timeout_seconds: { ...number('Czas na potwierdzenie (s)'), initial: 120 },
    }),
  },
  detectors: {
    area_id: text('Obszar Home Assistant', true),
    entity_id: entity('Encja detektora', true, ['binary_sensor']),
    friendly_name: text('Nazwa detektora', true),
    hazard: select(
      'Wykrywane zagrożenie',
      [
        ['smoke', 'Dym'],
        ['flammable_gas', 'Gaz palny'],
        ['carbon_monoxide', 'Tlenek węgla'],
        ['water_leak', 'Zalanie / wyciek wody'],
      ],
      true
    ),
    profile: text('Profil systemowy', true, 'Nazwa profilu detektora z konfiguracji systemowej.'),
    gas_identity: text('Rodzaj gazu', false, 'Wymagane tylko dla detektora gazu palnego.'),
    enabled: yesNo('Włączony'),
  },
  monitored_entities: {
    entity_id: entity('Monitorowana encja', true),
    description: text('Opis celu monitoringu', true),
    area_id: text('Obszar Home Assistant'),
    enabled: yesNo('Włączona'),
    ...monitorTiming,
  },
  component_overrides: monitorTiming,
  remote_batteries: {
    friendly_name: text('Nazwa urządzenia', true),
    percentage_entity: {
      ...entity('Poziom baterii (%)', false, ['sensor'], 'Encja sensor.* z klasą battery i jednostką %. Nie dodawaj tu baterii hosta.'),
      includeOnCreate: true,
    },
    low_entity: entity(
      'Sygnalizacja niskiej baterii',
      false,
      ['binary_sensor'],
      'Encja binary_sensor.* z klasą battery; on oznacza niski poziom.'
    ),
    enabled: yesNo('Monitoruj urządzenie'),
  },
};

export function initialObject(schema: Record<string, FieldSpec>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(schema)
      .filter(([, field]) => field.required || field.includeOnCreate)
      .map(([key, field]) => [key, structuredClone(field.initial)])
  );
}

export function updateObjectField(value: Record<string, unknown>, key: string, next: unknown): Record<string, unknown> {
  const updated = { ...value, [key]: next };
  if (key === 'kind' && next === 'numeric_range') {
    delete updated.expected_states;
    delete updated.attribute;
    updated.unit ??= '';
    updated.maximum ??= 0;
  }
  if (key === 'kind' && next === 'state' && 'expected_states' in value === false && 'name' in value) {
    delete updated.minimum;
    delete updated.maximum;
    delete updated.unit;
    updated.expected_states = [''];
  }
  if (key === 'kind' && next === 'state' && !('name' in value)) {
    delete updated.event;
    updated.entity_id ??= '';
    updated.from_state ??= '';
    updated.to_state ??= '';
  }
  if (key === 'kind' && next === 'event') {
    delete updated.entity_id;
    delete updated.from_state;
    delete updated.to_state;
    updated.event ??= '';
  }
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

export function normalizeMonitorConfiguration(source: Record<string, unknown>): Record<string, unknown> {
  const normalized = structuredClone(source);
  const asMap = (value: unknown): Record<string, unknown> =>
    value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
  const installation = asMap(normalized.installation);
  const settings = asMap(installation.component_settings);
  const monitor = asMap(settings.entity_monitor);
  for (const group of [asMap(installation.monitored_entities), asMap(monitor.component_overrides)]) {
    for (const raw of Object.values(group)) {
      const dependency = asMap(raw);
      const freshness = asMap(asMap(dependency.checks).freshness);
      const legacy = freshness.max_silence_seconds;
      if (legacy !== undefined && (dependency.report_timeout_seconds === undefined || dependency.report_timeout_seconds === legacy)) {
        dependency.report_timeout_seconds = legacy;
        delete freshness.max_silence_seconds;
      }
    }
  }
  return normalized;
}
