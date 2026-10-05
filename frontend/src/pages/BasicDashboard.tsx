import { useCallback, useRef, useState } from 'react';
import ActionsList from '../components/ActionsList';
import HelpTooltip from '../components/HelpTooltip';
import Icon from '../components/Icon';
import ModalDialog from '../components/ModalDialog';
import { basicDashboardItems } from '../domain/basicDashboard';
import { getCoverageView } from '../domain/coverage';
import { recoveryConfirmationBlock } from '../domain/recoveryConfirmation';
import { formatRelativeTime } from '../domain/safety';
import { useSafetyEntities } from '../hooks/useSafetyEntities';

export default function BasicDashboard({ onExpand }: { onExpand: () => void }) {
  const { summary, connection, entities, faults, recoveries, entityMonitorSummary } = useSafetyEntities();
  const { primaryFault, activeFaultCount, primaryRecovery, attentionRecoveries } = basicDashboardItems(faults, recoveries);
  const connected = connection.ready && !connection.cannotConnect;
  const coverage = getCoverageView(connected ? entities : {});
  const monitoringLimited =
    !connected ||
    coverage.state !== 'FULL' ||
    entityMonitorSummary.total === 0 ||
    entityMonitorSummary.unavailable + entityMonitorSummary.degraded + entityMonitorSummary.stale > 0;
  const confirmationBlock =
    primaryRecovery?.status === 'awaiting_confirmation' ? recoveryConfirmationBlock(primaryRecovery, connected) : null;
  const expired = Boolean(
    primaryRecovery &&
      ((primaryRecovery.expiresAt !== undefined &&
        (!Number.isFinite(primaryRecovery.expiresAt) || primaryRecovery.expiresAt * 1000 <= Date.now())) ||
        (primaryRecovery.validUntil !== undefined &&
          (!Number.isFinite(Date.parse(primaryRecovery.validUntil)) || Date.parse(primaryRecovery.validUntil) <= Date.now())))
  );
  const uncertainRecovery = primaryRecovery && ['unknown', 'unavailable'].includes(primaryRecovery.status);
  const [actionsOpen, setActionsOpen] = useState(false);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const closeActions = useCallback(() => setActionsOpen(false), []);

  return (
    <div className='page-stack basic-dashboard'>
      <section aria-label='Bieżąca ocena domu' className={`basic-assessment basic-assessment-${summary.tone}`}>
        <div className='basic-assessment-heading'>
          <span className='basic-state-icon'>
            <Icon name={summary.tone === 'safe' ? 'shield' : 'alert'} size={32} />
          </span>
          <div aria-live='polite'>
            <h2>{summary.label}</h2>
            <p>{connected ? summary.detail : 'Bieżącego stanu nie można potwierdzić.'}</p>
          </div>
          <HelpTooltip
            label='Ocena bezpieczeństwa'
            text='Ocena obejmuje monitorowane źródła. Brak alarmów nie potwierdza dostępności wszystkich czujników. Ograniczenia monitoringu i brak połączenia są pokazywane osobno.'
          />
        </div>
        {primaryFault && (
          <div className='basic-incident'>
            <h3>{primaryFault.name}</h3>
            <p>{primaryFault.locations.join(' · ') || 'Lokalizacja niepodana'}</p>
            {!connected && <small>Ostatnie znane zdarzenie</small>}
          </div>
        )}
        <div className={`basic-monitoring${monitoringLimited ? ' basic-monitoring-limited' : ''}`}>
          <Icon name={monitoringLimited ? 'alert' : 'shield'} size={18} />
          <span>
            {!connected ? 'Odczyty z pamięci' : monitoringLimited ? 'Monitoring ma ograniczenia' : 'Monitorowane źródła dostępne'}
          </span>
          <HelpTooltip
            label='Pokrycie monitoringu'
            text={
              !connected
                ? 'Połączenie nie dostarczyło bieżących danych. Zapamiętane odczyty nie potwierdzają obecnego bezpieczeństwa.'
                : coverage.detail + ' Szczegóły dostępności źródeł znajdziesz w widoku rozszerzonym.'
            }
          />
        </div>
      </section>

      <section aria-labelledby='basic-action-title' className='basic-action'>
        <h3 id='basic-action-title'>{!connected && primaryRecovery ? 'Ostatnie znane zalecenie' : 'Co zrobić teraz'}</h3>
        {primaryRecovery ? (
          <>
            <strong>{primaryRecovery.name}</strong>
            <p>
              {expired
                ? 'Zalecenie wygasło. Poczekaj na aktualną propozycję.'
                : uncertainRecovery
                  ? 'Nie można potwierdzić aktualnego zalecenia. Sprawdź jego szczegóły.'
                  : primaryRecovery.instruction ||
                    primaryRecovery.description ||
                    'System nie przekazał instrukcji. Sprawdź szczegóły zalecenia.'}
            </p>
            {confirmationBlock && <p className='basic-action-note'>{confirmationBlock}</p>}
            {(primaryRecovery.status === 'failed' || primaryRecovery.status === 'timed_out') && (
              <p className='basic-action-note'>Działanie nie zakończyło się poprawnie. Sprawdź szczegóły.</p>
            )}
            {primaryRecovery.status === 'executing' && (
              <p className='basic-action-note'>Działanie w trakcie — wynik nie jest jeszcze potwierdzony.</p>
            )}
            <button className='basic-action-button' onClick={() => setActionsOpen(true)} type='button'>
              {primaryRecovery.status === 'awaiting_confirmation' ? 'Sprawdź i potwierdź działanie' : 'Zobacz zalecenia'}
              {attentionRecoveries.length > 1 ? ` (${attentionRecoveries.length})` : ''}
            </button>
          </>
        ) : (
          <p>
            {!connected
              ? 'Aktualne zalecenia są niedostępne do czasu odzyskania połączenia.'
              : summary.tone === 'safe'
                ? 'Nie ma zgłoszonego działania do wykonania.'
                : 'Brak bieżącego zalecenia. Sprawdź szczegóły zdarzenia w widoku rozszerzonym.'}
          </p>
        )}
      </section>

      <footer className='basic-dashboard-footer'>
        <span>
          {connected ? `Aktualizacja ${formatRelativeTime(connection.lastUpdated?.toISOString())}` : 'Oczekiwanie na bieżące dane'}
        </span>
        <button className='text-button' onClick={onExpand} type='button'>
          {activeFaultCount > 1 ? `Wszystkie zdarzenia (${activeFaultCount})` : 'Szczegóły i monitoring'}
        </button>
      </footer>

      <ModalDialog open={actionsOpen} onClose={closeActions} labelledBy='basic-actions-dialog-title' initialFocus={closeButtonRef}>
        <div className='entity-dialog-header'>
          <h2 id='basic-actions-dialog-title'>Zalecenia i działania</h2>
          <button aria-label='Zamknij zalecenia' className='icon-button' onClick={closeActions} ref={closeButtonRef} type='button'>
            <Icon name='close' />
          </button>
        </div>
        <ActionsList recoveries={attentionRecoveries} />
      </ModalDialog>
    </div>
  );
}
