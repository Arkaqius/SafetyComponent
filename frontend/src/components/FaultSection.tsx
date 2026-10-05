import { useEffect, useMemo, useState } from 'react';
import { useHass } from '@hakit/core';
import {
  LEVEL_PRESENTATION,
  formatRelativeTime,
  localizedEntityState,
  type FaultStatus,
  type FaultView,
  type StatusTone,
} from '../domain/safety';
import Icon from './Icon';
import HelpTooltip from './HelpTooltip';
import StatusBadge from './StatusBadge';
import { notificationAcknowledgementEvent } from '../domain/notificationHistory';

type FaultFilter = 'attention' | 'active' | 'shadowed' | 'all';

interface FaultSectionProps {
  faults: FaultView[];
  acknowledgedTags?: ReadonlySet<string>;
  compact?: boolean;
  onSelectEntity?: (entityId: string) => void;
}

const statusPresentation: Record<FaultStatus, { label: string; tone: StatusTone }> = {
  not_evaluated: { label: 'Nieoceniona', tone: 'muted' },
  pass: { label: 'Warunek ustąpił', tone: 'safe' },
  pending_failure: { label: 'Potwierdzanie zagrożenia', tone: 'warning' },
  fail: { label: 'Zagrożenie potwierdzone', tone: 'danger' },
  pending_recovery: { label: 'Potwierdzanie ustąpienia', tone: 'warning' },
  unevaluable: { label: 'Brak wiarygodnej oceny', tone: 'warning' },
  inhibited: { label: 'Czasowo wyłączona', tone: 'warning' },
  disabled: { label: 'Wyłączona', tone: 'muted' },
  unavailable: { label: 'Niedostępna', tone: 'muted' },
  unknown: { label: 'Nieznana', tone: 'muted' },
};

const filters: Array<{ value: FaultFilter; label: string }> = [
  { value: 'attention', label: 'Wymagające uwagi' },
  { value: 'active', label: 'Aktywne' },
  { value: 'shadowed', label: 'Przesłonięte' },
  { value: 'all', label: 'Wszystkie' },
];

export default function FaultSection({ acknowledgedTags = new Set(), faults, compact = false, onSelectEntity }: FaultSectionProps) {
  const [filter, setFilter] = useState<FaultFilter>('attention');
  const [query, setQuery] = useState('');

  const filteredFaults = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase('pl');
    return faults.filter(fault => {
      const matchesFilter =
        filter === 'all' ||
        (filter === 'active' && fault.active) ||
        (filter === 'shadowed' && fault.shadowedBy.length > 0) ||
        (filter === 'attention' &&
          (fault.active !== false || ['unevaluable', 'pending_failure', 'unavailable', 'unknown'].includes(fault.status)));
      const matchesQuery =
        normalizedQuery.length === 0 ||
        [fault.name, fault.description, fault.entityId, ...fault.locations].join(' ').toLocaleLowerCase('pl').includes(normalizedQuery);
      return matchesFilter && matchesQuery;
    });
  }, [faults, filter, query]);

  const activeCount = faults.filter(fault => fault.active).length;

  return (
    <section className='panel fault-panel'>
      <div className='panel-header'>
        <div>
          <h2 className='label-with-help'>
            Aktywne zdarzenia{' '}
            <HelpTooltip
              label='Poziomy i stany usterek'
              text='L1: alarm krytyczny, L2: zagrożenie, L3: ostrzeżenie, L4: informacja. Usterka przesłonięta ustępuje miejsca ważniejszemu zdarzeniu, lecz nie oznacza to jej ustąpienia. Potwierdzenie powiadomienia nie usuwa usterki.'
            />
          </h2>
        </div>
        <span className={`count-badge${activeCount > 0 ? ' count-badge-alert' : ''}`}>
          {activeCount === 1 ? '1 aktywne' : `${activeCount} aktywnych`}
        </span>
      </div>

      {!compact && (
        <div className='filter-row' role='group' aria-label='Filtr usterek'>
          {filters.map(item => (
            <button
              aria-pressed={filter === item.value}
              className={`filter-button${filter === item.value ? ' filter-button-active' : ''}`}
              key={item.value}
              onClick={() => setFilter(item.value)}
              type='button'
            >
              {item.label}
            </button>
          ))}
        </div>
      )}

      {!compact && (
        <label className='search-field'>
          <span className='sr-only'>Szukaj usterek</span>
          <Icon name='alert' size={17} />
          <input
            onChange={event => setQuery(event.target.value)}
            placeholder='Szukaj po nazwie, lokalizacji lub encji…'
            type='search'
            value={query}
          />
        </label>
      )}

      <div aria-live='polite' className='fault-list'>
        {filteredFaults.length > 0 ? (
          filteredFaults.map(fault => (
            <FaultCard
              acknowledged={acknowledgedTags.has(fault.notificationTag)}
              fault={fault}
              key={fault.entityId}
              onSelectEntity={onSelectEntity}
            />
          ))
        ) : (
          <div className='empty-state'>
            <div className='empty-state-icon'>
              <Icon name='shield' size={28} />
            </div>
            <strong>{faults.length === 0 ? 'Brak encji usterek' : 'Brak usterek w tym widoku'}</strong>
            <p>
              {faults.length === 0
                ? 'Brak danych o usterkach z Home Assistanta.'
                : 'System nie raportuje zdarzeń spełniających wybrany filtr.'}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}

function FaultCard({
  acknowledged,
  fault,
  onSelectEntity,
}: {
  acknowledged: boolean;
  fault: FaultView;
  onSelectEntity?: (entityId: string) => void;
}) {
  const status = statusPresentation[fault.status];
  const level = fault.level ? LEVEL_PRESENTATION[fault.level] : undefined;
  const cardTone = fault.active === true || fault.latched === true ? (fault.level === 1 ? 'critical' : 'danger') : status.tone;
  const connection = useHass(store => store.connection);
  const connected = useHass(store => store.connectionStatus === 'connected' && store.ready);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');
  const canAcknowledge =
    fault.active && fault.shadowedBy.length === 0 && Boolean(fault.notificationTag) && Boolean(fault.level && fault.level <= 3);

  useEffect(() => {
    if (!acknowledged) setSubmitted(false);
  }, [acknowledged, fault.notificationTag]);

  const acknowledgeFault = async (): Promise<void> => {
    if (!connection || !connected || !fault.notificationTag) {
      setError('Brak połączenia z Home Assistantem.');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await connection.sendMessagePromise<unknown>(notificationAcknowledgementEvent(fault.notificationTag));
      setSubmitted(true);
    } catch {
      setError('Nie udało się wysłać potwierdzenia. Spróbuj ponownie.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <details
      className={`fault-card fault-${cardTone}`}
      data-entity-id={fault.entityId}
      open={fault.active === true || fault.latched === true}
    >
      <summary>
        <span className='fault-card-icon'>
          <Icon name='alert' size={20} />
        </span>
        <span className='fault-card-title'>
          <strong>{fault.name}</strong>
          <small>{fault.locations.length > 0 ? fault.locations.join(' · ') : 'Brak przypisanej lokalizacji'}</small>
        </span>
        <StatusBadge tone={fault.category === 'H' ? 'danger' : fault.category === 'D' ? 'info' : 'muted'}>
          {fault.category === 'H' ? 'Zagrożenie H' : fault.category === 'D' ? 'Diagnostyka D' : 'Brak kategorii'}
        </StatusBadge>
        {level && <span className={`level-chip status-${level.tone}`}>{level.shortLabel}</span>}
        {fault.active && <StatusBadge tone='danger'>Aktywna</StatusBadge>}
        {fault.latched && <StatusBadge tone='critical'>Zatrzaśnięta</StatusBadge>}
        {fault.shadowedBy.length > 0 && <StatusBadge tone='warning'>Przesłonięta</StatusBadge>}
        <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
        <Icon className='details-chevron' name='chevron' size={17} />
      </summary>
      <div className='fault-card-details'>
        <p>{fault.description || 'Brak dodatkowego opisu dla tej usterki.'}</p>
        <dl className='details-grid'>
          <div>
            <dt>Poziom</dt>
            <dd>{level?.label ?? 'Nie podano'}</dd>
          </div>
          <div>
            <dt>Stan</dt>
            <dd>{localizedEntityState(fault.entityId, fault.state)}</dd>
          </div>
          <div>
            <dt>Kategoria</dt>
            <dd>
              {fault.category === 'H'
                ? 'H — warunek zagrożenia'
                : fault.category === 'D'
                  ? 'D — utrata diagnostyki lub pokrycia'
                  : 'Nie podano'}
            </dd>
          </div>
          <div>
            <dt>Aktywacja</dt>
            <dd>{fault.active === null ? 'Nieznana' : fault.active ? 'Aktywna' : 'Nieaktywna'}</dd>
          </div>
          <div>
            <dt>Latch</dt>
            <dd>{fault.latched === null ? 'Brak danych' : fault.latched ? 'Aktywny — wymaga poprawnego resetu' : 'Nieaktywny'}</dd>
          </div>
          {fault.shadowedBy.length > 0 && (
            <div>
              <dt>Przesłonięta przez</dt>
              <dd>{fault.shadowedBy.join(', ')}</dd>
            </div>
          )}
          <div>
            <dt>Ostatnia zmiana</dt>
            <dd>{formatRelativeTime(fault.lastChanged)}</dd>
          </div>
        </dl>
        {fault.contributors.length > 0 && (
          <div className='fault-diagnostic-block'>
            <strong>Źródła oceny</strong>
            <ul className='fault-contributor-list'>
              {fault.contributors.map(contributor => (
                <li className={fault.activeContributors.includes(contributor) ? 'fault-contributor-active' : ''} key={contributor}>
                  <code>{contributor}</code>
                  <span>{fault.activeContributors.includes(contributor) ? 'Aktywny contributor' : 'Powiązany contributor'}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {fault.diagnosticData.freezeFrame && (
          <DiagnosticRecord label='Freeze frame — pierwsza aktywacja' record={fault.diagnosticData.freezeFrame} />
        )}
        {fault.diagnosticData.extendedData && <DiagnosticRecord label='Dane rozszerzone' record={fault.diagnosticData.extendedData} />}
        {canAcknowledge && (
          <div className='fault-acknowledgement'>
            <button
              className='fault-acknowledge-button'
              disabled={!connected || acknowledged || submitted || submitting}
              onClick={acknowledgeFault}
              type='button'
            >
              {acknowledged ? 'Potwierdzono' : submitted ? 'Potwierdzenie wysłane' : submitting ? 'Wysyłanie…' : 'Potwierdź powiadomienie'}
            </button>
            <small>Potwierdzenie wycisza ponowienia, ale nie usuwa aktywnej usterki.</small>
          </div>
        )}
        {error && <small className='recovery-error'>{error}</small>}
        <details className='technical-details'>
          <summary>Diagnostyka</summary>
          <code>{fault.entityId}</code>
        </details>
        {onSelectEntity && (
          <button className='text-button fault-details-button' onClick={() => onSelectEntity(fault.entityId)} type='button'>
            Pełne szczegóły i historia <Icon name='history' size={15} />
          </button>
        )}
      </div>
    </details>
  );
}

function DiagnosticRecord({ label, record }: { label: string; record: Record<string, unknown> }) {
  return (
    <div className='fault-diagnostic-block'>
      <strong>{label}</strong>
      <dl className='details-grid'>
        {Object.entries(record).map(([key, value]) => (
          <div key={key}>
            <dt>{humanizeDiagnosticKey(key)}</dt>
            <dd>{formatDiagnosticValue(value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function formatDiagnosticValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Tak' : 'Nie';
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  return JSON.stringify(value);
}

function humanizeDiagnosticKey(value: string): string {
  return value
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/^\w/, letter => letter.toUpperCase());
}
