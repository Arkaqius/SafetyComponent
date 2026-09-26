import assert from 'node:assert/strict';
import test from 'node:test';
import { batterySourceLabel, setBatteryMonitored, type BatterySource } from './batteryDiscovery.js';

const now = Date.parse('2026-01-01T12:00:00Z');
const source: BatterySource = {
  entity_id: 'sensor.battery',
  kind: 'percentage',
  state: '70',
  last_reported: new Date(now - 1000).toISOString(),
};

test('monitoring selection stores only deduplicated device exclusions', () => {
  assert.deepEqual(setBatteryMonitored(['other'], 'device', false), ['other', 'device']);
  assert.deepEqual(setBatteryMonitored(['device'], 'device', false), ['device']);
  assert.deepEqual(setBatteryMonitored(['other', 'device'], 'device', true), ['other']);
});

test('readouts distinguish valid, unavailable, stale and future battery samples', () => {
  assert.equal(batterySourceLabel(source, 60, now), '70%');
  for (const state of ['unavailable', '', 'NaN', '101', '-1']) {
    assert.equal(batterySourceLabel({ ...source, state }, 60, now), 'Brak wiarygodnego odczytu');
  }
  for (const last_reported of ['invalid', new Date(now + 1000).toISOString(), new Date(now - 61000).toISOString()]) {
    assert.equal(batterySourceLabel({ ...source, last_reported }, 60, now), 'Odczyt nieaktualny');
  }
  assert.equal(batterySourceLabel({ ...source, kind: 'low', state: 'on' }, 60, now), 'Niska bateria');
  assert.equal(batterySourceLabel({ ...source, kind: 'low', state: 'off' }, 60, now), 'Brak alarmu niskiej baterii');
});
