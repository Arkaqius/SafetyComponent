import { useEffect, useRef, useState } from 'react';
import { useHass } from '@hakit/core';
import { Link } from 'react-router-dom';
import RoutineReportResults from '../components/RoutineReportResults';
import StatusBadge from '../components/StatusBadge';
import { requestRoutine, routineRunLabel, type RoutineRun, type RoutineSummary } from '../domain/safetyRoutines';
import '../styles/safety-routines.css';

const time = (value: string | null) => (value ? new Date(value).toLocaleString('pl-PL') : '—');
const messages: Record<string, string> = {
  already_running: 'Ten scenariusz jest już wykonywany. Odśwież listę, aby zobaczyć jego przebieg.',
  routine_unavailable: 'Scenariusz jest wyłączony lub nie jest już dostępny.',
  run_unavailable: 'Ten raport nie jest już dostępny w historii. Wybierz inne wykonanie.',
  invalid_response: 'System zwrócił niepełne lub niezgodne dane. Spróbuj ponownie pobrać raport.',
  response_too_large: 'Raport jest zbyt duży, aby go pobrać. Pozostałe wykonania są dostępne w historii.',
};
const isActive = (run: RoutineRun) => run.state === 'waiting' || run.state === 'running';
const tone = (run: RoutineRun) => (isActive(run) ? 'info' : run.state === 'completed' && run.status === 'problem' ? 'warning' : 'muted');

function Spinner() {
  return <span className='routine-spinner' aria-hidden='true' />;
}

function RunCounts({ run }: { run: RoutineRun }) {
  return (
    <div className='routine-counts' aria-label='Podsumowanie sprawdzeń'>
      <span>
        OK <strong>{run.counts.pass}</strong>
      </span>
      <span className={run.counts.problem ? 'routine-count-problem' : undefined}>
        Problemy <strong>{run.counts.problem}</strong>
      </span>
      <span className={run.counts.unknown ? 'routine-count-unknown' : undefined}>
        Brak oceny <strong>{run.counts.unknown}</strong>
      </span>
      {run.counts.skipped > 0 && (
        <span>
          Pominięte <strong>{run.counts.skipped}</strong>
        </span>
      )}
    </div>
  );
}

export default function SafetyRoutines() {
  const connection = useHass(store => store.connection);
  const ready = useHass(store => store.ready);
  const connectionStatus = useHass(store => store.connectionStatus);
  const connected = ready && connectionStatus === 'connected';
  const [routines, setRoutines] = useState<RoutineSummary[]>([]);
  const [runs, setRuns] = useState<RoutineRun[]>([]);
  const [report, setReport] = useState<RoutineRun | null>(null);
  const [selection, setSelection] = useState<{ routine: string; run: string } | null>(null);
  const [listError, setListError] = useState('');
  const [reportError, setReportError] = useState('');
  const [commandError, setCommandError] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [busy, setBusy] = useState<{ action: 'run' | 'cancel'; routine: string } | null>(null);
  const [storageAvailable, setStorageAvailable] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [reportRefresh, setReportRefresh] = useState(0);
  const command = useRef<AbortController | null>(null);
  const reportRequest = useRef<AbortController | null>(null);
  const reportPanel = useRef<HTMLElement | null>(null);
  const focusReport = useRef(false);

  useEffect(() => () => command.current?.abort(), [connection, connected]);

  useEffect(() => {
    if (!connection || !connected) return;
    const controller = new AbortController();
    let inFlight = false;
    const load = async () => {
      if (inFlight) return;
      inFlight = true;
      setRefreshing(true);
      try {
        const data = await requestRoutine(connection, 'list', controller.signal);
        if (controller.signal.aborted) return;
        if (data.error) throw new Error(data.error);
        setRoutines(data.routines ?? []);
        setRuns(data.runs ?? []);
        setStorageAvailable(data.storage_available);
        setLastUpdated(new Date().toISOString());
        setListError('');
      } catch (caught) {
        if (!controller.signal.aborted)
          setListError(
            messages[caught instanceof Error ? caught.message : ''] ??
              'Nie udało się odświeżyć listy. Widoczne wykonania pochodzą z poprzedniego odczytu.'
          );
      } finally {
        inFlight = false;
        if (!controller.signal.aborted) setRefreshing(false);
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [connection, connected, refresh]);

  // Report selection owns its request, independently of list refreshes.
  useEffect(() => {
    if (!connection || !connected || !selection) return;
    const controller = new AbortController();
    reportRequest.current = controller;
    let timer: number | undefined;
    const load = async () => {
      setReportLoading(true);
      try {
        const data = await requestRoutine(connection, 'report', controller.signal, selection.routine, selection.run);
        if (controller.signal.aborted) return;
        if (data.error) throw new Error(data.error);
        setReport(data.run ?? null);
        setStorageAvailable(data.storage_available);
        setReportError('');
        if (data.run && isActive(data.run)) timer = window.setTimeout(() => void load(), 3000);
      } catch (caught) {
        if (!controller.signal.aborted)
          setReportError(messages[caught instanceof Error ? caught.message : ''] ?? 'Nie udało się pobrać raportu. Spróbuj ponownie.');
      } finally {
        if (!controller.signal.aborted) setReportLoading(false);
      }
    };
    void load();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
      if (reportRequest.current === controller) reportRequest.current = null;
    };
  }, [connection, connected, selection, reportRefresh]);

  useEffect(() => {
    if (selection && focusReport.current && reportPanel.current) {
      focusReport.current = false;
      const headerHeight = document.querySelector('.topbar')?.getBoundingClientRect().height ?? 0;
      reportPanel.current.style.setProperty('--routine-topbar-height', `${headerHeight}px`);
      reportPanel.current.focus({ preventScroll: true });
      reportPanel.current.scrollIntoView({ block: 'start', behavior: 'auto' });
    }
  }, [selection]);

  const openReport = (run: RoutineRun) => {
    setReport(current => (current?.run_id === run.run_id ? current : null));
    setReportError('');
    focusReport.current = true;
    setSelection({ routine: run.routine_id, run: run.run_id });
  };

  const runCommand = async (action: 'run' | 'cancel', routineId: string, runId?: string) => {
    if (!connection || !connected || command.current) return;
    const controller = new AbortController();
    command.current = controller;
    setBusy({ action, routine: routineId });
    setCommandError('');
    if (action === 'cancel') reportRequest.current?.abort();
    try {
      const data = await requestRoutine(connection, action, controller.signal, routineId, runId);
      if (controller.signal.aborted) return;
      if (data.error) throw new Error(data.error);
      if (data.run) {
        const next = data.run;
        setReport(next);
        setRuns(current => [next, ...current.filter(item => item.run_id !== next.run_id)].slice(0, 20));
        openReport(next);
      }
      setStorageAvailable(data.storage_available);
      setRefresh(value => value + 1);
    } catch (caught) {
      if (!controller.signal.aborted) {
        const code = caught instanceof Error ? caught.message : '';
        setCommandError(
          messages[code] ??
            (code === 'timeout'
              ? 'Brak potwierdzenia polecenia. Jego wynik jest nieznany; odśwież historię przed ponowieniem.'
              : 'Nie udało się potwierdzić wykonania polecenia. Odśwież historię przed ponowieniem.')
        );
      }
    } finally {
      if (command.current === controller) {
        command.current = null;
        setBusy(null);
      }
      if (action === 'cancel') setReportRefresh(value => value + 1);
    }
  };
  const selectedReport = report?.run_id === selection?.run ? report : null;

  return (
    <div className='page-stack safety-routines'>
      <section className='page-introduction'>
        <div>
          <span className='section-kicker'>Kontrola na żądanie</span>
          <h2>Scenariusze bezpieczeństwa</h2>
          <p>
            Sprawdź wybrane urządzenia przed snem lub wyjściem. Raport opisuje chwilę kontroli; nie potwierdza bieżącego bezpieczeństwa
            domu.
          </p>
          <div className='routine-links'>
            <Link className='text-link' to='/configuration/safety_routines'>
              Konfiguruj scenariusze
            </Link>
            <Link className='text-link' to='/help?temat=scenarios'>
              Wyzwalacze i wyniki kontroli
            </Link>
          </div>
        </div>
      </section>
      <details className='panel'>
        <summary>Jak działa kontrola</summary>
        <p>
          „Sprawdź teraz” i automatyczny wyzwalacz stosują to samo opóźnienie. Kontrola tylko odczytuje dane: nie zmienia ogrzewania, nie
          zamyka bram i sama nie wysyła powiadomień na telefon.
        </p>
        <p>
          „Nie można ocenić” może oznaczać brak oryginalnego czasu obserwacji. Wpisanie nazwy atrybutu nie tworzy danych w czujniku.
          Zapamiętane „zamknięte” lub niska moc bez potwierdzonej świeżości nie wystarczają do wyniku OK. Otwórz raport i przeczytaj
          wyjaśnienie każdej kontroli.
        </p>
      </details>
      {!connected && <p role='status'>Brak połączenia. Widoczne raporty są zapisami wcześniejszych kontroli.</p>}
      {commandError && <p role='alert'>{commandError}</p>}
      {!storageAvailable && (
        <p role='alert'>Historia nie mogła zostać odczytana lub zapisana. Widoczne wyniki mogą nie przetrwać restartu.</p>
      )}
      <section className='panel' aria-labelledby='routine-list-heading'>
        <div className='section-heading'>
          <h3 id='routine-list-heading'>Scenariusze</h3>
          <button
            className='secondary-button routine-action'
            disabled={!connected || refreshing}
            onClick={() => setRefresh(value => value + 1)}
          >
            {refreshing && connected && <Spinner />}
            {refreshing && connected ? 'Odświeżanie…' : 'Odśwież'}
          </button>
        </div>
        <p className='routine-refresh-state' role='status'>
          {refreshing && connected
            ? 'Pobieranie scenariuszy i ostatnich wykonań…'
            : lastUpdated
              ? `Lista odświeżona: ${time(lastUpdated)}`
              : 'Lista nie została jeszcze pobrana.'}
        </p>
        {listError && <p role='alert'>{listError}</p>}
        {lastUpdated && connected && !listError && routines.length === 0 && (
          <p>Brak skonfigurowanych scenariuszy. Dodaj scenariusz i wybierz sprawdzenia w konfiguracji.</p>
        )}
        <div className='routine-list'>
          {routines.map(routine => {
            const active = runs.find(run => run.routine_id === routine.routine_id && isActive(run));
            const starting = busy?.action === 'run' && busy.routine === routine.routine_id;
            return (
              <div className='routine-card' key={routine.routine_id}>
                <div>
                  <h4>{routine.name}</h4>
                  <p>
                    {routine.check_count} sprawdzeń{!routine.enabled ? ' · Wyłączony' : ''}
                  </p>
                  {active && (
                    <p className='routine-activity' role='status'>
                      {connected && <Spinner />}
                      {routineRunLabel(active)}
                      {!connected && ' · brak bieżących danych'}
                    </p>
                  )}
                  {active && connected && (
                    <p className='routine-stage-time'>
                      Planowany koniec etapu: {time(active.due_at)}. Oczekiwanie na potwierdzenie z systemu.
                    </p>
                  )}
                </div>
                <div className='routine-card-actions'>
                  {active && (
                    <button className='secondary-button' disabled={!connected} onClick={() => openReport(active)}>
                      Zobacz przebieg
                    </button>
                  )}
                  <button
                    className='primary-button routine-action'
                    disabled={!connected || Boolean(busy) || !routine.enabled || Boolean(active)}
                    onClick={() => void runCommand('run', routine.routine_id)}
                  >
                    {starting && <Spinner />}
                    {starting ? 'Uruchamianie…' : active ? 'Kontrola w toku' : 'Sprawdź teraz'}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </section>
      {selection && (
        <section
          className='panel routine-report'
          id='routine-report'
          ref={reportPanel}
          tabIndex={-1}
          aria-labelledby='routine-report-heading'
          aria-busy={reportLoading && connected}
        >
          <div className='section-heading'>
            <div>
              <span className='routine-report-caption'>Raport wykonania</span>
              <h3 id='routine-report-heading'>
                {selectedReport?.name ?? runs.find(run => run.run_id === selection.run)?.name ?? 'Wybrana kontrola'}
              </h3>
            </div>
            <button
              className='secondary-button'
              onClick={() => {
                setSelection(null);
                setReport(null);
              }}
            >
              Zamknij raport
            </button>
          </div>
          {reportLoading && connected && (
            <p className='routine-activity' role='status'>
              <Spinner />
              {selectedReport ? 'Aktualizowanie przebiegu…' : 'Pobieranie raportu…'}
            </p>
          )}
          {reportError && (
            <div className='routine-report-error'>
              <p role='alert'>{reportError}</p>
              <button
                className='secondary-button'
                disabled={!connected || reportLoading}
                onClick={() => setReportRefresh(value => value + 1)}
              >
                Ponów pobieranie raportu
              </button>
            </div>
          )}
          {!connected && !selectedReport && <p>Połącz się z systemem, aby pobrać raport.</p>}
          {selectedReport && (
            <>
              {isActive(selectedReport) && (
                <div className='routine-progress'>
                  <p className='routine-activity' role='status'>
                    {connected && <Spinner />}
                    {connected ? 'Oczekiwanie na wynik z systemu' : 'Brak bieżących danych'}
                  </p>
                  <p>Planowany koniec etapu {time(selectedReport.due_at)}.</p>
                  <button
                    className='secondary-button routine-action'
                    disabled={!connected || Boolean(busy)}
                    onClick={() => void runCommand('cancel', selectedReport.routine_id, selectedReport.run_id)}
                  >
                    {busy?.action === 'cancel' && <Spinner />}
                    {busy?.action === 'cancel' ? 'Anulowanie…' : 'Anuluj kontrolę'}
                  </button>
                </div>
              )}
              <RoutineReportResults key={selectedReport.run_id} run={selectedReport} />
              <details className='routine-run-timing'>
                <summary>Czas i przebieg</summary>
                <dl className='routine-report-times'>
                  <div>
                    <dt>Rozpoczęto</dt>
                    <dd>{time(selectedReport.started_at)}</dd>
                  </div>
                  {selectedReport.finished_at && (
                    <div>
                      <dt>Zakończono</dt>
                      <dd>{time(selectedReport.finished_at)}</dd>
                    </div>
                  )}
                  {selectedReport.observation_seconds > 0 && (
                    <>
                      <div>
                        <dt>Próbki</dt>
                        <dd>{selectedReport.sample_count}</dd>
                      </div>
                      <div>
                        <dt>Okno obserwacji</dt>
                        <dd>{selectedReport.observation_seconds} s</dd>
                      </div>
                    </>
                  )}
                </dl>
                {selectedReport.observation_seconds > 0 && <p>Wynik obejmuje chwile pobrania próbek.</p>}
              </details>
            </>
          )}
        </section>
      )}
      <section className='panel routine-history' aria-labelledby='routine-history-heading'>
        <div className='section-heading'>
          <h3 id='routine-history-heading'>Ostatnie wykonania</h3>
          <span className='routine-history-size'>{runs.length} / 20</span>
        </div>
        <p className='routine-history-description'>Od najnowszego. Każde ponowienie zachowuje osobny raport.</p>
        {runs.length === 0 && <p>Brak odczytanych wykonań.</p>}
        <ol className='routine-history-list'>
          {runs.map(run => {
            const selected = run.run_id === selection?.run;
            return (
              <li className={`routine-history-row${selected ? ' routine-history-selected' : ''}`} key={run.run_id}>
                <div className='routine-history-identity'>
                  <strong>{run.name}</strong>
                  <time dateTime={run.started_at}>{time(run.started_at)}</time>
                </div>
                <div className='routine-history-result'>
                  <StatusBadge tone={tone(run)}>
                    {routineRunLabel(run)}
                    {run.evidence_incomplete && run.status === 'problem' ? ' · dane niepełne' : ''}
                  </StatusBadge>
                  <RunCounts run={run} />
                </div>
                <button
                  className='secondary-button routine-action'
                  disabled={!connected}
                  aria-expanded={selected}
                  aria-controls='routine-report'
                  onClick={() => openReport(run)}
                >
                  {selected && reportLoading && connected && <Spinner />}Pokaż raport
                </button>
              </li>
            );
          })}
        </ol>
      </section>
    </div>
  );
}
