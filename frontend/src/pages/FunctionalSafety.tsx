import { useState } from 'react';
import { useHass } from '@hakit/core';
import StatusBadge from '../components/StatusBadge';
import {
  DETECTOR_TEST_RESULT_EVENT,
  getComponentProgress,
  getDetectorTests,
  getFunctionalSafetySources,
  getPeriodicTests,
  periodicTestResultMessage,
  notificationOperatorMessage,
  type PeriodicTestKey,
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
  healthy: 'Sprawne',
  degraded: 'Wymaga uwagi',
  queued: 'Oczekuje w kolejce',
  disabled: 'Wyłączone',
  active: 'Alarm aktywny',
  high: 'Trwałe wysokie obciążenie',
  offline: 'Brak WAN',
  low: 'Niska bateria',
  overdue: 'Zaległe',
  failed: 'Błąd',
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
  const { entities } = useSafetyEntities();
  const connection = useHass(store => store.connection);
  const [testMessage, setTestMessage] = useState('');
  const [periodicMessage, setPeriodicMessage] = useState('');
  const [savingPeriodicTest, setSavingPeriodicTest] = useState(false);
  const progress = getComponentProgress(entities);
  const detectorTests = getDetectorTests(entities);
  const periodicTests = getPeriodicTests(entities);
  const sources = getFunctionalSafetySources(entities);
  const notification = entities[NOTIFICATION_HEALTH_ENTITY_ID];
  const accepted = notification ? countAttribute(notification.attributes, 'accepted_attempts') : null;
  const failed = notification ? countAttribute(notification.attributes, 'failed_attempts') : null;
  const queued = notification ? countAttribute(notification.attributes, 'queued_count') : null;
  const [operatorBusy, setOperatorBusy] = useState(false);
  const operatorAction = async (action: 'test' | 'reset') => {
    const prompt =
      action === 'test'
        ? 'Wysłać testowe powiadomienie do skonfigurowanych usług notify? Test nie uruchomi syren i nie zapisze wyniku jako zaliczony.'
        : 'Usunąć historię, kolejkę, liczniki i potwierdzenia powiadomień? Historii nie można przywrócić. Aktywne usterki zostaną ponownie zgłoszone. Reset nie kasuje usterek i nie steruje syrenami.';
    if (!connection || !window.confirm(prompt)) return;
    setOperatorBusy(true);
    try {
      await connection.sendMessagePromise<unknown>(notificationOperatorMessage(action));
      setPeriodicMessage(
        'HA przyjął żądanie. Sprawdź wynik w diagnostyce lub na urządzeniach; samo przyjęcie żądania nie jest dowodem wykonania.'
      );
    } catch {
      setPeriodicMessage('Nie udało się wysłać żądania.');
    } finally {
      setOperatorBusy(false);
    }
  };

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

  const attestPeriodicTest = async (testKey: PeriodicTestKey, outcome: 'passed' | 'failed') => {
    if (!connection) {
      setPeriodicMessage('Brak połączenia z Home Assistant. Wynik nie został zapisany.');
      return;
    }
    const instruction =
      testKey === 'notification_delivery'
        ? 'Czy sprawdziłeś rzeczywiste odebranie powiadomienia we wszystkich wymaganych kanałach? Przyjęcie wywołania przez HA nie wystarcza.'
        : 'Czy wykonałeś odtworzenie kopii na osobnym systemie testowym i sprawdziłeś odtworzone dane? Nie odtwarzaj jej na działającym domu tylko w celu tego testu.';
    if (
      !window.confirm(
        `${instruction}\nZapiszesz wyłącznie potwierdzenie operatora: ${outcome === 'passed' ? 'zaliczony' : 'niezaliczony'}.`
      )
    )
      return;
    setSavingPeriodicTest(true);
    try {
      await connection.sendMessagePromise<unknown>(periodicTestResultMessage(testKey, outcome));
      setPeriodicMessage('Wysłano wynik do HA. Potwierdzeniem zapisu będzie aktualizacja historii testu poniżej.');
    } catch {
      setPeriodicMessage('Nie udało się wysłać wyniku. Sprawdź połączenie i spróbuj ponownie.');
    } finally {
      setSavingPeriodicTest(false);
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

      {periodicMessage && (
        <p className='panel' role='status'>
          {periodicMessage}
        </p>
      )}

      <h2>Źródła diagnostyczne</h2>
      <details className='panel functional-safety-group'>
        <summary>Postęp funkcji — ocena per komponent ({progress.length})</summary>
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
      </details>

      <section className='page-stack'>
        <div className='panel-header'>
          <div>
            <span className='section-kicker'>Platforma i konserwacja</span>
            <h3>Platforma i konserwacja</h3>
          </div>
        </div>
        <p>
          Poziomy alarmów: brak pamięci L2 (pamięć dostępna i PSI), utrata WAN L3, trwałe obciążenie CPU, dostępne aktualizacje i niska
          bateria L4. Dysk, temperatura hosta i kopie zapasowe mają osobne progi systemowe. Nieznane źródło nie oznacza sprawności.
        </p>
        {sources.length === 0 ? (
          <p>Brak diagnostyki źródeł.</p>
        ) : (
          <div className='functional-safety-list'>
            {(['host', 'wan', 'updates', 'batteries'] as const).map(group => (
              <details className='panel functional-safety-group' key={group}>
                <summary>
                  {{ host: 'Host i kopie zapasowe', wan: 'Łączność WAN', updates: 'Aktualizacje', batteries: 'Baterie urządzeń' }[group]} (
                  {sources.filter(source => source.group === group).length})
                </summary>
                {group === 'wan' && (
                  <p>
                    Ostatni raport encji jest dowodem odczytu źródła, nie niezależnym potwierdzeniem czasu testu Ping. Ostatnia ocena
                    monitora nie oznacza wykonania nowego testu WAN.
                  </p>
                )}
                {group === 'batteries' && (
                  <p>
                    Inwentarz urządzeń (nie monitor):{' '}
                    {sources.find(source => source.group === 'inventory')?.evidence.join(' · ') ?? 'Brak danych o wykrywaniu'}
                  </p>
                )}
                {sources
                  .filter(source => source.group === group)
                  .map(source => (
                    <article className='functional-safety-row' key={source.key}>
                      <div>
                        <strong>{source.label}</strong>
                        {source.detail ? <small>{source.detail}</small> : null}
                        {source.evidence.map((line, index) => (
                          <small key={index}>{line}</small>
                        ))}
                      </div>
                      <StatusBadge
                        tone={
                          ['active', 'offline', 'low', 'high', 'failed'].includes(source.status)
                            ? 'danger'
                            : ['available', 'overdue'].includes(source.status)
                              ? 'warning'
                              : source.status === 'unknown'
                                ? 'muted'
                                : 'info'
                        }
                      >
                        {source.status === 'low' && source.key === 'disk'
                          ? 'Mało wolnego miejsca'
                          : (sourceLabels[source.status] ?? 'Brak wiarygodnych danych')}
                      </StatusBadge>
                    </article>
                  ))}
              </details>
            ))}
          </div>
        )}
      </section>

      <details className='panel functional-safety-group'>
        <summary>Powiadomienia</summary>
        <div className='panel-header'>
          <div>
            <span className='section-kicker'>Ścieżka ostrzegania</span>
            <h2>Powiadomienia</h2>
          </div>
        </div>
        {notification ? (
          <>
            <StatusBadge tone={notification.state === 'healthy' ? 'info' : notification.state === 'unknown' ? 'muted' : 'warning'}>
              {String(notification.attributes.state_label ?? sourceLabels[notification.state] ?? 'Brak wiarygodnych danych')}
            </StatusBadge>
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
            <small>
              Ostatni reset:{' '}
              {typeof notification.attributes.last_reset_at === 'number'
                ? new Date(notification.attributes.last_reset_at * 1000).toLocaleString('pl-PL')
                : 'brak'}
            </small>
            <button
              className='secondary-button'
              type='button'
              disabled={operatorBusy || !connection}
              onClick={() => void operatorAction('reset')}
            >
              Resetuj powiadomienia i historię
            </button>
            <p>Reset nie usuwa wiadomości już dostarczonych na telefony. Bieżące zagrożenia zostaną ponownie zgłoszone.</p>
          </>
        ) : (
          <p>Brak diagnostyki kanału powiadomień. Nie zakładamy, że działa.</p>
        )}
      </details>

      <details className='panel functional-safety-group'>
        <summary>Testy czujników dymu, gazu i czadu</summary>
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
      </details>

      <details className='panel functional-safety-group'>
        <summary>Testy okresowe</summary>
        <span className='section-kicker'>Konserwacja platformy</span>
        <h2>Testy okresowe</h2>
        <p>
          Wyślij testowe powiadomienie i sprawdź rzeczywisty odbiór. Przyciski „Zapisz” tylko zapisują deklarację operatora. Żaden przycisk
          nie uruchamia syren ani nie odtwarza kopii. Przyjęcie przez HA nie dowodzi odbioru na telefonie.
        </p>
        <button className='primary-button' type='button' disabled={operatorBusy || !connection} onClick={() => void operatorAction('test')}>
          Wyślij testowe powiadomienie
        </button>
        <p>Test i reset są ograniczone do jednego żądania na minutę dla każdej operacji.</p>
        {periodicTests.length === 0 ? (
          <p>Brak harmonogramu testów okresowych. Nie oznacza to, że testy zostały wykonane.</p>
        ) : (
          <div className='functional-safety-list'>
            {periodicTests.map(test => (
              <article className='functional-safety-row' key={test.testKey}>
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
                            ? 'Brak wiarygodnej historii'
                            : 'Wymagany pierwszy test'}
                    {test.lastTestAt ? ` · ostatnio ${new Date(test.lastTestAt).toLocaleDateString('pl-PL')}` : ''}
                    {test.dueAt ? ` · termin ${new Date(test.dueAt).toLocaleDateString('pl-PL')}` : ''}
                    {test.intervalDays !== null ? ` · co ${test.intervalDays} dni` : ''}
                  </small>
                  <small>
                    {test.testKey === 'notification_delivery'
                      ? 'Sprawdź odbiór we wszystkich wymaganych kanałach.'
                      : 'Odtworzenie wyłącznie na osobnym systemie testowym.'}{' '}
                    Dowód: potwierdzenie operatora, nie test automatyczny.
                  </small>
                </div>
                <div className='functional-safety-actions'>
                  <button
                    className='text-button'
                    type='button'
                    disabled={savingPeriodicTest}
                    onClick={() => void attestPeriodicTest(test.testKey, 'passed')}
                  >
                    Zapisz: zaliczony
                  </button>
                  <button
                    className='text-button'
                    type='button'
                    disabled={savingPeriodicTest}
                    onClick={() => void attestPeriodicTest(test.testKey, 'failed')}
                  >
                    Zapisz: niezaliczony
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </details>
    </div>
  );
}
