import assert from 'node:assert/strict';
import test from 'node:test';
import { effectiveFunctionalSafetySettings, functionalSafetySettings } from './functionalSafetySettings.js';

test('null/omitted fields inherit and explicit zero is preserved', () => {
  assert.deepEqual(
    effectiveFunctionalSafetySettings(
      { cpu_high_percent: 90, cpu_recovery_percent: 70, backup_max_age_hours: 48 },
      { cpu_high_percent: null, cpu_recovery_percent: 0, backup_max_age_hours: 72 }
    ),
    { cpu_high_percent: 90, cpu_recovery_percent: 0, backup_max_age_hours: 72 }
  );
});

test('technical policy and malformed numbers cannot replace defaults', () => {
  assert.deepEqual(
    effectiveFunctionalSafetySettings(
      { memory_fault_level: 2, battery_low_percent: 15 },
      { memory_fault_level: 4, battery_low_percent: Infinity }
    ),
    { memory_fault_level: 2, battery_low_percent: 15 }
  );
  const keys = functionalSafetySettings.flatMap(([, fields]) => fields.map(([key]) => key));
  assert.equal(new Set(keys).size, 23);
  assert.ok(keys.every(key => !/fault_level|stale_after|state_file|evaluation_interval/.test(key)));
});
