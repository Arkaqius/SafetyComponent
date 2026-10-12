import { useState } from 'react';
import { recoveryNeedsAttention, type RecoveryView } from '../domain/safety';
import Icon from './Icon';
import HelpTooltip from './HelpTooltip';
import RecoveryActionCard from './RecoveryActionCard';

interface ActionsListProps {
  recoveries: RecoveryView[];
  onSelectEntity?: (entityId: string) => void;
}

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
              text='Instrukcja opisuje zalecane postępowanie. Zgoda pozwala systemowi wykonać komendę. Zgłoszenie wykonania opisuje Twoją pracę; gdy wymagany jest odczyt urządzenia, system nadal czeka na dowód rezultatu. Potwierdzenie powiadomienia jest osobną czynnością i nie usuwa usterki.'
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
          visibleRecoveries.map(recovery => (
            <RecoveryActionCard key={recovery.proposalId} onSelectEntity={onSelectEntity} recovery={recovery} />
          ))
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
