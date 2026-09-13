import assert from 'node:assert/strict';
import test from 'node:test';
import { getInternalEnvironmentMonitoring } from './internalHazards.js';
import { type EntityMap } from './safety.js';

test('keeps detector alarm and technical health as separate states', () => {
  const entities: EntityMap = {
    'sensor.internal_environment_summary': entity('active_hazard', {
      monitored_detectors: 2,
      active_hazards: 1,
      unavailable_detectors: 0,
      gas_switching_inhibited: true,
    }),
    'sensor.internal_environment_bathroom_flammable_gas': entity('healthy', {
      friendly_name: 'Czujnik gazu w łazience',
      area_name: 'Łazienka',
      source_entity_id: 'binary_sensor.bathroom_gasleak_detector_gas',
      hazard: 'flammable_gas',
      gas_identity: 'flammable_gas_unspecified',
      current_state: 'on',
      classification: 'alarm',
      alarm_active: true,
      health_fault_active: false,
      gas_switching_inhibited: true,
    }),
    'sensor.internal_environment_bathroom_carbon_monoxide': entity('healthy', {
      friendly_name: 'Czujnik tlenku węgla w łazience',
      area_name: 'Łazienka',
      source_entity_id: 'binary_sensor.bathroom_carbonoxide_detector_carbon_monoxide',
      hazard: 'carbon_monoxide',
      current_state: 'off',
      classification: 'clear',
      alarm_active: false,
      health_fault_active: false,
    }),
    'sensor.entity_health_internal_environment_bathroom_carbon_monoxide': entity('healthy', {
      source_entity_id: 'binary_sensor.bathroom_carbonoxide_detector_carbon_monoxide',
    }),
  };

  const view = getInternalEnvironmentMonitoring(entities);

  assert.equal(view.status, 'active_hazard');
  assert.equal(view.activeHazards, 1);
  assert.equal(view.gasSwitchingInhibited, true);
  assert.equal(view.detectors[0]?.status, 'alarm');
  assert.equal(view.detectors[0]?.healthFaultActive, false);
  assert.equal(view.detectors[1]?.status, 'healthy');
  assert.equal(view.detectors[1]?.healthEntityId, 'sensor.entity_health_internal_environment_bathroom_carbon_monoxide');
});

test('falls back to detector diagnostics when the summary is absent', () => {
  const entities: EntityMap = {
    'sensor.internal_environment_bathroom_carbon_monoxide': entity('unavailable', {
      friendly_name: 'Czujnik tlenku węgla',
      hazard: 'carbon_monoxide',
      classification: 'unavailable',
      alarm_active: false,
      health_fault_active: true,
    }),
  };

  const view = getInternalEnvironmentMonitoring(entities);

  assert.equal(view.status, 'unavailable');
  assert.equal(view.monitoredDetectors, 1);
  assert.equal(view.unavailableDetectors, 1);
  assert.equal(view.detectors[0]?.status, 'unavailable');
});

function entity(state: string, attributes: Record<string, unknown>) {
  return {
    state,
    attributes,
    last_changed: '2026-09-13T00:00:00Z',
    last_updated: '2026-09-13T00:00:00Z',
  };
}
