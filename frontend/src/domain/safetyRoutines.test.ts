import assert from 'node:assert/strict';
import test from 'node:test';
import type { Connection, HassEvent } from 'home-assistant-js-websocket';
import { parseRoutineResponse, requestRoutine, routineRequest, routineRunLabel, type RoutineRun } from './safetyRoutines.js';
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
const responseEvent = (value: unknown, requestId: string): HassEvent => ({
  event_type: 'safety_routine_response',
  origin: 'LOCAL',
  time_fired: run.started_at,
  context: { id: requestId, parent_id: null, user_id: null },
  data: { ...envelope(value), request_id: requestId },
});

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

test('routine wire responses may omit null fields but still require completion evidence', () => {
  const result = {
    check_id: 'Window',
    name: 'Okno',
    entity_id: 'binary_sensor.window',
    status: 'unknown',
    reason_label: 'Brak czasu obserwacji',
    expected_states: ['off'],
  };
  const detail = { ...run, status: 'unknown', counts: { pass: 0, problem: 0, unknown: 1, skipped: 0 }, results: [result] };
  assert.deepEqual(parseRoutineResponse(envelope(detail), 'request')?.run?.results, [
    { ...result, value: null, observed_at: null, minimum: null, maximum: null, unit: null },
  ]);
  assert.equal(parseRoutineResponse(envelope({ ...detail, finished_at: undefined }), 'request'), null);
  assert.equal(parseRoutineResponse(envelope({ ...detail, results: [{ ...result, observed_at: 'bad' }] }), 'request'), null);
  const waiting = {
    ...detail,
    state: 'waiting',
    finished_at: undefined,
    sample_count: 0,
    counts: { pass: 0, problem: 0, unknown: 0, skipped: 0 },
    results: [],
  };
  assert.equal(parseRoutineResponse(envelope(waiting), 'request')?.run?.finished_at, null);
  const list = { version: 1, request_id: 'request', storage_available: true, routines: [], runs: [waiting] };
  assert.equal(parseRoutineResponse(list, 'request')?.runs?.[0].finished_at, null);
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

test('a received report resolves even when subscription cleanup throws', async t => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'window');
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { setTimeout, clearTimeout } });
  t.after(() => (previous ? Object.defineProperty(globalThis, 'window', previous) : Reflect.deleteProperty(globalThis, 'window')));
  let listener: (event: HassEvent) => void = () => {};
  let cleaned = false;
  const connection = {
    async subscribeEvents(callback: (event: HassEvent) => void) {
      listener = callback;
      return () => {
        cleaned = true;
        throw new Error('closed connection');
      };
    },
    async sendMessagePromise(message: ReturnType<typeof routineRequest>) {
      listener(responseEvent(run, message.event_data.request_id));
    },
  } as unknown as Connection;
  const result = await requestRoutine(connection, 'report', new AbortController().signal, 'Bedtime', 'one');
  assert.equal(result.run?.run_id, 'one');
  await Promise.resolve();
  assert.equal(cleaned, true);
});

test('correlated malformed and wrong-run reports fail explicitly instead of timing out', async t => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'window');
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { setTimeout, clearTimeout } });
  t.after(() => (previous ? Object.defineProperty(globalThis, 'window', previous) : Reflect.deleteProperty(globalThis, 'window')));
  for (const bad of [
    { ...run, results: [] },
    { ...run, run_id: 'another' },
  ]) {
    let listener: (event: HassEvent) => void = () => {};
    let cleaned = 0;
    const connection = {
      async subscribeEvents(callback: (event: HassEvent) => void) {
        listener = callback;
        return () => {
          cleaned += 1;
        };
      },
      async sendMessagePromise(message: ReturnType<typeof routineRequest>) {
        listener(responseEvent(bad, message.event_data.request_id));
      },
    } as unknown as Connection;
    await assert.rejects(requestRoutine(connection, 'report', new AbortController().signal, 'Bedtime', 'one'), /invalid_response/);
    assert.equal(cleaned, 1);
  }
});

test('aborting before subscription completes releases it without sending a command', async t => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'window');
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { setTimeout, clearTimeout } });
  t.after(() => (previous ? Object.defineProperty(globalThis, 'window', previous) : Reflect.deleteProperty(globalThis, 'window')));
  let subscribe: (cleanup: () => void) => void = () => {};
  let sent = 0;
  let cleaned = 0;
  const connection = {
    subscribeEvents: () =>
      new Promise<() => void>(resolve => {
        subscribe = resolve;
      }),
    sendMessagePromise: async () => {
      sent += 1;
    },
  } as unknown as Connection;
  const controller = new AbortController();
  const pending = requestRoutine(connection, 'run', controller.signal, 'Bedtime');
  await Promise.resolve();
  controller.abort();
  await assert.rejects(pending, /disconnected/);
  subscribe(() => {
    cleaned += 1;
  });
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(sent, 0);
  assert.equal(cleaned, 1);
});
