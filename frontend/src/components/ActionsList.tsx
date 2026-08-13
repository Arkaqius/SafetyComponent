import { useState } from 'react';
import { formatRelativeTime, recoveryNeedsAttention, type RecoveryStatus, type RecoveryView, type StatusTone } from '../domain/safety';
import Icon from './Icon';
import StatusBadge from './StatusBadge';

interface ActionsListProps {
  recoveries: RecoveryView[];
  onSelectEntity?: (entityId: string) => void;
}

const statusPresentation: Record<RecoveryStatus, { label: string; tone: StatusTone }> = {
  to_perform: { label: 'Do wykonania', tone: 'warning' },
  do_not_perform: { label: 'Brak potrzeby', tone: 'safe' },
  unavailable: { label: 'Niedostępna', tone: 'muted' },
  unknown: { label: 'Stan nieznany', tone: 'muted' },
};

export default function ActionsList({ recoveries, onSelectEntity }: ActionsListProps) {
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
          <span className='section-kicker'>Działania naprawcze</span>
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
          visibleRecoveries.map(recovery => <RecoveryCard key={recovery.entityId} onSelectEntity={onSelectEntity} recovery={recovery} />)
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

function RecoveryCard({ recovery, onSelectEntity }: { recovery: RecoveryView; onSelectEntity?: (entityId: string) => void }) {
  const presentation = statusPresentation[recovery.status];

  return (
    <article className={`recovery-card recovery-${presentation.tone}${onSelectEntity ? ' entity-card-clickable' : ''}`}>
      <span className='recovery-card-icon'>
        <Icon name='recovery' size={20} />
      </span>
      <div className='recovery-card-copy'>
        <strong title={recovery.entityId}>{recovery.name}</strong>
        <p>{recovery.description || 'Brak dodatkowego opisu.'}</p>
        <small>Zmiana {formatRelativeTime(recovery.lastChanged)}</small>
        <code>{recovery.entityId}</code>
      </div>
      <StatusBadge tone={presentation.tone}>{presentation.label}</StatusBadge>
      {onSelectEntity && (
        <button
          aria-label={`Pokaż szczegóły ${recovery.name}`}
          className='entity-card-overlay-button'
          onClick={() => onSelectEntity(recovery.entityId)}
          type='button'
        />
      )}
    </article>
  );
}
