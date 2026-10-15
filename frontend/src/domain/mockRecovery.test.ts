import assert from 'node:assert/strict';
import test from 'node:test';
import { MOCK_ENTITIES } from '../dev/mockData.js';
import { getFaults, getRecoveries, recoveriesForFault } from './safety.js';
import { recoveryReportBlock } from './recoveryConfirmation.js';

test('local visual examples cover observed repair, procedural report and blocked exact fault actions', () => {
  const faults = getFaults(MOCK_ENTITIES);
  const recoveries = getRecoveries(MOCK_ENTITIES);
  const battery = recoveries.find(recovery => recovery.proposalId === 'demo-battery-repair')!;
  const inspection = recoveries.find(recovery => recovery.proposalId === 'demo-delivery-inspection')!;
  const blocked = recoveries.find(recovery => recovery.proposalId === 'demo-forecast-check')!;
  assert.equal(battery.completionCondition, 'owner_clear');
  assert.equal(recoveryReportBlock(battery, true), null);
  assert.equal(inspection.completionCondition, 'operator_report');
  assert.equal(recoveryReportBlock(inspection, true), null);
  assert.ok(blocked.blockedReason);
  for (const recovery of [battery, inspection, blocked]) {
    const fault = faults.find(fault => fault.faultId === recovery.faultId)!;
    assert.ok(fault);
    assert.ok(recoveriesForFault(fault, recoveries).includes(recovery));
  }
});
