import { useCallback, useState } from 'react';
import EntityDetailsDialog from '../components/EntityDetailsDialog';
import Icon from '../components/Icon';
import StatusBadge from '../components/StatusBadge';
import { type InternalDetectorStatus, type InternalDetectorView, type InternalEnvironmentStatus } from '../domain/internalHazards';
import { formatRelativeTime, type StatusTone } from '../domain/safety';
import { useSafetyEntities } from '../hooks/useSafetyEntities';

const summaryPresentation: Record<InternalEnvironmentStatus, { label: string; detail: string; tone: StatusTone }> = {
  active_hazard: {
    label: 'Aktywne zagrożenie',
    detail: 'Co najmniej jeden niezależny czujnik zgłasza alarm.',
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
  unavailable: { label: 'Niedostępny', tone: 'danger' },
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
            Widok prezentuje niezależne alarmy czujników dymu, gazu palnego i tlenku węgla. SafetyComponent przekazuje alarmy i zalecenia,
            ale nie steruje wentylacją, zaworami gazu, przekaźnikami ani zwykłym oświetleniem.
          </p>
        </div>
        <div className='internal-current-state'>
          <StatusBadge pulse={internalEnvironment.status === 'active_hazard'} tone={presentation.tone}>
            {presentation.label}
          </StatusBadge>
          <small>Aktualizacja {formatRelativeTime(internalEnvironment.lastUpdated)}</small>
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
          detail='blokada po alarmie gazowym'
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

      <section>
        <div className='section-heading internal-detector-heading'>
          <div>
            <span className='section-kicker'>Kanały alarmowe</span>
            <h2>Czujniki i ich niezależne stany</h2>
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
          <p>{internalEnvironment.persistenceError}</p>
        </section>
      )}

      <EntityDetailsDialog entities={entities} entityId={selectedEntityId} onClose={closeDetails} />
    </div>
  );
}

function DetectorCard({ detector, onSelectEntity }: { detector: InternalDetectorView; onSelectEntity: (entityId: string) => void }) {
  const presentation = detectorPresentation[detector.status];
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
          <dd>{detector.alarmActive ? 'Aktywny' : 'Nieaktywny'}</dd>
        </div>
        <div>
          <dt>Stan techniczny</dt>
          <dd>{detector.healthFaultActive ? 'Usterka czujnika' : 'Dostępny'}</dd>
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
          <dt>Stan źródłowy</dt>
          <dd>{detector.currentState}</dd>
        </div>
        <div>
          <dt>Klasyfikacja</dt>
          <dd>{classificationName(detector.classification)}</dd>
        </div>
      </dl>
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
    }[classification] ?? classification
  );
}
