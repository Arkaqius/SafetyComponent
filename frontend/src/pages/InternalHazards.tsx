import { useCallback, useState } from 'react';
import EntityDetailsDialog from '../components/EntityDetailsDialog';
import Icon from '../components/Icon';
import HelpTooltip from '../components/HelpTooltip';
import StatusBadge from '../components/StatusBadge';
import { type InternalDetectorStatus, type InternalDetectorView, type InternalEnvironmentStatus } from '../domain/internalHazards';
import { formatRelativeTime, localizedEntityState, type StatusTone } from '../domain/safety';
import { useSafetyEntities } from '../hooks/useSafetyEntities';

const summaryPresentation: Record<InternalEnvironmentStatus, { label: string; detail: string; tone: StatusTone }> = {
  active_hazard: {
    label: 'Aktywne zagrożenie',
    detail: 'Co najmniej jeden alarm pozostaje aktywny lub zachowany bez potwierdzonego ustąpienia.',
    tone: 'critical',
  },
  healthy: {
    label: 'Brak alarmów',
    detail: 'Wszystkie monitorowane kanały są dostępne i nie zgłaszają alarmu.',
    tone: 'safe',
  },
  degraded: {
    label: 'Ograniczona diagnostyka',
    detail: 'Nie wszystkie dane diagnostyczne można obecnie wiarygodnie ocenić.',
    tone: 'warning',
  },
  unavailable: {
    label: 'Utrata monitorowania',
    detail: 'Co najmniej jeden wymagany kanał alarmowy jest niedostępny.',
    tone: 'danger',
  },
  unknown: {
    label: 'Brak danych',
    detail: 'SafetyComponent nie opublikował jeszcze stanu monitoringu wewnętrznego.',
    tone: 'muted',
  },
};

const detectorPresentation: Record<InternalDetectorStatus, { label: string; tone: StatusTone }> = {
  alarm: { label: 'Alarm', tone: 'critical' },
  healthy: { label: 'Sprawny', tone: 'safe' },
  degraded: { label: 'Ograniczone dane', tone: 'warning' },
  unavailable: { label: 'Brak danych alarmowych', tone: 'danger' },
};

export default function InternalHazards() {
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const closeDetails = useCallback(() => setSelectedEntityId(null), []);
  const { entities, internalEnvironment } = useSafetyEntities();
  const presentation = summaryPresentation[internalEnvironment.status];
  const readyDetectors = internalEnvironment.detectors.filter(
    detector => detector.status === 'healthy' || detector.status === 'alarm'
  ).length;

  return (
    <div className='page-stack'>
      <section className={`page-introduction internal-introduction internal-${presentation.tone}`}>
        <div>
          <span className='section-kicker'>Bezpieczeństwo wewnątrz domu</span>
          <h2>Zagrożenia wewnętrzne</h2>
          <p>
            Widok prezentuje niezależne alarmy czujników dymu, gazu palnego, tlenku węgla i zalania. SafetyComponent przekazuje alarmy i
            zalecenia, ale nie steruje wentylacją, zaworami wody i gazu, przekaźnikami ani zwykłym oświetleniem.
          </p>
        </div>
        <div className='internal-current-state'>
          <StatusBadge pulse={internalEnvironment.status === 'active_hazard'} tone={presentation.tone}>
            {presentation.label}
          </StatusBadge>
          <small>Ostatni zapis podsumowania {formatRelativeTime(internalEnvironment.lastUpdated)}</small>
        </div>
      </section>

      <section aria-label='Podsumowanie zagrożeń wewnętrznych' className='metric-strip'>
        <Metric label='Aktywne alarmy' value={internalEnvironment.activeHazards} detail='niezależne kanały alarmowe' />
        <Metric
          label='Czujniki dostępne'
          value={`${readyDetectors}/${internalEnvironment.monitoredDetectors}`}
          detail='alarm może zostać oceniony'
        />
        <Metric label='Niedostępne' value={internalEnvironment.unavailableDetectors} detail='wymagają diagnostyki' />
        <Metric
          label='Ochrona wyjść lokalnych'
          value={internalEnvironment.gasSwitchingInhibited ? 'Aktywna' : 'Nieaktywna'}
          detail={internalEnvironment.gasInhibitionUnknown ? 'historia blokady niepotwierdzona' : 'niezależna blokada po alarmie gazowym'}
        />
      </section>

      {internalEnvironment.status === 'active_hazard' && (
        <section className='panel internal-alert-panel'>
          <Icon name='alert' size={27} />
          <div>
            <strong>{presentation.label}</strong>
            <p>{presentation.detail} Postępuj zgodnie z komunikatem alarmowym i opuść zagrożony obszar.</p>
          </div>
        </section>
      )}

      {(!internalEnvironment.monitoringEnabled || internalEnvironment.historyUnknown || internalEnvironment.gasInhibitionUnknown) && (
        <section className='panel internal-persistence-warning'>
          <strong>
            {internalEnvironment.monitoringEnabled ? 'Historia bezpieczeństwa wymaga weryfikacji' : 'Monitorowanie wyłączone'}
          </strong>
          <p>
            Nie można potwierdzić pełnej historii sprzed restartu. To osobna informacja od bieżących odczytów czujników i potwierdzenia
            zapisu w bazie.
          </p>
          <p>
            Niepewność historii nie oznacza wykrycia gazu, dymu ani zalania. Rzeczywiste zachowane alarmy i blokady pozostają widoczne
            osobno.
          </p>
          {internalEnvironment.gasInhibitionUnknown && (
            <p>Historia blokady po gazie jest niepotwierdzona. Wyjścia pozostają zablokowane; ten stan nie potwierdza obecności gazu.</p>
          )}
        </section>
      )}

      {internalEnvironment.retainedRecordsTotal > 0 && (
        <section className='panel' aria-label='Zachowane alarmy i blokady'>
          <h2>Zachowane alarmy i blokady</h2>
          <p>
            Alarm może pozostać zapisany po usunięciu lub wymianie czujnika. Ustąpienie alarmu nie zwalnia niezależnej blokady po gazie i
            nie potwierdza bezpiecznego powrotu.
          </p>
          {internalEnvironment.retainedRecords
            .filter(record => record.status !== 'current')
            .map(record => (
              <article key={record.recordId} className='internal-retained-record'>
                <h3>{record.name}</h3>
                <p>
                  {record.alarmActive ? 'Alarm zachowany — ustąpienie niepotwierdzone' : 'Alarm nieaktywny'}
                  {record.gasSwitchingInhibited ? ' · Blokada wyjść aktywna' : ''}
                </p>
                <p>
                  {record.status === 'orphan' ? 'Brak zgodnego czujnika w bieżącej konfiguracji.' : 'Bieżące źródło wymaga weryfikacji.'}
                </p>
                {!record.identityAvailable && <p>Stary zapis nie zawiera pełnej tożsamości źródła ani incydentu.</p>}
                <details>
                  <summary>Tożsamość zachowanego wpisu</summary>
                  <p>{record.sourceEntityId || 'Źródło nieznane'}</p>
                  <p>{record.incidentId || 'Identyfikator incydentu nieznany'}</p>
                </details>
              </article>
            ))}
          {internalEnvironment.retainedRecordsOmitted > 0 && (
            <p>
              Pominięte szczegóły: {internalEnvironment.retainedRecordsOmitted}. Podsumowanie uwzględnia wszystkie{' '}
              {internalEnvironment.retainedRecordsTotal} wpisów.
            </p>
          )}
        </section>
      )}

      <section>
        <div className='section-heading internal-detector-heading'>
          <div>
            <span className='section-kicker'>Kanały alarmowe</span>
            <h2 className='label-with-help'>
              Czujniki i ich niezależne stany{' '}
              <HelpTooltip
                label='Alarm i stan techniczny czujnika'
                text='Alarm zagrożenia i usterka techniczna to niezależne informacje. Niedostępność czujnika nie jest dowodem ustąpienia wcześniej zgłoszonego alarmu. Potwierdzenie powiadomienia nie kasuje alarmu ani nie naprawia czujnika.'
              />
            </h2>
          </div>
        </div>
        {internalEnvironment.detectors.length > 0 ? (
          <div className='internal-detector-grid'>
            {internalEnvironment.detectors.map(detector => (
              <DetectorCard detector={detector} key={detector.entityId} onSelectEntity={setSelectedEntityId} />
            ))}
          </div>
        ) : (
          <div className='panel empty-state page-empty-state'>
            <Icon name='shield' size={28} />
            <strong>Brak opublikowanych czujników</strong>
            <p>SafetyComponent nie udostępnia obecnie encji diagnostycznych monitoringu wewnętrznego.</p>
          </div>
        )}
      </section>

      {internalEnvironment.persistenceError && (
        <section className='panel internal-persistence-warning'>
          <strong>Stan alarmów nie może zostać zapisany</strong>
          <p>Nie można potwierdzić zachowania stanu alarmów po ponownym uruchomieniu aplikacji.</p>
          <details>
            <summary>Zaawansowana diagnostyka zapisu</summary>
            <code>{internalEnvironment.persistenceError}</code>
          </details>
        </section>
      )}

      <EntityDetailsDialog entities={entities} entityId={selectedEntityId} onClose={closeDetails} />
    </div>
  );
}

function DetectorCard({ detector, onSelectEntity }: { detector: InternalDetectorView; onSelectEntity: (entityId: string) => void }) {
  const presentation = detectorPresentation[detector.status];
  const healthEntityId = detector.healthEntityId;
  const alarmKnown = ['alarm', 'clear'].includes(detector.classification);
  return (
    <article className={`internal-detector-card detector-${presentation.tone}`}>
      <header>
        <span className='internal-detector-icon'>
          <Icon name={detector.status === 'alarm' ? 'alert' : 'shield'} size={22} />
        </span>
        <div>
          <h3>{hazardName(detector.hazard)}</h3>
          <small>{detector.name}</small>
        </div>
        <StatusBadge pulse={detector.status === 'alarm'} tone={presentation.tone}>
          {presentation.label}
        </StatusBadge>
      </header>
      <dl>
        <div>
          <dt>Alarm zagrożenia</dt>
          <dd>{detector.alarmActive ? 'Aktywny' : alarmKnown ? 'Nieaktywny' : 'Nie można ocenić'}</dd>
        </div>
        <div>
          <dt>Stan techniczny</dt>
          <dd>{detector.healthStatus === 'healthy' ? 'Stan alarmowy dostępny' : 'Brak wiarygodnego stanu alarmowego'}</dd>
        </div>
        <div>
          <dt>Lokalizacja</dt>
          <dd>{detector.areaName}</dd>
        </div>
        <div>
          <dt>Ostatnia obserwacja</dt>
          <dd>{formatRelativeTime(detector.lastObservedAt ?? detector.lastUpdated)}</dd>
        </div>
        <div>
          <dt>Ostatni kontakt urządzenia</dt>
          <dd>{detector.lastContactAt ? formatRelativeTime(detector.lastContactAt) : 'Brak potwierdzonych danych'}</dd>
        </div>
        <div>
          <dt>Stan źródłowy</dt>
          <dd>{localizedEntityState(detector.sourceEntityId, detector.currentState)}</dd>
        </div>
        <div>
          <dt>Klasyfikacja</dt>
          <dd>{classificationName(detector.classification)}</dd>
        </div>
      </dl>
      {detector.lastContactAt && !alarmKnown && (
        <p>Urządzenie zgłosiło kontakt, ale nie udostępnia stanu alarmowego. Nie można potwierdzić braku zagrożenia.</p>
      )}
      {(detector.pendingAlarmClear || detector.durableClearPending) && (
        <p>
          {detector.durableClearPending
            ? 'Ustąpienie oczekuje na potwierdzony zapis. Alarm pozostaje aktywny.'
            : 'Trwa nowy pełny okres potwierdzania ustąpienia alarmu.'}
        </p>
      )}
      {detector.hazard === 'flammable_gas' && (
        <div className={`internal-switching-state${detector.gasSwitchingInhibited ? ' switching-inhibited' : ''}`}>
          <span>Ochrona wyjść lokalnych</span>
          <strong>{detector.gasSwitchingInhibited ? 'Aktywna' : 'Nieaktywna'}</strong>
        </div>
      )}
      <div className='internal-detector-actions'>
        <button className='text-button' onClick={() => onSelectEntity(detector.entityId)} type='button'>
          Diagnostyka
        </button>
        {detector.sourceEntityId && (
          <button className='text-button' onClick={() => onSelectEntity(detector.sourceEntityId)} type='button'>
            Encja źródłowa
          </button>
        )}
        {healthEntityId && (
          <button className='text-button' onClick={() => onSelectEntity(healthEntityId)} type='button'>
            Stan monitorowania
          </button>
        )}
      </div>
    </article>
  );
}

function Metric({ detail, label, value }: { detail: string; label: string; value: number | string }) {
  return (
    <div className='metric-item'>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function hazardName(hazard: string): string {
  return (
    {
      smoke: 'Dym',
      flammable_gas: 'Gaz palny',
      carbon_monoxide: 'Tlenek węgla',
      water_leak: 'Zalanie / wyciek wody',
    }[hazard] ?? 'Nieznane zagrożenie'
  );
}

function classificationName(classification: string): string {
  return (
    {
      alarm: 'Alarm potwierdzony',
      clear: 'Brak alarmu',
      unavailable: 'Niedostępny',
      unevaluable: 'Nie można ocenić',
    }[classification] ?? 'Brak wiarygodnej klasyfikacji'
  );
}
