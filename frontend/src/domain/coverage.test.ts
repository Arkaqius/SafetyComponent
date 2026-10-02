import assert from 'node:assert/strict';
import test from 'node:test';
import { COVERAGE_ENTITY_ID, getCoverageView } from './coverage.js';
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
