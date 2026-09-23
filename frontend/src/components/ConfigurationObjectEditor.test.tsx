import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import ConfigurationObjectEditor from './ConfigurationObjectEditor.js';
import { initialObject, registrySchemas, updateObjectField } from './configurationFieldSchemas.js';

test('renders registry values as fields rather than raw JSON', () => {
  const html = renderToStaticMarkup(
    <ConfigurationObjectEditor
      label='Pomieszczenia'
      description='Rejestr pomieszczeń'
      value={{ LivingRoom: { area_id: 'living_room', temperature_sensor: 'sensor.living_room_temperature' } }}
      schema={registrySchemas.rooms}
      onChange={() => undefined}
    />
  );

  assert.match(html, /LivingRoom/);
  assert.match(html, /<details[^>]*><summary>LivingRoom<\/summary>/);
  assert.match(html, /sensor\.living_room_temperature/);
  assert.match(html, /Dodaj obiekt/);
  assert.match(html, /Dodaj pole/);
  assert.doesNotMatch(html, /Nowe pole w/);
  assert.doesNotMatch(html, /<textarea/);
});

test('new objects include all required typed fields', () => {
  assert.deepEqual(initialObject(registrySchemas.openings), {
    area_id: '',
    entity_id: '',
    friendly_name: '',
    kind: 'window',
  });
  assert.deepEqual(initialObject(registrySchemas.detectors), {
    area_id: '',
    entity_id: '',
    friendly_name: '',
    hazard: 'smoke',
    profile: '',
  });
});

test('dependent fields follow the selected detector and actuation type', () => {
  const gas = updateObjectField({ hazard: 'smoke' }, 'hazard', 'flammable_gas');
  assert.equal(gas.gas_identity, '');
  assert.deepEqual(updateObjectField(gas, 'hazard', 'smoke'), { hazard: 'smoke' });

  const confirmed = updateObjectField({ execution_policy: 'manual' }, 'execution_policy', 'user_confirmed');
  assert.equal(confirmed.actuator_entity_id, '');
  assert.deepEqual(updateObjectField(confirmed, 'execution_policy', 'manual'), { execution_policy: 'manual' });
});
