import { useMemo, useState } from 'react';
import Icon from '../components/Icon';
import StatusBadge from '../components/StatusBadge';
import {
  type EntityCheckView,
  type EntityHealth as EntityHealthState,
  type InventoryDeviceView,
  type InventoryEntityView,
  type MonitoredEntityView,
} from '../domain/entityHealth';
import { formatRelativeTime, localizedEntityState, type StatusTone } from '../domain/safety';
import { useEntityAudit } from '../hooks/useEntityAudit';
import { useEntityHistory } from '../hooks/useEntityHistory';

type MainView = 'monitored' | 'inventory';
type InventoryMode = 'entities' | 'devices';
type AvailabilityFilter = 'all' | 'available' | 'unavailable';
type AgeFilter = 'all' | 'hour' | 'day' | 'week' | 'older_week';
type InventorySort = 'health' | 'updated' | 'changed' | 'name' | 'area' | 'device';
const PAGE_SIZE = 50;

const healthPresentation: Record<EntityHealthState, { label: string; tone: StatusTone }> = {
  healthy: { label: 'Sprawna', tone: 'safe' },
  degraded: { label: 'Wymaga uwagi', tone: 'warning' },
  stale: { label: 'Dane nieaktualne', tone: 'warning' },
  unavailable: { label: 'Niedostępna', tone: 'danger' },
};

export default function EntityHealth() {
  const { monitored, summary, inventory, devices, registriesAvailable } = useEntityAudit();
  const [view, setView] = useState<MainView>('monitored');

  return (
    <div className='page-stack'>
      <section className='page-introduction'>
        <div>
          <span className='section-kicker'>Nadzór nad źródłami danych</span>
          <h2>Encje i urządzenia</h2>
          <p>Kontrola encji używanych przez funkcje bezpieczeństwa oraz informacyjny audyt Home Assistanta.</p>
        </div>
        <div className='page-introduction-stat'>
          <strong>
            {summary.healthy}/{summary.total}
          </strong>
          <span>monitorowanych encji sprawnych</span>
        </div>
      </section>

      <div className='view-tabs' role='tablist' aria-label='Zakres encji'>
        <button
          aria-selected={view === 'monitored'}
          className={view === 'monitored' ? 'active' : ''}
          onClick={() => setView('monitored')}
          role='tab'
          type='button'
        >
          Monitorowane
        </button>
        <button
          aria-selected={view === 'inventory'}
          className={view === 'inventory' ? 'active' : ''}
          onClick={() => setView('inventory')}
          role='tab'
          type='button'
        >
          Wszystkie encje
        </button>
      </div>

      {view === 'monitored' ? (
        <MonitoredView monitored={monitored} summary={summary} />
      ) : (
        <InventoryView devices={devices} inventory={inventory} registriesAvailable={registriesAvailable} />
      )}
    </div>
  );
}

function MonitoredView({
  monitored,
  summary,
}: {
  monitored: MonitoredEntityView[];
  summary: ReturnType<typeof useEntityAudit>['summary'];
}) {
  const [query, setQuery] = useState('');
  const [health, setHealth] = useState<'all' | EntityHealthState>('all');
  const [source, setSource] = useState<'all' | 'explicit' | 'component'>('all');
  const [owner, setOwner] = useState('all');
  const [area, setArea] = useState('all');
  const [selected, setSelected] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const owners = unique(monitored.flatMap(entity => entity.owners));
  const areas = unique(monitored.map(entity => entity.areaName).filter((value): value is string => Boolean(value)));
  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('pl');
    return monitored.filter(entity => {
      const matchesQuery =
        !normalized ||
        [entity.friendlyName, entity.entityId, ...entity.owners, ...entity.purposes].join(' ').toLocaleLowerCase('pl').includes(normalized);
      return (
        matchesQuery &&
        (health === 'all' || entity.health === health) &&
        (source === 'all' || entity.sourceGroups.includes(source)) &&
        (owner === 'all' || entity.owners.includes(owner)) &&
        (area === 'all' || entity.areaName === area)
      );
    });
  }, [area, health, monitored, owner, query, source]);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const rows = filtered.slice((Math.min(page, pages) - 1) * PAGE_SIZE, Math.min(page, pages) * PAGE_SIZE);

  return (
    <>
      <section aria-label='Podsumowanie monitorowanych encji' className='entity-health-summary'>
        <HealthMetric label='Wszystkie' value={summary.total} />
        <HealthMetric label='Sprawne' tone='safe' value={summary.healthy} />
        <HealthMetric label='Wymagają uwagi' tone='warning' value={summary.degraded + summary.stale} />
        <HealthMetric label='Niedostępne' tone='danger' value={summary.unavailable} />
      </section>

      <section className='panel entity-table-panel'>
        <div className='entity-filters'>
          <label className='search-field'>
            <span>Wyszukaj</span>
            <input
              onChange={event => {
                setQuery(event.target.value);
                setPage(1);
              }}
              placeholder='Nazwa, encja lub komponent'
              value={query}
            />
          </label>
          <SelectFilter
            label='Ocena'
            onChange={value => {
              setHealth(value as typeof health);
              setPage(1);
            }}
            value={health}
            options={[
              ['all', 'Wszystkie'],
              ['healthy', 'Sprawne'],
              ['degraded', 'Wymagają uwagi'],
              ['stale', 'Nieaktualne'],
              ['unavailable', 'Niedostępne'],
            ]}
          />
          <SelectFilter
            label='Grupa'
            onChange={value => {
              setSource(value as typeof source);
              setPage(1);
            }}
            value={source}
            options={[
              ['all', 'A i B'],
              ['explicit', 'A — wskazane'],
              ['component', 'B — komponenty'],
            ]}
          />
          <SelectFilter
            label='Właściciel'
            onChange={value => {
              setOwner(value);
              setPage(1);
            }}
            value={owner}
            options={[['all', 'Wszyscy'], ...owners.map(value => [value, componentLabel(value)] as [string, string])]}
          />
          <SelectFilter
            label='Pomieszczenie'
            onChange={value => {
              setArea(value);
              setPage(1);
            }}
            value={area}
            options={[['all', 'Wszystkie'], ...areas.map(value => [value, value] as [string, string])]}
          />
        </div>

        {rows.length > 0 ? (
          <div className='responsive-table'>
            <table className='entity-table'>
              <thead>
                <tr>
                  <th>Encja</th>
                  <th>Lokalizacja</th>
                  <th>Źródło</th>
                  <th>Stan encji</th>
                  <th>Ocena</th>
                  <th>Ostatnie dane</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(entity => {
                  const status = healthPresentation[entity.health];
                  return (
                    <tr
                      className={selected === entity.entityId ? 'selected' : ''}
                      key={entity.diagnosticEntityId}
                      onClick={() => setSelected(selected === entity.entityId ? null : entity.entityId)}
                    >
                      <td>
                        <button className='entity-name-button' title={entity.entityId} type='button'>
                          <strong>{entity.friendlyName}</strong>
                          <small>{entity.entityId}</small>
                        </button>
                      </td>
                      <td>{entity.areaName ?? 'Nieprzypisana'}</td>
                      <td>
                        {entity.sourceGroups.map(sourceCode => (sourceCode === 'explicit' ? 'A — wskazana' : 'B — komponent')).join(' · ')}
                      </td>
                      <td>{localizedEntityState(entity.entityId, entity.currentState)}</td>
                      <td>
                        <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
                      </td>
                      <td>{formatRelativeTime(entity.lastUpdated)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title='Brak encji spełniających filtry' detail='Zmień filtry lub sprawdź publikację diagnostyki C-ENT.' />
        )}
        <Pagination current={Math.min(page, pages)} onChange={setPage} pages={pages} total={filtered.length} />
      </section>

      {selected && monitored.find(entity => entity.entityId === selected) ? (
        <EntityDetails entity={monitored.find(entity => entity.entityId === selected)!} />
      ) : null}
    </>
  );
}

function InventoryView({
  inventory,
  devices,
  registriesAvailable,
}: {
  inventory: InventoryEntityView[];
  devices: InventoryDeviceView[];
  registriesAvailable: boolean;
}) {
  const [mode, setMode] = useState<InventoryMode>('entities');
  const [query, setQuery] = useState('');
  const [domain, setDomain] = useState('all');
  const [area, setArea] = useState('all');
  const [device, setDevice] = useState('all');
  const [availability, setAvailability] = useState<AvailabilityFilter>('all');
  const [source, setSource] = useState<'all' | 'explicit' | 'component' | 'informational'>('all');
  const [age, setAge] = useState<AgeFilter>('all');
  const [registryState, setRegistryState] = useState<'all' | 'active' | 'disabled' | 'hidden'>('all');
  const [sort, setSort] = useState<InventorySort>('health');
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const domains = unique(inventory.map(entity => entity.domain));
  const areas = unique(inventory.map(entity => entity.areaName).filter((value): value is string => Boolean(value)));
  const deviceNames = unique(inventory.map(entity => entity.deviceName).filter((value): value is string => Boolean(value)));
  const normalized = query.trim().toLocaleLowerCase('pl');
  const filteredEntities = inventory
    .filter(
      entity =>
        (!normalized ||
          [entity.friendlyName, entity.entityId, entity.deviceName, entity.areaName]
            .join(' ')
            .toLocaleLowerCase('pl')
            .includes(normalized)) &&
        (domain === 'all' || entity.domain === domain) &&
        (area === 'all' || entity.areaName === area) &&
        (device === 'all' || entity.deviceName === device) &&
        (availability === 'all' || (availability === 'available' ? entity.available : !entity.available)) &&
        (source === 'all' || (source === 'informational' ? !entity.monitored : entity.monitored?.sourceGroups.includes(source))) &&
        matchesAge(latestActivityTimestamp(entity), age) &&
        (registryState === 'all' ||
          (registryState === 'active'
            ? !entity.disabledBy && !entity.hiddenBy
            : registryState === 'disabled'
              ? Boolean(entity.disabledBy)
              : Boolean(entity.hiddenBy)))
    )
    .sort((left, right) => compareInventoryEntities(left, right, sort));
  const filteredDevices = devices.filter(
    device =>
      !normalized ||
      [device.name, device.manufacturer, device.model, device.areaName].join(' ').toLocaleLowerCase('pl').includes(normalized)
  );
  const collectionLength = mode === 'entities' ? filteredEntities.length : filteredDevices.length;
  const pages = Math.max(1, Math.ceil(collectionLength / PAGE_SIZE));
  const start = (Math.min(page, pages) - 1) * PAGE_SIZE;

  return (
    <section className='panel entity-table-panel'>
      <div className='inventory-notice'>
        <Icon name='activity' size={19} />
        <div>
          <strong>Widok informacyjny</strong>
          <span>Dane audytowe nie tworzą usterek ani alarmów.</span>
        </div>
      </div>
      {!registriesAvailable && (
        <p className='registry-notice'>Rejestry urządzeń i pomieszczeń pojawią się po zestawieniu pełnego połączenia z Home Assistantem.</p>
      )}
      <div className='view-tabs compact-tabs' role='tablist' aria-label='Sposób grupowania'>
        <button
          aria-selected={mode === 'entities'}
          className={mode === 'entities' ? 'active' : ''}
          onClick={() => {
            setMode('entities');
            setPage(1);
          }}
          role='tab'
          type='button'
        >
          Encje
        </button>
        <button
          aria-selected={mode === 'devices'}
          className={mode === 'devices' ? 'active' : ''}
          onClick={() => {
            setMode('devices');
            setPage(1);
          }}
          role='tab'
          type='button'
        >
          Urządzenia
        </button>
      </div>
      <div className='entity-filters'>
        <label className='search-field'>
          <span>Wyszukaj</span>
          <input
            onChange={event => {
              setQuery(event.target.value);
              setPage(1);
            }}
            placeholder='Nazwa, identyfikator lub urządzenie'
            value={query}
          />
        </label>
        {mode === 'entities' && (
          <SelectFilter
            label='Sortowanie'
            onChange={value => {
              setSort(value as InventorySort);
              setPage(1);
            }}
            value={sort}
            options={[
              ['health', 'Najpierw wymagające uwagi'],
              ['updated', 'Ostatnia aktualizacja'],
              ['changed', 'Ostatnia zmiana'],
              ['name', 'Nazwa'],
              ['area', 'Pomieszczenie'],
              ['device', 'Urządzenie'],
            ]}
          />
        )}
        {mode === 'entities' && (
          <SelectFilter
            label='Domena'
            onChange={value => {
              setDomain(value);
              setPage(1);
            }}
            value={domain}
            options={[['all', 'Wszystkie'], ...domains.map(value => [value, value] as [string, string])]}
          />
        )}
        {mode === 'entities' && (
          <SelectFilter
            label='Pomieszczenie'
            onChange={value => {
              setArea(value);
              setPage(1);
            }}
            value={area}
            options={[['all', 'Wszystkie'], ...areas.map(value => [value, value] as [string, string])]}
          />
        )}
        {mode === 'entities' && (
          <SelectFilter
            label='Urządzenie'
            onChange={value => {
              setDevice(value);
              setPage(1);
            }}
            value={device}
            options={[['all', 'Wszystkie'], ...deviceNames.map(value => [value, value] as [string, string])]}
          />
        )}
        {mode === 'entities' && (
          <SelectFilter
            label='Dostępność'
            onChange={value => {
              setAvailability(value as AvailabilityFilter);
              setPage(1);
            }}
            value={availability}
            options={[
              ['all', 'Wszystkie'],
              ['available', 'Dostępne'],
              ['unavailable', 'Niedostępne'],
            ]}
          />
        )}
        {mode === 'entities' && (
          <SelectFilter
            label='Źródło'
            onChange={value => {
              setSource(value as typeof source);
              setPage(1);
            }}
            value={source}
            options={[
              ['all', 'Wszystkie'],
              ['explicit', 'A — wskazane'],
              ['component', 'B — komponenty'],
              ['informational', 'C — informacyjne'],
            ]}
          />
        )}
        {mode === 'entities' && (
          <SelectFilter
            label='Ostatnie dane'
            onChange={value => {
              setAge(value as AgeFilter);
              setPage(1);
            }}
            value={age}
            options={[
              ['all', 'Dowolny czas'],
              ['hour', 'Do godziny'],
              ['day', 'Do 24 godzin'],
              ['week', 'Do 7 dni'],
              ['older_week', 'Ponad 7 dni'],
            ]}
          />
        )}
        {mode === 'entities' && (
          <SelectFilter
            label='Rejestr'
            onChange={value => {
              setRegistryState(value as typeof registryState);
              setPage(1);
            }}
            value={registryState}
            options={[
              ['all', 'Wszystkie'],
              ['active', 'Aktywne'],
              ['disabled', 'Wyłączone'],
              ['hidden', 'Ukryte'],
            ]}
          />
        )}
      </div>
      {mode === 'entities' ? (
        <InventoryEntityTable
          entities={filteredEntities.slice(start, start + PAGE_SIZE)}
          onSelect={entityId => setSelectedEntity(selectedEntity === entityId ? null : entityId)}
          selected={selectedEntity}
        />
      ) : (
        <DeviceCards
          devices={filteredDevices.slice(start, start + PAGE_SIZE)}
          onSelect={deviceId => setSelectedDevice(selectedDevice === deviceId ? null : deviceId)}
          selected={selectedDevice}
        />
      )}
      <Pagination current={Math.min(page, pages)} onChange={setPage} pages={pages} total={collectionLength} />
      {mode === 'entities' && selectedEntity && inventory.find(entity => entity.entityId === selectedEntity) ? (
        <InventoryEntityDetails entity={inventory.find(entity => entity.entityId === selectedEntity)!} />
      ) : null}
      {mode === 'devices' && selectedDevice && devices.find(device => device.deviceId === selectedDevice) ? (
        <DeviceDetails device={devices.find(device => device.deviceId === selectedDevice)!} />
      ) : null}
    </section>
  );
}

function InventoryEntityTable({
  entities,
  onSelect,
  selected,
}: {
  entities: InventoryEntityView[];
  onSelect: (entityId: string) => void;
  selected: string | null;
}) {
  if (entities.length === 0) return <EmptyState title='Brak encji spełniających filtry' detail='Zmień kryteria wyszukiwania.' />;
  return (
    <div className='responsive-table'>
      <table className='entity-table'>
        <thead>
          <tr>
            <th>Encja</th>
            <th>Stan</th>
            <th>Domena</th>
            <th>Pomieszczenie</th>
            <th>Urządzenie</th>
            <th>Ostatnia aktualizacja</th>
          </tr>
        </thead>
        <tbody>
          {entities.map(entity => (
            <tr className={selected === entity.entityId ? 'selected' : ''} key={entity.entityId} onClick={() => onSelect(entity.entityId)}>
              <td>
                <button className='entity-name-button' title={entity.entityId} type='button'>
                  <strong>{entity.friendlyName}</strong>
                  <small>{entity.entityId}</small>
                  <StatusBadge tone={entity.monitored ? 'info' : 'muted'}>
                    {entity.monitored
                      ? `Monitorowana ${entity.monitored.sourceGroups.map(group => (group === 'explicit' ? 'A' : 'B')).join('/')}`
                      : 'C — informacyjna'}
                  </StatusBadge>
                </button>
              </td>
              <td>
                <StatusBadge tone={entity.available ? 'safe' : 'muted'}>
                  {entity.available ? localizedEntityState(entity.entityId, entity.state) : 'Niedostępna'}
                </StatusBadge>
              </td>
              <td>{entity.domain}</td>
              <td>{entity.areaName ?? 'Nieprzypisana'}</td>
              <td>{entity.deviceName ?? 'Bez urządzenia'}</td>
              <td>{formatRelativeTime(latestActivityTimestamp(entity))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DeviceCards({
  devices,
  onSelect,
  selected,
}: {
  devices: InventoryDeviceView[];
  onSelect: (deviceId: string) => void;
  selected: string | null;
}) {
  if (devices.length === 0)
    return <EmptyState title='Brak urządzeń spełniających filtry' detail='Rejestr urządzeń nie zawiera pasujących pozycji.' />;
  return (
    <div className='device-audit-grid'>
      {devices.map(device => (
        <details className='device-audit-card' key={device.deviceId}>
          <summary>
            <div>
              <strong title={device.deviceId}>{device.name}</strong>
              <small>{[device.manufacturer, device.model].filter(Boolean).join(' · ') || 'Brak danych producenta'}</small>
            </div>
            <div className='device-audit-counts'>
              <StatusBadge tone={device.unavailableCount ? 'muted' : 'safe'}>
                {device.unavailableCount ? `${device.unavailableCount} niedostępnych` : 'Dostępne'}
              </StatusBadge>
              <span>{device.entities.length} encji</span>
            </div>
          </summary>
          <div className='device-audit-details'>
            <p>
              {device.areaName ?? 'Brak przypisanego pomieszczenia'} · najstarsze dane {formatRelativeTime(device.oldestUpdate)}
            </p>
            {device.entities.map(entity => (
              <div className='device-entity-row' key={entity.entityId}>
                <span title={entity.entityId}>{entity.friendlyName}</span>
                <StatusBadge tone={entity.available ? 'safe' : 'muted'}>
                  {entity.available ? localizedEntityState(entity.entityId, entity.state) : 'Niedostępna'}
                </StatusBadge>
              </div>
            ))}
            <button className='text-button' onClick={() => onSelect(device.deviceId)} type='button'>
              {selected === device.deviceId ? 'Ukryj historię' : 'Pokaż historię urządzenia'}
            </button>
          </div>
        </details>
      ))}
    </div>
  );
}

function InventoryEntityDetails({ entity }: { entity: InventoryEntityView }) {
  const history = useEntityHistory(entity.entityId, {
    hoursToShow: 24,
    minimalResponse: true,
    significantChangesOnly: true,
  });
  const transitions = history.timeline
    .filter((entry, index, timeline) => index === 0 || entry.state !== timeline[index - 1]?.state)
    .slice(-8)
    .reverse();
  return (
    <section className='entity-inventory-details'>
      <div className='panel-header'>
        <div>
          <span className='section-kicker'>Historia encji</span>
          <h2 title={entity.entityId}>{entity.friendlyName}</h2>
          <p className='technical-id'>{entity.entityId}</p>
        </div>
        <StatusBadge tone={entity.available ? 'safe' : 'muted'}>{entity.available ? 'Dostępna' : 'Niedostępna'}</StatusBadge>
      </div>
      <dl className='entity-detail-grid'>
        <div>
          <dt>Pomieszczenie</dt>
          <dd>{entity.areaName ?? 'Nieprzypisane'}</dd>
        </div>
        <div>
          <dt>Urządzenie</dt>
          <dd>{entity.deviceName ?? 'Bez urządzenia'}</dd>
        </div>
        <div>
          <dt>Ostatnia zmiana</dt>
          <dd>{formatRelativeTime(entity.lastChanged)}</dd>
        </div>
        <div>
          <dt>Ostatnia aktualizacja</dt>
          <dd>{formatRelativeTime(entity.lastUpdated)}</dd>
        </div>
      </dl>
      <HistoryTimeline entityId={entity.entityId} loading={history.loading} transitions={transitions} />
    </section>
  );
}

function DeviceDetails({ device }: { device: InventoryDeviceView }) {
  const [entityId, setEntityId] = useState(device.entities[0]?.entityId ?? '');
  const entity = device.entities.find(item => item.entityId === entityId) ?? device.entities[0];
  return (
    <section className='entity-inventory-details'>
      <div className='panel-header'>
        <div>
          <span className='section-kicker'>Historia urządzenia</span>
          <h2 title={device.deviceId}>{device.name}</h2>
          <p>{device.areaName ?? 'Brak przypisanego pomieszczenia'}</p>
        </div>
      </div>
      {device.entities.length > 0 ? (
        <>
          <label className='select-field device-history-select'>
            <span>Encja urządzenia</span>
            <select onChange={event => setEntityId(event.target.value)} value={entity?.entityId ?? ''}>
              {device.entities.map(item => (
                <option key={item.entityId} value={item.entityId}>
                  {item.friendlyName}
                </option>
              ))}
            </select>
          </label>
          {entity && <DeviceEntityHistory entity={entity} />}
        </>
      ) : (
        <p>Urządzenie nie ma encji dostępnych w rejestrze.</p>
      )}
    </section>
  );
}

function DeviceEntityHistory({ entity }: { entity: InventoryEntityView }) {
  const history = useEntityHistory(entity.entityId, {
    hoursToShow: 24,
    minimalResponse: true,
    significantChangesOnly: true,
  });
  const transitions = history.timeline
    .filter((entry, index, timeline) => index === 0 || entry.state !== timeline[index - 1]?.state)
    .slice(-8)
    .reverse();
  return <HistoryTimeline entityId={entity.entityId} loading={history.loading} transitions={transitions} />;
}

function HistoryTimeline({
  entityId,
  loading,
  transitions,
}: {
  entityId: string;
  loading: boolean;
  transitions: Array<{ state: string; last_changed: number }>;
}) {
  return (
    <div className='entity-history-preview'>
      <h3>Zmiany z ostatnich 24 godzin</h3>
      {loading && transitions.length === 0 ? (
        <p>Wczytywanie historii…</p>
      ) : transitions.length ? (
        <ol className='state-timeline'>
          {transitions.map(transition => (
            <li key={`${transition.last_changed}-${transition.state}`}>
              <span className='timeline-dot' />
              <div>
                <strong>{localizedEntityState(entityId, transition.state)}</strong>
                <time>{new Date(transition.last_changed).toLocaleString('pl-PL')}</time>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p>Brak zmian stanu w tym okresie.</p>
      )}
    </div>
  );
}

function EntityDetails({ entity }: { entity: MonitoredEntityView }) {
  const history = useEntityHistory(entity.entityId, { hoursToShow: 24, minimalResponse: true, significantChangesOnly: true });
  const transitions = history.timeline
    .filter((entry, index, timeline) => index === 0 || entry.state !== timeline[index - 1]?.state)
    .slice(-8)
    .reverse();
  return (
    <section className='panel entity-details-panel'>
      <div className='panel-header'>
        <div>
          <span className='section-kicker'>Szczegóły monitoringu</span>
          <h2 title={entity.entityId}>{entity.friendlyName}</h2>
          <p className='technical-id'>{entity.entityId}</p>
        </div>
        <StatusBadge tone={healthPresentation[entity.health].tone}>{healthPresentation[entity.health].label}</StatusBadge>
      </div>
      <dl className='entity-detail-grid'>
        <div>
          <dt>Źródło</dt>
          <dd>{entity.sourceGroups.map(source => (source === 'explicit' ? 'A — wskazana' : 'B — komponent')).join(' · ')}</dd>
        </div>
        <div>
          <dt>Właściciel</dt>
          <dd>{entity.owners.map(componentLabel).join(' · ')}</dd>
        </div>
        <div>
          <dt>Pomieszczenie</dt>
          <dd>{entity.areaName ?? 'Nieprzypisane'}</dd>
        </div>
        <div>
          <dt>Stan</dt>
          <dd>{localizedEntityState(entity.entityId, entity.currentState)}</dd>
        </div>
        <div>
          <dt>Ostatnia zmiana</dt>
          <dd>{formatRelativeTime(entity.lastChanged)}</dd>
        </div>
        <div>
          <dt>Ostatnia aktualizacja</dt>
          <dd>{formatRelativeTime(entity.lastUpdated)}</dd>
        </div>
        <div>
          <dt>Ostatni poprawny odczyt</dt>
          <dd>
            {entity.lastValidAt
              ? `${localizedEntityState(entity.entityId, entity.lastValidValue)} · ${formatRelativeTime(entity.lastValidAt)}`
              : 'Brak potwierdzonego odczytu'}
          </dd>
        </div>
        <div>
          <dt>Potwierdzenie awarii</dt>
          <dd>{entity.failureDebounceSeconds} s</dd>
        </div>
        <div>
          <dt>Potwierdzenie powrotu</dt>
          <dd>{entity.recoveryDebounceSeconds} s</dd>
        </div>
        {entity.detectionBudgetSeconds !== undefined && (
          <div>
            <dt>Budżet wykrycia</dt>
            <dd>{entity.detectionBudgetSeconds} s</dd>
          </div>
        )}
      </dl>
      <div className='check-list'>
        {entity.checks.map(check => (
          <CheckRow check={check} key={check.check} />
        ))}
      </div>
      <div className='entity-history-preview'>
        <h3>Zmiany z ostatnich 24 godzin</h3>
        {history.loading && transitions.length === 0 ? (
          <p>Wczytywanie historii…</p>
        ) : transitions.length ? (
          <ol className='state-timeline'>
            {transitions.map(transition => (
              <li key={`${transition.last_changed}-${transition.state}`}>
                <span className='timeline-dot' />
                <div>
                  <strong>{localizedEntityState(entity.entityId, transition.state)}</strong>
                  <time>{new Date(transition.last_changed).toLocaleString('pl-PL')}</time>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p>Brak zmian stanu w tym okresie.</p>
        )}
      </div>
    </section>
  );
}

function CheckRow({ check }: { check: EntityCheckView }) {
  const tone: StatusTone =
    check.result === 'failed' ? 'danger' : check.result === 'pending_failure' ? 'warning' : check.result === 'passed' ? 'safe' : 'muted';
  return (
    <article className='check-row'>
      <div>
        <strong>{checkLabel(check.check)}</strong>
        <span>{reasonLabel(check.reason, check.observedValue)}</span>
      </div>
      <StatusBadge tone={tone}>{resultLabel(check.result)}</StatusBadge>
      <small>{Object.keys(check.calibration).length ? calibrationLabel(check.calibration) : 'Kontrola podstawowa'}</small>
    </article>
  );
}

function HealthMetric({ label, value, tone = 'info' }: { label: string; value: number; tone?: StatusTone }) {
  return (
    <article className={`health-metric metric-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}
function SelectFilter({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<[string, string]>;
  onChange: (value: string) => void;
}) {
  return (
    <label className='select-field'>
      <span>{label}</span>
      <select onChange={event => onChange(event.target.value)} value={value}>
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  );
}
function Pagination({
  current,
  pages,
  total,
  onChange,
}: {
  current: number;
  pages: number;
  total: number;
  onChange: (page: number) => void;
}) {
  return (
    <div className='pagination'>
      <span>
        {total} pozycji · strona {current} z {pages}
      </span>
      <div>
        <button disabled={current <= 1} onClick={() => onChange(current - 1)} type='button'>
          Poprzednia
        </button>
        <button disabled={current >= pages} onClick={() => onChange(current + 1)} type='button'>
          Następna
        </button>
      </div>
    </div>
  );
}
function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className='empty-state compact-empty-state'>
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}
function unique(values: string[]): string[] {
  return [...new Set(values)].sort((left, right) => left.localeCompare(right, 'pl'));
}
function componentLabel(value: string): string {
  return (
    (
      {
        TemperatureComponent: 'Temperatury',
        SafetyDoorsComponent: 'Wejścia',
        ExternalHazardComponent: 'Zagrożenia zewnętrzne',
        SafetyFunctions: 'System',
        installation: 'Konfiguracja użytkownika',
      } as Record<string, string>
    )[value] ?? value
  );
}
function checkLabel(value: string): string {
  return (
    (
      {
        availability: 'Dostępność',
        freshness: 'Aktualność danych',
        required_value: 'Wymagana wartość',
        allowed_values: 'Dozwolone wartości',
        finite_number: 'Poprawna liczba',
        numeric_range: 'Zakres wartości',
        rate_of_change: 'Tempo zmiany',
      } as Record<string, string>
    )[value] ?? value
  );
}
function resultLabel(value: string): string {
  return (
    (
      {
        passed: 'Poprawna',
        failed: 'Niepoprawna',
        pending_failure: 'Potwierdzanie awarii',
        pending_recovery: 'Potwierdzanie powrotu',
        unevaluable: 'Brak oceny',
        not_tested: 'Nieprzetestowana',
      } as Record<string, string>
    )[value] ?? value
  );
}
function reasonLabel(reason: string, value: unknown): string {
  const labels: Record<string, string> = {
    entity_available: 'Encja odpowiada',
    entity_unavailable: 'Encja zgłasza brak dostępności',
    entity_missing: 'Encja nie istnieje',
    fresh: 'Dane są aktualne',
    freshness_expired: 'Nie otrzymano aktualnych danych w wymaganym czasie',
    startup_grace: 'Oczekiwanie po uruchomieniu',
    timestamp_unavailable: 'Brak wiarygodnego czasu ostatnich danych',
    finite_number: 'Odczyt jest poprawną liczbą',
    not_finite_number: 'Odczyt nie jest poprawną liczbą',
    required_value_present: 'Wartość jest obecna',
    required_value_missing: 'Brakuje wymaganej wartości',
    value_allowed: 'Wartość jest dozwolona',
    value_not_allowed: 'Wartość nie należy do dozwolonych',
    inside_numeric_range: 'Wartość mieści się w zakresie',
    outside_numeric_range: 'Wartość jest poza zakresem',
    rate_inside_bounds: 'Tempo zmiany mieści się w granicach',
    rate_outside_bounds: 'Tempo zmiany przekracza granicę',
    insufficient_samples: 'Za mało próbek do oceny',
    insufficient_elapsed_time: 'Za krótki odstęp między próbkami',
    target_unavailable: 'Brak wartości do oceny',
    unsupported_check: 'Nieobsługiwany rodzaj kontroli',
  };
  const observed = value === null || value === undefined ? '' : ` · odczyt: ${String(value)}`;
  return `${labels[reason] ?? reason}${observed}`;
}
function calibrationLabel(calibration: Record<string, unknown>): string {
  const labels: Record<string, string> = {
    timestamp_source: 'Źródło czasu',
    max_silence_seconds: 'Maksymalny czas bez danych',
    target: 'Badana wartość',
    value: 'Wymagana wartość',
    values: 'Dozwolone wartości',
    minimum: 'Minimum',
    maximum: 'Maksimum',
    window_seconds: 'Okno pomiarowe',
    min_samples: 'Minimalna liczba próbek',
    maximum_rise_per_minute: 'Maksymalne tempo wzrostu na minutę',
    maximum_fall_per_minute: 'Maksymalne tempo spadku na minutę',
  };
  const values: Record<string, string> = {
    last_updated: 'ostatnia aktualizacja',
    state: 'stan encji',
  };
  const seconds = new Set(['max_silence_seconds', 'window_seconds']);
  return Object.entries(calibration)
    .map(([key, value]) => {
      const rendered = Array.isArray(value) ? value.join(', ') : (values[String(value)] ?? String(value));
      return `${labels[key] ?? key.replace(/_/g, ' ')}: ${rendered}${seconds.has(key) ? ' s' : ''}`;
    })
    .join(' · ');
}
function matchesAge(timestamp: string | undefined, filter: AgeFilter): boolean {
  if (filter === 'all') return true;
  if (!timestamp) return filter === 'older_week';
  const age = Date.now() - Date.parse(timestamp);
  if (!Number.isFinite(age)) return filter === 'older_week';
  const hour = 3_600_000;
  if (filter === 'hour') return age <= hour;
  if (filter === 'day') return age <= 24 * hour;
  if (filter === 'week') return age <= 7 * 24 * hour;
  return age > 7 * 24 * hour;
}

function latestActivityTimestamp(entity: InventoryEntityView): string | undefined {
  const candidates = [entity.lastUpdated, entity.lastChanged].filter(
    (value): value is string => typeof value === 'string' && Number.isFinite(Date.parse(value))
  );
  return candidates.sort((left, right) => Date.parse(right) - Date.parse(left))[0];
}

function compareInventoryEntities(left: InventoryEntityView, right: InventoryEntityView, sort: InventorySort): number {
  if (sort === 'health') {
    const rank = (entity: InventoryEntityView) => {
      if (!entity.available) return 4;
      if (!entity.monitored) return 0;
      return { healthy: 0, degraded: 2, stale: 3, unavailable: 4 }[entity.monitored.health];
    };
    const difference = rank(right) - rank(left);
    if (difference) return difference;
  }
  if (sort === 'updated' || sort === 'changed') {
    const key = sort === 'updated' ? 'lastUpdated' : 'lastChanged';
    const difference = timestampValue(right[key]) - timestampValue(left[key]);
    if (difference) return difference;
  }
  const text =
    sort === 'area'
      ? [left.areaName ?? '', right.areaName ?? '']
      : sort === 'device'
        ? [left.deviceName ?? '', right.deviceName ?? '']
        : [left.friendlyName, right.friendlyName];
  return text[0].localeCompare(text[1], 'pl') || left.friendlyName.localeCompare(right.friendlyName, 'pl');
}

function timestampValue(value: string | undefined): number {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}
