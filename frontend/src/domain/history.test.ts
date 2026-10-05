import assert from 'node:assert/strict';
import test from 'node:test';
import { chartSegments, historySegments, historyTimeline, mergeHistoryStates, numericHistory, readHistoryStates } from './history.js';

test('empty Recorder snapshots and absent requested entities produce empty history', () => {
  assert.deepEqual(readHistoryStates({ states: {} }, 'sensor.temperature'), []);
  assert.deepEqual(readHistoryStates({ states: { 'sensor.temperature': [] } }, 'sensor.temperature'), []);
});

test('rejects malformed Recorder payloads before date formatting or numeric charts', () => {
  for (const payload of [
    null,
    {},
    { states: [] },
    { states: { 'sensor.temperature': '20' } },
    { states: { 'sensor.temperature': [{ s: '20', lu: 'invalid' }] } },
    { states: { 'sensor.temperature': [{ s: '20', lu: Infinity }] } },
    { states: { 'sensor.temperature': [{ s: '20', lu: 1, lc: NaN }] } },
    { states: { 'sensor.temperature': [{ s: '20', lu: 1, a: [] }] } },
  ]) {
    assert.throws(() => readHistoryStates(payload, 'sensor.temperature'), /invalid_history/);
  }
});

test('stream merges deduplicate updates and keep the last known boundary predecessor', () => {
  const previous = [
    { s: '10', lu: 1, a: {} },
    { s: '11', lu: 2, a: {} },
  ];
  const incoming = [
    { s: '12', lu: 3, a: {} },
    { s: '13', lu: 3, a: {} },
  ];
  assert.deepEqual(
    mergeHistoryStates(previous, incoming, 2500).map(item => item.s),
    ['11', '13']
  );
});

test('no state is fabricated before the first recorded point', () => {
  const timeline = historyTimeline([{ s: 'off', lu: 8, a: {} }]);
  assert.deepEqual(historySegments(timeline, 1000, 10000), [
    { state: null, duration: 7000 },
    { state: 'off', duration: 2000 },
  ]);
  assert.deepEqual(historySegments([], 1000, 10000), [{ state: null, duration: 9000 }]);
});

test('an actual predecessor can establish the state at the window boundary', () => {
  assert.deepEqual(
    historySegments(
      historyTimeline([
        { s: 'on', lu: 1, a: {} },
        { s: 'off', lu: 8, a: {} },
      ]),
      5000,
      10000
    ),
    [
      { state: 'on', duration: 3000 },
      { state: 'off', duration: 2000 },
    ]
  );
});

test('chart positions follow timestamps and preserve unavailable and blank gaps', () => {
  const points = numericHistory([
    { s: '10', lu: 0, a: {} },
    { s: '11', lu: 1, a: {} },
    { s: 'unavailable', lu: 2, a: {} },
    { s: ' ', lu: 3, a: {} },
    { s: '12', lu: 10, a: {} },
  ]);
  assert.deepEqual(chartSegments(points, 0, 10000, 100), [
    [
      { x: 0, value: 10 },
      { x: 10, value: 11 },
    ],
    [{ x: 100, value: 12 }],
  ]);
});

test('chart excludes future and out-of-window observations', () => {
  assert.deepEqual(
    chartSegments(
      [
        { time: -1, value: 1 },
        { time: 101, value: 2 },
      ],
      0,
      100,
      10
    ),
    []
  );
});
