import assert from 'node:assert/strict';
import test from 'node:test';
import { buildDeviceInventory, buildEntityInventory, getEntityMonitorSummary, getMonitoredEntities } from './entityHealth.js';
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

test('joins Home Assistant entity, device, area, and monitoring records', () => {
  const states: EntityMap = {
    'sensor.office_temperature': {
      state: '21.5',
      attributes: { friendly_name: 'Temperatura biura' },
      last_updated: '2026-08-13T10:00:00Z',
    },
  };
  const monitored = getMonitoredEntities({
    'sensor.entity_health_temperature_office': {
      state: 'healthy',
      attributes: {
        entity_id: 'sensor.office_temperature',
        entity_key: 'TemperatureOffice',
        friendly_name: 'Temperatura biura',
        current_state: '21.5',
        source_groups: ['component'],
        owners: ['TemperatureComponent'],
        purposes: ['Temperature input'],
        fault_owner: 'entity_monitor',
        checks: [],
      },
    },
  });
  const inventory = buildEntityInventory(
    states,
    [
      {
        entity_id: 'sensor.office_temperature',
        name: null,
        device_id: 'device-1',
        area_id: null,
        disabled_by: null,
        hidden_by: null,
      },
    ],
    [
      {
        id: 'device-1',
        name: 'Czujnik biuro',
        name_by_user: null,
        manufacturer: 'Acme',
        model: 'T1',
        area_id: 'office',
        disabled_by: null,
      },
    ],
    [{ area_id: 'office', name: 'Biuro' }],
    monitored
  );
  assert.equal(inventory[0]?.areaName, 'Biuro');
  assert.equal(inventory[0]?.deviceName, 'Czujnik biuro');
  assert.equal(inventory[0]?.monitored?.health, 'healthy');
  const devices = buildDeviceInventory(
    inventory,
    [
      {
        id: 'device-1',
        name: 'Czujnik biuro',
        name_by_user: null,
        manufacturer: 'Acme',
        model: 'T1',
        area_id: 'office',
        disabled_by: null,
      },
    ],
    [{ area_id: 'office', name: 'Biuro' }]
  );
  assert.equal(devices[0]?.entities.length, 1);
  assert.equal(devices[0]?.unavailableCount, 0);
});
