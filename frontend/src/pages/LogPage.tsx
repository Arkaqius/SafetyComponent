import { useState } from 'react';
import Icon, { type IconName } from '../components/Icon';
import StatusBadge from '../components/StatusBadge';
import {
  FAULT_PREFIX,
  HEALTH_ENTITY_ID,
  RECOVERY_PREFIX,
  SYSTEM_STATE_ENTITY_ID,
  friendlyEntityName,
  getFaultStatus,
  getRecoveryStatus,
  normalizeState,
  type EntitySnapshot,
  type StatusTone,
} from '../domain/safety';
import { useEntityHistory } from '../hooks/useEntityHistory';
import { useSafetyEntities } from '../hooks/useSafetyEntities';

type HistoryCategory = 'all' | 'system' | 'fault' | 'recovery';
type HistoryHours = 6 | 24 | 72;

interface HistoryEntity {
  entityId: string;
  entity: EntitySnapshot;
  category: Exclude<HistoryCategory, 'all'>;
}

const categoryLabels: Record<HistoryCategory, string> = {
  all: 'Wszystkie',
  system: 'System',
  fault: 'Usterki',
  recovery: 'Recovery',
};

export default function LogPage() {
  const { entities } = useSafetyEntities();
  const [category, setCategory] = useState<HistoryCategory>('all');
  const [hours, setHours] = useState<HistoryHours>(24);

  const historyEntities = Object.entries(entities)
    .filter(([entityId]) => isHistoryEntity(entityId))
    .map(([entityId, entity]) => ({
      entityId,
      entity,
      category: entityCategory(entityId),
    }))
    .filter(item => category === 'all' || item.category === category)
    .sort(
      (left, right) =>
        Date.parse(right.entity.last_changed ?? '') - Date.parse(left.entity.last_changed ?? '') ||
        friendlyEntityName(left.entityId, left.entity).localeCompare(friendlyEntityName(right.entityId, right.entity), 'pl')
    );

  return (
    <div className='page-stack'>
      <section className='page-introduction'>
        <div>
          <span className='section-kicker'>Home Assistant history</span>
          <h2>Historia stanów SafetyComponent</h2>
          <p>Widok korzysta z historii encji Home Assistanta. Pokazuje rzeczywiste przejścia stanów zamiast przykładowych logów.</p>
        </div>
        <div className='page-introduction-stat'>
          <strong>{historyEntities.length}</strong>
          <span>obserwowanych encji</span>
        </div>
      </section>

      <section className='history-controls'>
        <div className='filter-row' role='group' aria-label='Kategoria historii'>
          {(Object.keys(categoryLabels) as HistoryCategory[]).map(value => (
            <button
              aria-pressed={category === value}
              className={`filter-button${category === value ? ' filter-button-active' : ''}`}
              key={value}
              onClick={() => setCategory(value)}
              type='button'
            >
              {categoryLabels[value]}
            </button>
          ))}
        </div>
        <label className='select-field compact-select'>
          <span>Zakres</span>
          <select onChange={event => setHours(Number(event.target.value) as HistoryHours)} value={hours}>
            <option value={6}>6 godzin</option>
            <option value={24}>24 godziny</option>
            <option value={72}>3 dni</option>
          </select>
        </label>
      </section>

      {historyEntities.length > 0 ? (
        <section aria-live='polite' className='history-grid'>
          {historyEntities.map(item => (
            <HistoryCard hours={hours} item={item} key={item.entityId} />
          ))}
        </section>
      ) : (
        <section className='panel empty-state page-empty-state'>
          <div className='empty-state-icon'>
            <Icon name='history' size={30} />
          </div>
          <strong>Brak encji w wybranej kategorii</strong>
          <p>Sprawdź połączenie z Home Assistantem lub wybierz inną kategorię.</p>
        </section>
      )}
    </div>
  );
}

function HistoryCard({ item, hours }: { item: HistoryEntity; hours: HistoryHours }) {
  const history = useEntityHistory(item.entityId, {
    hoursToShow: hours,
    minimalResponse: true,
    significantChangesOnly: true,
  });
  const transitions = history.timeline
    .filter((entry, index, timeline) => index === 0 || entry.state !== timeline[index - 1]?.state)
    .slice(-7)
    .reverse();
  const presentation = statePresentation(item);
  const icon: IconName = item.category === 'fault' ? 'alert' : item.category === 'recovery' ? 'recovery' : 'activity';

  return (
    <article className='history-card'>
      <div className='history-card-header'>
        <span className={`history-card-icon history-${item.category}`}>
          <Icon name={icon} size={20} />
        </span>
        <div>
          <h3>{friendlyEntityName(item.entityId, item.entity)}</h3>
          <code>{item.entityId}</code>
        </div>
        <StatusBadge tone={presentation.tone}>{presentation.label}</StatusBadge>
      </div>

      {history.loading && transitions.length === 0 ? (
        <div className='history-loading'>
          <span className='loading-line' />
          <span className='loading-line loading-line-short' />
        </div>
      ) : transitions.length > 0 ? (
        <ol className='state-timeline'>
          {transitions.map(transition => (
            <li key={`${transition.last_changed}-${transition.state}`}>
              <span className='timeline-dot' />
              <div>
                <strong>{transition.state}</strong>
                <time dateTime={new Date(transition.last_changed).toISOString()}>
                  {new Date(transition.last_changed).toLocaleString('pl-PL', {
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    month: 'short',
                  })}
                </time>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <div className='history-empty'>Brak zmian stanu w wybranym okresie.</div>
      )}
    </article>
  );
}

function isHistoryEntity(entityId: string): boolean {
  return (
    entityId === HEALTH_ENTITY_ID ||
    entityId === SYSTEM_STATE_ENTITY_ID ||
    entityId.startsWith(FAULT_PREFIX) ||
    entityId.startsWith(RECOVERY_PREFIX)
  );
}

function entityCategory(entityId: string): HistoryEntity['category'] {
  if (entityId.startsWith(FAULT_PREFIX)) return 'fault';
  if (entityId.startsWith(RECOVERY_PREFIX)) return 'recovery';
  return 'system';
}

function statePresentation(item: HistoryEntity): { label: string; tone: StatusTone } {
  if (item.category === 'fault') {
    const state = getFaultStatus(item.entity.state);
    if (state === 'set') return { label: 'Aktywna', tone: 'danger' };
    if (state === 'shadowed') return { label: 'Przesłonięta', tone: 'warning' };
    if (state === 'cleared') return { label: 'Usunięta', tone: 'safe' };
    return { label: item.entity.state, tone: 'muted' };
  }

  if (item.category === 'recovery') {
    const state = getRecoveryStatus(item.entity.state);
    if (state === 'to_perform') return { label: 'Do wykonania', tone: 'warning' };
    if (state === 'do_not_perform') return { label: 'Brak potrzeby', tone: 'safe' };
    return { label: item.entity.state, tone: 'muted' };
  }

  const state = normalizeState(item.entity.state);
  if (item.entityId === HEALTH_ENTITY_ID) {
    if (state === 'running') return { label: 'Działa', tone: 'safe' };
    if (state === 'init') return { label: 'Uruchamianie', tone: 'warning' };
    return { label: item.entity.state, tone: 'critical' };
  }
  return state === '0' || state === 'safe'
    ? { label: 'Bezpieczny', tone: 'safe' }
    : { label: `Poziom ${item.entity.state}`, tone: 'warning' };
}
