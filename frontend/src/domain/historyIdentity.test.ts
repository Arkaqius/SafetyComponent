import assert from 'node:assert/strict';
import test from 'node:test';
import { historyTimeline, historyTransitions } from './history.js';
import { entityLocations } from './safety.js';

test('history preserves locations and activation changes within the same raw fault state', () => {
  const timeline = historyTimeline([
    { s: 'FAIL', lu: 1, a: { friendly_name: 'Prognoza', location: 'Garaż', active: true } },
    { s: 'FAIL', lu: 2, lc: 1, a: { friendly_name: 'Prognoza', location: 'Kuchnia', active: true } },
    { s: 'FAIL', lu: 3, lc: 1, a: { friendly_name: 'Prognoza', location: 'Kuchnia', active: true, checked_at: 'later' } },
    { s: 'FAIL', lu: 4, lc: 1, a: { friendly_name: 'Prognoza', location: 'Kuchnia', active: false } },
    { s: 'PASS', lu: 5, a: { friendly_name: 'Prognoza', location: '', active: false } },
  ]);
  const transitions = historyTransitions(timeline);
  assert.deepEqual(
    transitions.map(point => point.last_changed),
    [1000, 2000, 4000, 5000]
  );
  assert.deepEqual(
    transitions.map(point => entityLocations({ state: point.state, attributes: point.attributes ?? {} })),
    [['Garaż'], ['Kuchnia'], ['Kuchnia'], []]
  );
});

test('history excludes split MQTT snapshots without inferring activation or changing valid times', () => {
  const transitions = historyTransitions(
    historyTimeline([
      { s: 'PASS', lu: 1, a: { publication_state: 'PASS', active: false } },
      { s: 'PASS', lu: 2, a: { publication_state: 'FAIL', active: true } },
      { s: 'FAIL', lu: 3, a: { publication_state: 'FAIL', active: true } },
      { s: 'FAIL', lu: 4, a: { publication_state: 'PASS', active: false } },
      { s: 'PASS', lu: 5, a: { publication_state: 'PASS', active: false } },
      { s: 'PASS', lu: 6, a: { publication_state: 'PASS', active: true, latched: true } },
    ])
  );
  assert.deepEqual(
    transitions.map(point => [point.state, point.last_changed]),
    [
      ['PASS', 1000],
      ['FAIL', 3000],
      ['PASS', 5000],
      ['PASS', 6000],
    ]
  );
});

test('legacy contradictory labels are excluded but missing evidence remains unknown', () => {
  const transitions = historyTransitions(
    historyTimeline([
      { s: 'PASS', lu: 1, a: { state_label: 'Zagrożenie potwierdzone', active: true } },
      { s: 'FAIL', lu: 2, a: { state_label: 'Zagrożenie potwierdzone', active: true } },
      { s: 'FAIL', lu: 3, a: { state_label: 'Warunek ustąpił', active: false } },
      { s: 'PASS', lu: 4, a: { state_label: 'Warunek ustąpił', active: false } },
      { s: 'UNEVALUABLE', lu: 5, a: {} },
    ])
  );
  assert.deepEqual(
    transitions.map(point => point.last_changed),
    [2000, 4000, 5000]
  );
  assert.deepEqual(transitions[2].attributes, {});
});
