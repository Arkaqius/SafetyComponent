import { Link } from 'react-router-dom';
import ActionsList from '../components/ActionsList';
import FaultSection from '../components/FaultSection';
import Icon from '../components/Icon';
import SummaryCard from '../components/SummaryCard';
import { formatNumeric, formatRelativeTime, normalizeState, trendPresentation, type ActivityItem } from '../domain/safety';
import { useSafetyEntities } from '../hooks/useSafetyEntities';

export default function Dashboard() {
  const { faults, healthEntity, recentActivity, recoveries, summary, systemEntity, temperatures } = useSafetyEntities();
  const healthState = normalizeState(healthEntity?.state);
  const unavailableTemperatures = temperatures.filter(temperature => temperature.state === null).length;

  return (
    <div className='page-stack'>
      <section className={`safety-hero hero-${summary.tone}`}>
        <div className='safety-hero-icon'>
          <Icon name={summary.tone === 'safe' ? 'shield' : 'alert'} size={32} />
        </div>
        <div className='safety-hero-copy'>
          <span className='section-kicker'>Bieżąca ocena</span>
          <h2>{summary.label}</h2>
          <p>{summary.detail}. Interfejs prezentuje dane na żywo z encji MQTT w Home Assistant.</p>
        </div>
        <div className='safety-hero-meta'>
          <span>Stan raportowany</span>
          <strong>{systemEntity?.state ?? '—'}</strong>
          <small>Zmiana {formatRelativeTime(systemEntity?.last_changed)}</small>
        </div>
      </section>

      <section aria-label='Podsumowanie systemu' className='summary-grid'>
        <SummaryCard
          detail={healthState === 'running' ? 'Heartbeat i MQTT są aktywne' : `Stan: ${healthEntity?.state ?? 'brak'}`}
          icon='activity'
          label='Kondycja usługi'
          tone={healthState === 'running' ? 'safe' : healthState === 'init' ? 'warning' : 'critical'}
          value={healthState === 'running' ? 'Działa' : 'Sprawdź'}
        />
        <SummaryCard
          detail={`${summary.shadowedFaultCount} przesłoniętych`}
          icon='alert'
          label='Aktywne usterki'
          tone={summary.activeFaultCount > 0 ? 'danger' : 'safe'}
          value={summary.activeFaultCount}
        />
        <SummaryCard
          detail={`${recoveries.length} wszystkich encji recovery`}
          icon='recovery'
          label='Działania wymagane'
          tone={summary.actionableRecoveryCount > 0 ? 'warning' : 'safe'}
          value={summary.actionableRecoveryCount}
        />
        <SummaryCard
          detail={unavailableTemperatures > 0 ? `${unavailableTemperatures} bez aktualnego odczytu` : 'Wszystkie odczyty dostępne'}
          icon='temperature'
          label='Monitorowane temperatury'
          tone={unavailableTemperatures > 0 ? 'warning' : 'info'}
          value={temperatures.length}
        />
      </section>

      <div className='dashboard-columns'>
        <FaultSection compact faults={faults} />
        <ActionsList recoveries={recoveries} />
      </div>

      <div className='dashboard-columns dashboard-columns-secondary'>
        <section className='panel temperatures-preview'>
          <div className='panel-header'>
            <div>
              <span className='section-kicker'>Temperature Component</span>
              <h2>Monitorowane pomiary</h2>
            </div>
            <Link className='text-link' to='/temperature'>
              Pełny widok <Icon name='chevron' size={15} />
            </Link>
          </div>
          {temperatures.length > 0 ? (
            <div className='temperature-preview-list'>
              {temperatures.slice(0, 6).map(temperature => {
                const trend = trendPresentation(temperature.rate);
                return (
                  <article className='temperature-preview-row' key={temperature.entityId}>
                    <span className='temperature-preview-icon'>
                      <Icon name='temperature' size={18} />
                    </span>
                    <span className='temperature-preview-name'>
                      <strong title={temperature.entityId}>{temperature.name}</strong>
                      <small>Aktualizacja {formatRelativeTime(temperature.lastUpdated)}</small>
                    </span>
                    <strong className='temperature-preview-value'>
                      {formatNumeric(temperature.state, 1)} {temperature.unit}
                    </strong>
                    <span className={`trend-chip ${trend.className}`}>
                      {trend.symbol} {trend.label}
                    </span>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className='empty-state compact-empty-state'>
              <strong>Brak monitorowanych temperatur</strong>
              <p>Nie znaleziono par encji trendów publikowanych przez SafetyComponent.</p>
            </div>
          )}
        </section>

        <section className='panel activity-panel'>
          <div className='panel-header'>
            <div>
              <span className='section-kicker'>Live state</span>
              <h2>Ostatnie zmiany</h2>
            </div>
            <Link className='text-link' to='/history'>
              Historia <Icon name='chevron' size={15} />
            </Link>
          </div>
          {recentActivity.length > 0 ? (
            <ol className='activity-list'>
              {recentActivity.slice(0, 6).map(item => (
                <ActivityRow item={item} key={item.entityId} />
              ))}
            </ol>
          ) : (
            <div className='empty-state compact-empty-state'>
              <strong>Brak danych aktywności</strong>
              <p>Encje SafetyComponent nie są jeszcze dostępne.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function ActivityRow({ item }: { item: ActivityItem }) {
  const icon = item.category === 'fault' ? 'alert' : item.category === 'recovery' ? 'recovery' : 'activity';
  return (
    <li>
      <span className={`activity-marker activity-${item.category}`}>
        <Icon name={icon} size={16} />
      </span>
      <span className='activity-copy'>
        <strong>{item.name}</strong>
        <small>{formatRelativeTime(item.timestamp)}</small>
      </span>
      <code>{item.state}</code>
    </li>
  );
}
