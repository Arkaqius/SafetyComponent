import { HEALTH_ENTITY_ID, type EntityMap } from './safety.js';
import { getStartupView, PROGRESS_ENTITY_ID } from './startup.js';

/** Sample collection ends only on a numeric backend result, independently of startup grace. */
export function getTemperatureSamplingView(entities: EntityMap, now = Date.now(), connected = true) {
  const rates = new Set<string>();
  for (const entity of Object.values(entities)) {
    if (String(entity.attributes.entity_key ?? '').startsWith('TemperatureForecast')) {
      const source = entity.attributes.source_entity_id;
      if (typeof source === 'string') rates.add(source);
    }
  }
  const pending = [...rates]
    .map(id => entities[id])
    .filter(rate => {
      if (!rate) return false;
      const state = rate.state.trim();
      return state === '' || !Number.isFinite(Number(state));
    });
  const tracked = pending.filter(rate => ['waiting_for_samples', 'source_unavailable'].includes(String(rate.attributes.sampling_status)));
  if (tracked.length === 0) return null;
  const progress = entities[PROGRESS_ENTITY_ID];
  const startup = progress?.attributes.startup as Record<string, unknown> | undefined;
  const reported = typeof startup?.reported_at === 'string' ? Date.parse(startup.reported_at) : NaN;
  if (
    !connected ||
    entities[HEALTH_ENTITY_ID]?.state !== 'running' ||
    !Number.isFinite(reported) ||
    now - reported >= 180_000 ||
    getStartupView(entities, now, connected)?.available === false
  ) {
    return {
      label: 'Prognoza temperatury · brak aktualnych danych',
      detail: 'Nie można potwierdzić zakończenia zbierania próbek. Sprawdź połączenie i stan aplikacji.',
    };
  }
  const missing = tracked.some(rate => {
    const source = entities[String(rate.attributes.source_entity_id)];
    return (
      rate.attributes.sampling_status === 'source_unavailable' ||
      !source ||
      source.state.trim() === '' ||
      !Number.isFinite(Number(source.state))
    );
  });
  if (missing) {
    return {
      label: 'Prognoza temperatury · brak odczytu źródłowego',
      detail: 'Brakuje poprawnego odczytu temperatury do obliczenia tempa zmian. Sprawdź diagnostykę źródeł.',
    };
  }
  const intervals = [...new Set(tracked.map(rate => Number(rate.attributes.sample_interval_seconds)))];
  const interval =
    intervals.length === 1 && Number.isFinite(intervals[0]) && intervals[0] > 0 ? ` Próbki są pobierane co ${intervals[0] / 60} min.` : '';
  return {
    label: 'Prognoza temperatury · oczekiwanie na próbki',
    detail: `Liczba pomieszczeń oczekujących na tempo zmian: ${tracked.length}.${interval} Komunikat zniknie po otrzymaniu wyników. Bieżąca temperatura jest oceniana niezależnie.`,
  };
}
