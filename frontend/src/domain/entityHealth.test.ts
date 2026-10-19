import assert from 'node:assert/strict';
import test from 'node:test';
import { formatEntityCheckObservation, getEntityMonitorSummary, getMonitoredEntities } from './entityHealth.js';
import type { EntityMap } from './safety.js';

test('normalizes monitored diagnostics and summary', () => {
  const entities: EntityMap = {
    'sensor.entity_health_temperature_office': {
      state: 'stale',
      attributes: {
        source_entity_id: 'sensor.office_temperature',
        entity_key: 'TemperatureOffice',
        friendly_name: 'Temperatura biura',
        current_state: '21.5',
        source_groups: ['component'],
        owners: ['TemperatureComponent'],
        purposes: ['Temperature input'],
        fault_owner: 'entity_monitor',
        failure_debounce_seconds: 15,
        recovery_debounce_seconds: 60,
        checks: [{ check: 'freshness', result: 'failed', reason: 'freshness_expired' }],
      },
    },
    'sensor.entity_monitor_summary': {
      state: 'stale',
      attributes: { total: 1, healthy: 0, degraded: 0, stale: 1, unavailable: 0 },
    },
  };

  const monitored = getMonitoredEntities(entities);
  assert.equal(monitored[0]?.entityId, 'sensor.office_temperature');
  assert.equal(monitored[0]?.checks[0]?.reason, 'freshness_expired');
  assert.deepEqual(getEntityMonitorSummary(entities, monitored), {
    health: 'stale',
    total: 1,
    healthy: 0,
    degraded: 0,
    stale: 1,
    unavailable: 0,
  });
});

test('accepts the legacy entity_id attribute as a fallback', () => {
  const monitored = getMonitoredEntities({
    'sensor.entity_health_temperature_office': {
      state: 'healthy',
      attributes: {
        entity_id: 'sensor.office_temperature',
        entity_key: 'TemperatureOffice',
        source_groups: ['component'],
        owners: ['TemperatureComponent'],
        purposes: ['Temperature input'],
        fault_owner: 'entity_monitor',
        checks: [],
      },
    },
  });

  assert.equal(monitored[0]?.entityId, 'sensor.office_temperature');
});

test('formats freshness age as elapsed time instead of a sensor reading', () => {
  assert.equal(formatEntityCheckObservation('freshness', 7222.761), 'czas od ostatniej aktualizacji: 2 godz. 0 min 23 s');
  assert.equal(formatEntityCheckObservation('numeric_range', 23.5), 'odczyt: 23.5');
});

test('unrelated HA entities do not become monitored even when unavailable', () => {
  const entities: EntityMap = {
    'sensor.unrelated': { state: 'unavailable', attributes: { friendly_name: 'Unrelated' } },
  };
  assert.deepEqual(getMonitoredEntities(entities), []);
  assert.equal(getEntityMonitorSummary(entities).total, 0);
});
