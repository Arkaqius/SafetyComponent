import assert from 'node:assert/strict';
import test from 'node:test';
import { getStartupView, startupOperatorView, PROGRESS_ENTITY_ID } from './startup.js';
import { HEALTH_ENTITY_ID, getFaults, getRecoveries, getSafetySummary, type EntityMap } from './safety.js';

const now = Date.parse('2026-10-09T08:00:00Z');
function entities(remaining = 600): EntityMap {
  return {
    [HEALTH_ENTITY_ID]: { state: 'running', attributes: {} },
    [PROGRESS_ENTITY_ID]: {
      state: 'observed',
      attributes: {
        startup: {
          phase: 'settling',
          duration_seconds: 600,
          remaining_seconds: remaining,
          reported_at: new Date(now).toISOString(),
        },
      },
    },
  };
}

test('countdown represents server grace and persists until backend confirms completion', () => {
  assert.equal(getStartupView(entities(), now)?.countdown, '10:00');
  assert.equal(getStartupView(entities(), now + 15_000)?.countdown, '9:45');
  const expired = getStartupView(entities(5), now + 10_000);
  assert.equal(expired?.countdown, '0:00');
  assert.match(expired?.detail ?? '', /potwierdzenie/);
  const complete = entities();
  Object.assign(complete[PROGRESS_ENTITY_ID].attributes.startup as Record<string, unknown>, { phase: 'complete', remaining_seconds: 0 });
  assert.equal(getStartupView(complete, now), null);
});

test('offline, stale and invalid startup metadata never claim monitoring is ready', () => {
  for (const view of [
    getStartupView(entities(), now, false),
    getStartupView(entities(), now + 181_000),
    getStartupView(entities(-1), now),
  ]) {
    assert.equal(view?.available, false);
    assert.equal(view?.remainingSeconds, null);
    assert.match(view?.label ?? '', /brak aktualnych danych/);
  }
  const offline = entities();
  offline[HEALTH_ENTITY_ID].state = 'unavailable';
  assert.equal(getStartupView(offline, now)?.available, false);
});

test('backend clock ahead does not extend countdown beyond configured grace', () => {
  assert.equal(getStartupView(entities(), now - 60_000)?.countdown, '10:00');
  assert.equal(getStartupView(entities(), now - 60_001)?.available, false);
  assert.equal(getStartupView({}, now), null);
});

test('before the first startup report, offline placeholders do not become operator events', () => {
  const input: EntityMap = {
    [HEALTH_ENTITY_ID]: { state: 'unavailable', attributes: {} },
    [PROGRESS_ENTITY_ID]: { state: 'unavailable', attributes: {} },
    'sensor.fault_placeholder': { state: 'unavailable', attributes: { friendly_name: 'Pamięć hosta' } },
    'sensor.fault_gas': { state: 'FAIL', attributes: { active: true, category: 'H', level: 1 } },
  };
  const faults = getFaults(input);
  const startup = getStartupView(input, now);
  assert.equal(startup?.waitingForApp, true);
  assert.equal(startup?.remainingSeconds, null);
  const summary = getSafetySummary(input[HEALTH_ENTITY_ID], undefined, faults, []);
  const view = startupOperatorView(startup, faults, [], summary);
  assert.deepEqual(
    view.faults.map(fault => fault.entityId),
    ['sensor.fault_gas']
  );
  assert.equal(view.summary.effectiveLevel, 1);
  assert.equal(getStartupView({ ...input, [HEALTH_ENTITY_ID]: { state: 'init', attributes: {} } }, now)?.label, 'Rozruch monitoringu');
  assert.equal(getStartupView(input, now, false)?.waitingForApp, undefined);
  assert.equal(getStartupView(entities(), now)?.available, true);
});

test('completion requires current valid backend evidence while legacy reports remain compatible', () => {
  const complete = entities(0);
  (complete[PROGRESS_ENTITY_ID].attributes.startup as Record<string, unknown>).phase = 'complete';
  assert.equal(getStartupView(complete, now), null);
  assert.equal(getStartupView(complete, now, false)?.available, false);
  assert.equal(getStartupView(complete, now + 181_000)?.available, false);
  for (const value of [null, 'malformed', {}, { phase: 'invalid' }]) {
    const invalid = entities();
    invalid[PROGRESS_ENTITY_ID].attributes.startup = value;
    assert.equal(getStartupView(invalid, now)?.available, false);
  }
  delete complete[PROGRESS_ENTITY_ID].attributes.startup;
  assert.equal(getStartupView(complete, now), null);
});

test('startup emits no diagnostic incident or recommendation and does not claim a safe assessment', () => {
  const faults = getFaults({
    'sensor.fault_memory': { state: 'UNEVALUABLE', attributes: { fault_id: 'Memory', level: 3, category: 'D', active: false } },
    'sensor.fault_io': { state: 'FAIL', attributes: { fault_id: 'IO', level: 2, category: 'D', active: true } },
  });
  const recoveries = getRecoveries({
    'sensor.recovery_io': { state: 'TO_PERFORM', attributes: { proposals: [{ proposal_id: 'io', fault_id: 'IO', status: 'TO_PERFORM' }] } },
  });
  const summary = getSafetySummary({ state: 'running', attributes: {} }, { state: 'hazard', attributes: {} }, faults, recoveries);
  const view = startupOperatorView(getStartupView(entities(), now), faults, recoveries, summary);
  assert.equal(view.summary.label, 'Rozruch monitoringu');
  assert.equal(view.summary.tone, 'info');
  assert.equal(view.summary.activeFaultCount, 0);
  assert.deepEqual(view.faults, []);
  assert.deepEqual(view.recoveries, []);
  assert.equal(startupOperatorView(null, faults, recoveries, summary).faults, faults);
  assert.equal(startupOperatorView(getStartupView(entities(), now, false), faults, recoveries, summary).faults, faults);
});

test('startup keeps current or retained L1 danger and its recommendation immediate', () => {
  const faults = getFaults({
    'sensor.fault_gas': { state: 'UNEVALUABLE', attributes: { fault_id: 'Gas', level: 1, category: 'H', active: true } },
    'sensor.fault_memory': { state: 'UNEVALUABLE', attributes: { level: 3, category: 'D', active: false } },
  });
  const recoveries = getRecoveries({
    'sensor.recovery_gas': {
      state: 'TO_PERFORM',
      attributes: { proposals: [{ proposal_id: 'gas', fault_id: 'Gas', status: 'TO_PERFORM' }] },
    },
  });
  const summary = getSafetySummary({ state: 'running', attributes: {} }, { state: 'emergency', attributes: {} }, faults, recoveries);
  const view = startupOperatorView(getStartupView(entities(), now), faults, recoveries, summary);
  assert.equal(view.summary.effectiveLevel, 1);
  assert.equal(view.summary.tone, 'critical');
  assert.deepEqual(
    view.faults.map(fault => fault.faultId),
    ['Gas']
  );
  assert.deepEqual(
    view.recoveries.map(recovery => recovery.proposalId),
    ['gas']
  );
});
