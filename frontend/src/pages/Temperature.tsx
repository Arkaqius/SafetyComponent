import { useMemo, useState } from 'react';
import Icon from '../components/Icon';
import { formatNumeric, formatRelativeTime, trendPresentation, type TemperatureView } from '../domain/safety';
import { useEntityHistory } from '../hooks/useEntityHistory';
import { useSafetyEntities } from '../hooks/useSafetyEntities';

type TemperatureSort = 'name' | 'highest' | 'lowest' | 'trend';

export default function Temperature() {
  const { temperatures } = useSafetyEntities();
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<TemperatureSort>('name');

  const visibleTemperatures = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase('pl');
    return temperatures
      .filter(temperature => [temperature.name, temperature.entityId].join(' ').toLocaleLowerCase('pl').includes(normalizedQuery))
      .sort((left, right) => {
        if (sort === 'highest') return (right.state ?? Number.NEGATIVE_INFINITY) - (left.state ?? Number.NEGATIVE_INFINITY);
        if (sort === 'lowest') return (left.state ?? Number.POSITIVE_INFINITY) - (right.state ?? Number.POSITIVE_INFINITY);
        if (sort === 'trend') return Math.abs(right.rate ?? 0) - Math.abs(left.rate ?? 0);
        return left.name.localeCompare(right.name, 'pl');
      });
  }, [query, sort, temperatures]);

  const availableValues = temperatures.map(temperature => temperature.state).filter((value): value is number => value !== null);
  const average = availableValues.length > 0 ? availableValues.reduce((sum, value) => sum + value, 0) / availableValues.length : null;
  const minimum = availableValues.length > 0 ? Math.min(...availableValues) : null;
  const maximum = availableValues.length > 0 ? Math.max(...availableValues) : null;

  return (
    <div className='page-stack'>
      <section className='page-introduction'>
        <div>
          <span className='section-kicker'>Temperature Component</span>
          <h2>Odczyty monitorowane przez system</h2>
          <p>
            Lista powstaje automatycznie na podstawie encji trendów <code>_rate</code> publikowanych przez SafetyComponent. Nie stosuje
            dodatkowych, wymyślonych progów.
          </p>
        </div>
        <div className='page-introduction-stat'>
          <strong>{temperatures.length}</strong>
          <span>aktywnych źródeł</span>
        </div>
      </section>

      <section aria-label='Statystyki temperatury' className='metric-strip'>
        <Metric label='Średnia' value={average} />
        <Metric label='Najniższa' value={minimum} />
        <Metric label='Najwyższa' value={maximum} />
        <div className='metric-item'>
          <span>Dostępność</span>
          <strong>
            {availableValues.length}/{temperatures.length}
          </strong>
          <small>źródeł z odczytem</small>
        </div>
      </section>

      <section className='list-controls'>
        <label className='search-field temperature-search'>
          <span className='sr-only'>Szukaj temperatury</span>
          <Icon name='temperature' size={17} />
          <input
            onChange={event => setQuery(event.target.value)}
            placeholder='Szukaj pomieszczenia lub encji…'
            type='search'
            value={query}
          />
        </label>
        <label className='select-field'>
          <span>Sortowanie</span>
          <select onChange={event => setSort(event.target.value as TemperatureSort)} value={sort}>
            <option value='name'>Nazwa A–Z</option>
            <option value='highest'>Najwyższa temperatura</option>
            <option value='lowest'>Najniższa temperatura</option>
            <option value='trend'>Największa zmiana</option>
          </select>
        </label>
      </section>

      {visibleTemperatures.length > 0 ? (
        <section aria-live='polite' className='temperature-grid'>
          {visibleTemperatures.map(temperature => (
            <TemperatureCard key={temperature.entityId} temperature={temperature} />
          ))}
        </section>
      ) : (
        <section className='panel empty-state page-empty-state'>
          <div className='empty-state-icon'>
            <Icon name='temperature' size={30} />
          </div>
          <strong>{temperatures.length === 0 ? 'Brak danych temperatury' : 'Brak wyników wyszukiwania'}</strong>
          <p>
            {temperatures.length === 0
              ? 'Nie znaleziono encji temperatur posiadających parę trendu SafetyComponent.'
              : 'Zmień tekst wyszukiwania, aby zobaczyć inne pomiary.'}
          </p>
        </section>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | null }) {
  return (
    <div className='metric-item'>
      <span>{label}</span>
      <strong>{formatNumeric(value, 1)} °C</strong>
      <small>bieżące odczyty</small>
    </div>
  );
}

function TemperatureCard({ temperature }: { temperature: TemperatureView }) {
  const history = useEntityHistory(temperature.entityId, {
    hoursToShow: 24,
    minimalResponse: true,
    significantChangesOnly: false,
  });
  const trend = trendPresentation(temperature.rate);
  const historyValues = history.entityHistory.map(item => Number(item.s)).filter(value => Number.isFinite(value));
  if (temperature.state !== null) historyValues.push(temperature.state);
  const historyMinimum = historyValues.length > 0 ? Math.min(...historyValues) : null;
  const historyMaximum = historyValues.length > 0 ? Math.max(...historyValues) : null;

  return (
    <article className='temperature-card'>
      <div className='temperature-card-header'>
        <span className='temperature-card-icon'>
          <Icon name='temperature' size={21} />
        </span>
        <div>
          <h3>{temperature.name}</h3>
          <code>{temperature.entityId}</code>
        </div>
        <span className={`trend-chip ${trend.className}`}>
          {trend.symbol} {trend.label}
        </span>
      </div>

      <div className='temperature-reading'>
        <strong>{formatNumeric(temperature.state, 2)}</strong>
        <span>{temperature.unit}</span>
      </div>

      <Sparkline loading={history.loading} values={historyValues} />

      <dl className='temperature-details'>
        <div>
          <dt>Zmiana</dt>
          <dd>{formatNumeric(temperature.rate, 3)} °C/min</dd>
        </div>
        <div>
          <dt>Przyspieszenie</dt>
          <dd>{formatNumeric(temperature.acceleration, 3)} °C/min²</dd>
        </div>
        <div>
          <dt>Min. / maks. 24 h</dt>
          <dd>
            {formatNumeric(historyMinimum, 1)} / {formatNumeric(historyMaximum, 1)} °C
          </dd>
        </div>
      </dl>

      <span className='card-updated'>Aktualizacja {formatRelativeTime(temperature.lastUpdated)}</span>
    </article>
  );
}

function Sparkline({ values, loading }: { values: number[]; loading: boolean }) {
  if (loading && values.length < 2) {
    return <div aria-label='Ładowanie historii' className='sparkline sparkline-loading' />;
  }
  if (values.length < 2) {
    return (
      <div className='sparkline sparkline-empty'>
        <span>Historia 24 h pojawi się po zebraniu danych</span>
      </div>
    );
  }

  const width = 320;
  const height = 82;
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = Math.max(maximum - minimum, 0.1);
  const points = values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * width;
      const y = height - ((value - minimum) / range) * (height - 12) - 6;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  return (
    <div className='sparkline'>
      <svg aria-label='Wykres temperatury z ostatnich 24 godzin' preserveAspectRatio='none' role='img' viewBox={`0 0 ${width} ${height}`}>
        <line className='sparkline-grid' x1='0' x2={width} y1={height / 2} y2={height / 2} />
        <polyline className='sparkline-line' points={points} />
      </svg>
      <span>24 godziny</span>
    </div>
  );
}
