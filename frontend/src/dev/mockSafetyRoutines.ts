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
      routines: [{ routine_id: 'Bedtime', name: 'Przed snem', enabled: true, check_count: 3 }],
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
      counts: { pass: 1, problem: 1, unknown: 1, skipped: 0 },
      results: [
        {
          check_id: 'HouseAsleep',
          name: 'Domownicy śpią',
          entity_id: 'sensor.demo_activity',
          status: 'problem',
          reason_label: 'Odczyt nie spełnia oczekiwania',
          value: 'awake',
          observed_at: now,
          expected_states: ['asleep'],
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
        {
          check_id: 'HousePower',
          name: 'Moc całego domu',
          entity_id: 'sensor.demo_house_power',
          status: 'pass',
          reason_label: 'Ostatni znany odczyt jest zgodny z oczekiwaniem',
          value: 499,
          observed_at: null,
          expected_states: null,
          minimum: 0,
          maximum: 499.9,
          unit: 'W',
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
