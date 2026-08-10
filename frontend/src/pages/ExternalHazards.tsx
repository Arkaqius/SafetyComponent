import Icon from '../components/Icon';
import StatusBadge from '../components/StatusBadge';
import {
  formatRelativeTime,
  observationDisplayName,
  type ExternalHazardStatus,
  type ExternalProviderView,
  type ImgwWarningView,
} from '../domain/safety';
import { useSafetyEntities } from '../hooks/useSafetyEntities';

export default function ExternalHazards() {
  const { externalHazards } = useSafetyEntities();
  const presentation = hazardPresentation(externalHazards.status);
  const healthyProviders = externalHazards.providers.filter(provider => provider.status === 'ok').length;

  return (
    <div className='page-stack'>
      <section className={`page-introduction external-introduction external-${presentation.tone}`}>
        <div>
          <span className='section-kicker'>Warunki zewnętrzne</span>
          <h2>Ochrona domu przed warunkami zewnętrznymi</h2>
          <p>
            System łączy dane pogodowe, bieżącą jakość powietrza i oficjalne ostrzeżenia IMGW ze stanem skonfigurowanych okien i drzwi. Ten
            moduł wyłącznie ostrzega — nie steruje żadnym urządzeniem.
          </p>
        </div>
        <div className='external-current-state'>
          <StatusBadge pulse={externalHazards.status === 'severe' || externalHazards.status === 'warning'} tone={presentation.tone}>
            {presentation.label}
          </StatusBadge>
          <small>Ocena {formatRelativeTime(externalHazards.lastEvaluatedAt ?? externalHazards.lastUpdated)}</small>
        </div>
      </section>

      <section aria-label='Podsumowanie zagrożeń zewnętrznych' className='metric-strip'>
        <Metric
          label='Aktywne zagrożenia'
          value={externalHazards.activeHazards.length}
          detail={`${externalHazards.activeSymptomCount} aktywnych warunków`}
        />
        <Metric label='Narażone wejścia' value={externalHazards.affectedOpenings.length} detail='okna, drzwi lub brama' />
        <Metric
          label='Źródła dostępne'
          value={`${healthyProviders}/${externalHazards.providers.length}`}
          detail='niezależne źródła danych'
        />
        <Metric label='Blokady porad' value={externalHazards.adviceInhibition.length} detail='sprzeczne porady otwarcia' />
      </section>

      {externalHazards.activeHazards.length > 0 ? (
        <section className='panel external-active-panel'>
          <div className='panel-header'>
            <div>
              <span className='section-kicker'>Bieżąca ekspozycja</span>
              <h2>Warunki wymagające uwagi</h2>
            </div>
          </div>
          <div className='external-active-grid'>
            <div>
              <span>Zagrożenia</span>
              <strong>{externalHazards.activeHazards.join(', ')}</strong>
            </div>
            <div>
              <span>Dotknięte wejścia</span>
              <strong>{externalHazards.affectedOpenings.join(', ') || 'Brak'}</strong>
            </div>
          </div>
        </section>
      ) : (
        <section className='panel external-clear-panel'>
          <span className='external-clear-icon'>
            <Icon name='shield' size={26} />
          </span>
          <div>
            <strong>{externalHazards.status === 'clear' ? 'Brak aktywnej ekspozycji' : 'Ocena wymaga aktualnych danych'}</strong>
            <p>{presentation.detail}</p>
          </div>
        </section>
      )}

      {externalHazards.adviceInhibition.length > 0 && (
        <section className='panel advice-panel'>
          <div className='panel-header'>
            <div>
              <span className='section-kicker'>Spójność zaleceń</span>
              <h2>Nie zalecaj otwierania okien</h2>
            </div>
          </div>
          <ul>
            {externalHazards.adviceInhibition.map(item => (
              <li key={`${item.reason}-${item.source}`}>
                <strong>{humanizeReason(item.reason)}</strong>
                <span>
                  Źródło: {providerDisplayName(item.source)}
                  {item.validUntil ? ` · ważne do ${new Date(item.validUntil).toLocaleString('pl-PL')}` : ''}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className='panel imgw-warnings-panel'>
        <div className='panel-header'>
          <div>
            <span className='section-kicker'>Oficjalne komunikaty</span>
            <h2>Ostrzeżenia IMGW</h2>
            <p>Aktualne ostrzeżenia IMGW dotyczące lokalizacji domu.</p>
          </div>
          <strong className='imgw-warning-count'>{externalHazards.imgwWarnings.length}</strong>
        </div>
        {externalHazards.imgwWarnings.length > 0 ? (
          <div className='imgw-warning-list'>
            {externalHazards.imgwWarnings.map(warning => (
              <ImgwWarning key={warning.id} warning={warning} />
            ))}
          </div>
        ) : (
          <p className='imgw-warning-empty'>IMGW nie zwrócił aktualnych ostrzeżeń.</p>
        )}
      </section>

      <section>
        <div className='section-heading external-provider-heading'>
          <div>
            <span className='section-kicker'>Źródła danych</span>
            <h2>Stan niezależnych integracji</h2>
          </div>
        </div>
        <div className='external-provider-grid'>
          {externalHazards.providers.map(provider => (
            <ProviderCard key={provider.entityId} provider={provider} />
          ))}
        </div>
      </section>
    </div>
  );
}

function ImgwWarning({ warning }: { warning: ImgwWarningView }) {
  return (
    <article className={`imgw-warning-card${warning.locallyApplicable ? ' imgw-warning-local' : ''}`}>
      <header>
        <div>
          <h3>{warning.eventName}</h3>
          <small>{warning.office || 'IMGW-PIB'}</small>
        </div>
        <div className='imgw-warning-badges'>
          {warning.locallyApplicable && <span className='imgw-local-badge'>Dotyczy domu</span>}
          {warning.degree && <span className='imgw-degree-badge'>Stopień {warning.degree}</span>}
        </div>
      </header>
      <p>{warning.content || 'Brak opisu ostrzeżenia.'}</p>
      {warning.comment && <p className='imgw-warning-comment'>{warning.comment}</p>}
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
          <small>{providerDescription(provider.provider)}</small>
        </div>
        <StatusBadge tone={tone}>{label}</StatusBadge>
      </header>
      <dl>
        <div>
          <dt>Ostatni poprawny odczyt</dt>
          <dd>{formatRelativeTime(provider.lastSuccessAt)}</dd>
        </div>
        <div>
          <dt>Obserwacje</dt>
          <dd>
            <span className='provider-observation-count' tabIndex={provider.observations.length > 0 ? 0 : undefined}>
              {provider.observationCount}
              {provider.observations.length > 0 ? (
                <span className='provider-observation-tooltip' role='tooltip'>
                  <strong>Monitorowane dane</strong>
                  {provider.observations.map(observation => (
                    <span key={observation.id}>{observationDisplayName(observation, provider.provider)}</span>
                  ))}
                </span>
              ) : null}
            </span>
          </dd>
        </div>
        <div>
          <dt>Kolejne błędy</dt>
          <dd>{provider.consecutiveFailures}</dd>
        </div>
        {provider.detailCode && (
          <div>
            <dt>Diagnostyka</dt>
            <dd>
              <code>{provider.detailCode}</code>
            </dd>
          </div>
        )}
      </dl>
    </article>
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

function providerDisplayName(provider: string): string {
  const names: Record<string, string> = {
    OpenMeteoWeatherApiComponent: 'Dane pogodowe Open-Meteo',
    ImgwWarningsApiComponent: 'Ostrzeżenia IMGW',
    GiosAirQualityApiComponent: 'Jakość powietrza GIOŚ',
    OpenMeteoAirQualityApiComponent: 'Jakość powietrza Open-Meteo',
  };
  return names[provider] ?? provider;
}

function providerDescription(provider: string): string {
  const descriptions: Record<string, string> = {
    OpenMeteoWeatherApiComponent: 'temperatura, wiatr, opady i burze',
    ImgwWarningsApiComponent: 'oficjalne komunikaty dla lokalizacji domu',
    GiosAirQualityApiComponent: 'bieżące pomiary z najbliższej stacji',
    OpenMeteoAirQualityApiComponent: 'model dla współrzędnych domu',
  };
  return descriptions[provider] ?? 'zewnętrzne źródło danych';
}

function humanizeReason(reason: string): string {
  const labels: Record<string, string> = {
    outdoor_air_pollution: 'Zanieczyszczone powietrze na zewnątrz',
    wind: 'Niebezpieczny wiatr',
    storm: 'Burza',
    ionizing_radiation: 'Oficjalny komunikat radiologiczny',
  };
  return labels[reason] ?? reason.replace(/_/g, ' ');
}
