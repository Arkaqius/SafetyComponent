import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import ActionsList from '../components/ActionsList';
import AverageTemperatureDialog from '../components/AverageTemperatureDialog';
import DoorLastActivity from '../components/DoorLastActivity';
import EntityDetailsDialog from '../components/EntityDetailsDialog';
import FaultSection from '../components/FaultSection';
import Icon from '../components/Icon';
import StatusBadge from '../components/StatusBadge';
import SummaryCard from '../components/SummaryCard';
import {
  formatNumeric,
  formatRelativeTime,
  getAirQualityPresentation,
  systemStatePresentation,
  type TemperatureView,
} from '../domain/safety';
import { useSafetyEntities } from '../hooks/useSafetyEntities';
import { ENTITY_MONITOR_SUMMARY_ID } from '../domain/entityHealth';

export default function Dashboard() {
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [averageDialogOpen, setAverageDialogOpen] = useState(false);
  const closeEntityDetails = useCallback(() => setSelectedEntityId(null), []);
  const { entities, entityMonitorSummary, externalHazards, faults, recoveries, safetyDoors, summary, systemEntity, temperatures } =
    useSafetyEntities();
  const systemState = systemStatePresentation(systemEntity?.state);
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
  const airQuality = getAirQualityPresentation(externalHazards);
  const environmentalTone =
    externalHazards.status === 'severe'
      ? 'critical'
      : externalHazards.status === 'warning'
        ? 'danger'
        : externalHazards.status === 'watch'
          ? 'warning'
          : externalHazards.status === 'clear'
            ? 'safe'
            : 'muted';

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
          <p>{summary.detail}. Interfejs prezentuje aktualne dane SafetyComponent z Home Assistanta.</p>
        </div>
        <div className='safety-hero-meta'>
          <span>Stan raportowany</span>
          <strong>{systemState.label}</strong>
          <small>Zmiana {formatRelativeTime(systemEntity?.last_changed)}</small>
        </div>
      </button>

      <section className='entity-monitor-overview'>
        <div>
          <span className='section-kicker'>Źródła danych</span>
          <strong>Monitorowane encje</strong>
          <small>
            {entityMonitorSummary.total === 0
              ? 'Brak opublikowanej diagnostyki C-ENT'
              : `${entityMonitorSummary.healthy}/${entityMonitorSummary.total} encji działa prawidłowo`}
          </small>
        </div>
        <StatusBadge
          tone={
            entityMonitorSummary.unavailable > 0
              ? 'danger'
              : entityMonitorSummary.degraded + entityMonitorSummary.stale > 0
                ? 'warning'
                : entityMonitorSummary.total > 0
                  ? 'safe'
                  : 'muted'
          }
        >
          {entityMonitorSummary.unavailable > 0
            ? `${entityMonitorSummary.unavailable} niedostępnych`
            : entityMonitorSummary.degraded + entityMonitorSummary.stale > 0
              ? `${entityMonitorSummary.degraded + entityMonitorSummary.stale} wymaga uwagi`
              : entityMonitorSummary.total > 0
                ? 'Wszystkie sprawne'
                : 'Brak danych'}
        </StatusBadge>
        <button className='text-button' onClick={() => setSelectedEntityId(ENTITY_MONITOR_SUMMARY_ID)} type='button'>
          Szczegóły <Icon name='history' size={15} />
        </button>
        <Link className='text-link' to='/entities'>
          Pokaż encje <Icon name='chevron' size={15} />
        </Link>
      </section>

      <section aria-label='Podsumowanie temperatur' className='summary-grid'>
        <SummaryCard
          detail={`${values.length}/${temperatures.length} dostępnych pomiarów`}
          icon='temperature'
          label='Średnia temperatura'
          tone={average === null ? 'muted' : 'info'}
          value={temperatureValue(average)}
          onClick={() => setAverageDialogOpen(true)}
        />
        <SummaryCard
          detail={minimum?.roomName ?? 'Brak dostępnego pomiaru'}
          icon='temperature'
          label='Najniższa temperatura'
          tone={minimum ? 'info' : 'muted'}
          value={temperatureValue(minimum?.state ?? null)}
          onClick={minimum ? () => setSelectedEntityId(minimum.entityId) : undefined}
        />
        <SummaryCard
          detail={maximum?.roomName ?? 'Brak dostępnego pomiaru'}
          icon='temperature'
          label='Najwyższa temperatura'
          tone={maximum ? 'info' : 'muted'}
          value={temperatureValue(maximum?.state ?? null)}
          onClick={maximum ? () => setSelectedEntityId(maximum.entityId) : undefined}
        />
        <SummaryCard
          detail={fastestRising ? `${formatNumeric(fastestRising.rate, 3)} °C/min` : 'Brak wyraźnego wzrostu'}
          icon='temperature'
          label='Temperatura rośnie'
          tone={fastestRising ? 'warning' : 'safe'}
          value={fastestRising?.roomName ?? 'Stabilnie'}
          onClick={fastestRising ? () => setSelectedEntityId(fastestRising.entityId) : undefined}
        />
      </section>

      <div className='dashboard-columns'>
        <FaultSection compact faults={faults} onSelectEntity={setSelectedEntityId} />
        <ActionsList onSelectEntity={setSelectedEntityId} recoveries={recoveries} />
      </div>

      <div className='dashboard-columns dashboard-columns-secondary'>
        <section className='panel environment-overview-panel'>
          <div className='panel-header'>
            <div>
              <span className='section-kicker'>Warunki zewnętrzne</span>
              <h2>Otoczenie domu</h2>
            </div>
            <Link className='text-link' to='/external-hazards'>
              Szczegóły <Icon name='chevron' size={15} />
            </Link>
          </div>

          <div className='environment-overview-grid'>
            <button
              className='environment-overview-item dashboard-entity-trigger'
              disabled={!externalHazards.providers.find(provider => provider.provider === 'OpenMeteoAirQualityApiComponent')}
              onClick={() =>
                setSelectedEntityId(
                  externalHazards.providers.find(provider => provider.provider === 'OpenMeteoAirQualityApiComponent')?.entityId ?? null
                )
              }
              type='button'
            >
              <span>Aktualna jakość powietrza</span>
              <strong>{airQuality.label}</strong>
              <small>
                {airQuality.sourceName ? `${airQuality.sourceName} · ` : ''}
                {airQuality.detail}
              </small>
              <StatusBadge tone={airQuality.tone}>{airQuality.tone === 'muted' ? 'Brak danych' : 'Aktualny odczyt'}</StatusBadge>
            </button>
            <button
              className='environment-overview-item dashboard-entity-trigger'
              onClick={() => setSelectedEntityId(externalHazards.entityId)}
              type='button'
            >
              <span>Ostrzeżenia dla domu</span>
              <strong>{externalHazards.imgwWarnings.length}</strong>
              <small>
                {externalHazards.imgwWarnings.length > 0
                  ? externalHazards.imgwWarnings.map(warning => warning.eventName).join(' · ')
                  : 'Brak aktualnych ostrzeżeń IMGW dla lokalizacji domu'}
              </small>
              <StatusBadge tone={environmentalTone}>
                {externalHazards.activeHazards.length > 0
                  ? externalHazards.activeHazards.length === 1
                    ? '1 aktywne zagrożenie'
                    : externalHazards.activeHazards.length < 5
                      ? `${externalHazards.activeHazards.length} aktywne zagrożenia`
                      : `${externalHazards.activeHazards.length} aktywnych zagrożeń`
                  : 'Brak ekspozycji'}
              </StatusBadge>
            </button>
          </div>
        </section>

        <section className='panel door-overview-panel'>
          <div className='panel-header'>
            <div>
              <span className='section-kicker'>Wejścia</span>
              <h2>Ostatnie otwarcia</h2>
            </div>
            <Link className='text-link' to='/safety-doors'>
              Wszystkie wejścia <Icon name='chevron' size={15} />
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
        onClose={() => setAverageDialogOpen(false)}
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
