import assert from 'node:assert/strict';
import test from 'node:test';
import { getMonitoredTemperatures, type EntityMap } from './safety.js';

const evaluatedAt = '2026-10-13T08:30:00Z';
const lowId = 'RiskyTemperatureOfficeForeCast';
const highId = 'RiskyTemperatureHighOfficeForeCast';

function observation(symptomId = lowId, status = 'risk') {
  return {
    status,
    symptom_id: symptomId,
    temperature_c: 20,
    rate_per_minute: -0.02,
    modeled_temperature_c: 15.2,
    threshold_c: 18,
    forecast_timespan_hours: 4,
    evaluated_at: evaluatedAt,
  };
}

function inputs(): EntityMap {
  return {
    'sensor.office': { state: '20', attributes: {} },
    'sensor.office_rate': { state: '-0.02', attributes: { attribution: 'Data provided by SafetyFunction' } },
    'sensor.office_low_threshold': { state: '18', attributes: { forecast_evaluation: observation() } },
    'sensor.office_high_threshold': { state: '28', attributes: { forecast_evaluation: observation(highId, 'within_limits') } },
    'sensor.fault_riskytemperatureforecast': {
      state: 'FAIL',
      attributes: { active: true, active_contributors: [lowId] },
    },
    'sensor.office_forecast_health': { state: 'healthy', attributes: { entity_key: 'TemperatureForecastOffice' } },
  };
}

test('available forecast inputs do not cancel a modeled risk or a qualified fault', () => {
  const [temperature] = getMonitoredTemperatures(inputs());
  assert.equal(temperature.lowForecast.status, 'risk');
  assert.equal(temperature.lowForecast.modeledTemperature, 15.2);
  assert.equal(temperature.lowForecast.timespanHours, 4);
  assert.equal(temperature.lowForecast.evaluatedAt, evaluatedAt);
  assert.equal(temperature.lowForecast.activeFault, true);
  assert.equal(temperature.highForecast.activeFault, false);
});

test('a newer within-limits observation does not clear a still-active qualified fault', () => {
  const entities = inputs();
  entities['sensor.office_low_threshold'].attributes.forecast_evaluation = observation(lowId, 'within_limits');
  const [temperature] = getMonitoredTemperatures(entities);
  assert.equal(temperature.lowForecast.status, 'within_limits');
  assert.equal(temperature.lowForecast.activeFault, true);
});

test('modeled risk before fault qualification remains risk with no qualified active fault', () => {
  const entities = inputs();
  entities['sensor.fault_riskytemperatureforecast'] = { state: 'PENDING_FAILURE', attributes: { active: false } };
  const [temperature] = getMonitoredTemperatures(entities);
  assert.equal(temperature.lowForecast.status, 'risk');
  assert.equal(temperature.lowForecast.activeFault, false);
});

test('fault ownership requires the exact symptom identifier and validated activation metadata', () => {
  for (const attributes of [
    { active: true },
    { active_contributors: [lowId] },
    { active: 'true', active_contributors: [lowId] },
    { active: true, active_contributors: [42] },
  ]) {
    const entities = inputs();
    entities['sensor.fault_riskytemperatureforecast'].attributes = attributes;
    assert.equal(getMonitoredTemperatures(entities)[0].lowForecast.activeFault, null);
  }
  const entities = inputs();
  entities['sensor.fault_riskytemperatureforecast'].attributes.active_contributors = [`${lowId}Extension`];
  assert.equal(getMonitoredTemperatures(entities)[0].lowForecast.activeFault, false);
  entities['sensor.fault_riskytemperatureforecast'].state = 'unavailable';
  assert.equal(getMonitoredTemperatures(entities)[0].lowForecast.activeFault, null);
});

test('unavailable threshold data and unevaluable or unknown observations hide retained model values', () => {
  for (const status of ['unevaluable', 'not_evaluated', 'unexpected']) {
    const entities = inputs();
    entities['sensor.office_low_threshold'].attributes.forecast_evaluation = observation(lowId, status);
    const forecast = getMonitoredTemperatures(entities)[0].lowForecast;
    assert.equal(forecast.modeledTemperature, null);
    assert.equal(forecast.temperature, null);
    assert.equal(forecast.rate, null);
    assert.equal(forecast.activeFault, true);
  }
  for (const state of ['unavailable', 'unknown', 'malformed', 'Infinity', '']) {
    const entities = inputs();
    entities['sensor.office_low_threshold'].state = state;
    assert.equal(getMonitoredTemperatures(entities)[0].lowForecast.status, 'unevaluable');
    assert.equal(getMonitoredTemperatures(entities)[0].lowForecast.modeledTemperature, null);
  }
});

test('malformed forecast fields cannot masquerade as a valid within-limits assessment', () => {
  for (const patch of [
    { modeled_temperature_c: null },
    { modeled_temperature_c: '15.2' },
    { temperature_c: NaN },
    { rate_per_minute: Infinity },
    { threshold_c: null },
    { forecast_timespan_hours: 0 },
    { evaluated_at: 'invalid' },
    { symptom_id: '' },
  ]) {
    const entities = inputs();
    entities['sensor.office_low_threshold'].attributes.forecast_evaluation = { ...observation(lowId, 'within_limits'), ...patch };
    const forecast = getMonitoredTemperatures(entities)[0].lowForecast;
    assert.equal(forecast.status, 'unevaluable');
    assert.equal(forecast.modeledTemperature, null);
  }
});

test('older backend and malformed payloads retain an explicitly unknown assessment', () => {
  for (const raw of [null, [], false, 'invalid']) {
    const entities = inputs();
    entities['sensor.office_low_threshold'].attributes.forecast_evaluation = raw;
    assert.equal(getMonitoredTemperatures(entities)[0].lowForecast.status, 'unknown');
  }
  const entities = inputs();
  delete entities['sensor.office_low_threshold'].attributes.forecast_evaluation;
  const forecast = getMonitoredTemperatures(entities)[0].lowForecast;
  assert.equal(forecast.status, 'not_reported');
  assert.equal(forecast.modeledTemperature, null);
  assert.equal(forecast.activeFault, null);
  delete entities['sensor.office_low_threshold'];
  assert.equal(getMonitoredTemperatures(entities)[0].lowForecast.status, 'not_reported');
});
