import assert from 'node:assert/strict';
import test from 'node:test';
import { parseRoutineResponse, routineRequest, routineRunLabel, type RoutineRun } from './safetyRoutines.js';
import { initialObject, registrySchemas, routineCheckSchema, updateObjectField } from '../components/configurationFieldSchemas.js';

const run: RoutineRun = {
  run_id: 'one',
  routine_id: 'Bedtime',
  name: 'Przed snem',
  state: 'completed',
  status: 'pass',
  started_at: '2026-10-31T20:00:00Z',
  finished_at: '2026-10-31T20:00:00Z',
  due_at: '2026-10-31T20:00:00Z',
  sample_count: 1,
  observation_seconds: 0,
  evidence_incomplete: false,
  counts: { pass: 1, problem: 0, unknown: 0, skipped: 0 },
  results: [
    {
      check_id: 'Window',
      name: 'Okno',
      entity_id: 'binary_sensor.window',
      status: 'pass',
      reason_label: 'Potwierdzono oczekiwany stan',
      value: 'off',
      observed_at: '2026-10-31T20:00:00Z',
      expected_states: ['off'],
      minimum: null,
      maximum: null,
      unit: null,
    },
  ],
};
const envelope = (value: unknown) => ({ version: 1, request_id: 'request', storage_available: true, run: value });

test('routine reports require correlation, complete evidence and consistent counts', () => {
  assert.ok(parseRoutineResponse(envelope(run), 'request'));
  assert.equal(parseRoutineResponse(envelope(run), 'other'), null);
  assert.equal(parseRoutineResponse(envelope({ ...run, results: [] }), 'request'), null);
  assert.equal(parseRoutineResponse(envelope({ ...run, counts: { ...run.counts, unknown: 1 } }), 'request'), null);
  assert.equal(parseRoutineResponse(envelope({ ...run, results: [{ ...run.results![0], value: Infinity }] }), 'request'), null);
  assert.equal(parseRoutineResponse(envelope({ ...run, started_at: 'bad' }), 'request'), null);
});

test('pending, interrupted and all-skipped reports cannot claim success', () => {
  for (const state of ['running', 'waiting', 'cancelled', 'interrupted']) {
    assert.equal(parseRoutineResponse(envelope({ ...run, state }), 'request'), null);
    assert.ok(parseRoutineResponse(envelope({ ...run, state, status: 'unknown' }), 'request'));
  }
  const skipped = { ...run, counts: { pass: 0, problem: 0, unknown: 0, skipped: 1 }, results: [{ ...run.results![0], status: 'skipped' }] };
  assert.equal(parseRoutineResponse(envelope(skipped), 'request'), null);
  assert.ok(parseRoutineResponse(envelope({ ...skipped, status: 'not_applicable' }), 'request'));
  assert.equal(routineRunLabel(run), 'OK w chwili kontroli');
});

test('manual commands use the separate correlated event API', () => {
  assert.deepEqual(routineRequest('request', 'run', 'Bedtime'), {
    type: 'fire_event',
    event_type: 'safety_routine_request',
    event_data: { request_id: 'request', action: 'run', routine_id: 'Bedtime' },
  });
});

test('configuration editor starts disabled and switches mutually exclusive contracts', () => {
  assert.equal(initialObject(registrySchemas.safety_routines).enabled, false);
  const state = initialObject(routineCheckSchema);
  assert.equal(state.kind, 'state');
  const numeric = updateObjectField(state, 'kind', 'numeric_range');
  assert.equal(numeric.expected_states, undefined);
  assert.equal(numeric.maximum, 0);
  const restored = updateObjectField(numeric, 'kind', 'state');
  assert.equal(restored.unit, undefined);
  assert.deepEqual(restored.expected_states, ['']);
  const trigger = updateObjectField({ kind: 'event', event: 'bedtime' }, 'kind', 'state');
  assert.equal(trigger.event, undefined);
  assert.equal(trigger.from_state, '');
});
