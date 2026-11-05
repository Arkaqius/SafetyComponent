import Icon, { type IconName } from './Icon';
import { routineRunLabel, type CheckStatus, type RoutineResult, type RoutineRun } from '../domain/safetyRoutines';

const groups: ReadonlyArray<{ status: CheckStatus; title: string; icon: IconName }> = [
  { status: 'problem', title: 'Wymaga uwagi', icon: 'alert' },
  { status: 'unknown', title: 'Brak oceny', icon: 'help' },
  { status: 'pass', title: 'Zgodne z oczekiwaniem', icon: 'shield' },
  { status: 'skipped', title: 'Pominięte', icon: 'chevron' },
];

const stateLabels = new Map([
  ['awake', 'Domownicy nie śpią'],
  ['asleep', 'Domownicy śpią'],
  ['occupied', 'Domownicy są w domu'],
  ['empty', 'Nikogo nie ma w domu'],
  ['home', 'W domu'],
  ['away_short', 'Krótka nieobecność'],
  ['away_long', 'Długa nieobecność'],
  ['preheat', 'Podgrzewanie przed powrotem'],
  ['open', 'Otwarte'],
  ['closed', 'Zamknięte'],
  ['locked', 'Zaryglowane'],
  ['unlocked', 'Odryglowane'],
  ['true', 'Tak'],
  ['false', 'Nie'],
]);

const number = new Intl.NumberFormat('pl-PL', { maximumSignificantDigits: 17 });
const finishedTime = new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'short' });

function stateLabel(value: string, entity: string) {
  if (value === 'on') return entity.startsWith('binary_sensor.') ? 'Sygnał aktywny' : 'Włączone';
  if (value === 'off') return entity.startsWith('binary_sensor.') ? 'Sygnał nieaktywny' : 'Wyłączone';
  return stateLabels.get(value) ?? 'Stan opisany w szczegółach';
}

function range(result: RoutineResult, format: (value: number) => string) {
  const unit = result.unit ? ` ${result.unit}` : '';
  if (result.minimum !== null && result.maximum !== null) return `${format(result.minimum)}–${format(result.maximum)}${unit}`;
  if (result.minimum !== null) return `Co najmniej ${format(result.minimum)}${unit}`;
  if (result.maximum !== null) return `Najwyżej ${format(result.maximum)}${unit}`;
  return 'Brak progu';
}

function CheckRow({ result }: { result: RoutineResult }) {
  const readout =
    typeof result.value === 'number'
      ? `${number.format(result.value)}${result.unit ? ` ${result.unit}` : ''}`
      : result.value === null
        ? 'Brak odczytu'
        : stateLabel(String(result.value), result.entity_id);
  const expected = result.expected_states
    ? [...new Set(result.expected_states.map(state => stateLabel(state, result.entity_id)))].join(' lub ')
    : range(result, value => number.format(value));

  return (
    <li>
      <details className='routine-check'>
        <summary className='routine-check-summary'>
          <span className='routine-check-name'>
            <strong>{result.name}</strong>
            {(result.status === 'unknown' || result.status === 'skipped') && <span>{result.reason_label}</span>}
          </span>
          {(result.status === 'problem' || result.status === 'pass') && (
            <span className='routine-check-reading'>
              <span className='routine-check-current'>
                Odczyt <strong>{readout}</strong>
              </span>
              {result.status === 'problem' && expected !== result.name && (
                <span>
                  Oczekiwanie <b>{expected}</b>
                </span>
              )}
            </span>
          )}
          <Icon name='chevron' size={16} className='routine-report-chevron' />
        </summary>
        <dl className='routine-check-details'>
          <div>
            <dt>Odczyt źródłowy</dt>
            <dd>{result.value === null ? 'Brak wartości' : `${String(result.value)}${result.unit ? ` ${result.unit}` : ''}`}</dd>
          </div>
          <div>
            <dt>Oczekiwanie</dt>
            <dd>{result.expected_states?.join(', ') ?? range(result, String)}</dd>
          </div>
          <div>
            <dt>Encja</dt>
            <dd>
              <code>{result.entity_id}</code>
            </dd>
          </div>
          <div>
            <dt>Czas obserwacji</dt>
            <dd>
              {result.observed_at ? (
                <time dateTime={result.observed_at}>{new Date(result.observed_at).toLocaleString('pl-PL')}</time>
              ) : (
                'Brak znacznika źródła'
              )}
            </dd>
          </div>
          <div>
            <dt>Wyjaśnienie</dt>
            <dd>{result.reason_label}</dd>
          </div>
        </dl>
      </details>
    </li>
  );
}

export default function RoutineReportResults({ run }: { run: RoutineRun }) {
  const resultGroups = groups.map(group => ({ ...group, results: run.results?.filter(result => result.status === group.status) ?? [] }));
  const total = Object.values(run.counts).reduce((sum, count) => sum + count, 0);
  const status = run.state === 'completed' ? run.status : 'pending';
  const icon = groups.find(group => group.status === status)?.icon ?? 'history';
  return (
    <div className='routine-report-results'>
      <div className='routine-verdict' data-status={status}>
        <span className='routine-verdict-mark'>
          <Icon name={icon} size={24} />
        </span>
        <div className='routine-verdict-copy'>
          <h4>{routineRunLabel(run)}</h4>
          {run.finished_at && <time dateTime={run.finished_at}>{finishedTime.format(new Date(run.finished_at))}</time>}
        </div>
        {total > 0 && (
          <div className='routine-verdict-breakdown'>
            <div className='routine-verdict-track' aria-hidden='true'>
              {groups
                .filter(group => run.counts[group.status] > 0)
                .map(({ status }) => (
                  <span key={status} data-status={status} style={{ flexGrow: run.counts[status] }} />
                ))}
            </div>
            <ul className='routine-verdict-counts' aria-label='Podsumowanie sprawdzeń'>
              {groups
                .filter(group => run.counts[group.status] > 0)
                .map(({ status, title }) => (
                  <li key={status} data-status={status}>
                    {title} <strong>{run.counts[status]}</strong>
                  </li>
                ))}
            </ul>
          </div>
        )}
      </div>
      {run.evidence_incomplete && run.counts.unknown === 0 && (
        <p className='routine-report-note'>Podczas kontroli brakowało części danych.</p>
      )}
      {resultGroups.map(({ status, title, icon, results }) => {
        if (!results.length) return null;
        const rows = (
          <ul className='routine-check-list'>
            {results.map(result => (
              <CheckRow key={result.check_id} result={result} />
            ))}
          </ul>
        );
        const heading = (
          <>
            <Icon name={icon} size={17} />
            <span>{title}</span>
            <span className='routine-group-count'>{results.length}</span>
          </>
        );
        return status === 'pass' || status === 'skipped' ? (
          <details className='routine-result-group' data-status={status} key={status}>
            <summary className='routine-group-heading'>
              {heading}
              <Icon name='chevron' size={16} className='routine-report-chevron' />
            </summary>
            {rows}
          </details>
        ) : (
          <section className='routine-result-group' data-status={status} key={status}>
            <h5 className='routine-group-heading'>{heading}</h5>
            {rows}
          </section>
        );
      })}
    </div>
  );
}
