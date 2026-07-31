import Icon from '../components/Icon';
import StatusBadge from '../components/StatusBadge';
import { formatRelativeTime, type SafetyDoorView } from '../domain/safety';
import { useSafetyEntities } from '../hooks/useSafetyEntities';

export default function SafetyDoors() {
  const { safetyDoors } = useSafetyEntities();
  const activeCount = safetyDoors.filter(door => door.status === 'active').length;
  const openCount = safetyDoors.filter(door => door.doorState === 'open').length;
  const availableCount = safetyDoors.filter(door => door.status !== 'unavailable').length;

  return (
    <div className='page-stack'>
      <section className='page-introduction'>
        <div>
          <span className='section-kicker'>Safety Doors Component</span>
          <h2>Monitorowane drzwi i bramy</h2>
          <p>
            Lista zawiera wyłącznie wejścia skonfigurowane w SafetyComponent. Alarm staje się aktywny po ciągłym otwarciu dłuższym
            niż indywidualny timeout.
          </p>
        </div>
        <div className='page-introduction-stat'>
          <strong>{safetyDoors.length}</strong>
          <span>skonfigurowanych wejść</span>
        </div>
      </section>

      <section aria-label='Podsumowanie Safety Doors' className='metric-strip'>
        <DoorMetric label='Alarm aktywny' value={activeCount} detail='przekroczony timeout' />
        <DoorMetric label='Otwarte' value={openCount} detail='łącznie z czasem tolerancji' />
        <DoorMetric label='Dostępne' value={availableCount} detail={`z ${safetyDoors.length} skonfigurowanych`} />
      </section>

      {safetyDoors.length > 0 ? (
        <section aria-live='polite' className='safety-door-grid'>
          {safetyDoors.map(door => (
            <SafetyDoorCard door={door} key={door.entityId} />
          ))}
        </section>
      ) : (
        <section className='panel empty-state page-empty-state'>
          <div className='empty-state-icon'>
            <Icon name='door' size={30} />
          </div>
          <strong>Brak skonfigurowanych Safety Doors</strong>
          <p>Dodaj drzwi lub bramę w konfiguracji backendu, aby rozpocząć monitorowanie.</p>
        </section>
      )}
    </div>
  );
}

function DoorMetric({ label, value, detail }: { label: string; value: number; detail: string }) {
  return (
    <div className='metric-item'>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function SafetyDoorCard({ door }: { door: SafetyDoorView }) {
  const presentation = doorPresentation(door);

  return (
    <article className={`safety-door-card safety-door-${presentation.tone}`}>
      <div className='safety-door-card-header'>
        <span className='safety-door-card-icon'>
          <Icon name='door' size={22} />
        </span>
        <div>
          <h3>{door.name}</h3>
          <code>{door.sourceEntityId || door.entityId}</code>
        </div>
        <StatusBadge pulse={door.status === 'active'} tone={presentation.tone}>
          {presentation.label}
        </StatusBadge>
      </div>

      <div className='safety-door-state'>
        <strong>{presentation.headline}</strong>
        <span>{presentation.detail}</span>
      </div>

      <dl className='safety-door-details'>
        <div>
          <dt>Timeout</dt>
          <dd>{formatDuration(door.timeoutSeconds)}</dd>
        </div>
        <div>
          <dt>Czas otwarcia</dt>
          <dd>{door.doorState === 'open' ? formatDuration(door.openDurationSeconds) : '—'}</dd>
        </div>
        <div>
          <dt>Pozostało</dt>
          <dd>{door.doorState === 'open' && door.status === 'inactive' ? formatDuration(door.remainingSeconds) : '—'}</dd>
        </div>
      </dl>

      <span className='card-updated'>Aktualizacja {formatRelativeTime(door.lastUpdated)}</span>
    </article>
  );
}

function doorPresentation(door: SafetyDoorView): {
  label: string;
  headline: string;
  detail: string;
  tone: 'safe' | 'danger' | 'warning' | 'muted';
} {
  if (door.status === 'active') {
    return {
      label: 'Aktywny',
      headline: 'Timeout przekroczony',
      detail: 'Drzwi lub brama nadal pozostają otwarte.',
      tone: 'danger',
    };
  }
  if (door.status === 'blocked') {
    const conditionDetail =
      door.conditionEntityId && door.conditionState
        ? `Warunek ${door.conditionEntityId} ma stan „${door.conditionState}”.`
        : 'Skonfigurowany warunek blokuje monitorowanie.';
    return {
      label: 'Wstrzymane',
      headline: 'Monitoring zablokowany',
      detail: `${conditionDetail} Timeout nie jest liczony.`,
      tone: 'muted',
    };
  }
  if (door.status === 'unavailable' || door.status === 'unknown') {
    return {
      label: 'Brak danych',
      headline: 'Stan niedostępny',
      detail: 'Nie można potwierdzić aktualnego stanu wejścia.',
      tone: 'muted',
    };
  }
  if (door.doorState === 'open') {
    return {
      label: 'Odliczanie',
      headline: 'Otwarte',
      detail: `Alarm uaktywni się za ${formatDuration(door.remainingSeconds)}.`,
      tone: 'warning',
    };
  }
  return {
    label: 'Bezpieczne',
    headline: 'Zamknięte',
    detail: 'Timeout nie jest aktywny.',
    tone: 'safe',
  };
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return '—';
  const safeSeconds = Math.max(0, Math.round(seconds));
  if (safeSeconds < 60) return `${safeSeconds} s`;
  const minutes = Math.floor(safeSeconds / 60);
  const remainder = safeSeconds % 60;
  return remainder === 0 ? `${minutes} min` : `${minutes} min ${remainder} s`;
}
