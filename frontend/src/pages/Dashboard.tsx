import { useCallback, useState } from 'react';
import { Link, useOutletContext } from 'react-router-dom';
import ActionsList from '../components/ActionsList';
import AverageTemperatureDialog from '../components/AverageTemperatureDialog';
import DoorLastActivity from '../components/DoorLastActivity';
import EntityDetailsDialog from '../components/EntityDetailsDialog';
import FaultSection from '../components/FaultSection';
import Icon from '../components/Icon';
import StatusBadge from '../components/StatusBadge';
import SummaryCard from '../components/SummaryCard';
import HelpTooltip from '../components/HelpTooltip';
import { formatNumeric, formatRelativeTime, type TemperatureView } from '../domain/safety';
import { useSafetyEntities } from '../hooks/useSafetyEntities';
import { NOTIFICATION_DELIVERY_HEALTH_ID, readAcknowledgedNotificationTags } from '../domain/notificationHistory';
import type { ViewModeContext } from '../components/ViewModeSwitch';
import BasicDashboard from './BasicDashboard';
import { basicDashboardItems } from '../domain/basicDashboard';

export default function Dashboard() {
  const view = useOutletContext<ViewModeContext>();
  return view.viewMode === 'basic' ? <BasicDashboard onExpand={() => view.onViewModeChange('advanced')} /> : <AdvancedDashboard />;
}

function AdvancedDashboard() {
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [averageDialogOpen, setAverageDialogOpen] = useState(false);
  const closeEntityDetails = useCallback(() => setSelectedEntityId(null), []);
  const closeAverageDetails = useCallback(() => setAverageDialogOpen(false), []);
  const { connection, entities, entityMonitorSummary, faults, recoveries, safetyDoors, summary, systemEntity, temperatures } =
    useSafetyEntities();
  const values = temperatures.filter((temperature): temperature is TemperatureView & { state: number } => temperature.state !== null);
  const average = values.length > 0 ? values.reduce((sum, temperature) => sum + temperature.state, 0) / values.length : null;
  const minimum = values.reduce<(TemperatureView & { state: number }) | null>(
    (current, temperature) => (!current || temperature.state < current.state ? temperature : current),
    null
  );
  const maximum = values.reduce<(TemperatureView & { state: number }) | null>(
    (current, temperature) => (!current || temperature.state > current.state ? temperature : current),
    null
  );
  const fastestRising = temperatures
    .filter(temperature => temperature.rate !== null && temperature.rate >= 0.005)
    .sort((left, right) => (right.rate ?? 0) - (left.rate ?? 0))[0];
  const acknowledgedNotificationTags = new Set(readAcknowledgedNotificationTags(entities[NOTIFICATION_DELIVERY_HEALTH_ID]));
  const { primaryFault } = basicDashboardItems(faults, recoveries);

  return (
    <div className='page-stack'>
      <button
        className={`safety-hero dashboard-entity-trigger hero-${summary.tone}`}
        onClick={() => setSelectedEntityId(systemEntity ? 'sensor.safetysystem_state' : 'sensor.safety_app_health')}
        type='button'
      >
        <div className='safety-hero-icon'>
          <Icon name={summary.tone === 'safe' ? 'shield' : 'alert'} size={32} />
        </div>
        <div className='safety-hero-copy'>
          <span className='section-kicker'>Bieżąca ocena</span>
          <h2>{summary.label}</h2>
          <p>{summary.detail}</p>
          {primaryFault && (
            <strong className='hero-incident'>
              {primaryFault.name} · {primaryFault.locations.join(' · ') || 'Lokalizacja niepodana'}
            </strong>
          )}
        </div>
        <div className='safety-hero-meta'>
          <small>
            {connection.cannotConnect || !connection.ready ? 'Ostatnia znana zmiana oceny' : 'Ostatnia zmiana oceny'}{' '}
            {formatRelativeTime(systemEntity?.last_changed)}
          </small>
        </div>
      </button>

      <div className='dashboard-columns dashboard-events'>
        <FaultSection
          acknowledgedTags={acknowledgedNotificationTags}
          compact
          faults={faults}
          recoveries={recoveries}
          onSelectEntity={setSelectedEntityId}
        />
        <ActionsList onSelectEntity={setSelectedEntityId} recoveries={recoveries} />
      </div>

      <section className='entity-monitor-overview'>
        <div>
          <small className='label-with-help'>
            {entityMonitorSummary.total === 0
              ? 'Pokrycie monitoringu nieznane'
              : `${entityMonitorSummary.healthy}/${entityMonitorSummary.total} źródeł działa prawidłowo${connection.cannotConnect || !connection.ready ? ' · ostatnie znane dane' : ''}`}
            <HelpTooltip
              label='Pokrycie monitoringu'
              text='Licznik dotyczy źródeł objętych diagnostyką systemu. Nie jest liczbą wszystkich urządzeń w domu. Nieaktualne, niedostępne lub niepoprawne dane ograniczają ocenę; po utracie połączenia licznik jest ostatnim znanym wynikiem.'
            />
          </small>
        </div>
        <StatusBadge
          tone={
            connection.cannotConnect || !connection.ready
              ? 'muted'
              : entityMonitorSummary.unavailable > 0
                ? 'danger'
                : entityMonitorSummary.degraded + entityMonitorSummary.stale > 0
                  ? 'warning'
                  : entityMonitorSummary.total > 0
                    ? 'safe'
                    : 'muted'
          }
        >
          {connection.cannotConnect || !connection.ready
            ? 'Niezweryfikowane'
            : entityMonitorSummary.unavailable > 0
              ? `${entityMonitorSummary.unavailable} niedostępnych`
              : entityMonitorSummary.degraded + entityMonitorSummary.stale > 0
                ? `${entityMonitorSummary.degraded + entityMonitorSummary.stale} wymaga uwagi`
                : entityMonitorSummary.total > 0
                  ? 'Wszystkie sprawne'
                  : 'Brak danych'}
        </StatusBadge>
        <Link className='text-link' to='/functional-safety'>
          Źródła danych <Icon name='chevron' size={15} />
        </Link>
      </section>

      <section aria-label='Podsumowanie temperatur' className='summary-grid'>
        <SummaryCard
          detail={`${values.length}/${temperatures.length} dostępnych pomiarów`}
          icon='temperature'
          label='Średnia temperatura'
          help='Średnia arytmetyczna dostępnych odczytów monitorowanych źródeł. Nie zastępuje pomiaru w konkretnym pomieszczeniu. Dotknij karty, aby zobaczyć pomiary składowe; przy utracie połączenia wartości są ostatnimi znanymi danymi.'
          tone={average === null ? 'muted' : 'info'}
          value={temperatureValue(average)}
          onClick={() => setAverageDialogOpen(true)}
        />
        <SummaryCard
          detail={minimum?.roomName ?? 'Brak dostępnego pomiaru'}
          icon='temperature'
          label='Najniższa temperatura'
          help='Najniższy dostępny odczyt spośród monitorowanych źródeł. Pod wartością podano nazwę źródła lub jego lokalizację. To odczyt ze źródła, a nie minimum z całej historii dnia.'
          tone={minimum ? 'info' : 'muted'}
          value={temperatureValue(minimum?.state ?? null)}
          onClick={minimum ? () => setSelectedEntityId(minimum.entityId) : undefined}
        />
        <SummaryCard
          detail={maximum?.roomName ?? 'Brak dostępnego pomiaru'}
          icon='temperature'
          label='Najwyższa temperatura'
          help='Najwyższy dostępny odczyt spośród monitorowanych źródeł. Nie jest historycznym maksimum dnia. Otwórz kartę, aby sprawdzić czas aktualizacji i historię tego źródła.'
          tone={maximum ? 'info' : 'muted'}
          value={temperatureValue(maximum?.state ?? null)}
          onClick={maximum ? () => setSelectedEntityId(maximum.entityId) : undefined}
        />
        <SummaryCard
          detail={fastestRising ? `${formatNumeric(fastestRising.rate, 3)} °C/min` : 'Brak wyraźnego wzrostu'}
          icon='temperature'
          label='Temperatura rośnie'
          help='Pokazuje źródło z największym raportowanym dodatnim tempem zmiany, co najmniej 0,005 °C/min. Brak wyraźnego wzrostu nie potwierdza, że wszystkie temperatury są prawidłowe lub aktualne.'
          tone={fastestRising ? 'warning' : 'safe'}
          value={fastestRising?.roomName ?? 'Stabilnie'}
          onClick={fastestRising ? () => setSelectedEntityId(fastestRising.entityId) : undefined}
        />
      </section>

      <div className='dashboard-columns dashboard-columns-secondary'>
        <section className='panel door-overview-panel'>
          <div className='panel-header'>
            <div>
              <span className='section-kicker'>Drzwi i bramy</span>
              <h2>Ostatnie otwarcia</h2>
            </div>
            <Link className='text-link' to='/safety-doors'>
              Drzwi i bramy <Icon name='chevron' size={15} />
            </Link>
          </div>
          {safetyDoors.length > 0 ? (
            <div className='door-overview-list'>
              {safetyDoors.map(door => (
                <button
                  className='door-overview-row dashboard-entity-trigger'
                  key={door.entityId}
                  onClick={() => setSelectedEntityId(door.entityId)}
                  type='button'
                >
                  <span className={`door-overview-indicator door-overview-${door.doorState}`} />
                  <div>
                    <strong>{door.sourceEntityName}</strong>
                    <DoorLastActivity compact door={door} />
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className='empty-state compact-empty-state'>
              <strong>Brak monitorowanych wejść</strong>
              <p>SafetyComponent nie publikuje obecnie monitorowanych wejść.</p>
            </div>
          )}
        </section>
      </div>
      <AverageTemperatureDialog
        average={average}
        onClose={closeAverageDetails}
        onSelectEntity={setSelectedEntityId}
        open={averageDialogOpen}
        temperatures={temperatures}
      />
      <EntityDetailsDialog entities={entities} entityId={selectedEntityId} onClose={closeEntityDetails} />
    </div>
  );
}

function temperatureValue(value: number | null): string {
  return value === null ? '—' : `${formatNumeric(value, 1)} °C`;
}
