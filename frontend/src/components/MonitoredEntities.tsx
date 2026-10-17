import { useMemo, useState } from 'react';
import HelpTooltip from './HelpTooltip';
import StatusBadge from './StatusBadge';
import {
  formatEntityCheckObservation,
  type EntityCheckView,
  type EntityHealth as EntityHealthState,
  type EntityMonitorSummary,
  type MonitoredEntityView,
} from '../domain/entityHealth';
import { formatRelativeTime, localizedEntityState, type StatusTone } from '../domain/safety';
import { useEntityHistory } from '../hooks/useEntityHistory';

const PAGE_SIZE = 50;

const healthPresentation: Record<EntityHealthState, { label: string; tone: StatusTone }> = {
  healthy: { label: 'Sprawna', tone: 'safe' },
  degraded: { label: 'Wymaga uwagi', tone: 'warning' },
  stale: { label: 'Dane nieaktualne', tone: 'warning' },
  unavailable: { label: 'Niedostępna', tone: 'danger' },
};

export default function MonitoredEntities({ monitored, summary }: { monitored: MonitoredEntityView[]; summary: EntityMonitorSummary }) {
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
  const selectedEntity = monitored.find(entity => entity.diagnosticEntityId === selected);

  return (
    <section className='page-stack' aria-label='Monitorowane encje'>
      <header className='panel-header'>
        <div>
          <h2>Monitorowane encje ({summary.total})</h2>
          <p>Źródła danych używane przez funkcje bezpieczeństwa. Baterie urządzeń mają osobną podzakładkę.</p>
        </div>
      </header>
      <section aria-label='Podsumowanie monitorowanych encji' className='entity-health-summary'>
        <HealthMetric
          label='Wszystkie'
          value={summary.total}
          help='Źródła objęte diagnostyką SafetyComponent. To nie jest liczba wszystkich encji Home Assistanta ani urządzeń w domu.'
        />
        <HealthMetric
          label='Sprawne'
          tone='safe'
          value={summary.healthy}
          help='Źródła uznane za sprawne przez diagnostykę. To ocena jakości danych, a nie potwierdzenie braku zagrożenia: sprawny czujnik może zgłaszać alarm.'
        />
        <HealthMetric
          label='Wymagają uwagi'
          tone='warning'
          value={summary.degraded + summary.stale}
          help='Źródła z ograniczoną jakością danych lub nieaktualnym odczytem. Rozwiń źródło, aby zobaczyć wyniki kontroli i ich przyczyny.'
        />
        <HealthMetric
          label='Niedostępne'
          tone='danger'
          value={summary.unavailable}
          help='Źródła, których wymaganych danych nie można obecnie wiarygodnie wykorzystać. Brak danych nie potwierdza bezpiecznego stanu; po utracie połączenia widoczne liczby są ostatnim znanym wynikiem.'
        />
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
            label='Pochodzenie'
            onChange={value => {
              setSource(value as typeof source);
              setPage(1);
            }}
            value={source}
            options={[
              ['all', 'Użytkownika i systemu'],
              ['explicit', 'Wskazane przez użytkownika'],
              ['component', 'Ochrona działania systemu'],
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
                      className={selected === entity.diagnosticEntityId ? 'selected' : ''}
                      key={entity.diagnosticEntityId}
                      onClick={() => setSelected(selected === entity.diagnosticEntityId ? null : entity.diagnosticEntityId)}
                    >
                      <td>
                        <button className='entity-name-button' title={entity.entityId} type='button'>
                          <strong>{entity.friendlyName}</strong>
                          <small>{entity.entityId}</small>
                        </button>
                      </td>
                      <td>{entity.areaName ?? 'Nieprzypisana'}</td>
                      <td>
                        {entity.sourceGroups
                          .map(sourceCode => (sourceCode === 'explicit' ? 'Wskazana przez użytkownika' : 'Ochrona działania systemu'))
                          .join(' · ')}
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

      {selectedEntity ? <EntityDetails entity={selectedEntity} /> : null}
    </section>
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
          <dd>
            {entity.sourceGroups
              .map(source => (source === 'explicit' ? 'Wskazana przez użytkownika' : 'Ochrona działania systemu'))
              .join(' · ')}
          </dd>
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
        {history.status === 'error' || history.status === 'disconnected' ? (
          <p role='status'>{history.error ?? 'Historia niedostępna: brak połączenia.'}</p>
        ) : history.loading && transitions.length === 0 ? (
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
        <span>{reasonLabel(check.check, check.reason, check.observedValue)}</span>
      </div>
      <StatusBadge tone={tone}>{resultLabel(check.result)}</StatusBadge>
      <small>{Object.keys(check.calibration).length ? calibrationLabel(check.calibration) : 'Kontrola podstawowa'}</small>
    </article>
  );
}

function HealthMetric({ label, value, tone = 'info', help }: { label: string; value: number; tone?: StatusTone; help?: string }) {
  return (
    <article className={`health-metric metric-${tone}`}>
      <span className='label-with-help'>
        {label}
        {help && <HelpTooltip label={label} text={help} />}
      </span>
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
        recovery_command: 'Wykonanie działania naprawczego',
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
function reasonLabel(check: string, reason: string, value: unknown): string {
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
    no_outstanding_command_failure: 'Brak zapisanej awarii polecenia',
    restored_command_failure: 'Zapisana awaria polecenia po ponownym uruchomieniu',
    command_failed: 'Polecenie wykonania zostało odrzucone',
    postcondition_timeout: 'Nie potwierdzono oczekiwanego skutku w wymaganym czasie',
    postcondition_unverified_after_restart: 'Nie potwierdzono skutku przed ponownym uruchomieniem',
    postcondition_confirmed: 'Potwierdzono oczekiwany stan końcowy',
  };
  const observation = formatEntityCheckObservation(check, value);
  const observed = observation ? ` · ${observation}` : '';
  return `${labels[reason] ?? reason}${observed}`;
}
function calibrationLabel(calibration: Record<string, unknown>): string {
  const labels: Record<string, string> = {
    timestamp_source: 'Źródło czasu',
    max_silence_seconds: 'Maksymalny wiek raportu',
    report_timeout_seconds: 'Maksymalny wiek raportu',
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
    last_reported: 'ostatni raport źródła',
    state: 'stan encji',
  };
  const seconds = new Set(['max_silence_seconds', 'report_timeout_seconds', 'window_seconds']);
  return Object.entries(calibration)
    .map(([key, value]) => {
      const rendered = Array.isArray(value) ? value.join(', ') : (values[String(value)] ?? String(value));
      return `${labels[key] ?? key.replace(/_/g, ' ')}: ${rendered}${seconds.has(key) ? ' s' : ''}`;
    })
    .join(' · ');
}
