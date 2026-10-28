import { Fragment, useState } from 'react';
import { filterBatteryRows, type BatteryFilter, type BatteryRow, type BatterySort } from '../domain/batteryHealth';
import StatusBadge from './StatusBadge';
import { friendlyEntityName, type EntityMap } from '../domain/safety';

const labels = { low: 'Niska bateria', unknown: 'Brak wiarygodnej oceny', current: 'Prawidłowy' } as const;
const filters: Array<[BatteryFilter, string]> = [
  ['all', 'Wszystkie'],
  ['low', 'Niskie'],
  ['unknown', 'Brak oceny'],
  ['current', 'Prawidłowe'],
];
const PAGE_SIZE = 50;

export default function BatteryHealth({ rows, total, entities = {} }: { rows: BatteryRow[]; total: number | null; entities?: EntityMap }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<BatteryFilter>('all');
  const [sort, setSort] = useState<BatterySort>('attention');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const filtered = filterBatteryRows(rows, query, status, sort);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(page, pages);
  const visible = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);
  return (
    <section className='page-stack' aria-label='Baterie urządzeń'>
      <header className='panel-header'>
        <div>
          <h2>Baterie urządzeń</h2>
          <p>Najpierw niskie baterie i brak oceny. Rozwiń urządzenie, aby sprawdzić odczyty i ostatni kontakt.</p>
        </div>
      </header>
      <div className='filter-row' role='group' aria-label='Filtr stanu baterii'>
        {filters.map(([value, label]) => (
          <button
            key={value}
            type='button'
            aria-pressed={status === value}
            className={`filter-button${status === value ? ' filter-button-active' : ''}`}
            onClick={() => {
              setStatus(value);
              setPage(1);
            }}
          >
            {label} ({value === 'all' ? rows.length : rows.filter(row => row.status === value).length})
          </button>
        ))}
      </div>
      <section className='panel entity-table-panel'>
        <div className='entity-filters battery-filters'>
          <label className='search-field'>
            <span>Szukaj baterii</span>
            <input
              type='search'
              value={query}
              placeholder='Nazwa urządzenia lub encja'
              onChange={event => {
                setQuery(event.target.value);
                setPage(1);
              }}
            />
          </label>
          <label className='select-field'>
            <span>Sortowanie baterii</span>
            <select
              value={sort}
              onChange={event => {
                setSort(event.target.value as BatterySort);
                setPage(1);
              }}
            >
              <option value='attention'>Wymagające uwagi najpierw</option>
              <option value='percentage-asc'>Poziom baterii: rosnąco</option>
              <option value='percentage-desc'>Poziom baterii: malejąco</option>
              <option value='name'>Nazwa urządzenia</option>
            </select>
          </label>
        </div>
        <p className='battery-results' role='status'>
          Wyniki: {filtered.length} z {rows.length} odczytanych urządzeń
          {total !== null && total > rows.length ? ` · monitoring obejmuje ${total}` : ''}
        </p>
        {visible.length ? (
          <table className='battery-table'>
            <thead>
              <tr>
                <th>Urządzenie</th>
                <th>Poziom</th>
                <th>Ocena</th>
                <th>Encje źródłowe</th>
              </tr>
            </thead>
            <tbody>
              {visible.map(row => (
                <Fragment key={row.key}>
                  <tr>
                    <td data-label='Urządzenie'>
                      <button
                        className='entity-name-button'
                        type='button'
                        aria-expanded={selected === row.key}
                        aria-controls={`battery-details-${row.key}`}
                        onClick={() => setSelected(selected === row.key ? null : row.key)}
                      >
                        <strong>{row.name}</strong>
                        <small>{selected === row.key ? 'Ukryj szczegóły' : 'Pokaż szczegóły'}</small>
                      </button>
                    </td>
                    <td data-label='Poziom'>
                      <strong className='battery-level'>{row.percentage === null ? '—' : `${row.percentage}%`}</strong>
                    </td>
                    <td data-label='Ocena'>
                      <StatusBadge tone={row.status === 'low' ? 'danger' : row.status === 'current' ? 'info' : 'muted'}>
                        {labels[row.status]}
                      </StatusBadge>
                    </td>
                    <td data-label='Encje źródłowe'>
                      {row.entityIds.length ? (
                        row.entityIds.map((id, index) => (
                          <span key={id} title={id}>
                            {index > 0 ? ' · ' : ''}
                            {friendlyEntityName(id, entities[id])}
                          </span>
                        ))
                      ) : (
                        <span>Brak danych o encji</span>
                      )}
                    </td>
                  </tr>
                  <tr className='battery-details-row' id={`battery-details-${row.key}`} hidden={selected !== row.key}>
                    <td colSpan={4}>
                      <section aria-label={`Szczegóły baterii: ${row.name}`} className='battery-evidence'>
                        <details>
                          <summary>Zaawansowana diagnostyka baterii</summary>
                          {row.entityIds.map(id => (
                            <code key={id}>{id}</code>
                          ))}
                          {row.evidence.map((line, index) => (
                            <p key={index}>{line}</p>
                          ))}
                        </details>
                        {row.detail && <p>{row.detail}</p>}
                        {!row.evidence.length && <p>Brak szczegółowych odczytów. Stan pochodzi z podsumowania monitoringu.</p>}
                      </section>
                    </td>
                  </tr>
                </Fragment>
              ))}
            </tbody>
          </table>
        ) : (
          <div className='empty-state compact-empty-state'>
            <strong>{rows.length ? 'Brak baterii spełniających filtry' : 'Brak danych baterii'}</strong>
            <p>
              {rows.length
                ? 'Zmień filtr stanu lub wyszukiwane hasło.'
                : 'Nie można na tej podstawie potwierdzić stanu urządzeń. Sprawdź dostępność diagnostyki.'}
            </p>
          </div>
        )}
        {pages > 1 && (
          <div className='pagination'>
            <span>
              Strona {current} z {pages}
            </span>
            <div>
              <button type='button' disabled={current === 1} onClick={() => setPage(current - 1)}>
                Poprzednia
              </button>
              <button type='button' disabled={current === pages} onClick={() => setPage(current + 1)}>
                Następna
              </button>
            </div>
          </div>
        )}
      </section>
      <details className='panel functional-safety-group'>
        <summary>Jak oceniana jest bateria?</summary>
        <p>
          Jeśli urządzenie udostępnia czas ostatniego kontaktu, to na nim opiera się ocena świeżości. Procent nie musi się zmieniać. Brak
          wiarygodnego kontaktu lub odczytu oznacza brak oceny. Prawidłowa bateria nie potwierdza sprawności funkcji bezpieczeństwa.
        </p>
      </details>
    </section>
  );
}
