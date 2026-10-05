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
