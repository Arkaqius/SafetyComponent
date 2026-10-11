import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import ConfigurationObjectEditor from './ConfigurationObjectEditor.js';
import { initialObject, normalizeMonitorConfiguration, registrySchemas, updateObjectField } from './configurationFieldSchemas.js';

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
  assert.match(html, /role="combobox"/);
  assert.match(html, /aria-label="Czujnik temperatury"/);
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
  assert.deepEqual(initialObject(registrySchemas.remote_batteries), {
    friendly_name: '',
    percentage_entity: '',
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

test('legacy report age migrates into two visible monitor timers without losing allocations', () => {
  const legacy = {
    installation: {
      monitored_entities: {
        Office: {
          entity_id: 'sensor.office_temperature',
          description: 'Office',
          failure_debounce_seconds: 60,
          recovery_debounce_seconds: 60,
          detection_budget_seconds: 4020,
          checks: { freshness: { timestamp_source: 'last_reported', max_silence_seconds: 3600 } },
        },
      },
      component_settings: {
        entity_monitor: {
          component_overrides: {
            TemperatureKitchen: { checks: { freshness: { timestamp_source: 'last_updated', max_silence_seconds: 14400 } } },
          },
        },
      },
    },
  };
  const normalized = normalizeMonitorConfiguration(legacy) as typeof legacy;
  const entry = normalized.installation.monitored_entities.Office;
  assert.equal((entry as Record<string, unknown>).report_timeout_seconds, 3600);
  assert.equal(entry.detection_budget_seconds, 4020);
  assert.equal(entry.recovery_debounce_seconds, 60);
  assert.equal(entry.checks.freshness.timestamp_source, 'last_reported');
  assert.equal(entry.checks.freshness.max_silence_seconds, undefined);
  assert.equal(legacy.installation.monitored_entities.Office.checks.freshness.max_silence_seconds, 3600);
  const html = renderToStaticMarkup(
    <ConfigurationObjectEditor
      label='Monitor'
      description='Monitor'
      value={{ Office: entry }}
      schema={registrySchemas.monitored_entities}
      onChange={() => undefined}
    />
  );
  assert.match(html, /Maksymalny wiek raportu/);
  assert.match(html, /Czas potwierdzenia awarii/);
  assert.doesNotMatch(html, /Nieobsługiwane pole|Budżet wykrycia|Potwierdzenie powrotu|Maksymalny wiek raportu \(stare ustawienie\)/);
});
