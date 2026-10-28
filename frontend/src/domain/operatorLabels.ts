import type { EntityMap } from './safety.js';

/** Polish operator labels; raw contracts remain available in technical details. */
const components: Record<string, string> = {
  TemperatureComponent: 'Monitorowanie temperatury',
  SafetyDoorsComponent: 'Monitorowanie drzwi i bram',
  ExternalHazardComponent: 'Zagrożenia zewnętrzne',
  InternalEnvironmentalHazardMonitorComponent: 'Czujniki zagrożeń wewnętrznych',
  EntityMonitorComponent: 'Monitoring wejść',
  FunctionalSafetyMonitor: 'Kondycja systemu i konserwacja',
  SelfDiagnosticsComponent: 'Diagnostyka aplikacji',
  SafetyFunctions: 'System bezpieczeństwa',
  installation: 'Konfiguracja użytkownika',
};

const codes: Record<string, string> = {
  external_exposure: 'Narażenie przez otwarte okna i drzwi',
  temperature: 'Ochrona przed niebezpieczną temperaturą',
  temperature_forecast: 'Prognoza temperatury',
  door_timeout: 'Czas otwarcia drzwi i bram',
  weather: 'Warunki pogodowe',
  outdoor_air_quality: 'Jakość powietrza na zewnątrz',
  operator: 'Użytkownik',
  operator_attestation: 'Potwierdzenie użytkownika',
  owner_clear: 'Aktualna ocena funkcji bezpieczeństwa',
  entity_state: 'Aktualny odczyt urządzenia',
  opening_closed: 'Potwierdzone zamknięcie',
  postcondition: 'Potwierdzony rezultat',
  owner_unverified: 'Oczekiwanie na aktualną ocenę funkcji bezpieczeństwa',
  not_evaluated: 'Brak wykonanej oceny',
  unavailable: 'Niedostępne',
  unknown: 'Brak wiarygodnych danych',
};

export function componentLabel(value: string): string {
  return components[value] ?? 'Inny komponent systemu';
}

export function operatorCodeLabel(value: string, fallback = 'Nieopisany zakres — sprawdź diagnostykę'): string {
  return codes[value] ?? components[value] ?? fallback;
}

export function operatorExplanation(value: string, fallback = 'Szczegóły przyczyny są dostępne w diagnostyce'): string {
  return codes[value] ?? (/^[\w.:-]+$/.test(value) ? fallback : value);
}

export function evidenceSourceLabel(value: string): string {
  if (/^[a-z_]+\.[a-z0-9_]+$/.test(value)) return 'Odczyt urządzenia';
  return operatorCodeLabel(value, 'Źródło potwierdzenia opisane w diagnostyce');
}

/** Resolve published binding metadata, never guess a device from a technical ID. */
export function boundEntityName(binding: string, entities: EntityMap): string {
  const bound = Object.entries(entities).find(([id, entity]) => id === binding || entity.attributes.entity_key === binding);
  if (!bound) return 'Nie podano nazwy urządzenia';
  const sourceId = bound[1].attributes.source_entity_id ?? bound[1].attributes.entity_id;
  const source = typeof sourceId === 'string' ? entities[sourceId] : undefined;
  const name = source?.attributes.friendly_name ?? bound[1].attributes.friendly_name;
  return typeof name === 'string' && name.trim() && name !== binding ? name.replace(/^Safety Component\s*/i, '') : 'Urządzenie bez nazwy';
}

export function coverageCauseLabel(cause: string, entities: EntityMap): string {
  const binding = coverageBinding(cause, entities);
  return binding ? `Problem z odczytem: ${boundEntityName(binding, entities)}` : 'Ograniczenie monitorowania bezpieczeństwa';
}

export function coverageSubjectName(cause: string, subject: string, entities: EntityMap): string {
  return boundEntityName(coverageBinding(cause, entities) ?? subject, entities);
}

function coverageBinding(cause: string, entities: EntityMap): string | undefined {
  return Object.values(entities)
    .map(entity => entity.attributes.entity_key)
    .filter((key): key is string => typeof key === 'string' && cause.startsWith(`EntityHealthFailure${key}`))
    .sort((a, b) => b.length - a.length)[0];
}
