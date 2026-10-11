import assert from 'node:assert/strict';
import test from 'node:test';
import { getStartupView, PROGRESS_ENTITY_ID } from './startup.js';
import { HEALTH_ENTITY_ID, type EntityMap } from './safety.js';

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
  assert.equal(getStartupView({}, now), null);
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
