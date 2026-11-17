import { HEALTH_ENTITY_ID, recoveriesForFault, type EntityMap, type FaultView, type RecoveryView, type SafetySummary } from './safety.js';

export const PROGRESS_ENTITY_ID = 'sensor.safety_evaluation_progress';

export interface StartupView {
  available: boolean;
  remainingSeconds: number | null;
  countdown: string;
  label: string;
  detail: string;
}

/** Hold startup diagnostics off the operator view without hiding real danger. */
export function startupOperatorView(startup: StartupView | null, faults: FaultView[], recoveries: RecoveryView[], summary: SafetySummary) {
  if (!startup?.available) return { faults, recoveries, summary };
  const visibleFaults = faults.filter(fault => fault.category !== 'D' && (fault.active === true || fault.latched === true));
  const visibleRecoveries = recoveries.filter(
    recovery => recovery.status === 'executing' || visibleFaults.some(fault => recoveriesForFault(fault, [recovery]).length > 0)
  );
  const diagnosticAggregate = faults.some(
    fault => fault.category === 'D' && fault.active === true && fault.level === summary.effectiveLevel
  );
  const reportedDanger =
    summary.effectiveLevel !== null && summary.effectiveLevel > 0 && summary.effectiveLevel <= 2 && !diagnosticAggregate;
  const hasDanger = visibleFaults.length > 0 || reportedDanger;
  return {
    faults: visibleFaults,
    recoveries: visibleRecoveries,
    summary: {
      ...summary,
      ...(!hasDanger ? { label: startup.label, detail: startup.detail, tone: 'info' as const, effectiveLevel: null } : {}),
      activeFaultCount: visibleFaults.filter(fault => fault.level !== 4).length,
      informationalFaultCount: visibleFaults.filter(fault => fault.level === 4).length,
      shadowedFaultCount: visibleFaults.filter(fault => fault.shadowedBy.length > 0).length,
      actionableRecoveryCount: visibleRecoveries.filter(recovery => recovery.status === 'to_perform').length,
    },
  };
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
    now - reported >= -60_000 &&
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
        ? 'Trwa zbieranie danych. Oceny i zalecenia diagnostyczne pojawią się po zakończeniu rozruchu. Wykrywanie zagrożeń działa od razu.'
        : 'Oczekiwanie na potwierdzenie uruchomienia diagnostyki przez system. Wykrywanie zagrożeń nadal działa.',
  };
}
