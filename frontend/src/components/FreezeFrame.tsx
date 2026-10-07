const fieldLabels: Record<string, string> = {
  version: 'Wersja danych',
  captured_at: 'Zapisano aktywację',
  fault: 'Usterka',
  category: 'Kategoria',
  priority: 'Priorytet',
  symptom: 'Źródło aktywacji',
  context: 'Kontekst aktywacji',
  configuration: 'Konfiguracja podczas aktywacji',
  configuration_fingerprint: 'Skrót konfiguracji',
  source: 'Dane źródłowe',
  active_restrictions: 'Ograniczenia podczas aktywacji',
  subject: 'Obiekt lub lokalizacja',
  first_failure_at: 'Pierwsza aktywacja',
  last_failure_at: 'Ostatnia aktywacja',
  last_valid_pass_at: 'Ostatnie potwierdzone ustąpienie',
  activation_count: 'Liczba aktywacji',
  last_reason: 'Przyczyna ostatniej aktywacji',
  active_duration_seconds: 'Czas aktywności (s)',
  clock_uncertain: 'Niepewność pomiaru czasu',
};

export default function FreezeFrame({ record }: { record: Record<string, unknown> }) {
  return (
    <section aria-label='Freeze frame' className='fault-diagnostic-block'>
      <strong>Freeze frame</strong>
      <p>Dane z aktywacji usterki oraz jej liczniki i czasy.</p>
      <dl className='details-grid'>
        {Object.entries(record).map(([key, value]) => (
          <div key={key}>
            <dt>{fieldLabels[key] ?? key}</dt>
            <dd>{formatValue(value)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Tak' : 'Nie';
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  return JSON.stringify(value);
}
