import { HEALTH_ENTITY_ID, type EntityMap } from './safety.js';

export const PROGRESS_ENTITY_ID = 'sensor.safety_evaluation_progress';

export interface StartupView {
  available: boolean;
  remainingSeconds: number | null;
  countdown: string;
  label: string;
  detail: string;
}

/** Keep startup visible until the backend confirms its monotonic deadline. */
export function getStartupView(entities: EntityMap, now = Date.now(), connected = true): StartupView | null {
  const progress = entities[PROGRESS_ENTITY_ID];
  const value = progress?.attributes.startup;
  // Older backend versions do not publish startup metadata.
  if (value === undefined) return null;
  const startup = value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
  const reported = typeof startup.reported_at === 'string' ? Date.parse(startup.reported_at) : NaN;
  const duration = startup.duration_seconds;
  const remaining = startup.remaining_seconds;
  const valid =
    typeof duration === 'number' &&
    Number.isFinite(duration) &&
    duration >= 0 &&
    typeof remaining === 'number' &&
    Number.isFinite(remaining) &&
    remaining >= 0 &&
    remaining <= duration &&
    ['settling', 'complete'].includes(String(startup.phase)) &&
    (startup.phase !== 'complete' || remaining === 0) &&
    Number.isFinite(reported);
  const available =
    connected &&
    entities[HEALTH_ENTITY_ID]?.state === 'running' &&
    ['observed', 'unknown', 'attention'].includes(progress.state) &&
    valid &&
    now - reported < 180_000;
  if (!available) {
    return {
      available: false,
      remainingSeconds: null,
      countdown: '—',
      label: 'Rozruch monitoringu · brak aktualnych danych',
      detail: 'Nie można potwierdzić zakończenia rozruchu. Sprawdź połączenie i stan aplikacji.',
    };
  }
  if (startup.phase === 'complete') return null;
  const seconds = Math.max(0, Math.ceil(remaining - Math.max(0, now - reported) / 1000));
  return {
    available: true,
    remainingSeconds: seconds,
    countdown: `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`,
    label: 'Rozruch monitoringu',
    detail:
      seconds > 0
        ? 'Trwa stabilizacja źródeł. Zgłaszanie usterek diagnostycznych jest opóźnione. Wykrywanie zagrożeń działa od razu.'
        : 'Oczekiwanie na potwierdzenie uruchomienia diagnostyki przez system. Wykrywanie zagrożeń nadal działa.',
  };
}
