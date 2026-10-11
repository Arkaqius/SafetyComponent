import assert from 'node:assert/strict';
import test from 'node:test';
import { configurationEntityOptions, matchingConfigurationEntities } from './configurationEntities.js';

const inventory = configurationEntityOptions({
  'sensor.office_temperature': { state: 'unavailable', attributes: { friendly_name: 'Temperatura biura' } },
  'binary_sensor.office_window': { state: 'off', attributes: { friendly_name: 'Okno biura' } },
  'sensor.without_name': { state: 'unknown', attributes: {} },
});

test('unavailable entities remain selectable and unnamed entities retain their stable ID', () => {
  assert.equal(inventory.find(option => option.id === 'sensor.office_temperature')?.unavailable, true);
  assert.equal(inventory.find(option => option.id === 'sensor.without_name')?.name, 'sensor.without_name');
});

test('entity search combines friendly names and IDs with field domain restrictions', () => {
  assert.deepEqual(
    matchingConfigurationEntities(inventory, 'BIURA', ['sensor']).map(option => option.id),
    ['sensor.office_temperature']
  );
  assert.deepEqual(
    matchingConfigurationEntities(inventory, 'biura office_temp').map(option => option.id),
    ['sensor.office_temperature']
  );
  assert.deepEqual(matchingConfigurationEntities(inventory, '', ['cover']), []);
});

test('an unrestricted monitor can select any domain without pretending a missing ID exists', () => {
  assert.equal(matchingConfigurationEntities(inventory, '').length, 3);
  assert.deepEqual(matchingConfigurationEntities(inventory, 'sensor.not_installed'), []);
});
