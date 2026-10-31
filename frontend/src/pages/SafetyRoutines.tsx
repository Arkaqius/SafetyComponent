import { useEffect, useRef, useState } from 'react';
import { useHass } from '@hakit/core';
import { Link } from 'react-router-dom';
import StatusBadge from '../components/StatusBadge';
import { requestRoutine, routineRunLabel, routineStatusLabel, type RoutineRun, type RoutineSummary } from '../domain/safetyRoutines';

const time = (value: string | null) => (value ? new Date(value).toLocaleString('pl-PL') : '—');
const messages: Record<string, string> = {
  already_running: 'Ten scenariusz jest już wykonywany.',
  routine_unavailable: 'Scenariusz jest wyłączony lub nie jest już dostępny.',
  run_unavailable: 'Raport nie jest już dostępny w historii.',
  timeout: 'Brak odpowiedzi. Wynik uruchomienia jest nieznany; odśwież historię przed ponowieniem.',
};

export default function SafetyRoutines() {
  const connection = useHass(store => store.connection);
  const ready = useHass(store => store.ready);
  const connectionStatus = useHass(store => store.connectionStatus);
  const connected = ready && connectionStatus === 'connected';
  const [routines, setRoutines] = useState<RoutineSummary[]>([]);
  const [runs, setRuns] = useState<RoutineRun[]>([]);
  const [report, setReport] = useState<RoutineRun | null>(null);
  const [selection, setSelection] = useState<{ routine: string; run: string } | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [storageAvailable, setStorageAvailable] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const command = useRef<AbortController | null>(null);

  useEffect(() => () => command.current?.abort(), [connection, connected]);
  useEffect(() => {
    if (!connection || !connected) return;
    const controller = new AbortController();
    let inFlight = false;
    const load = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const data = await requestRoutine(connection, 'list', controller.signal);
        if (controller.signal.aborted) return;
        if (data.error) throw new Error(data.error);
        setRoutines(data.routines ?? []);
        setRuns(data.runs ?? []);
        setStorageAvailable(data.storage_available);
        if (selection) {
          const details = await requestRoutine(connection, 'report', controller.signal, selection.routine, selection.run);
          if (controller.signal.aborted) return;
          if (details.error) throw new Error(details.error);
          setReport(details.run ?? null);
          setStorageAvailable(details.storage_available);
        }
        setError('');
      } catch (caught) {
        if (!controller.signal.aborted)
          setError(messages[caught instanceof Error ? caught.message : ''] ?? 'Nie udało się pobrać aktualnych raportów.');
      } finally {
        inFlight = false;
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [connection, connected, selection, refresh]);

  const runCommand = async (action: 'run' | 'cancel', routineId: string, runId?: string) => {
    if (!connection || !connected || busy) return;
    command.current?.abort();
    const controller = new AbortController();
    command.current = controller;
    setBusy(true);
    setError('');
    try {
      const data = await requestRoutine(connection, action, controller.signal, routineId, runId);
      if (controller.signal.aborted) return;
      if (data.error) throw new Error(data.error);
      if (data.run) {
        setReport(data.run);
        setSelection({ routine: data.run.routine_id, run: data.run.run_id });
      }
      setStorageAvailable(data.storage_available);
      setRefresh(value => value + 1);
    } catch (caught) {
      if (!controller.signal.aborted)
        setError(messages[caught instanceof Error ? caught.message : ''] ?? 'Nie udało się potwierdzić wykonania polecenia.');
    } finally {
      setBusy(false);
    }
  };
  const selectedReport = report && report.run_id === selection?.run ? report : null;

  return (
    <div className='page-stack'>
      <section className='page-introduction'>
        <div>
          <span className='section-kicker'>Kontrola na żądanie</span>
          <h2>Scenariusze bezpieczeństwa</h2>
          <p>
            Sprawdź wybrane urządzenia przed snem lub wyjściem. Raport opisuje chwilę kontroli; nie potwierdza bieżącego bezpieczeństwa
            domu.
          </p>
          <Link className='text-link' to='/configuration/safety_routines'>
            Konfiguruj scenariusze
          </Link>
        </div>
      </section>
      {!connected && <p role='status'>Brak połączenia. Widoczne raporty są zapisami wcześniejszych kontroli.</p>}
      {error && <p role='alert'>{error}</p>}
      {!storageAvailable && (
        <p role='alert'>Historia nie mogła zostać odczytana lub zapisana. Widoczne wyniki mogą nie przetrwać restartu.</p>
      )}
      <section className='panel'>
        <div className='section-heading'>
          <h3>Scenariusze</h3>
          <button className='secondary-button' disabled={!connected} onClick={() => setRefresh(value => value + 1)}>
            Odśwież
          </button>
        </div>
        {loading && connected && <p role='status'>Pobieranie scenariuszy…</p>}
        {!loading && connected && !error && routines.length === 0 && (
          <p>Brak skonfigurowanych scenariuszy. Dodaj scenariusz i wybierz sprawdzenia w konfiguracji.</p>
        )}
        {routines.map(routine => {
          const active = runs.find(run => run.routine_id === routine.routine_id && ['waiting', 'running'].includes(run.state));
          return (
            <div className='section-heading' key={routine.routine_id}>
              <div>
                <h4>{routine.name}</h4>
                <p>
                  {routine.check_count} kontroli{!routine.enabled ? ' · Wyłączony' : active ? ` · ${routineRunLabel(active)}` : ''}
                </p>
              </div>
              <button
                className='primary-button'
                disabled={!connected || busy || !routine.enabled || Boolean(active)}
                onClick={() => void runCommand('run', routine.routine_id)}
              >
                Sprawdź teraz
              </button>
            </div>
          );
        })}
      </section>
      <section className='panel'>
        <h3>Ostatnie wykonania</h3>
        <p>Każde ponowienie tworzy nowy raport. Historia obejmuje ostatnie 20 wykonań.</p>
        {runs.length === 0 && <p>Brak odczytanych wykonań.</p>}
        {runs.map(run => (
          <div className='section-heading' key={run.run_id}>
            <div>
              <strong>{run.name}</strong>
              <p>
                {time(run.started_at)} · {routineRunLabel(run)}
              </p>
            </div>
            <button
              className='secondary-button'
              disabled={!connected}
              onClick={() => {
                setReport(null);
                setSelection({ routine: run.routine_id, run: run.run_id });
              }}
            >
              Pokaż raport
            </button>
          </div>
        ))}
      </section>
      {selection && !selectedReport && connected && !error && <p role='status'>Pobieranie raportu…</p>}
      {selectedReport && (
        <section className='panel'>
          <div className='section-heading'>
            <h3>{selectedReport.name}</h3>
            <StatusBadge tone={selectedReport.state === 'completed' && selectedReport.status === 'problem' ? 'warning' : 'muted'}>
              {routineRunLabel(selectedReport)}
            </StatusBadge>
          </div>
          <p>
            Rozpoczęto: {time(selectedReport.started_at)} · Zakończono: {time(selectedReport.finished_at)}
          </p>
          {['waiting', 'running'].includes(selectedReport.state) && (
            <>
              <p>Planowany koniec tego etapu: {time(selectedReport.due_at)}. Oczekiwanie na wynik z systemu.</p>
              <button
                className='secondary-button'
                disabled={!connected || busy}
                onClick={() => void runCommand('cancel', selectedReport.routine_id, selectedReport.run_id)}
              >
                Anuluj kontrolę
              </button>
            </>
          )}
          <p>
            OK: {selectedReport.counts.pass} · Problemy: {selectedReport.counts.problem} · Nie można ocenić: {selectedReport.counts.unknown}{' '}
            · Pominięte: {selectedReport.counts.skipped}
          </p>
          {selectedReport.observation_seconds > 0 && (
            <p>
              Próbki: {selectedReport.sample_count}. Okno obserwacji: {selectedReport.observation_seconds} s. Wynik nie opisuje zmian
              pomiędzy próbkami.
            </p>
          )}
          {selectedReport.evidence_incomplete && (
            <p role='status'>Podczas kontroli wystąpiły braki danych. Wykryty problem pozostaje widoczny także przy niepełnej ocenie.</p>
          )}
          <div className='table-scroll'>
            <table>
              <thead>
                <tr>
                  <th>Kontrola</th>
                  <th>Wynik</th>
                  <th>Odczyt i oczekiwanie</th>
                  <th>Wyjaśnienie</th>
                </tr>
              </thead>
              <tbody>
                {selectedReport.results?.map(result => (
                  <tr key={result.check_id}>
                    <td>
                      {result.name}
                      <small> · Obserwacja: {time(result.observed_at)}</small>
                    </td>
                    <td>{routineStatusLabel(result.status)}</td>
                    <td>
                      {result.value === null ? '—' : String(result.value)} {result.unit ?? ''}
                      <br />
                      Oczekiwano:{' '}
                      {result.expected_states?.join(', ') ?? `${result.minimum ?? '−∞'} – ${result.maximum ?? '+∞'} ${result.unit ?? ''}`}
                    </td>
                    <td>{result.reason_label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
