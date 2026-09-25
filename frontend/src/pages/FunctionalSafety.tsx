import { useState } from 'react';
import { useHass } from '@hakit/core';
import StatusBadge from '../components/StatusBadge';
import {
  DETECTOR_TEST_RESULT_EVENT,
  getComponentProgress,
  getDetectorTests,
  getFunctionalSafetySources,
  NOTIFICATION_HEALTH_ENTITY_ID,
} from '../domain/functionalSafety';
import type { StatusTone } from '../domain/safety';
import { useSafetyEntities } from '../hooks/useSafetyEntities';

const progressLabels = {
  observed: 'Ocena wykonana',
  unknown: 'Brak oceny',
  overdue: 'Ocena spóźniona',
  error: 'Błąd oceny',
} as const;

const progressTones: Record<keyof typeof progressLabels, StatusTone> = {
  observed: 'info',
  unknown: 'muted',
  overdue: 'danger',
  error: 'danger',
};

const sourceLabels: Record<string, string> = {
  active: 'Alarm aktywny',
  high: 'Trwałe wysokie obciążenie',
  offline: 'Brak WAN',
  low: 'Niska bateria',
  available: 'Aktualizacja dostępna',
  current: 'Aktualny',
  online: 'Online',
  normal: 'Prawidłowy',
  observed: 'Zaobserwowany',
  qualifying: 'Potwierdzanie',
  recovering: 'Potwierdzanie powrotu',
  unknown: 'Brak wiarygodnych danych',
};

function countAttribute(attributes: Record<string, unknown>, key: string): number | null {
  const value = attributes[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export default function FunctionalSafety() {
  const { entities, recoveries } = useSafetyEntities();
  const connection = useHass(store => store.connection);
  const [testMessage, setTestMessage] = useState('');
  const progress = getComponentProgress(entities);
  const detectorTests = getDetectorTests(entities);
  const sources = getFunctionalSafetySources(entities);
  const notification = entities[NOTIFICATION_HEALTH_ENTITY_ID];
  const activeRecoveries = recoveries.filter(recovery => recovery.status !== 'do_not_perform');
  const accepted = notification ? countAttribute(notification.attributes, 'accepted_attempts') : null;
  const failed = notification ? countAttribute(notification.attributes, 'failed_attempts') : null;
  const queued = notification ? countAttribute(notification.attributes, 'queued_count') : null;

  const attestTest = async (detectorKey: string, outcome: 'passed' | 'failed') => {
    if (!connection) {
      setTestMessage('Brak połączenia z Home Assistant.');
      return;
    }
    if (
      !window.confirm(
        `Czy fizyczny test detektora ${detectorKey} został wykonany? Zapiszesz wynik: ${outcome === 'passed' ? 'zaliczony' : 'niezaliczony'}.`
      )
    )
      return;
    try {
      await connection.sendMessagePromise<unknown>({
        type: 'fire_event',
        event_type: DETECTOR_TEST_RESULT_EVENT,
        event_data: { detector_key: detectorKey, outcome },
      });
      setTestMessage('Wysłano wynik do Home Assistant. Potwierdzeniem zapisu będzie aktualizacja stanu poniżej.');
    } catch {
      setTestMessage('Nie udało się wysłać wyniku. Sprawdź połączenie i spróbuj ponownie.');
    }
  };

  return (
    <div className='page-stack functional-safety-page'>
      <header className='panel'>
        <span className='section-kicker'>Functional safety</span>
        <h1>Zdrowie funkcji bezpieczeństwa</h1>
        <p>
          Postęp oceny, jakość kanału powiadomień i potwierdzenie wykonania to różne rzeczy. Brak aktywnego alarmu nie dowodzi, że wszystkie
          funkcje działają.
        </p>
      </header>

      <section className='panel'>
        <div className='panel-header'>
          <div>
            <span className='section-kicker'>Ocena per komponent</span>
            <h2>Postęp funkcji</h2>
          </div>
        </div>
        <p>
          „Ocena wykonana” potwierdza ukończenie logiki, nie jakość jej wejść. Komponenty zdarzeniowe mogą pozostawać bezczynne; jakość ich
          źródeł nadzoruje osobno monitoring encji.
        </p>
        {progress.length === 0 ? (
          <div className='empty-state compact-empty-state'>Brak diagnostyki postępu — nie zakładamy sprawności komponentów.</div>
        ) : (
          <div className='functional-safety-list'>
            {progress.map(component => (
              <article className='functional-safety-row' key={component.name}>
                <div>
                  <strong>{component.name}</strong>
                  <small>
                    {component.lastCompletedAt
                      ? `Ostatnia ocena: ${new Date(component.lastCompletedAt).toLocaleString('pl-PL')}`
                      : 'Nie zakończono jeszcze żadnej oceny'}
                    {component.evaluationMode === 'periodic' && component.expectedIntervalSeconds !== null
                      ? ` · termin ${component.expectedIntervalSeconds} s`
                      : ' · ocena zdarzeniowa'}
                  </small>
                  {component.missedDeadlineCount > 0 && <small>Przekroczone terminy: {component.missedDeadlineCount}</small>}
                </div>
                <StatusBadge tone={progressTones[component.status]}>{progressLabels[component.status]}</StatusBadge>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className='panel'>
        <div className='panel-header'>
          <div>
            <span className='section-kicker'>Platforma i konserwacja</span>
            <h2>Źródła diagnostyczne</h2>
          </div>
        </div>
        <p>
          Poziomy alarmów: brak pamięci L2 (pamięć dostępna i PSI), utrata WAN L3, trwałe obciążenie CPU, dostępne aktualizacje i niska
          bateria L4. Nieznane źródło nie oznacza sprawności.
        </p>
        {sources.length === 0 ? (
          <p>Brak diagnostyki źródeł.</p>
        ) : (
          <div className='functional-safety-list'>
            {sources.map(source => (
              <article className='functional-safety-row' key={source.key}>
                <div>
                  <strong>{source.label}</strong>
                  {source.detail ? <small>{source.detail}</small> : null}
                </div>
                <StatusBadge
                  tone={
                    ['active', 'offline', 'low', 'high'].includes(source.status)
                      ? 'danger'
                      : source.status === 'available'
                        ? 'warning'
                        : source.status === 'unknown'
                          ? 'muted'
                          : 'info'
                  }
                >
                  {sourceLabels[source.status] ?? source.status}
                </StatusBadge>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className='panel'>
        <div className='panel-header'>
          <div>
            <span className='section-kicker'>Ścieżka ostrzegania</span>
            <h2>Powiadomienia</h2>
          </div>
        </div>
        {notification ? (
          <>
            <StatusBadge tone={notification.state === 'healthy' ? 'info' : 'warning'}>{notification.state}</StatusBadge>
            <div className='functional-safety-metrics'>
              <span>
                Przyjęte przez HA: <strong>{accepted ?? '—'}</strong>
              </span>
              <span>
                Nieudane próby: <strong>{failed ?? '—'}</strong>
              </span>
              <span>
                W kolejce: <strong>{queued ?? '—'}</strong>
              </span>
            </div>
            <p>Przyjęcie wywołania przez Home Assistant nie potwierdza dostarczenia na fizyczny telefon.</p>
          </>
        ) : (
          <p>Brak diagnostyki kanału powiadomień. Nie zakładamy, że działa.</p>
        )}
      </section>

      <section className='panel'>
        <div className='panel-header'>
          <div>
            <span className='section-kicker'>Ścieżka wykonania</span>
            <h2>Działania i efekt</h2>
          </div>
        </div>
        {activeRecoveries.length === 0 ? (
          <p>Brak aktywnych działań. Nie oznacza to testu aktuatorów.</p>
        ) : (
          <div className='functional-safety-list'>
            {activeRecoveries.map(recovery => (
              <article className='functional-safety-row' key={recovery.proposalId}>
                <div>
                  <strong>{recovery.name}</strong>
                  <small>{recovery.instruction || recovery.description}</small>
                </div>
                <StatusBadge
                  tone={
                    recovery.status === 'confirmed'
                      ? 'safe'
                      : recovery.status === 'failed' || recovery.status === 'timed_out'
                        ? 'danger'
                        : 'warning'
                  }
                >
                  {recovery.status === 'confirmed'
                    ? 'Potwierdzony efekt'
                    : recovery.status === 'failed'
                      ? 'Niepowodzenie'
                      : recovery.status === 'timed_out'
                        ? 'Brak potwierdzenia w terminie'
                        : 'Efekt niepotwierdzony'}
                </StatusBadge>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className='panel'>
        <div className='panel-header'>
          <div>
            <span className='section-kicker'>Konserwacja</span>
            <h2>Testy czujników dymu, gazu i czadu</h2>
          </div>
        </div>
        <p>
          Najpierw wykonaj fizyczny test zgodnie z instrukcją urządzenia. Poniższe przyciski tylko zapisują jego wynik — nie uruchamiają ani
          nie wyciszają czujnika.
        </p>
        {testMessage && <p role='status'>{testMessage}</p>}
        {detectorTests.length === 0 ? (
          <p>Brak danych o harmonogramie testów. Nie zakładamy, że testy zostały wykonane.</p>
        ) : (
          <div className='functional-safety-list'>
            {detectorTests.map(test => (
              <article className='functional-safety-row' key={test.detectorKey}>
                <div>
                  <strong>{test.friendlyName}</strong>
                  <small>
                    {test.status === 'current'
                      ? 'Test aktualny'
                      : test.status === 'failed'
                        ? 'Ostatni test niezaliczony'
                        : test.status === 'overdue'
                          ? 'Test zaległy'
                          : test.status === 'unknown'
                            ? 'Historia testów niedostępna'
                            : 'Wymagany pierwszy test'}
                    {test.lastTestAt ? ` · ostatnio ${new Date(test.lastTestAt).toLocaleDateString('pl-PL')}` : ''}
                    {test.dueAt ? ` · termin ${new Date(test.dueAt).toLocaleDateString('pl-PL')}` : ''}
                  </small>
                </div>
                <div className='functional-safety-actions'>
                  <button className='text-button' onClick={() => void attestTest(test.detectorKey, 'passed')} type='button'>
                    Zapisz: zaliczony
                  </button>
                  <button className='text-button' onClick={() => void attestTest(test.detectorKey, 'failed')} type='button'>
                    Zapisz: niezaliczony
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className='panel'>
        <span className='section-kicker'>Granica obserwacji</span>
        <h2>Awaria całej aplikacji lub hosta</h2>
        <p>
          Ten widok działa przez Home Assistant i nie wykryje jego całkowitego zaniku ani utraty zasilania hosta. Takie pokrycie wymaga
          niezależnego obserwatora i osobnego kanału alarmowego.
        </p>
      </section>
    </div>
  );
}
