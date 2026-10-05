import { useState } from 'react';
import { useHass } from '@hakit/core';
import { formatRelativeTime, recoveryNeedsAttention, type RecoveryStatus, type RecoveryView, type StatusTone } from '../domain/safety';
import Icon from './Icon';
import HelpTooltip from './HelpTooltip';
import StatusBadge from './StatusBadge';
import { recoveryConfirmationBlock } from '../domain/recoveryConfirmation';

interface ActionsListProps {
  recoveries: RecoveryView[];
  onSelectEntity?: (entityId: string) => void;
}

const statusPresentation: Record<RecoveryStatus, { label: string; tone: StatusTone }> = {
  to_perform: { label: 'Do wykonania', tone: 'warning' },
  awaiting_confirmation: { label: 'Wymaga potwierdzenia', tone: 'warning' },
  executing: { label: 'W trakcie', tone: 'info' },
  confirmed: { label: 'Potwierdzone', tone: 'safe' },
  failed: { label: 'Niepowodzenie', tone: 'danger' },
  timed_out: { label: 'Przekroczono czas', tone: 'danger' },
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
          <h2 className='label-with-help'>
            Zalecenia i działania{' '}
            <HelpTooltip
              label='Zalecenia i potwierdzenia'
              text='Instrukcja opisuje zalecane postępowanie. Gdy działanie wymaga potwierdzenia, przycisk wysyła zgodę do systemu; sam frontend nie wykonuje działania. Propozycja może wygasnąć lub zostać wstrzymana. Potwierdzenie powiadomienia o usterce jest osobną czynnością.'
            />
          </h2>
        </div>
        <span className={`count-badge${requiringAttention.length > 0 ? ' count-badge-warning' : ''}`}>{countLabel}</span>
      </div>

      <div className='panel-toolbar'>
        {recoveries.length > 0 && (
          <button className='text-button' onClick={() => setShowAll(value => !value)} type='button'>
            {showAll ? 'Pokaż wymagające uwagi' : `Pokaż wszystkie (${recoveries.length})`}
          </button>
        )}
      </div>

      <div aria-live='polite' className='recovery-list'>
        {visibleRecoveries.length > 0 ? (
          visibleRecoveries.map(recovery => <RecoveryCard key={recovery.proposalId} onSelectEntity={onSelectEntity} recovery={recovery} />)
        ) : (
          <div className='empty-state'>
            <div className='empty-state-icon'>
              <Icon name='recovery' size={28} />
            </div>
            <strong>{recoveries.length === 0 ? 'Brak danych o zaleceniach' : 'Brak działań wymagających uwagi'}</strong>
            <p>
              {recoveries.length === 0
                ? 'System nie przekazał zaleceń. Sprawdź dostępność monitoringu.'
                : 'System nie zgłasza obecnie działania wymagającego uwagi.'}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}

function RecoveryCard({ recovery, onSelectEntity }: { recovery: RecoveryView; onSelectEntity?: (entityId: string) => void }) {
  const presentation = statusPresentation[recovery.status];
  const connection = useHass(store => store.connection);
  const connected = useHass(store => store.connectionStatus === 'connected' && store.ready);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const blockedReason = recoveryConfirmationBlock(recovery, connected);

  const confirmRecovery = async (): Promise<void> => {
    const block = recoveryConfirmationBlock(recovery, connected);
    if (!connection || block) {
      setError(block ?? 'Brak połączenia z Home Assistantem.');
      return;
    }
    if (!window.confirm(`Czy na pewno chcesz wykonać tę akcję?\n${recovery.instruction}`)) return;
    const afterConfirmation = recoveryConfirmationBlock(
      recovery,
      useHass.getState().connectionStatus === 'connected' && useHass.getState().ready
    );
    if (afterConfirmation) {
      setError(afterConfirmation);
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await connection.sendMessagePromise<unknown>({
        type: 'fire_event',
        event_type: 'safety_recovery_confirm',
        event_data: {
          proposal_id: recovery.proposalId,
          confirmation_token: recovery.confirmationToken,
        },
      });
    } catch {
      setError('Nie udało się wysłać potwierdzenia. Spróbuj ponownie.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <article className={`recovery-card recovery-${presentation.tone}${onSelectEntity ? ' entity-card-clickable' : ''}`}>
      <span className='recovery-card-icon'>
        <Icon name='recovery' size={20} />
      </span>
      <div className='recovery-card-copy'>
        <strong>{recovery.name}</strong>
        <p>{recovery.instruction || recovery.description || 'Brak instrukcji wykonania.'}</p>
        {(recovery.reason || recovery.source) && <small>{recovery.reason ? `Powód: ${recovery.reason}` : ''}</small>}
        {recovery.validUntil && <small>Ważne do {new Date(recovery.validUntil).toLocaleString('pl-PL')}</small>}
        {error && <small className='recovery-error'>{error}</small>}
        {recovery.status === 'awaiting_confirmation' && blockedReason && <small className='recovery-error'>{blockedReason}</small>}
        <small>Zmiana {formatRelativeTime(recovery.lastChanged)}</small>
      </div>
      <StatusBadge tone={presentation.tone}>{presentation.label}</StatusBadge>
      {recovery.status === 'awaiting_confirmation' && (
        <button className='recovery-confirm-button' disabled={submitting || Boolean(blockedReason)} onClick={confirmRecovery} type='button'>
          {submitting ? 'Wysyłanie…' : 'Potwierdź zamknięcie'}
        </button>
      )}
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
