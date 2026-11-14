import Icon from '../components/Icon';
import HelpTooltip from '../components/HelpTooltip';
import StatusBadge from '../components/StatusBadge';
import {
  formatRelativeTime,
  observationDisplayName,
  type ExternalCategoryView,
  type ExternalHazardStatus,
  type ExternalProviderView,
  type OfficialWarningView,
} from '../domain/safety';
import { useSafetyEntities } from '../hooks/useSafetyEntities';

export default function ExternalHazards() {
  const { externalHazards } = useSafetyEntities();
  const official = externalHazards.categories.find(category => category.capability === 'OfficialWeatherWarnings')!;
  const allDisabled = externalHazards.categories.every(category => ['disabled', 'component_disabled'].includes(category.selectionState));
  const testOnly = externalHazards.categories.some(category => category.selectionState === 'test') && !externalHazards.monitoringActive;
  const presentation =
    externalHazards.activeHazards.length || externalHazards.monitoringEvaluated
      ? hazardPresentation(externalHazards.status)
      : {
          tone: 'muted' as const,
          label: allDisabled ? 'Wyłączone' : testOnly ? 'Podgląd testowy' : 'Ocena niepotwierdzona',
          detail: allDisabled
            ? 'Monitorowanie danych zewnętrznych jest wyłączone.'
            : testOnly
              ? 'Dane syntetyczne nie potwierdzają rzeczywistego bezpieczeństwa domu.'
              : 'Ocena wymaga aktualnego stanu zastosowanej konfiguracji i wiarygodnych danych.',
        };
  const evaluated = externalHazards.monitoringEvaluated;
  const displayCount = (count: number) => (count > 0 || evaluated ? count : '—');
  const healthy = externalHazards.categories.filter(category =>
    ['healthy_empty', 'active', 'available'].includes(category.evidenceState)
  ).length;
  const selected = externalHazards.categories.filter(category => category.selectionState === 'enabled').length;
  return (
    <div className={`page-stack external-monitoring-${presentation.tone}`}>
      <section className={`page-introduction external-introduction external-${presentation.tone}`}>
        <div>
          <span className='section-kicker'>Warunki zewnętrzne</span>
          <h2>Ochrona domu przed warunkami zewnętrznymi</h2>
          <p>
            System łączy wybrane źródła pogody, jakości powietrza i oficjalnych ostrzeżeń ze stanem skonfigurowanych okien i drzwi.
            Wyłączenie źródła nie potwierdza braku zagrożenia. Polecenia zamknięcia wymagają osobnego potwierdzenia.
          </p>
        </div>
        <div className='external-current-state'>
          <StatusBadge tone={presentation.tone} pulse={externalHazards.status === 'severe' || externalHazards.status === 'warning'}>
            {presentation.label}
          </StatusBadge>
          <small>Ocena {formatRelativeTime(externalHazards.lastEvaluatedAt ?? externalHazards.lastUpdated)}</small>
        </div>
      </section>
      <section aria-label='Podsumowanie zagrożeń zewnętrznych' className='metric-strip'>
        <Metric
          label='Aktywne zagrożenia'
          value={displayCount(externalHazards.activeHazards.length)}
          detail={
            externalHazards.activeSymptomCount > 0
              ? `${externalHazards.activeSymptomCount} aktywnych warunków`
              : 'Brak bieżącej oceny bez aktywnego monitorowania'
          }
        />
        <Metric label='Narażone wejścia' value={displayCount(externalHazards.affectedOpenings.length)} detail='okna, drzwi lub brama' />
        <Metric
          label='Źródła dostępne'
          value={selected ? `${healthy}/${selected}` : '—'}
          detail={selected ? 'wybrane rzeczywiste źródła' : 'brak aktywnych rzeczywistych źródeł'}
        />
        <Metric label='Blokady porad' value={displayCount(externalHazards.adviceInhibition.length)} detail='sprzeczne porady otwarcia' />
      </section>
      <section aria-label='Kategorie danych zewnętrznych' className='external-provider-grid'>
        {externalHazards.categories.map(category => (
          <article
            className={`panel external-category-card provider-${categoryTone(category)}`}
            data-capability={category.capability}
            key={category.capability}
          >
            <h3>{category.label}</h3>
            <StatusBadge tone={categoryTone(category)}>{categoryMessage(category)}</StatusBadge>
            {category.name && category.selectionState === 'enabled' ? <p>{category.name}</p> : null}
            <p className='external-category-count'>
              Bieżące obserwacje: <strong>{category.currentCount ?? '—'}</strong>
            </p>
            {category.hazards.length ? <small>Zakres: {category.hazards.map(hazardLabel).join(', ')}</small> : null}
            {category.diagnostic ? <ProviderCard provider={category.diagnostic} /> : null}
          </article>
        ))}
      </section>
      {(externalHazards.coverageDetails?.length ?? 0) > 0 ? (
        <section className='panel external-coverage-panel' aria-label='Zakres danych zewnętrznych'>
          <h2>Zakres danych zewnętrznych</h2>
          <p>Dostępność jednej kategorii nie potwierdza pokrycia innej.</p>
          <ul>
            {externalHazards.coverageDetails?.map(item => {
              const category = externalHazards.categories.find(category => category.capability === item.capability)!;
              return (
                <li key={`${item.capability}-${item.hazard}`}>
                  <strong>
                    {providerDescription(item.capability)} — {hazardLabel(item.hazard)}
                  </strong>
                  :{' '}
                  {['disabled', 'component_disabled', 'test', 'unknown'].includes(category.selectionState)
                    ? categoryMessage(category)
                    : coverageLabel(item.status)}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
      {externalHazards.activeHazards.length > 0 ? (
        <section className='panel external-active-panel'>
          <h2>Warunki wymagające uwagi</h2>
          {externalHazards.retainedDanger ? (
            <p className='configuration-message configuration-message-warning'>
              Zachowane rzeczywiste zagrożenie — brak nowych dowodów pozwalających je skasować. Wyłączone źródło lub podgląd testowy nie
              usuwa alarmu.
            </p>
          ) : null}
          <div className='external-active-grid'>
            <div>
              <span>Zagrożenia</span>
              <strong>{externalHazards.activeHazards.map(hazardLabel).join(', ')}</strong>
            </div>
            <div>
              <span>Dotknięte wejścia</span>
              <strong>{externalHazards.affectedOpenings.join(', ') || 'Zakres wymaga weryfikacji'}</strong>
            </div>
          </div>
        </section>
      ) : (
        <section className={`panel external-clear-panel ${!evaluated ? 'provider-muted' : ''}`}>
          <span className='external-clear-icon'>
            <Icon name='shield' size={26} />
          </span>
          <div>
            <strong>
              {evaluated && externalHazards.status === 'clear'
                ? 'Brak aktywnej ekspozycji'
                : allDisabled
                  ? 'Monitorowanie wyłączone'
                  : 'Ocena wymaga aktualnych danych'}
            </strong>
            <p>{presentation.detail}</p>
          </div>
        </section>
      )}
      {externalHazards.adviceInhibition.length > 0 ? (
        <section className='panel advice-panel'>
          <h2>Nie zalecaj otwierania okien</h2>
          <ul>
            {externalHazards.adviceInhibition.map(item => (
              <li key={`${item.reason}-${item.source}`}>
                <strong>{humanizeReason(item.reason)}</strong>
                <span>
                  Źródło: {externalHazards.providers.find(provider => provider.provider === item.source)?.name ?? 'Wybrane źródło danych'}
                  {item.validUntil ? ` · ważne do ${new Date(item.validUntil).toLocaleString('pl-PL')}` : ''}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <section className={`panel official-warnings-panel provider-${categoryTone(official)}`} aria-label='Oficjalne ostrzeżenia pogodowe'>
        <div className='panel-header'>
          <div>
            <span className='section-kicker'>Oficjalne komunikaty</span>
            <h2>Oficjalne ostrzeżenia pogodowe</h2>
            <p>Komunikaty wybranego rzeczywistego źródła dla lokalizacji domu.</p>
          </div>
          <strong className='official-warning-count'>{official.currentCount ?? '—'}</strong>
        </div>
        {externalHazards.officialWarnings.length ? (
          <div className='official-warning-list'>
            {externalHazards.officialWarnings.map(warning => (
              <OfficialWarning key={`${warning.provider}:${warning.id}`} warning={warning} />
            ))}
          </div>
        ) : (
          <p className='official-warning-empty'>{categoryMessage(official)}</p>
        )}
      </section>
      {externalHazards.testPreview ? (
        <section className='panel external-test-preview' aria-label='Podgląd źródła testowego'>
          <span className='section-kicker'>Źródło testowe — dane syntetyczne</span>
          <h2>{externalHazards.testPreview.name}</h2>
          <p>Podgląd nie wpływa na rzeczywiste alarmy, pokrycie, powiadomienia ani polecenia.</p>
          <StatusBadge tone='muted'>{previewHealthLabel(externalHazards.testPreview.health)}</StatusBadge>
          <p>
            Scenariusz testowy: <strong>{externalHazards.testPreview.scenario}</strong>
          </p>
          <p>
            Testowe obserwacje: <strong>{externalHazards.testPreview.count}</strong>
          </p>
          {externalHazards.testPreview.warnings.map(warning => (
            <div key={warning.id}>
              <strong>Dane testowe</strong>
              <OfficialWarning warning={warning} />
            </div>
          ))}
          {!externalHazards.testPreview.warnings.length
            ? externalHazards.testPreview.observations.map(item => (
                <article className='official-warning-card' key={item.id}>
                  <h3>{hazardLabel(item.hazardType)} — dane testowe</h3>
                  <p>
                    {item.displayValue} {item.displayUnit}
                  </p>
                </article>
              ))
            : null}
        </section>
      ) : testOnly ? (
        <section className='panel external-test-preview' aria-label='Podgląd źródła testowego'>
          <h2>Źródło testowe — dane syntetyczne</h2>
          <p>Oczekiwanie na dane testowe z bieżącego uruchomienia.</p>
        </section>
      ) : null}
      {externalHazards.retainedWarnings.length > 0 ? (
        <section className='panel external-retained-panel' aria-label='Zachowane ostrzeżenia'>
          <h2>Zachowane ostrzeżenia</h2>
          <p>Historyczne lub pochodzące z nieaktywnego źródła. Nie potwierdzają aktualnego stanu monitorowania.</p>
          {externalHazards.retainedWarnings.map(warning => (
            <OfficialWarning key={`${warning.provider}:${warning.id}`} warning={warning} />
          ))}
        </section>
      ) : null}
    </div>
  );
}

function categoryTone(category: ExternalCategoryView) {
  if (category.selectionState !== 'enabled') return 'muted' as const;
  if (category.evidenceState === 'active') return 'danger' as const;
  if (['healthy_empty', 'available'].includes(category.evidenceState)) return 'safe' as const;
  if (['unavailable', 'stale'].includes(category.evidenceState)) return 'warning' as const;
  return 'muted' as const;
}
function categoryMessage(category: ExternalCategoryView): string {
  if (category.selectionState === 'disabled') return 'Wyłączone';
  if (category.selectionState === 'component_disabled') return 'Wyłączone — komponent nie monitoruje';
  if (category.selectionState === 'unknown') return 'Brak aktualnego stanu konfiguracji';
  if (category.selectionState === 'test') return 'Źródło testowe — dane syntetyczne';
  return {
    unknown: 'Brak aktualnej oceny',
    unsupported: 'Zagrożenie poza zakresem źródła',
    awaiting_evidence: 'Oczekiwanie na dane',
    unavailable: 'Brak wiarygodnych danych',
    stale: 'Dane nieaktualne',
    healthy_empty: 'Brak aktualnych ostrzeżeń w obsługiwanym zakresie',
    active: 'Aktywne ostrzeżenia',
    available: 'Dane dostępne',
    not_evaluated: 'Nie oceniono',
  }[category.evidenceState];
}
function previewHealthLabel(health: string): string {
  return (
    {
      ok: 'Dane testowe dostępne',
      unavailable: 'Test: źródło niedostępne',
      stale: 'Test: dane nieaktualne',
      schema_error: 'Test: błąd danych',
    }[health] ?? 'Test: stan nieznany'
  );
}

function OfficialWarning({ warning }: { warning: OfficialWarningView }) {
  return (
    <article className={`official-warning-card${warning.locallyApplicable ? ' official-warning-local' : ''}`}>
      <header>
        <div>
          <h3>{warning.eventName}</h3>
          <small>{warning.office || warning.sourceName}</small>
        </div>
        <div className='official-warning-badges'>
          {warning.locallyApplicable && <span className='official-local-badge'>Dotyczy domu</span>}
          {warning.degree && <span className='official-degree-badge'>Poziom {warning.degree}</span>}
        </div>
      </header>
      <p>{warning.content || 'Brak opisu ostrzeżenia.'}</p>
      {warning.comment && <p className='official-warning-comment'>{warning.comment}</p>}
      <dl>
        <div>
          <dt>Obowiązuje</dt>
          <dd>{formatPeriod(warning.validFrom, warning.validTo)}</dd>
        </div>
        <div>
          <dt>Prawdopodobieństwo</dt>
          <dd>{warning.probability ? `${warning.probability}%` : 'brak danych'}</dd>
        </div>
        <div>
          <dt>Lokalizacja</dt>
          <dd>Dotyczy lokalizacji domu</dd>
        </div>
      </dl>
    </article>
  );
}

function formatPeriod(from?: string, to?: string): string {
  const format = (value?: string) => {
    if (!value) return 'brak danych';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 'brak danych' : date.toLocaleString('pl-PL');
  };
  return `${format(from)} – ${format(to)}`;
}

function Metric({ label, value, detail }: { label: string; value: number | string; detail: string }) {
  return (
    <div className='metric-item'>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function ProviderCard({ provider }: { provider: ExternalProviderView }) {
  const tone =
    provider.status === 'ok' ? 'safe' : provider.status === 'stale' ? 'warning' : provider.status === 'unknown' ? 'muted' : 'danger';
  const label =
    provider.status === 'ok'
      ? 'Dostępne'
      : provider.status === 'stale'
        ? 'Nieaktualne'
        : provider.status === 'schema_error'
          ? 'Błąd danych'
          : provider.status === 'unavailable'
            ? 'Niedostępne'
            : 'Stan nieznany';
  return (
    <article className={`external-provider-card provider-${tone}`}>
      <header>
        <span className='external-provider-icon'>
          <Icon name='environment' size={21} />
        </span>
        <div>
          <h3>{provider.name}</h3>
          <small>{providerDescription(provider.capability)}</small>
          {provider.hazards?.length ? <small>Zakres: {provider.hazards.map(hazardLabel).join(', ')}</small> : null}
        </div>
        <StatusBadge tone={tone}>{label}</StatusBadge>
      </header>
      <dl>
        <div>
          <dt className='label-with-help'>
            Ostatni poprawny odczyt{' '}
            <HelpTooltip
              label='Aktualność źródła zewnętrznego'
              text='Czas ostatniego poprawnego pobrania danych ze źródła. Może być starszy niż dopuszczalny czas aktualności. Bieżącą dostępność wskazuje status źródła; ostatni poprawny odczyt sam nie potwierdza aktualnej oceny.'
            />
          </dt>
          <dd>{formatRelativeTime(provider.lastSuccessAt)}</dd>
        </div>
        <div>
          <dt>Obserwacje</dt>
          <dd className='label-with-help'>
            {provider.observationCount ?? '—'}
            <HelpTooltip
              label={`Monitorowane dane: ${provider.name}`}
              text={
                provider.observations.length > 0
                  ? provider.observations.map(observationDisplayName).join(' · ')
                  : 'Brak udostępnionej listy obserwacji. Sam licznik nie potwierdza aktualności danych.'
              }
            />
          </dd>
        </div>
        <div>
          <dt className='label-with-help'>
            Kolejne błędy{' '}
            <HelpTooltip
              label='Błędy pobierania danych'
              text='Liczba nieudanych prób pobrania danych pod rząd. Szczegóły problemu opisuje diagnostyka źródła. Zerowy licznik nie zastępuje sprawdzenia statusu i aktualności odczytu.'
            />
          </dt>
          <dd>{provider.consecutiveFailures}</dd>
        </div>
        {provider.detailCode && (
          <div>
            <dt>Diagnostyka</dt>
            <dd>
              <details>
                <summary>Zaawansowana diagnostyka źródła</summary>
                <code>{provider.detailCode}</code>
              </details>
            </dd>
          </div>
        )}
      </dl>
    </article>
  );
}

function hazardLabel(hazard: string): string {
  return (
    (
      { frost: 'mróz', wind: 'wiatr', rain: 'deszcz', storm: 'burza', outdoor_air_pollution: 'zanieczyszczenie powietrza' } as Record<
        string,
        string
      >
    )[hazard] ?? 'nieznane zagrożenie'
  );
}

function coverageLabel(status: string): string {
  return (
    (
      {
        not_configured: 'Nie skonfigurowano źródła',
        unsupported: 'Zagrożenie poza zakresem źródła',
        awaiting_evidence: 'Oczekiwanie na dane',
        unavailable: 'Brak wiarygodnych danych',
        available: 'Dane dostępne',
        no_current_warnings: 'Brak bieżących ostrzeżeń w obsługiwanym zakresie',
      } as Record<string, string>
    )[status] ?? 'Stan pokrycia nieznany'
  );
}

function hazardPresentation(status: ExternalHazardStatus): {
  label: string;
  detail: string;
  tone: 'safe' | 'warning' | 'danger' | 'critical' | 'muted';
} {
  if (status === 'clear')
    return { label: 'Bezpiecznie', detail: 'Świeże dane nie wskazują aktywnego zagrożenia dla otwartych okien lub drzwi.', tone: 'safe' };
  if (status === 'watch') return { label: 'Obserwacja', detail: 'Warunki wskazują, że dom może wymagać zabezpieczenia.', tone: 'warning' };
  if (status === 'warning')
    return { label: 'Ostrzeżenie', detail: 'Co najmniej jedno wejście jest narażone na aktywne warunki zewnętrzne.', tone: 'danger' };
  if (status === 'severe')
    return { label: 'Pilne ostrzeżenie', detail: 'Aktywny jest urzędowy komunikat wymagający pilnej uwagi.', tone: 'critical' };
  return { label: 'Dane niepełne', detail: 'Nie można potwierdzić pełnej oceny wszystkich skonfigurowanych źródeł.', tone: 'muted' };
}

function providerDescription(capability: string): string {
  const descriptions: Record<string, string> = {
    WeatherPointModel: 'temperatura, wiatr, opady i burze',
    OfficialWeatherWarnings: 'oficjalne komunikaty dla lokalizacji domu',
    OutdoorAirQuality: 'model dla współrzędnych domu',
  };
  return descriptions[capability] ?? 'zewnętrzne źródło danych';
}

function humanizeReason(reason: string): string {
  const labels: Record<string, string> = {
    outdoor_air_pollution: 'Zanieczyszczone powietrze na zewnątrz',
    wind: 'Niebezpieczny wiatr',
    storm: 'Burza',
  };
  return labels[reason] ?? 'Dodatkowa blokada porady otwierania';
}
