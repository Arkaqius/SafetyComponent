import assert from 'node:assert/strict';
import test from 'node:test';
import { getHeatingSystems } from './heating.js';
import { type EntityMap } from './safety.js';

function fixture(state = 'degraded'): EntityMap {
  return {
    'sensor.heating_system_main': {
      entity_id: 'sensor.heating_system_main',
      state,
      attributes: {
        friendly_name: 'Kotłownia',
        phase_label: 'Podgrzewanie CWU',
        coverage_label: 'Częściowe pokrycie',
        inputs: [
          {
            role: 'flow_temperature',
            label: 'Temperatura zasilania',
            source_name: 'Kocioł',
            value_label: '35',
            quality_label: 'Wiek pomiaru niepotwierdzony',
          },
        ],
        rules: [{ label: 'Odpowiedź kotła', status: 'UNEVALUABLE', active: true, reasons: ['Brak świeżych danych'] }],
      },
    },
  } as EntityMap;
}

test('heating uses presentation labels and retains active faults when unevaluable', () => {
  const view = getHeatingSystems(fixture())[0];
  assert.equal(view.name, 'Kotłownia');
  assert.equal(view.inputs[0].name, 'Temperatura zasilania');
  assert.equal(view.rules[0].active, true);
  assert.equal(view.rules[0].status, 'UNEVALUABLE');
});

test('unavailable heating cannot display retained observations as current', () => {
  const view = getHeatingSystems(fixture('unavailable'))[0];
  assert.equal(view.available, false);
  assert.equal(view.phase, 'Brak bieżących danych');
  assert.equal(view.inputs[0].value, 'Brak bieżących danych');
  assert.equal(view.rules[0].active, true);
});

test('connection loss preserves active faults while invalidating current presentation', () => {
  const view = getHeatingSystems(fixture(), false)[0];
  assert.equal(view.available, false);
  assert.equal(view.inputs[0].value, 'Brak bieżących danych');
  assert.equal(view.rules[0].active, true);
});

test('missing heating and malformed attributes never imply a healthy installation', () => {
  assert.deepEqual(getHeatingSystems({}), []);
  const entities = fixture();
  entities['sensor.heating_system_main'].attributes = {};
  assert.equal(getHeatingSystems(entities)[0].available, false);
});
