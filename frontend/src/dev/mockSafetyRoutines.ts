import type { RoutineRun } from '../domain/safetyRoutines';

const runs: RoutineRun[] = [];
export function resetRoutineDemo() {
  runs.length = 0;
}

/** Local fixtures only; the production entry does not import this module. */
export function routineDemoResponse(data: Record<string, unknown>) {
  const envelope = { version: 1, request_id: data.request_id, storage_available: true };
  if (data.action === 'list')
    return {
      ...envelope,
      routines: [{ routine_id: 'Bedtime', name: 'Przed snem', enabled: true, check_count: 2 }],
      runs: [...runs].reverse().map(run => ({ ...run, results: undefined })),
    };
  if (data.action === 'run' && data.routine_id === 'Bedtime') {
    const now = new Date().toISOString();
    const run: RoutineRun = {
      run_id: crypto.randomUUID(),
      routine_id: 'Bedtime',
      name: 'Przed snem',
      state: 'completed',
      status: 'problem',
      started_at: now,
      due_at: now,
      finished_at: now,
      sample_count: 1,
      observation_seconds: 0,
      evidence_incomplete: true,
      counts: { pass: 0, problem: 1, unknown: 1, skipped: 0 },
      results: [
        {
          check_id: 'Window',
          name: 'Okno w kuchni',
          entity_id: 'binary_sensor.demo_window',
          status: 'problem',
          reason_label: 'Odczyt nie spełnia oczekiwania',
          value: 'on',
          observed_at: now,
          expected_states: ['off'],
          minimum: null,
          maximum: null,
          unit: null,
        },
        {
          check_id: 'Door',
          name: 'Drzwi wejściowe',
          entity_id: 'binary_sensor.demo_door',
          status: 'unknown',
          reason_label: 'Źródło jest niedostępne',
          value: null,
          observed_at: null,
          expected_states: ['off'],
          minimum: null,
          maximum: null,
          unit: null,
        },
      ],
    };
    runs.push(run);
    if (runs.length > 20) runs.shift();
    return { ...envelope, run };
  }
  if (data.action === 'report') {
    const run = runs.find(run => run.run_id === data.run_id && run.routine_id === data.routine_id);
    if (run) return { ...envelope, run };
  }
  return { ...envelope, error: 'run_unavailable' };
}
