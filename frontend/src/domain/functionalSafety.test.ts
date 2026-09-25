import assert from 'node:assert/strict';
import test from 'node:test';
import { getComponentProgress, getDetectorTests, getFunctionalSafetySources } from './functionalSafety.js';
import type { EntityMap } from './safety.js';

test('keeps missing and observed components separate', () => {
  const entities: EntityMap = {
    'sensor.safety_evaluation_progress': {
      state: 'unknown',
      attributes: {
        components: {
          EntityMonitorComponent: {
            status: 'unknown',
            last_completed_at: null,
            expected_interval_seconds: 15,
            age_seconds: null,
            completed_count: 0,
            missed_deadline_count: 0,
            evaluation_mode: 'periodic',
          },
          TemperatureComponent: {
            status: 'observed',
            last_completed_at: '2026-09-25T00:00:00Z',
            expected_interval_seconds: null,
            age_seconds: 10,
            completed_count: 1,
            missed_deadline_count: 0,
            evaluation_mode: 'event_driven',
          },
        },
      },
    },
  };

  const progress = getComponentProgress(entities);
  assert.equal(progress.length, 2);
  assert.equal(progress[0].status, 'unknown');
  assert.equal(progress[1].evaluationMode, 'event_driven');
});

test('does not invent progress from malformed attributes', () => {
  assert.deepEqual(getComponentProgress({}), []);
  assert.deepEqual(
    getComponentProgress({
      'sensor.safety_evaluation_progress': { state: 'observed', attributes: { components: [] } },
    }),
    []
  );
  assert.deepEqual(
    getComponentProgress({
      'sensor.safety_evaluation_progress': { state: 'unavailable', attributes: { components: { X: { status: 'observed' } } } },
    }),
    []
  );
});

test('requires an explicit detector test record', () => {
  assert.deepEqual(getDetectorTests({}), []);
  assert.deepEqual(
    getDetectorTests({
      'sensor.safety_detector_tests': {
        state: 'attention',
        attributes: { tests: [{ detector_key: 'KitchenSmoke', friendly_name: 'Smoke', hazard: 'smoke', status: 'due' }] },
      },
    }),
    [{ detectorKey: 'KitchenSmoke', friendlyName: 'Smoke', hazard: 'smoke', status: 'due', lastTestAt: null, dueAt: null }]
  );
});

test('keeps unknown platform sources visible without inventing health', () => {
  assert.deepEqual(getFunctionalSafetySources({}), []);
  const rows = getFunctionalSafetySources({
    'sensor.functional_safety_sources': {
      state: 'unknown',
      attributes: {
        memory: { status: 'unknown', reason: 'not_configured' },
        wan: { status: 'offline' },
        updates: { home_assistant_core: { status: 'unknown', reason: 'not_configured' } },
        remote_batteries: { SmokeDetector: { status: 'low', friendly_name: 'Smoke detector' } },
      },
    },
  });
  assert.deepEqual(
    rows.map(row => row.status),
    ['unknown', 'offline', 'unknown', 'low']
  );
  assert.equal(rows[3].label, 'Bateria: Smoke detector');
});
