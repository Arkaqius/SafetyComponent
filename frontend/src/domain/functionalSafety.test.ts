import assert from 'node:assert/strict';
import test from 'node:test';
import {
  getComponentProgress,
  getDetectorTests,
  getFunctionalSafetySources,
  getPeriodicTests,
  periodicTestResultMessage,
  notificationOperatorMessage,
} from './functionalSafety.js';
import { parseFunctionalSafetyDiagnostics } from './functionalSafetyApi.js';
import type { EntityMap } from './safety.js';

test('operator commands require explicit confirmation and differ from attestations', () => {
  assert.deepEqual(notificationOperatorMessage('test'), {
    type: 'fire_event',
    event_type: 'safety_notification_test',
    event_data: { confirmed: true },
  });
  assert.deepEqual(notificationOperatorMessage('reset'), {
    type: 'fire_event',
    event_type: 'safety_notification_reset',
    event_data: { confirmed: true },
  });
});

test('battery raw readings and source times remain visible without implying health', () => {
  const rows = getFunctionalSafetySources(
    {
      'sensor.functional_safety_sources': {
        state: 'unknown',
        attributes: { remote_battery_count: 1, remote_battery_omitted_count: 1 },
      },
    },
    {
      remote_batteries: {
        D: {
          status: 'unknown',
          friendly_name: 'Remote',
          percentage: null,
          sources: [
            {
              entity_id: 'sensor.battery',
              state: '73',
              unit: '%',
              last_reported: '2026-09-01T00:00:00Z',
              last_updated: '2026-08-01T00:00:00Z',
            },
          ],
        },
      },
    }
  );
  assert.equal(rows[0].group, 'batteries');
  assert.equal(rows[0].status, 'unknown');
  assert.ok(rows[0].evidence.some(line => line.includes('73 %')));
  assert.ok(rows[0].evidence.some(line => line.includes('Ostatni raport')));
});

test('functional safety API accepts only a versioned complete snapshot', () => {
  const payload = {
    schema_version: 1,
    generated_at: '2026-09-28T20:12:21Z',
    overall_state: 'observed',
    diagnostics: { remote_batteries: {} },
  };
  assert.deepEqual(parseFunctionalSafetyDiagnostics(payload), payload);
  assert.equal(parseFunctionalSafetyDiagnostics({ ...payload, schema_version: 2 }), null);
  assert.equal(parseFunctionalSafetyDiagnostics({ ...payload, generated_at: 'broken' }), null);
  assert.equal(parseFunctionalSafetyDiagnostics({ ...payload, diagnostics: [] }), null);
});

test('dev offered version never replaces publisher stable version', () => {
  const rows = getFunctionalSafetySources({
    'sensor.functional_safety_sources': {
      state: 'attention',
      attributes: {
        updates: {
          safety_component: {
            status: 'available',
            installed_version: '0.3.1-dev6',
            latest_version: '0.3.1-dev7',
            stable_release: { status: 'current', version: 'v0.3.1', checked_at: '2026-09-27T00:00:00Z' },
          },
        },
      },
    },
  });
  assert.equal(rows[0].group, 'updates');
  assert.ok(rows[0].evidence.includes('Najnowsza stabilna wg wydawcy: v0.3.1'));
});

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
  assert.deepEqual(
    getDetectorTests({
      'sensor.safety_detector_tests': {
        state: 'attention',
        attributes: { tests: [{ detector_key: 'UtilityLeak', friendly_name: 'Leak', hazard: 'water_leak', status: 'due' }] },
      },
    })[0]?.hazard,
    'water_leak'
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

test('shows platform maintenance readings and unknown backup evidence', () => {
  const rows = getFunctionalSafetySources({
    'sensor.functional_safety_sources': {
      state: 'unknown',
      attributes: {
        disk: { status: 'low', free_mib: 512 },
        host_temperature: { status: 'normal', temperature_c: 45 },
        backup: { status: 'unknown', last_success_at: 'broken' },
      },
    },
  });
  assert.deepEqual(
    rows.map(row => row.status),
    ['low', 'normal', 'unknown']
  );
  assert.match(rows[0].detail, /512 MiB/);
  assert.match(rows[1].detail, /45 °C/);
  assert.match(rows[2].detail, /Brak wiarygodnej/);
  const corrupt = getFunctionalSafetySources({
    'sensor.functional_safety_sources': {
      state: 'observed',
      attributes: {
        disk: { status: 'normal', free_mib: '512' },
        host_temperature: { status: 'normal', temperature_c: Infinity },
        backup: { status: 'current', last_success_at: 'bad timestamp', age_hours: 1 },
      },
    },
  });
  assert.deepEqual(
    corrupt.map(row => row.status),
    ['unknown', 'unknown', 'unknown']
  );
});

test('periodic tests require valid operator evidence before showing current', () => {
  const record = {
    test_key: 'notification_delivery',
    status: 'current',
    source: 'operator_attestation',
    interval_days: 30,
    last_test_at: '2026-09-26T12:00:00Z',
    due_at: '2026-10-26T12:00:00Z',
    last_result: 'passed',
  };
  const parse = (value: unknown) =>
    getPeriodicTests({ 'sensor.safety_periodic_tests': { state: 'current', attributes: { tests: [value] } } });
  assert.equal(parse(record)[0].status, 'current');
  assert.equal(parse({ ...record, source: 'home_assistant_acceptance' })[0].status, 'unknown');
  assert.equal(parse({ ...record, last_test_at: 'bad date' })[0].status, 'unknown');
  assert.equal(parse({ ...record, last_result: 'failed' })[0].status, 'unknown');
  assert.equal(parse({ ...record, interval_days: -1 })[0].status, 'unknown');
  assert.deepEqual(parse({ ...record, test_key: 'detector_tamper' }), []);
  assert.deepEqual(getPeriodicTests({}), []);
  assert.deepEqual(getPeriodicTests({ 'sensor.safety_periodic_tests': { state: 'unavailable', attributes: { tests: [record] } } }), []);
});

test('attestation payload only records a result; never calls notification or restore services', () => {
  assert.deepEqual(periodicTestResultMessage('backup_restore', 'failed'), {
    type: 'fire_event',
    event_type: 'safety_periodic_test_result',
    event_data: { test_key: 'backup_restore', outcome: 'failed' },
  });
  assert.deepEqual(periodicTestResultMessage('notification_delivery', 'passed').event_data, {
    test_key: 'notification_delivery',
    outcome: 'passed',
  });
});
