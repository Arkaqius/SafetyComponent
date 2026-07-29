import { useMemo, useState } from 'react';
import { LEVEL_PRESENTATION, formatRelativeTime, type FaultStatus, type FaultView, type StatusTone } from '../domain/safety';
import Icon from './Icon';
import StatusBadge from './StatusBadge';

type FaultFilter = 'attention' | 'set' | 'shadowed' | 'all';

interface FaultSectionProps {
  faults: FaultView[];
  compact?: boolean;
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

export default function FaultSection({ faults, compact = false }: FaultSectionProps) {
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
          <span className='section-kicker'>Fault Manager</span>
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
          filteredFaults.map(fault => <FaultCard fault={fault} key={fault.entityId} />)
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

function FaultCard({ fault }: { fault: FaultView }) {
  const status = statusPresentation[fault.status];
  const level = fault.level ? LEVEL_PRESENTATION[fault.level] : undefined;

  return (
    <details className={`fault-card fault-${status.tone}`} open={fault.status === 'set'}>
      <summary>
        <span className='fault-card-icon'>
          <Icon name='alert' size={20} />
        </span>
        <span className='fault-card-title'>
          <strong>{fault.name}</strong>
          <small>{fault.locations.length > 0 ? fault.locations.join(' · ') : fault.entityId}</small>
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
            <dt>Stan HA</dt>
            <dd>{fault.state}</dd>
          </div>
          <div>
            <dt>Ostatnia zmiana</dt>
            <dd>{formatRelativeTime(fault.lastChanged)}</dd>
          </div>
        </dl>
      </div>
    </details>
  );
}
