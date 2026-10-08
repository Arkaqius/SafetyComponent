import assert from 'node:assert/strict';
import test from 'node:test';
import { COVERAGE_ENTITY_ID, coverageCauseStateLabel, coverageEffectLabel, getCoverageView } from './coverage.js';
import type { EntityMap } from './safety.js';

function entities(state: string, attributes: Record<string, unknown> = {}): EntityMap {
  return { [COVERAGE_ENTITY_ID]: { state, attributes } };
}

test('missing or unrecognized coverage never looks full', () => {
  assert.equal(getCoverageView({}).state, 'UNKNOWN');
  assert.equal(getCoverageView(entities('unavailable')).state, 'UNKNOWN');
  assert.equal(getCoverageView(entities('unexpected')).tone, 'muted');
});

test('technical loss is distinct from fault severity and exclusions', () => {
  const degraded = getCoverageView(entities('DEGRADED', { affected_count: 2 }));
  assert.equal(degraded.tone, 'danger');
  assert.match(degraded.detail, /2 ograniczeń/);
  const partial = getCoverageView(entities('PARTIAL', { exclusions: { room_a: 'operator' } }));
  assert.equal(partial.tone, 'warning');
  assert.match(partial.detail, /1 wyłączenie/);
});

test('invalid bindings are visible as unknown coverage', () => {
  const view = getCoverageView(
    entities('UNKNOWN', {
      binding_errors: { input_a: 'missing H target' },
      unresolved_h_count: 3,
    })
  );
  assert.match(view.detail, /1 błędnych powiązań/);
  assert.match(view.detail, /3 nieocenionych/);
});

test('exposes bounded D-to-H restriction details without conflating the effect', () => {
  const view = getCoverageView(
    entities('DEGRADED', {
      baseline_count: 4,
      affected_count: 1,
      affected: [
        {
          cause: 'AppHealthDelivery',
          cause_state: 'active',
          fault: 'RiskyTemperature',
          symptom: 'RiskyTemperatureOffice',
          capability: 'app_delivery',
          subject: 'Office',
          effect: 'notification',
        },
        { cause: 'incomplete-row' },
      ],
      affected_omitted: 2,
      unresolved_h_symptoms: ['RiskyTemperatureKitchen'],
      exclusions: { RiskyTemperatureBedroom: 'operator' },
    })
  );

  assert.equal(view.baselineCount, 4);
  assert.equal(view.restrictions.length, 1);
  assert.equal(view.restrictions[0].effect, 'notification');
  assert.equal(view.restrictions[0].causeState, 'active');
  assert.equal(view.restrictionsOmitted, 2);
  assert.deepEqual(view.unresolvedSymptoms, ['RiskyTemperatureKitchen']);
  assert.deepEqual(view.exclusions, [{ symptom: 'RiskyTemperatureBedroom', reason: 'operator' }]);
  assert.equal(coverageEffectLabel('notification'), 'Powiadomienie');
  assert.equal(coverageCauseStateLabel('active'), 'Aktywna przyczyna');
});
