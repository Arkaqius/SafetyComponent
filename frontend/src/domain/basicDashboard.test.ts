import assert from 'node:assert/strict';
import test from 'node:test';
import { basicDashboardItems } from './basicDashboard.js';
import { getFaults, getRecoveries, type EntityMap } from './safety.js';

test('brief prioritizes active severity, including a latched PASS, and counts shadowed incidents', () => {
  const entities: EntityMap = {
    'sensor.fault_warning': { state: 'FAIL', attributes: { active: true, level: 2 } },
    'sensor.fault_latched': { state: 'PASS', attributes: { active: true, level: 1, latched: true } },
    'sensor.fault_shadowed': { state: 'FAIL', attributes: { active: true, level: 1, shadowed_by: ['latched'] } },
    'sensor.fault_clear': { state: 'PASS', attributes: { active: false, level: 1 } },
  };
  const faults = getFaults(entities);
  const order = faults.map(fault => fault.entityId);
  const brief = basicDashboardItems(faults, []);
  assert.equal(brief.primaryFault?.entityId, 'sensor.fault_latched');
  assert.equal(brief.activeFaultCount, 3);
  assert.deepEqual(
    faults.map(fault => fault.entityId),
    order
  );
});

test('brief retains an active incident even when all are shadowed, without inventing active state', () => {
  const entities: EntityMap = {
    'sensor.fault_active': { state: 'FAIL', attributes: { active: true, level: 2, shadowed_by: ['other'] } },
    'sensor.fault_uncertain': { state: 'unavailable', attributes: {} },
  };
  const brief = basicDashboardItems(getFaults(entities), []);
  assert.equal(brief.primaryFault?.entityId, 'sensor.fault_active');
  assert.equal(brief.activeFaultCount, 1);
  assert.equal(
    basicDashboardItems(getFaults({ 'sensor.fault_uncertain': entities['sensor.fault_uncertain'] }), []).primaryFault,
    undefined
  );
});

test('brief keeps failed and uncertain recommendations visible, excluding completed and unnecessary actions', () => {
  const recoveries = getRecoveries({
    'sensor.recovery_done': { state: 'CONFIRMED', attributes: {} },
    'sensor.recovery_none': { state: 'DO_NOT_PERFORM', attributes: {} },
    'sensor.recovery_failed': { state: 'FAILED', attributes: {} },
    'sensor.recovery_missing': { state: 'unavailable', attributes: {} },
  });
  const brief = basicDashboardItems([], recoveries);
  assert.deepEqual(brief.attentionRecoveries.map(recovery => recovery.status).sort(), ['failed', 'unavailable']);
  assert.ok(brief.primaryRecovery);
});
