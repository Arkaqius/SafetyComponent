import assert from 'node:assert/strict';
import test from 'node:test';
import { filterBatteryRows, getBatteryRows } from './batteryHealth.js';
import { getFunctionalSafetySources, type SourceView } from './functionalSafety.js';

const sources: SourceView[] = [
  {
    key: 'battery-full',
    label: 'Bateria: Alfa',
    status: 'current',
    percentage: 90,
    group: 'batteries',
    detail: '',
    evidence: [],
    sourceEntities: ['sensor.room_battery'],
  },
  {
    key: 'battery-unknown',
    label: 'Bateria: Beta',
    status: 'unknown',
    percentage: 73,
    group: 'batteries',
    detail: '',
    evidence: ['73 % (odczyt źródłowy)'],
  },
  { key: 'battery-low', label: 'Bateria: Gamma', status: 'low', percentage: 0, group: 'batteries', detail: '', evidence: [] },
  { key: 'battery-binary', label: 'Bateria: Delta', status: 'current', percentage: null, group: 'batteries', detail: '', evidence: [] },
];

test('battery attention sorting preserves zero and puts low and unknown before current', () => {
  const rows = getBatteryRows(sources);
  assert.deepEqual(
    filterBatteryRows(rows, '', 'all', 'attention').map(row => row.key),
    ['battery-low', 'battery-unknown', 'battery-full', 'battery-binary']
  );
  assert.equal(rows.find(row => row.key === 'battery-low')?.percentage, 0);
  assert.equal(rows.find(row => row.key === 'battery-unknown')?.percentage, null);
  assert.ok(rows.find(row => row.key === 'battery-unknown')?.evidence[0].includes('73'));
  assert.equal(rows.find(row => row.key === 'battery-binary')?.status, 'current');
});

test('both percentage sort directions put missing levels last and never mutate input', () => {
  const rows = getBatteryRows(sources);
  const original = structuredClone(rows);
  for (const sort of ['percentage-asc', 'percentage-desc'] as const) {
    const sorted = filterBatteryRows(rows, '', 'all', sort);
    assert.deepEqual(
      sorted.slice(0, 2).map(row => row.percentage),
      sort === 'percentage-asc' ? [0, 90] : [90, 0]
    );
    assert.ok(sorted.slice(2).every(row => row.percentage === null));
  }
  assert.deepEqual(rows, original);
});

test('battery filters combine names and raw source IDs with backend status', () => {
  const rows = getBatteryRows(sources);
  assert.deepEqual(
    filterBatteryRows(rows, ' ROOM_BATTERY ', 'current', 'name').map(row => row.name),
    ['Alfa']
  );
  assert.deepEqual(filterBatteryRows(rows, 'alfa', 'low', 'attention'), []);
  assert.deepEqual(
    filterBatteryRows(rows, '', 'unknown', 'name').map(row => row.name),
    ['Beta']
  );
});

test('malformed or unrecognized battery assessments cannot become a trusted percentage', () => {
  const rows = getBatteryRows([
    ...[NaN, Infinity, -1, 101].map(percentage => ({ ...sources[0], percentage })),
    { ...sources[0], status: 'unexpected' },
    { ...sources[0], group: 'host' },
  ]);
  assert.equal(rows.length, 5);
  assert.ok(rows.every(row => row.percentage === null));
  assert.equal(rows[4].status, 'unknown');
});

test('full API battery rows retain source IDs and validated percentages for sorting', () => {
  const rows = getBatteryRows(
    getFunctionalSafetySources(
      {
        'sensor.functional_safety_sources': { state: 'attention', attributes: { remote_batteries: {} } },
      },
      {
        remote_batteries: {
          A: {
            status: 'low',
            friendly_name: 'Remote',
            percentage: 12,
            source_entities: ['sensor.remote_battery'],
            sources: [{ entity_id: 'sensor.remote_battery' }],
          },
        },
      }
    )
  );
  assert.equal(rows[0].percentage, 12);
  assert.deepEqual(rows[0].entityIds, ['sensor.remote_battery']);
});

test('unknown battery evidence retains raw values without calling an aggregate percentage trustworthy', () => {
  const rows = getBatteryRows(
    getFunctionalSafetySources(
      {
        'sensor.functional_safety_sources': { state: 'unknown', attributes: {} },
      },
      {
        remote_batteries: {
          A: { status: 'unknown', percentage: 73, sources: [{ entity_id: 'sensor.remote_battery', state: '73', unit: '%' }] },
        },
      }
    )
  );
  assert.equal(rows[0].percentage, null);
  assert.ok(rows[0].evidence.includes('Wiarygodny poziom baterii: —%'));
  assert.ok(rows[0].evidence.some(line => line.includes('73 % (odczyt źródłowy)')));
});
