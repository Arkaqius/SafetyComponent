import { useState } from 'react';
import { formatRelativeTime, recoveryNeedsAttention, type RecoveryStatus, type RecoveryView, type StatusTone } from '../domain/safety';
import Icon from './Icon';
import StatusBadge from './StatusBadge';

interface ActionsListProps {
  recoveries: RecoveryView[];
}

const statusPresentation: Record<RecoveryStatus, { label: string; tone: StatusTone }> = {
  to_perform: { label: 'Do wykonania', tone: 'warning' },
  do_not_perform: { label: 'Brak potrzeby', tone: 'safe' },
  unavailable: { label: 'Niedostępna', tone: 'muted' },
  unknown: { label: 'Stan nieznany', tone: 'muted' },
};

export default function ActionsList({ recoveries }: ActionsListProps) {
  const [showAll, setShowAll] = useState(false);
  const actionable = recoveries.filter(recovery => recovery.status === 'to_perform');
  const requiringAttention = recoveries.filter(recoveryNeedsAttention);
  const visibleRecoveries = showAll ? recoveries : requiringAttention;
  const countLabel =
    requiringAttention.length === 0
      ? '0 do wykonania'
      : actionable.length > 0 && actionable.length === requiringAttention.length
        ? `${actionable.length} do wykonania`
        : requiringAttention.length === 1
          ? '1 wymaga uwagi'
          : `${requiringAttention.length} wymagają uwagi`;

  return (
    <section className='panel recovery-panel'>
      <div className='panel-header'>
        <div>
          <span className='section-kicker'>Recovery Manager</span>
          <h2>Działania naprawcze</h2>
        </div>
        <span className={`count-badge${requiringAttention.length > 0 ? ' count-badge-warning' : ''}`}>{countLabel}</span>
      </div>

      <div className='panel-toolbar'>
        <p>Sensory diagnostyczne — wykonanie akcji pozostaje po stronie SafetyComponent.</p>
        {recoveries.length > 0 && (
          <button className='text-button' onClick={() => setShowAll(value => !value)} type='button'>
            {showAll ? 'Pokaż wymagające uwagi' : `Pokaż wszystkie (${recoveries.length})`}
          </button>
        )}
      </div>

      <div aria-live='polite' className='recovery-list'>
        {visibleRecoveries.length > 0 ? (
          visibleRecoveries.map(recovery => <RecoveryCard key={recovery.entityId} recovery={recovery} />)
        ) : (
          <div className='empty-state'>
            <div className='empty-state-icon'>
              <Icon name='recovery' size={28} />
            </div>
            <strong>{recoveries.length === 0 ? 'Brak encji recovery' : 'Brak działań do wykonania'}</strong>
            <p>
              {recoveries.length === 0
                ? 'Home Assistant nie udostępnia obecnie żadnych encji sensor.recovery_*.'
                : 'Wszystkie działania naprawcze mają stan DO_NOT_PERFORM.'}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}

function RecoveryCard({ recovery }: { recovery: RecoveryView }) {
  const presentation = statusPresentation[recovery.status];

  return (
    <article className={`recovery-card recovery-${presentation.tone}`}>
      <span className='recovery-card-icon'>
        <Icon name='recovery' size={20} />
      </span>
      <div className='recovery-card-copy'>
        <strong>{recovery.name}</strong>
        <p>{recovery.description || recovery.entityId}</p>
        <small>Zmiana {formatRelativeTime(recovery.lastChanged)}</small>
      </div>
      <StatusBadge tone={presentation.tone}>{presentation.label}</StatusBadge>
    </article>
  );
}
