import { useMemo, useState } from 'react';
import Icon from '../components/Icon';
import HelpTooltip from '../components/HelpTooltip';
import { formatNumeric, formatRelativeTime, trendPresentation, type TemperatureForecastView, type TemperatureView } from '../domain/safety';
import StatusBadge from '../components/StatusBadge';
import { useEntityHistory } from '../hooks/useEntityHistory';
import { useSafetyEntities } from '../hooks/useSafetyEntities';
import { chartSegments, numericHistory } from '../domain/history';

type TemperatureSort = 'name' | 'highest' | 'lowest' | 'trend';

export default function Temperature() {
  const { temperatures } = useSafetyEntities();
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<TemperatureSort>('name');

  const visibleTemperatures = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase('pl');
    return temperatures
      .filter(temperature =>
        [temperature.roomName, temperature.name, temperature.entityId].join(' ').toLocaleLowerCase('pl').includes(normalizedQuery)
      )
      .sort((left, right) => {
        if (sort === 'highest') return (right.state ?? Number.NEGATIVE_INFINITY) - (left.state ?? Number.NEGATIVE_INFINITY);
        if (sort === 'lowest') return (left.state ?? Number.POSITIVE_INFINITY) - (right.state ?? Number.POSITIVE_INFINITY);
        if (sort === 'trend') return Math.abs(right.rate ?? 0) - Math.abs(left.rate ?? 0);
        return left.roomName.localeCompare(right.roomName, 'pl');
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
          <span className='section-kicker'>Temperatury</span>
          <h2>Odczyty monitorowane przez system</h2>
          <p>Aktualne pomiary, tempo zmian, granice temperatury i ostatnie oceny prognozy.</p>
        </div>
        <div className='page-introduction-stat'>
          <strong>{temperatures.length}</strong>
          <span>aktywnych źródeł</span>
        </div>
      </section>

      <p className='temperature-forecast-explanation'>
        Kondycja „healthy” oznacza dostępne dane wejściowe, a nie bezpieczną prognozę. Ostatnia ocena modelu i potwierdzony alarm są
        pokazane oddzielnie. Zadania naprawy monitorowania nie są oceną ryzyka temperatury.
      </p>

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
  const historyPoints = numericHistory(history.entityHistory);
  const historyValues = historyPoints.map(item => item.value).filter((value): value is number => value !== null);
  const historyMinimum = historyValues.length > 0 ? Math.min(...historyValues) : null;
  const historyMaximum = historyValues.length > 0 ? Math.max(...historyValues) : null;

  return (
    <article className='temperature-card'>
      <div className='temperature-card-header'>
        <span className='temperature-card-icon'>
          <Icon name='temperature' size={21} />
        </span>
        <div>
          <h3 title={`${temperature.name} · ${temperature.entityId}`}>{temperature.roomName}</h3>
        </div>
        <span className={`trend-chip ${trend.className}`}>
          {trend.symbol} {trend.label}
        </span>
      </div>

      <div className='temperature-reading'>
        <strong>{formatNumeric(temperature.state, 2)}</strong>
        <span>{temperature.unit}</span>
      </div>

      <Sparkline
        highThreshold={temperature.highThreshold}
        loading={history.loading}
        lowThreshold={temperature.lowThreshold}
        points={historyPoints}
        error={history.error ?? (history.status === 'disconnected' ? 'Brak połączenia z historią' : null)}
      />

      <dl className='temperature-details'>
        <div>
          <dt className='label-with-help'>
            Zmiana{' '}
            <HelpTooltip
              label='Tempo zmiany temperatury'
              text='Wartość dodatnia oznacza wzrost, a ujemna spadek temperatury. Jednostka °C/min opisuje zmianę na minutę, nie samą temperaturę. To raportowany trend; brak wartości oznacza brak danych do jego oceny.'
            />
          </dt>
          <dd>{formatNumeric(temperature.rate, 3)} °C/min</dd>
        </div>
        <div>
          <dt className='label-with-help'>
            Przyspieszenie{' '}
            <HelpTooltip
              label='Przyspieszenie temperatury'
              text='Pokazuje, jak zmienia się tempo wzrostu lub spadku. Wartość dodatnia oznacza, że tempo staje się bardziej dodatnie, a ujemna — bardziej ujemne. Jednostka to °C/min². Odczyt należy interpretować razem z temperaturą i jej tempem zmiany.'
            />
          </dt>
          <dd>{formatNumeric(temperature.acceleration, 3)} °C/min²</dd>
        </div>
        <div>
          <dt className='label-with-help'>
            Min. / maks. 24 h{' '}
            <HelpTooltip
              label='Zakres temperatury z historii'
              text='Najniższa i najwyższa wartość w dostępnych próbkach historii Home Assistanta z ostatnich 24 godzin. Luki w historii mogą ukrywać wcześniejsze skrajne wartości. Brak próbek nie oznacza stabilnej temperatury.'
            />
          </dt>
          <dd>
            {formatNumeric(historyMinimum, 1)} / {formatNumeric(historyMaximum, 1)} °C
          </dd>
        </div>
        <div>
          <dt className='label-with-help'>
            Próg dolny{' '}
            <HelpTooltip
              label='Dolna granica temperatury'
              text='Granica skonfigurowana dla tego monitorowanego źródła. Nie jest uniwersalną temperaturą komfortu. Kreska oznacza, że próg nie został udostępniony.'
            />
          </dt>
          <dd>{formatThreshold(temperature.lowThreshold)}</dd>
        </div>
        <div>
          <dt className='label-with-help'>
            Próg górny{' '}
            <HelpTooltip
              label='Górna granica temperatury'
              text='Granica skonfigurowana dla tego monitorowanego źródła. Ocenę zagrożenia przedstawiają zdarzenia systemu; sam widoczny próg nie zastępuje tej oceny. Kreska oznacza brak udostępnionego progu.'
            />
          </dt>
          <dd>{formatThreshold(temperature.highThreshold)}</dd>
        </div>
      </dl>

      <ForecastDetails forecast={temperature.lowForecast} label='Prognoza dolnej granicy' />
      <ForecastDetails forecast={temperature.highForecast} label='Prognoza górnej granicy' />

      <span className='card-updated'>Aktualizacja {formatRelativeTime(temperature.lastUpdated)}</span>
    </article>
  );
}

function ForecastDetails({ forecast, label }: { forecast: TemperatureForecastView; label: string }) {
  const labels: Record<TemperatureForecastView['status'], string> = {
    risk: 'Model wskazał ryzyko',
    within_limits: 'Model w granicach',
    unevaluable: 'Nie można ocenić prognozy',
    not_evaluated: 'Oczekiwanie na ocenę',
    not_reported: 'Brak szczegółów oceny w tej wersji systemu',
    unknown: 'Nieznany wynik oceny',
  };
  const assessmentTime = forecast.evaluatedAt
    ? new Date(forecast.evaluatedAt).toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'medium' })
    : '—';
  return (
    <section aria-label={label} className='temperature-forecast'>
      <h4>{label}</h4>
      <StatusBadge tone={forecast.status === 'risk' ? 'warning' : 'muted'}>{labels[forecast.status]}</StatusBadge>
      <p>
        {forecast.activeFault === true
          ? 'Potwierdzony alarm dla tej prognozy pozostaje aktywny.'
          : forecast.activeFault === false
            ? 'Brak potwierdzonego aktywnego alarmu dla tej prognozy. To nie potwierdza bezpiecznej temperatury.'
            : 'Nie można ustalić, czy ta prognoza ma aktywny alarm. Sprawdź zdarzenia systemu.'}
      </p>
      <dl className='temperature-details'>
        <div>
          <dt>Ostatnia temperatura modelu</dt>
          <dd>{formatForecastTemperature(forecast.modeledTemperature)}</dd>
        </div>
        <div>
          <dt>Horyzont prognozy</dt>
          <dd>{forecast.timespanHours === null ? '—' : `${formatNumeric(forecast.timespanHours, 2)} h`}</dd>
        </div>
        <div>
          <dt>Granica prognozy</dt>
          <dd>{formatForecastTemperature(forecast.threshold)}</dd>
        </div>
        <div>
          <dt>Pomiar użyty w ocenie</dt>
          <dd>{formatForecastTemperature(forecast.temperature)}</dd>
        </div>
        <div>
          <dt>Tempo użyte w ocenie</dt>
          <dd>{forecast.rate === null ? '—' : `${formatNumeric(forecast.rate, 3)} °C/min`}</dd>
        </div>
        <div>
          <dt>Czas ostatniej oceny</dt>
          <dd>{assessmentTime}</dd>
        </div>
      </dl>
    </section>
  );
}

function Sparkline({
  points,
  error,
  loading,
  lowThreshold,
  highThreshold,
}: {
  points: Array<{ time: number; value: number | null }>;
  error: string | null;
  loading: boolean;
  lowThreshold: number | null;
  highThreshold: number | null;
}) {
  const values = points.map(item => item.value).filter((value): value is number => value !== null);
  if (error)
    return (
      <div className='sparkline sparkline-empty' role='status'>
        {error}
      </div>
    );
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
  const chartValues = [...values, ...(lowThreshold === null ? [] : [lowThreshold]), ...(highThreshold === null ? [] : [highThreshold])];
  const minimum = Math.min(...chartValues);
  const maximum = Math.max(...chartValues);
  const range = Math.max(maximum - minimum, 0.1);
  const yForValue = (value: number) => height - ((value - minimum) / range) * (height - 12) - 6;
  const end = Date.now();
  const segments = chartSegments(points, end - 24 * 3_600_000, end, width);

  return (
    <div className='sparkline'>
      <svg aria-label='Wykres temperatury z ostatnich 24 godzin' preserveAspectRatio='none' role='img' viewBox={`0 0 ${width} ${height}`}>
        <line className='sparkline-grid' x1='0' x2={width} y1={height / 2} y2={height / 2} />
        {lowThreshold !== null ? (
          <ThresholdLine label={`Dolny ${formatNumeric(lowThreshold, 1)} °C`} tone='low' width={width} y={yForValue(lowThreshold)} />
        ) : null}
        {highThreshold !== null ? (
          <ThresholdLine label={`Górny ${formatNumeric(highThreshold, 1)} °C`} tone='high' width={width} y={yForValue(highThreshold)} />
        ) : null}
        {segments.map((segment, index) => (
          <g key={index}>
            <polyline
              className='sparkline-line'
              points={segment.map(point => `${point.x.toFixed(1)},${yForValue(point.value).toFixed(1)}`).join(' ')}
            />
            {segment.length === 1 && <circle className='sparkline-point' cx={segment[0].x} cy={yForValue(segment[0].value)} r='2' />}
          </g>
        ))}
      </svg>
      <span>24 godziny</span>
    </div>
  );
}

function ThresholdLine({ label, tone, width, y }: { label: string; tone: 'low' | 'high'; width: number; y: number }) {
  const labelY = tone === 'high' ? y + 7 : y - 5;
  return (
    <g className={`sparkline-threshold sparkline-threshold-${tone}`}>
      <line x1='0' x2={width} y1={y} y2={y} />
      <text dominantBaseline='middle' textAnchor='end' x={width - 4} y={labelY}>
        {label}
      </text>
    </g>
  );
}

function formatThreshold(value: number | null): string {
  return value === null ? '—' : `${formatNumeric(value, 1)} °C`;
}

function formatForecastTemperature(value: number | null): string {
  return value === null ? '—' : `${formatNumeric(value, 2)} °C`;
}
