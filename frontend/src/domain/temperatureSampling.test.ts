import assert from 'node:assert/strict';
import test from 'node:test';
import { getTemperatureSamplingView } from './temperatureSampling.js';
import { getStartupView, PROGRESS_ENTITY_ID } from './startup.js';
import { HEALTH_ENTITY_ID, type EntityMap } from './safety.js';

const now = Date.parse('2026-10-11T21:41:00Z');
function inputs(): EntityMap {
  return {
    [HEALTH_ENTITY_ID]: { state: 'running', attributes: {} },
    [PROGRESS_ENTITY_ID]: {
      state: 'observed',
      attributes: { startup: { phase: 'complete', duration_seconds: 600, remaining_seconds: 0, reported_at: new Date(now).toISOString() } },
    },
    'sensor.diagnostic': {
      state: 'unavailable',
      attributes: { entity_key: 'TemperatureForecastOffice', source_entity_id: 'sensor.office_rate' },
    },
    'sensor.office': { state: '22', attributes: {} },
    'sensor.office_rate': {
      state: 'unknown',
      attributes: { source_entity_id: 'sensor.office', sample_interval_seconds: 900, sampling_status: 'waiting_for_samples' },
    },
  };
}

test('sampling notice outlasts startup grace and waits for a numeric backend result', () => {
  const entities = inputs();
  assert.equal(getStartupView(entities, now), null);
  assert.match(getTemperatureSamplingView(entities, now)?.label ?? '', /oczekiwanie na próbki/);
  assert.match(getTemperatureSamplingView(entities, now)?.detail ?? '', /15 min/);
  entities[PROGRESS_ENTITY_ID].attributes.startup = {
    ...(entities[PROGRESS_ENTITY_ID].attributes.startup as object),
    reported_at: new Date(now + 900_000).toISOString(),
  };
  assert.ok(getTemperatureSamplingView(entities, now + 900_000));
  entities['sensor.office_rate'].state = '0';
  assert.equal(getTemperatureSamplingView(entities, now + 900_000), null);
});

test('missing source is distinct from sample collection and connection loss cannot confirm readiness', () => {
  const entities = inputs();
  entities['sensor.office'].state = 'unavailable';
  assert.match(getTemperatureSamplingView(entities, now)?.label ?? '', /brak odczytu źródłowego/);
  assert.match(getTemperatureSamplingView(entities, now, false)?.label ?? '', /brak aktualnych danych/);
  assert.match(getTemperatureSamplingView(inputs(), now + 180_001)?.label ?? '', /brak aktualnych danych/);
});

test('unknown or malformed values do not imply a completed forecast and legacy metadata is supported', () => {
  for (const state of ['unknown', 'unavailable', '', 'NaN', 'Infinity']) {
    const entities = inputs();
    entities['sensor.office_rate'].state = state;
    assert.ok(getTemperatureSamplingView(entities, now));
  }
  const entities = inputs();
  delete entities['sensor.office_rate'].attributes.sampling_status;
  assert.equal(getTemperatureSamplingView(entities, now), null);
  assert.equal(getTemperatureSamplingView({}, now), null);
});
