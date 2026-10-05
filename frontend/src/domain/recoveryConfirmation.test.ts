import assert from 'node:assert/strict';
import test from 'node:test';
import { getRecoveries } from './safety.js';
import { recoveryConfirmationBlock } from './recoveryConfirmation.js';

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
