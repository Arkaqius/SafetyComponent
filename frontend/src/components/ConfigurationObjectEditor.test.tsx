import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import ConfigurationObjectEditor from './ConfigurationObjectEditor.js';

test('renders registry values as fields rather than raw JSON', () => {
  const html = renderToStaticMarkup(
    <ConfigurationObjectEditor
      label='Pomieszczenia'
      description='Rejestr pomieszczeń'
      value={{ LivingRoom: { area_id: 'living_room', temperature_sensor: 'sensor.living_room_temperature' } }}
      newEntry={{ area_id: '', temperature_sensor: '' }}
      onChange={() => undefined}
    />
  );

  assert.match(html, /LivingRoom/);
  assert.match(html, /sensor\.living_room_temperature/);
  assert.match(html, /Dodaj obiekt/);
  assert.match(html, /Dodaj pole/);
  assert.doesNotMatch(html, /<textarea/);
});

test('renders localization overrides as editable names', () => {
  const html = renderToStaticMarkup(
    <ConfigurationObjectEditor
      label='Nadpisania nazw encji'
      description='Nazwy'
      value={{ 'sensor.example': 'Czujnik' }}
      newEntry=''
      onChange={() => undefined}
    />
  );

  assert.match(html, /sensor\.example/);
  assert.match(html, /Czujnik/);
  assert.match(html, /Dodaj nazwę/);
});
