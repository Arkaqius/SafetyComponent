import assert from 'node:assert/strict';
import test from 'node:test';
import { getFaults, getRecoveries, recoveriesForFault } from './safety.js';
import { publicRecoveryAttributes, recoveryConfirmationBlock, recoveryReportBlock, recoveryReportEvent } from './recoveryConfirmation.js';

test('confirmation rejects expired, malformed, tokenless and disconnected proposals', () => {
  const proposal = { proposal_id: 'gate', status: 'AWAITING_CONFIRMATION', confirmation_token: 'token', expires_at: 2000 };
  const read = (overrides: Record<string, unknown> = {}) =>
    getRecoveries({
      'sensor.recovery_gate': { state: 'AWAITING_CONFIRMATION', attributes: { proposals: [{ ...proposal, ...overrides }] } },
    })[0];
  assert.equal(recoveryConfirmationBlock(read(), true, 1000_000), null);
  assert.match(recoveryConfirmationBlock(read(), false, 1000_000)!, /brak połączenia/);
  assert.match(recoveryConfirmationBlock(read(), true, 2000_000)!, /wygasła/);
  assert.match(recoveryConfirmationBlock(read({ valid_until: 'invalid' }), true, 1000_000)!, /wygasła/);
  assert.notEqual(recoveryConfirmationBlock(read({ confirmation_token: '' }), true, 1000_000), null);
});

test('manual work reports require explicit permission and current incident capabilities', () => {
  const raw = {
    proposal_id: 'battery',
    proposal_instance_id: 'incident-2',
    status: 'TO_PERFORM',
    execution_policy: 'manual',
    completion_condition: 'observed',
    manual_report_allowed: true,
    report_token: 'capability',
  };
  const read = (overrides: Record<string, unknown> = {}) =>
    getRecoveries({ 'sensor.recovery_battery': { state: 'TO_PERFORM', attributes: { proposals: [{ ...raw, ...overrides }] } } })[0];
  assert.equal(recoveryReportBlock(read(), true), null);
  for (const overrides of [
    { manual_report_allowed: 'true' },
    { report_token: '' },
    { proposal_instance_id: '' },
    { execution_policy: 'user_confirmed' },
    { completion_condition: 'advisory' },
    { report_status: 'awaiting_evidence' },
    { reported_at: '2026-10-12T10:00:00Z' },
    { status: 'CONFIRMED' },
  ]) {
    assert.notEqual(recoveryReportBlock(read(overrides), true), null);
  }
  assert.match(recoveryReportBlock(read(), false)!, /brak połączenia/);
  assert.match(recoveryReportBlock(read({ expires_at: 1 }), true)!, /wygasła/);
  assert.equal(recoveryReportBlock(read({ blocked_reason: 'Odczyt niedostępny' }), true), 'Odczyt niedostępny');
  assert.deepEqual(recoveryReportEvent(read()), {
    type: 'fire_event',
    event_type: 'safety_recovery_report',
    event_data: { proposal_id: 'battery', proposal_instance_id: 'incident-2', report_token: 'capability' },
  });
});

test('fault action linking uses the exact raw fault ID without name, case or location guesses', () => {
  const faults = getFaults({
    'sensor.fault_batterylow': { state: 'FAIL', attributes: { fault_id: 'BatteryLow', friendly_name: 'Bateria' } },
  });
  const recoveries = getRecoveries({
    'sensor.recovery_battery': {
      state: 'TO_PERFORM',
      attributes: {
        proposals: [
          { proposal_id: 'correct', status: 'TO_PERFORM', fault_id: 'BatteryLow' },
          { proposal_id: 'different-case', status: 'TO_PERFORM', fault_id: 'batterylow' },
          { proposal_id: 'friendly-name', status: 'TO_PERFORM', fault_id: 'Bateria' },
          { proposal_id: 'missing', status: 'TO_PERFORM' },
        ],
      },
    },
  });
  assert.deepEqual(
    recoveriesForFault(faults[0], recoveries).map(recovery => recovery.proposalId),
    ['correct']
  );
});

test('recovery metadata keeps reported work distinct from observed outcome evidence', () => {
  const recovery = getRecoveries({
    'sensor.recovery_battery': {
      state: 'TO_PERFORM',
      attributes: {
        proposals: [
          {
            proposal_id: 'battery',
            status: 'TO_PERFORM',
            completion_condition: 'observed',
            manual_report_allowed: true,
            report_status: 'awaiting_evidence',
            reported_at: '2026-10-12T10:00:00Z',
            report_source: 'operator',
            evidence_at: '2026-10-12T10:01:00Z',
            evidence_source: 'sensor.battery',
          },
        ],
      },
    },
  })[0];
  assert.equal(recovery.status, 'to_perform');
  assert.equal(recovery.reportStatus, 'awaiting_evidence');
  assert.equal(recovery.reportSource, 'operator');
  assert.equal(recovery.evidenceSource, 'sensor.battery');
});

test('entity diagnostics recursively exclude capability tokens and private reporting actor', () => {
  assert.deepEqual(
    publicRecoveryAttributes({
      proposals: [
        {
          proposal_id: 'battery',
          confirmation_token: 'secret',
          report_token: 'secret2',
          report_user_id: 'private',
          instruction: 'Wymień baterię',
        },
      ],
      evidence: { source: 'sensor.battery', report_token: 'nested-secret' },
    }),
    { proposals: [{ proposal_id: 'battery', instruction: 'Wymień baterię' }], evidence: { source: 'sensor.battery' } }
  );
});
