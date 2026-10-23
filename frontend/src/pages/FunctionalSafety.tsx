import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import BatteryHealth from '../components/BatteryHealth';
import { getBatteryRows } from '../domain/batteryHealth';
import { useHass } from '@hakit/core';
import MonitoredEntities from '../components/MonitoredEntities';
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
  FUNCTIONAL_SAFETY_SOURCES_ENTITY_ID,
  NOTIFICATION_HEALTH_ENTITY_ID,
} from '../domain/functionalSafety';
import { fetchFunctionalSafetyDiagnostics, type FunctionalSafetyDiagnosticsPayload } from '../domain/functionalSafetyApi';
import type { StatusTone } from '../domain/safety';
import { useSafetyEntities } from '../hooks/useSafetyEntities';

const healthTabs = [
  ['entities', 'Monitorowane encje'],
  ['batteries', 'Baterie'],
  ['platform', 'Platforma'],
  ['tests', 'Testy i powiadomienia'],
] as const;

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
  const { entities, monitoredEntities, entityMonitorSummary, connection: safetyConnection } = useSafetyEntities();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = healthTabs.find(([key]) => key === searchParams.get('tab'))?.[0] ?? 'entities';
  const selectTab = (key: string) =>
    setSearchParams(current => {
      const next = new URLSearchParams(current);
      next.set('tab', key);
      return next;
    });
  const connection = useHass(store => store.connection);
  const [testMessage, setTestMessage] = useState('');
  const [periodicMessage, setPeriodicMessage] = useState('');
  const [savingPeriodicTest, setSavingPeriodicTest] = useState(false);
  const [diagnosticsApi, setDiagnosticsApi] = useState<{
    status: 'loading' | 'ready' | 'error';
    data: FunctionalSafetyDiagnosticsPayload | null;
  }>({ status: 'loading', data: null });
  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const data = await fetchFunctionalSafetyDiagnostics();
        if (!disposed) setDiagnosticsApi({ status: 'ready', data });
      } catch {
        if (!disposed) setDiagnosticsApi(current => ({ status: 'error', data: current.data }));
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 15_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, []);
  const progress = getComponentProgress(entities);
  const detectorTests = getDetectorTests(entities);
  const periodicTests = getPeriodicTests(entities);
  const sources = getFunctionalSafetySources(entities, diagnosticsApi.status === 'ready' ? diagnosticsApi.data?.diagnostics : undefined);
  const batteryRows = getBatteryRows(sources);
  const functionalSafetySummary = entities[FUNCTIONAL_SAFETY_SOURCES_ENTITY_ID];
  const totalBatteries = functionalSafetySummary ? countAttribute(functionalSafetySummary.attributes, 'remote_battery_count') : null;
  const omittedBatteries = functionalSafetySummary
    ? countAttribute(functionalSafetySummary.attributes, 'remote_battery_omitted_count')
    : null;
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

  const sourceProvenance = (
    <div className='system-health-provenance'>
      {diagnosticsApi.status === 'loading' ? <p role='status'>Pobieranie pełnej diagnostyki z backendu…</p> : null}
      {diagnosticsApi.status === 'ready' && diagnosticsApi.data ? (
        <p>Pełna diagnostyka z backendu · aktualizacja {new Date(diagnosticsApi.data.generated_at).toLocaleString('pl-PL')}</p>
      ) : null}
      {diagnosticsApi.status === 'error' ? (
        <p role='status'>
          Pełna diagnostyka API jest niedostępna — pokazujemy ograniczony stan encji Home Assistant.
          {omittedBatteries !== null && omittedBatteries > 0
            ? ` Pominięte baterie: ${omittedBatteries} z ${totalBatteries ?? 'nieznanej liczby'}.`
            : ''}
        </p>
      ) : null}
    </div>
  );

  return (
    <div className='page-stack functional-safety-page'>
      <header className='system-health-intro'>
        <p>Brak alarmów nie potwierdza pełnej sprawności. Wybierz zakres diagnostyki.</p>
      </header>

      {periodicMessage && (
        <p className='panel' role='status'>
          {periodicMessage}
        </p>
      )}

      {(safetyConnection.cannotConnect || !safetyConnection.ready) && (
        <p className='panel' role='status'>
          Brak połączenia z Home Assistant. Poniżej ostatnie znane wyniki, bez potwierdzenia bieżącej sprawności.
        </p>
      )}
      <div className='system-health-tabs' role='tablist' aria-label='Sekcje zdrowia systemu'>
        {healthTabs.map(([key, label], index) => (
          <button
            key={key}
            type='button'
            role='tab'
            id={`system-health-tab-${key}`}
            aria-controls={`system-health-panel-${key}`}
            aria-selected={activeTab === key}
            tabIndex={activeTab === key ? 0 : -1}
            onClick={() => selectTab(key)}
            onKeyDown={event => {
              const offset = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
              const target =
                event.key === 'Home'
                  ? 0
                  : event.key === 'End'
                    ? healthTabs.length - 1
                    : offset
                      ? (index + offset + healthTabs.length) % healthTabs.length
                      : null;
              if (target === null) return;
              event.preventDefault();
              selectTab(healthTabs[target][0]);
              document.getElementById(`system-health-tab-${healthTabs[target][0]}`)?.focus();
            }}
          >
            <span>{label}</span>
            {key === 'entities' && <small>{entityMonitorSummary.total}</small>}
            {key === 'batteries' && (
              <small>
                {diagnosticsApi.status !== 'ready' && totalBatteries !== null && totalBatteries > batteryRows.length
                  ? `${batteryRows.length}/${totalBatteries}`
                  : batteryRows.length}
              </small>
            )}
          </button>
        ))}
      </div>
      <section
        role='tabpanel'
        id='system-health-panel-entities'
        aria-labelledby='system-health-tab-entities'
        className='page-stack system-health-panel'
        hidden={activeTab !== 'entities'}
      >
        <MonitoredEntities monitored={monitoredEntities} summary={entityMonitorSummary} />
      </section>
      <section
        role='tabpanel'
        id='system-health-panel-batteries'
        aria-labelledby='system-health-tab-batteries'
        className='page-stack system-health-panel'
        hidden={activeTab !== 'batteries'}
      >
        {sourceProvenance}
        <BatteryHealth rows={batteryRows} total={totalBatteries} />
      </section>
      <section
        role='tabpanel'
        id='system-health-panel-platform'
        aria-labelledby='system-health-tab-platform'
        className='page-stack system-health-panel'
        hidden={activeTab !== 'platform'}
      >
        {sourceProvenance}
        <details className='panel functional-safety-group'>
          <summary>Postęp funkcji — ocena per komponent ({progress.length})</summary>
          <div className='panel-header'>
            <div>
              <span className='section-kicker'>Ocena per komponent</span>
              <h2>Postęp funkcji</h2>
            </div>
          </div>
          <p>
            „Ocena wykonana” potwierdza ukończenie logiki, nie jakość jej wejść. Komponenty zdarzeniowe mogą pozostawać bezczynne; jakość
            ich źródeł nadzoruje osobno monitoring encji.
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
            Poziomy alarmów: brak pamięci L2 (pamięć dostępna i PSI); utrata WAN, trwałe obciążenie CPU, mało miejsca na dysku, wysoka
            temperatura hosta, problemy z kopiami zapasowymi, dostępne aktualizacje i testy czujników wymagające uwagi L3. Niska bateria i
            testy okresowe L4 to informacje, które nie pogarszają ogólnego stanu systemu. Nieznane źródło nie oznacza sprawności.
          </p>
          {sources.length === 0 ? (
            <p>Brak diagnostyki źródeł.</p>
          ) : (
            <div className='functional-safety-list'>
              {(['host', 'wan', 'updates'] as const).map(group => (
                <details className='panel functional-safety-group' key={group}>
                  <summary>
                    {{ host: 'Host i kopie zapasowe', wan: 'Łączność WAN', updates: 'Aktualizacje' }[group]} (
                    {sources.filter(source => source.group === group).length})
                  </summary>
                  {group === 'wan' && (
                    <p>
                      Ostatni raport encji jest dowodem odczytu źródła, nie niezależnym potwierdzeniem czasu testu Ping. Ostatnia ocena
                      monitora nie oznacza wykonania nowego testu WAN.
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
      </section>
      <section
        role='tabpanel'
        id='system-health-panel-tests'
        aria-labelledby='system-health-tab-tests'
        className='page-stack system-health-panel'
        hidden={activeTab !== 'tests'}
      >
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
            Najpierw wykonaj fizyczny test zgodnie z instrukcją urządzenia. Poniższe przyciski tylko zapisują jego wynik — nie uruchamiają
            ani nie wyciszają czujnika.
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
            Wyślij testowe powiadomienie i sprawdź rzeczywisty odbiór. Przyciski „Zapisz” tylko zapisują deklarację operatora. Żaden
            przycisk nie uruchamia syren ani nie odtwarza kopii. Przyjęcie przez HA nie dowodzi odbioru na telefonie.
          </p>
          <button
            className='primary-button'
            type='button'
            disabled={operatorBusy || !connection}
            onClick={() => void operatorAction('test')}
          >
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
      </section>
    </div>
  );
}
