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
import StatusBadge from './StatusBadge';
import { notificationAcknowledgementEvent } from '../domain/notificationHistory';

type FaultFilter = 'attention' | 'set' | 'shadowed' | 'all';

interface FaultSectionProps {
  faults: FaultView[];
  acknowledgedTags?: ReadonlySet<string>;
  compact?: boolean;
  onSelectEntity?: (entityId: string) => void;
}

const statusPresentation: Record<FaultStatus, { label: string; tone: StatusTone }> = {
  set: { label: 'Aktywna', tone: 'danger' },
  shadowed: { label: 'Przesłonięta', tone: 'warning' },
  cleared: { label: 'Usunięta', tone: 'safe' },
  not_tested: { label: 'Nieprzetestowana', tone: 'muted' },
  unavailable: { label: 'Niedostępna', tone: 'muted' },
  unknown: { label: 'Nieznana', tone: 'muted' },
};

const filters: Array<{ value: FaultFilter; label: string }> = [
  { value: 'attention', label: 'Wymagające uwagi' },
  { value: 'set', label: 'Aktywne' },
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
        fault.status === filter ||
        (filter === 'attention' && ['set', 'shadowed', 'unavailable', 'unknown'].includes(fault.status));
      const matchesQuery =
        normalizedQuery.length === 0 ||
        [fault.name, fault.description, fault.entityId, ...fault.locations].join(' ').toLocaleLowerCase('pl').includes(normalizedQuery);
      return matchesFilter && matchesQuery;
    });
  }, [faults, filter, query]);

  const activeCount = faults.filter(fault => fault.status === 'set').length;

  return (
    <section className='panel fault-panel'>
      <div className='panel-header'>
        <div>
          <span className='section-kicker'>Usterki</span>
          <h2>Usterki systemu</h2>
        </div>
        <span className={`count-badge${activeCount > 0 ? ' count-badge-alert' : ''}`}>{activeCount} aktywnych</span>
      </div>

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
                ? 'Home Assistant nie udostępnia obecnie żadnych encji sensor.fault_*.'
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
  const { useStore } = useHass();
  const connection = useStore(store => store.connection);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');
  const canAcknowledge = fault.status === 'set' && Boolean(fault.notificationTag) && Boolean(fault.level && fault.level <= 3);

  useEffect(() => {
    if (!acknowledged) setSubmitted(false);
  }, [acknowledged, fault.notificationTag]);

  const acknowledgeFault = async (): Promise<void> => {
    if (!connection || !fault.notificationTag) {
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
    <details className={`fault-card fault-${status.tone}`} open={fault.status === 'set'}>
      <summary>
        <span className='fault-card-icon'>
          <Icon name='alert' size={20} />
        </span>
        <span className='fault-card-title'>
          <strong title={fault.entityId}>{fault.name}</strong>
          <small>{fault.locations.length > 0 ? fault.locations.join(' · ') : 'Brak przypisanej lokalizacji'}</small>
          <small className='technical-id'>{fault.entityId}</small>
        </span>
        {level && <span className={`level-chip status-${level.tone}`}>{level.shortLabel}</span>}
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
            <dt>Ostatnia zmiana</dt>
            <dd>{formatRelativeTime(fault.lastChanged)}</dd>
          </div>
        </dl>
        {canAcknowledge && (
          <div className='fault-acknowledgement'>
            <button
              className='fault-acknowledge-button'
              disabled={acknowledged || submitted || submitting}
              onClick={acknowledgeFault}
              type='button'
            >
              {acknowledged ? 'Potwierdzono' : submitted ? 'Potwierdzenie wysłane' : submitting ? 'Wysyłanie…' : 'Potwierdź powiadomienie'}
            </button>
            <small>Potwierdzenie wycisza ponowienia, ale nie usuwa aktywnej usterki.</small>
          </div>
        )}
        {error && <small className='recovery-error'>{error}</small>}
        {onSelectEntity && (
          <button className='text-button fault-details-button' onClick={() => onSelectEntity(fault.entityId)} type='button'>
            Pełne szczegóły i historia <Icon name='history' size={15} />
          </button>
        )}
      </div>
    </details>
  );
}
