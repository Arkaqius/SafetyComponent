import { useCallback, useState } from 'react';
import EntityDetailsDialog from '../components/EntityDetailsDialog';
import FaultSection from '../components/FaultSection';
import Icon from '../components/Icon';
import StatusBadge from '../components/StatusBadge';
import SummaryCard from '../components/SummaryCard';
import {
  COVERAGE_ENTITY_ID,
  coverageCauseStateLabel,
  coverageEffectLabel,
  getCoverageView,
  type CoverageRestriction,
} from '../domain/coverage';
import { NOTIFICATION_DELIVERY_HEALTH_ID, readAcknowledgedNotificationTags } from '../domain/notificationHistory';
import type { FaultView, StatusTone } from '../domain/safety';
import { useSafetyEntities } from '../hooks/useSafetyEntities';

export default function FaultManagement() {
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const closeEntityDetails = useCallback(() => setSelectedEntityId(null), []);
  const { connection, entities, faults } = useSafetyEntities();
  const coverage = getCoverageView(connection.cannotConnect || !connection.ready ? {} : entities);
  const hazardFaults = faults.filter(fault => fault.category === 'H');
  const diagnosticFaults = faults.filter(fault => fault.category === 'D');
  const activeHazards = hazardFaults.filter(fault => fault.active === true);
  const activeDiagnostics = diagnosticFaults.filter(fault => fault.active === true);
  const activeLatches = faults.filter(fault => fault.active === true && fault.latched === true);
  const acknowledgedTags = new Set(readAcknowledgedNotificationTags(entities[NOTIFICATION_DELIVERY_HEALTH_ID]));

  return (
    <div className='page-stack fault-management-page'>
      <section className='panel fault-management-intro'>
        <div>
          <span className='section-kicker'>Fault Management</span>
          <h2>Usterki, diagnostyka i pokrycie</h2>
          <p>
            Warunki zagrożenia kategorii H są prezentowane oddzielnie od usterek diagnostycznych kategorii D. Utrata kanału powiadomień nie
            oznacza automatycznie utraty wykrywania zagrożenia.
          </p>
        </div>
        <StatusBadge tone={coverage.tone}>{coverage.label}</StatusBadge>
      </section>

      <section aria-label='Podsumowanie Fault Management' className='summary-grid'>
        <SummaryCard
          detail={`${hazardFaults.length} zdefiniowanych warunków H`}
          icon='alert'
          label='Aktywne zagrożenia'
          tone={activeHazards.length > 0 ? 'danger' : 'safe'}
          value={activeHazards.length}
        />
        <SummaryCard
          detail={`${diagnosticFaults.length} zdefiniowanych usterek D`}
          icon='activity'
          label='Aktywne diagnostyki'
          tone={activeDiagnostics.length > 0 ? 'warning' : diagnosticFaults.length > 0 ? 'safe' : 'muted'}
          value={activeDiagnostics.length}
        />
        <SummaryCard
          detail={coverage.detail}
          icon='shield'
          label='Pokrycie bezpieczeństwa'
          onClick={() => setSelectedEntityId(COVERAGE_ENTITY_ID)}
          tone={coverage.tone}
          value={coverage.state}
        />
        <SummaryCard
          detail='Aktywny latch nie jest ukrywany przez bieżący wynik PASS'
          icon='history'
          label='Aktywne latche'
          tone={activeLatches.length > 0 ? 'critical' : 'safe'}
          value={activeLatches.length}
        />
      </section>

      {coverage.state === 'FULL' && activeHazards.length > 0 && (
        <section className='panel fault-contract-note fault-contract-note-warning'>
          <Icon name='alert' size={22} />
          <div>
            <strong>Pełne pokrycie nie oznacza braku zagrożeń</strong>
            <p>Wszystkie wymagane funkcje dostarczyły ocenę, ale {activeHazards.length} warunków H pozostaje aktywnych.</p>
          </div>
        </section>
      )}

      <CoverageDetails coverage={coverage} faults={faults} onSelectEntity={setSelectedEntityId} />

      <FaultSection acknowledgedTags={acknowledgedTags} faults={faults} onSelectEntity={setSelectedEntityId} />

      <EntityDetailsDialog entities={entities} entityId={selectedEntityId} onClose={closeEntityDetails} />
    </div>
  );
}

function CoverageDetails({
  coverage,
  faults,
  onSelectEntity,
}: {
  coverage: ReturnType<typeof getCoverageView>;
  faults: FaultView[];
  onSelectEntity: (entityId: string) => void;
}) {
  const hasDetails =
    coverage.restrictions.length > 0 ||
    coverage.exclusions.length > 0 ||
    coverage.bindingErrors.length > 0 ||
    coverage.unresolvedSymptoms.length > 0;

  return (
    <section className='panel coverage-details-panel'>
      <div className='panel-header'>
        <div>
          <span className='section-kicker'>D → H</span>
          <h2>Wpływ diagnostyki na funkcje bezpieczeństwa</h2>
        </div>
        <button className='text-button' onClick={() => onSelectEntity(COVERAGE_ENTITY_ID)} type='button'>
          Surowa encja <Icon name='history' size={15} />
        </button>
      </div>

      <p className='coverage-explanation'>
        Przyczyna D ogranicza wyłącznie wskazaną zdolność i zakres H. Stan pokrycia jest niezależny od priorytetu aktywnej usterki.
      </p>

      {coverage.restrictions.length > 0 && (
        <div className='coverage-restriction-list'>
          {coverage.restrictions.map((restriction, index) => (
            <RestrictionRow
              faults={faults}
              key={`${restriction.cause}-${restriction.symptom}-${restriction.effect}-${index}`}
              restriction={restriction}
            />
          ))}
          {coverage.restrictionsOmitted > 0 && <small>Pominięto dalszych ograniczeń: {coverage.restrictionsOmitted}.</small>}
        </div>
      )}

      {coverage.exclusions.length > 0 && (
        <DiagnosticList
          items={coverage.exclusions.map(item => ({ id: item.symptom, detail: item.reason }))}
          label='Wyłączenia zakresu'
          tone='warning'
        />
      )}
      {coverage.bindingErrors.length > 0 && (
        <DiagnosticList
          items={coverage.bindingErrors.map(item => ({ id: item.source, detail: item.reason }))}
          label='Błędy powiązań diagnostycznych'
          tone='danger'
        />
      )}
      {coverage.unresolvedSymptoms.length > 0 && (
        <DiagnosticList
          items={coverage.unresolvedSymptoms.map(symptom => ({ id: symptom, detail: 'Brak aktualnej, rozstrzygającej oceny.' }))}
          label='Nieocenione funkcje H'
          tone='muted'
        />
      )}

      {!hasDetails && (
        <div className='empty-state compact-empty-state'>
          <Icon name='shield' size={24} />
          <strong>{coverage.state === 'FULL' ? 'Brak ograniczeń pokrycia' : 'Brak opublikowanych szczegółów'}</strong>
          <p>{coverage.detail}</p>
        </div>
      )}
    </section>
  );
}

function RestrictionRow({ restriction, faults }: { restriction: CoverageRestriction; faults: FaultView[] }) {
  const fault = faults.find(
    item =>
      item.entityId
        .split('.')
        .at(-1)
        ?.replace(/^fault_/, '')
        .toLowerCase() === restriction.fault.toLowerCase()
  );
  const tone: StatusTone =
    restriction.causeState === 'active' ? 'danger' : restriction.causeState === 'invalid_binding' ? 'critical' : 'warning';
  return (
    <article className='coverage-restriction-row'>
      <div className='coverage-restriction-heading'>
        <div>
          <strong title={restriction.cause}>{humanize(restriction.cause)}</strong>
          <small>
            wpływa na {fault?.name ?? humanize(restriction.fault)} · {coverageEffectLabel(restriction.effect)}
          </small>
        </div>
        <StatusBadge tone={tone}>{coverageCauseStateLabel(restriction.causeState)}</StatusBadge>
      </div>
      <dl className='details-grid'>
        <div>
          <dt>Zdolność</dt>
          <dd>{humanize(restriction.capability) || 'Nie podano'}</dd>
        </div>
        <div>
          <dt>Zakres</dt>
          <dd>{humanize(restriction.subject) || 'Nie podano'}</dd>
        </div>
        <div>
          <dt>Symptom H</dt>
          <dd className='technical-id'>{restriction.symptom}</dd>
        </div>
      </dl>
      {restriction.effect === 'notification' && (
        <small className='coverage-channel-note'>Ograniczony jest kanał powiadomień, nie sama detekcja zagrożenia.</small>
      )}
    </article>
  );
}

function DiagnosticList({ items, label, tone }: { items: Array<{ id: string; detail: string }>; label: string; tone: StatusTone }) {
  return (
    <div className='coverage-diagnostic-list'>
      <div className='coverage-diagnostic-heading'>
        <strong>{label}</strong>
        <StatusBadge tone={tone}>{items.length}</StatusBadge>
      </div>
      <ul>
        {items.map(item => (
          <li key={item.id}>
            <code>{item.id}</code>
            <span>{item.detail}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function humanize(value: string): string {
  return value
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^\w/, letter => letter.toUpperCase());
}
