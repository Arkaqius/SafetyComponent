import { useMemo, useRef, useState, type CSSProperties } from 'react';
import {
  FAULT_PREFIX,
  RECOVERY_PREFIX,
  friendlyEntityName,
  getFaultStatus,
  getRecoveryStatus,
  localizedEntityState,
  normalizeState,
  type EntityMap,
  type EntitySnapshot,
  type StatusTone,
} from '../domain/safety';
import { useEntityHistory } from '../hooks/useEntityHistory';
import Icon from './Icon';
import StatusBadge from './StatusBadge';
import ModalDialog from './ModalDialog';
import { historySegments, type HistoryPoint } from '../domain/history';

type HistoryHours = 6 | 24 | 72 | 168;

interface EntityDetailsDialogProps {
  entities: EntityMap;
  entityId: string | null;
  onClose: () => void;
}

interface HistorySegment {
  duration: number;
  label: string;
  state: string | null;
  tone: StatusTone;
}

export default function EntityDetailsDialog({ entities, entityId, onClose }: EntityDetailsDialogProps) {
  const [hours, setHours] = useState<HistoryHours>(24);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const entity = entityId ? entities[entityId] : undefined;
  const history = useEntityHistory(entityId ?? 'sensor.safety_app_health', {
    disable: !entityId,
    hoursToShow: hours,
    minimalResponse: true,
    significantChangesOnly: true,
  });
  const transitions = useMemo(
    () =>
      history.timeline
        .filter((entry, index, timeline) => index === 0 || entry.state !== timeline[index - 1]?.state)
        .slice(-12)
        .reverse(),
    [history.timeline]
  );
  const segments = useMemo(() => buildHistorySegments(entityId, history.timeline, hours), [entityId, history.timeline, hours]);

  if (!entityId) return null;

  const exactName = fullEntityName(entityId, entity);
  const shortName = friendlyEntityName(entityId, entity);
  const presentation = entityPresentation(entityId, entity);
  const attributes = Object.entries(entity?.attributes ?? {}).filter(([key]) => key !== 'friendly_name');

  return (
    <ModalDialog initialFocus={closeButtonRef} labelledBy='entity-dialog-title' onClose={onClose} open={Boolean(entityId)}>
      <header className='entity-dialog-header'>
        <div className='entity-dialog-heading'>
          <span className='section-kicker'>{entityCategory(entityId)}</span>
          <h2 id='entity-dialog-title'>{exactName}</h2>
          {shortName !== exactName && <p>{shortName}</p>}
          <code>{entityId}</code>
        </div>
        <StatusBadge tone={presentation.tone}>{presentation.label}</StatusBadge>
        <button
          aria-label='Zamknij szczegóły encji'
          className='icon-button entity-dialog-close'
          onClick={onClose}
          ref={closeButtonRef}
          type='button'
        >
          <Icon name='close' size={20} />
        </button>
      </header>

      <div className='entity-dialog-scroll'>
        <dl className='entity-dialog-facts'>
          <div>
            <dt>Aktualny stan</dt>
            <dd>{entity ? localizedEntityState(entityId, entity.state) : 'Encja niedostępna'}</dd>
          </div>
          <div>
            <dt>Stan techniczny</dt>
            <dd>{entity?.state ?? 'unavailable'}</dd>
          </div>
          <div>
            <dt>Ostatnia zmiana</dt>
            <dd>{formatTimestamp(entity?.last_changed)}</dd>
          </div>
          <div>
            <dt>Ostatnia aktualizacja</dt>
            <dd>{formatTimestamp(entity?.last_updated)}</dd>
          </div>
        </dl>

        <section className='entity-dialog-history'>
          <div className='entity-dialog-section-header'>
            <div>
              <span className='section-kicker'>Rejestrator Home Assistanta</span>
              <h3>Historia stanu</h3>
            </div>
            <label className='select-field compact-select'>
              <span>Zakres</span>
              <select onChange={event => setHours(Number(event.target.value) as HistoryHours)} value={hours}>
                <option value={6}>6 godzin</option>
                <option value={24}>24 godziny</option>
                <option value={72}>3 dni</option>
                <option value={168}>7 dni</option>
              </select>
            </label>
          </div>

          {history.status === 'error' || history.status === 'disconnected' ? (
            <p role='status'>{history.error ?? 'Historia niedostępna: brak połączenia z Home Assistantem.'}</p>
          ) : history.loading && transitions.length === 0 ? (
            <div className='history-loading'>
              <span className='loading-line' />
              <span className='loading-line loading-line-short' />
            </div>
          ) : transitions.length > 0 ? (
            <>
              <div aria-label={`Przebieg stanu z ostatnich ${hours} godzin`} className='entity-history-bar'>
                {segments.map((segment, index) => (
                  <span
                    className={`entity-history-segment history-segment-${segment.tone}`}
                    key={`${segment.state}-${index}`}
                    style={{ '--segment-duration': Math.max(segment.duration, 1) } as CSSProperties}
                    title={`${segment.label} · ${formatDuration(segment.duration)}`}
                  />
                ))}
              </div>
              <div className='entity-history-axis'>
                <span>{historyRangeLabel(hours)}</span>
                <span>Teraz</span>
              </div>
              <ol className='state-timeline entity-dialog-timeline'>
                {transitions.map(transition => (
                  <li key={`${transition.last_changed}-${transition.state}`}>
                    <span className={`timeline-dot timeline-${stateTone(entityId, transition.state)}`} />
                    <div>
                      <strong>{localizedEntityState(entityId, transition.state)}</strong>
                      <time dateTime={new Date(transition.last_changed).toISOString()}>
                        {formatHistoryTimestamp(transition.last_changed)}
                      </time>
                    </div>
                  </li>
                ))}
              </ol>
            </>
          ) : (
            <div className='history-empty'>Brak zapisanych zmian stanu w wybranym okresie.</div>
          )}
        </section>

        <details className='entity-dialog-attributes' open={attributes.length > 0 && attributes.length <= 6}>
          <summary>
            Atrybuty encji <span>{attributes.length}</span>
          </summary>
          {attributes.length > 0 ? (
            <dl>
              {attributes.map(([key, value]) => (
                <div key={key}>
                  <dt>{attributeLabel(key)}</dt>
                  <dd>{formatAttributeValue(value)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p>Ta encja nie publikuje dodatkowych atrybutów.</p>
          )}
        </details>
      </div>
    </ModalDialog>
  );
}

function fullEntityName(entityId: string, entity?: EntitySnapshot): string {
  const friendlyName = entity?.attributes.friendly_name;
  return typeof friendlyName === 'string' && friendlyName.trim() ? friendlyName : friendlyEntityName(entityId, entity);
}

function entityCategory(entityId: string): string {
  if (entityId.startsWith(FAULT_PREFIX)) return 'Usterka SafetyComponent';
  if (entityId.startsWith(RECOVERY_PREFIX)) return 'Działanie naprawcze';
  if (entityId.startsWith('binary_sensor.')) return 'Czujnik binarny';
  if (entityId.startsWith('sensor.internal_environment_')) return 'Monitoring zagrożeń wewnętrznych';
  if (entityId.startsWith('sensor.entity_health_')) return 'Diagnostyka monitorowanej encji';
  if (entityId.startsWith('sensor.external_provider_')) return 'Zewnętrzne źródło danych';
  return 'Encja Home Assistanta';
}

function entityPresentation(entityId: string, entity?: EntitySnapshot): { label: string; tone: StatusTone } {
  if (!entity) return { label: 'Niedostępna', tone: 'muted' };
  if (entityId.startsWith(FAULT_PREFIX)) {
    const status = getFaultStatus(entity.state);
    if (entity.attributes.active === true) return { label: 'Aktywna', tone: 'danger' };
    if (status === 'fail' || status === 'unevaluable') return { label: localizedEntityState(entityId, entity.state), tone: 'warning' };
    if (status === 'pass') return { label: 'Warunek ustąpił', tone: 'safe' };
  }
  if (entityId.startsWith(RECOVERY_PREFIX)) {
    const status = getRecoveryStatus(entity.state);
    if (status === 'to_perform') return { label: 'Do wykonania', tone: 'warning' };
    if (status === 'do_not_perform') return { label: 'Brak potrzeby', tone: 'safe' };
  }
  const normalized = normalizeState(entity.state);
  if (['unavailable', 'unknown', 'none', ''].includes(normalized)) return { label: 'Dane niedostępne', tone: 'muted' };
  if (['off', 'closed', 'clear', 'cleared', 'healthy', 'ok', 'running', 'no_faults'].includes(normalized)) {
    return { label: localizedEntityState(entityId, entity.state), tone: 'safe' };
  }
  if (['on', 'open', 'opened', 'set', 'hazard', 'warning', 'stale', 'degraded'].includes(normalized)) {
    return { label: localizedEntityState(entityId, entity.state), tone: 'warning' };
  }
  return { label: localizedEntityState(entityId, entity.state), tone: 'info' };
}

function stateTone(entityId: string | null, state: string): StatusTone {
  return entityPresentation(entityId ?? '', { state, attributes: {} }).tone;
}

function buildHistorySegments(entityId: string | null, timeline: HistoryPoint[], hours: number): HistorySegment[] {
  const end = Date.now();
  const start = end - hours * 3_600_000;
  return historySegments(timeline, start, end).map(point => {
    return {
      duration: point.duration,
      label: point.state === null ? 'Brak danych' : localizedEntityState(entityId ?? '', point.state),
      state: point.state,
      tone: point.state === null ? 'muted' : stateTone(entityId, point.state),
    };
  });
}

function formatTimestamp(value?: string): string {
  if (!value) return 'Brak danych';
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? new Date(timestamp).toLocaleString('pl-PL') : value;
}

function formatHistoryTimestamp(timestamp: number): string {
  return new Date(timestamp).toLocaleString('pl-PL', {
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    month: 'short',
  });
}

function formatDuration(milliseconds: number): string {
  const minutes = Math.max(1, Math.round(milliseconds / 60_000));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round((minutes / 60) * 10) / 10;
  return `${hours.toLocaleString('pl-PL')} godz.`;
}

function historyRangeLabel(hours: number): string {
  if (hours === 6) return '6 godz. temu';
  if (hours === 24) return '24 godz. temu';
  if (hours === 72) return '3 dni temu';
  return '7 dni temu';
}

const ATTRIBUTE_LABELS: Record<string, string> = {
  description: 'Opis',
  device_class: 'Klasa urządzenia',
  level: 'Poziom',
  location: 'Lokalizacja',
  source_entity: 'Encja źródłowa',
  source_entity_id: 'Encja źródłowa',
  state_class: 'Klasa stanu',
  unit_of_measurement: 'Jednostka',
};

function attributeLabel(key: string): string {
  return ATTRIBUTE_LABELS[key] ?? key.replace(/_/g, ' ');
}

function formatAttributeValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Tak' : 'Nie';
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
