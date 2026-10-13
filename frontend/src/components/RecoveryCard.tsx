import { formatRelativeTime, type RecoveryStatus, type RecoveryView, type StatusTone } from '../domain/safety.js';
import { recoveryConfirmationBlock, recoveryReportBlock } from '../domain/recoveryConfirmation.js';
import Icon from './Icon.js';
import StatusBadge from './StatusBadge.js';

export type RecoveryRequest = 'consent' | 'report';

interface RecoveryCardProps {
  recovery: RecoveryView;
  connected: boolean;
  submitting?: boolean;
  submitted?: RecoveryRequest;
  error?: string;
  onRequest: (request: RecoveryRequest) => void;
  onSelectEntity?: (entityId: string) => void;
  compact?: boolean;
}

const statuses: Record<RecoveryStatus, { label: string; tone: StatusTone }> = {
  to_perform: { label: 'Do wykonania', tone: 'warning' },
  awaiting_confirmation: { label: 'Wymaga zgody', tone: 'warning' },
  executing: { label: 'W trakcie', tone: 'info' },
  confirmed: { label: 'Potwierdzone', tone: 'safe' },
  failed: { label: 'Niepowodzenie', tone: 'danger' },
  timed_out: { label: 'Przekroczono czas', tone: 'danger' },
  do_not_perform: { label: 'Brak potrzeby', tone: 'safe' },
  unavailable: { label: 'Niedostępna', tone: 'muted' },
  unknown: { label: 'Stan nieznany', tone: 'muted' },
};

function evidenceTime(value: string): string {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? new Date(parsed).toLocaleString('pl-PL') : 'brak wiarygodnego czasu';
}

function reportSourceLabel(value: string): string {
  return value === 'operator' ? 'użytkownik' : value;
}

/** Shared operator presentation: consent, work reporting and evidence stay distinct. */
export default function RecoveryCard({
  recovery,
  connected,
  submitting = false,
  submitted,
  error,
  onRequest,
  onSelectEntity,
  compact = false,
}: RecoveryCardProps) {
  const expired =
    ['to_perform', 'awaiting_confirmation', 'executing'].includes(recovery.status) &&
    Boolean(
      (recovery.expiresAt !== undefined && (!Number.isFinite(recovery.expiresAt) || recovery.expiresAt * 1000 <= Date.now())) ||
        (recovery.validUntil !== undefined &&
          (!Number.isFinite(Date.parse(recovery.validUntil)) || Date.parse(recovery.validUntil) <= Date.now()))
    );
  const presentation =
    recovery.blockedReason || expired ? { label: 'Wstrzymane', tone: 'warning' as StatusTone } : statuses[recovery.status];
  const consentBlock = recoveryConfirmationBlock(recovery, connected);
  const reportBlock = recoveryReportBlock(recovery, connected);
  const showReport =
    recovery.executionPolicy === 'manual' && recovery.manualReportAllowed === true && recovery.completionCondition !== 'advisory';
  const reported = Boolean(recovery.reportedAt) || Boolean(recovery.reportStatus && recovery.reportStatus !== 'not_reported');
  const block =
    recovery.blockedReason ||
    (expired ? 'Propozycja wygasła. Oczekiwanie na aktualne zalecenie.' : null) ||
    (recovery.status === 'awaiting_confirmation' ? consentBlock : showReport && !reported ? reportBlock : null);

  return (
    <article className={`recovery-card recovery-${presentation.tone}`} data-proposal-id={recovery.proposalId}>
      <span className='recovery-card-icon'>
        <Icon name='recovery' size={20} />
      </span>
      <div className='recovery-card-copy'>
        <strong>{recovery.name}</strong>
        <p>
          {expired
            ? 'Zalecenie wygasło. Poczekaj na aktualną propozycję.'
            : ['unavailable', 'unknown'].includes(recovery.status)
              ? 'Nie można potwierdzić aktualnego zalecenia. Sprawdź dostępność monitoringu.'
              : recovery.instruction || recovery.description || 'Brak instrukcji wykonania.'}
        </p>
        <small>
          {recovery.executionPolicy === 'manual'
            ? 'Wykonuje: użytkownik'
            : recovery.executionPolicy === 'user_confirmed'
              ? 'Wykonuje: system po Twojej zgodzie'
              : recovery.executionPolicy === 'automatic'
                ? 'Wykonuje: system'
                : 'Wykonawca nieznany'}
        </small>
        {!compact && recovery.expectedResult && <small>Oczekiwany rezultat: {recovery.expectedResult}</small>}
        {!compact && recovery.completionCondition === 'advisory' && (
          <small>Instrukcja postępowania. System nie potwierdza jej wykonania.</small>
        )}
        {!compact && recovery.completionCondition === 'operator_report' && (
          <small>Wykonanie tej czynności potwierdza użytkownik. System nie sprawdza jej samodzielnie; zgłoszenie nie usuwa usterki.</small>
        )}
        {!compact && recovery.reason && <small>Powód: {recovery.reason}</small>}
        {!compact && recovery.source && <small>Źródło zalecenia: {recovery.source}</small>}
        {!compact && recovery.validUntil && <small>Ważne do {evidenceTime(recovery.validUntil)}</small>}
        {error && <small className='recovery-error'>{error}</small>}
        {block && <small className='recovery-error'>Działanie wstrzymane: {block}</small>}
        {submitted && (
          <small>
            {submitted === 'report'
              ? 'Zgłoszenie wysłane. Oczekiwanie na odpowiedź systemu.'
              : 'Zgoda wysłana. Oczekiwanie na odpowiedź systemu.'}
          </small>
        )}
        {reported && recovery.status !== 'confirmed' && <small>Zgłoszono wykonanie. System nadal czeka na potwierdzenie rezultatu.</small>}
        {!compact && recovery.reportedAt && (
          <small>
            Zgłoszenie użytkownika: {evidenceTime(recovery.reportedAt)}
            {recovery.reportSource ? ` · ${reportSourceLabel(recovery.reportSource)}` : ''}
          </small>
        )}
        {!compact && recovery.evidenceAt && (
          <small>
            Dowód rezultatu: {evidenceTime(recovery.evidenceAt)}
            {recovery.evidenceSource ? ` · ${recovery.evidenceSource}` : ''}
          </small>
        )}
        {!compact && <small>Zmiana {formatRelativeTime(recovery.lastChanged)}</small>}
        {!compact && recovery.latestOutcome && (
          <small>
            Ostatni wynik:{' '}
            {
              { completed: 'zakończono', withdrawn: 'wycofano zalecenie', failed: 'niepowodzenie', timed_out: 'przekroczono czas' }[
                recovery.latestOutcome.outcome
              ]
            }
            . {formatRelativeTime(recovery.latestOutcome.recordedAt)}
          </small>
        )}
        {!compact && recovery.latestOutcome?.reportedAt && (
          <small>
            Zgłoszenie dla ostatniego wyniku: {evidenceTime(recovery.latestOutcome.reportedAt)}
            {recovery.latestOutcome.reportSource ? ` · ${reportSourceLabel(recovery.latestOutcome.reportSource)}` : ''}
          </small>
        )}
        {!compact && recovery.latestOutcome?.evidenceAt && (
          <small>
            Dowód ostatniego wyniku: {evidenceTime(recovery.latestOutcome.evidenceAt)}
            {recovery.latestOutcome.evidenceSource ? ` · ${recovery.latestOutcome.evidenceSource}` : ''}
          </small>
        )}
      </div>
      <StatusBadge tone={presentation.tone}>{presentation.label}</StatusBadge>
      {!compact && recovery.status === 'awaiting_confirmation' && (
        <button
          className='recovery-confirm-button'
          disabled={submitting || submitted === 'consent' || Boolean(consentBlock)}
          onClick={() => onRequest('consent')}
          type='button'
        >
          {submitting ? 'Wysyłanie…' : 'Zezwól na wykonanie'}
        </button>
      )}
      {!compact && showReport && ['to_perform', 'executing'].includes(recovery.status) && (
        <button
          className='recovery-confirm-button'
          disabled={submitting || submitted === 'report' || Boolean(reportBlock)}
          onClick={() => onRequest('report')}
          type='button'
        >
          {reported ? 'Wykonanie zgłoszone' : submitting ? 'Wysyłanie…' : 'Zgłoś wykonanie'}
        </button>
      )}
      {onSelectEntity && (
        <button
          className='text-button recovery-confirm-button'
          onClick={() => onSelectEntity(recovery.entityId)}
          type='button'
          aria-label={`Pokaż szczegóły ${recovery.name}`}
        >
          Szczegóły i historia
        </button>
      )}
    </article>
  );
}
