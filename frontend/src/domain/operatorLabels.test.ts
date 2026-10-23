import assert from 'node:assert/strict';
import test from 'node:test';
import {
  componentLabel,
  coverageCauseLabel,
  coverageSubjectName,
  evidenceSourceLabel,
  operatorCodeLabel,
  operatorExplanation,
} from './operatorLabels.js';
import { friendlyEntityName, getFaults, localizedEntityState, type EntityMap } from './safety.js';
import { formatEntityCheckObservation, getMonitoredEntities } from './entityHealth.js';

test('HA names are preserved while missing names and unknown contracts stay explicitly unnamed', () => {
  assert.equal(friendlyEntityName('sensor.office', { state: '20', attributes: { friendly_name: 'Office' } }), 'Office');
  assert.equal(friendlyEntityName('sensor.fault_private_identifier'), 'Usterka bez nazwy');
  assert.equal(friendlyEntityName('sensor.some_private_id'), 'Encja bez nazwy');
  assert.equal(
    friendlyEntityName('sensor.fault_battery', { state: 'FAIL', attributes: { friendly_name: 'Fault: Niska bateria: Czujnik biura' } }),
    'Niska bateria: Czujnik biura'
  );
  assert.equal(getFaults({ 'sensor.fault_private_identifier': { state: 'FAIL', attributes: { active: true } } })[0].active, true);
});

test('operator states are localized without changing signed numbers or inventing positive health', () => {
  assert.equal(localizedEntityState('sensor.temperature', '-5.25'), '-5.25');
  assert.equal(localizedEntityState('sensor.source', 'unavailable'), 'Niedostępna');
  assert.equal(localizedEntityState('sensor.source', 'unrecognized_raw_state'), 'Nieznany stan — sprawdź diagnostykę');
  assert.equal(formatEntityCheckObservation('availability', 'unavailable'), 'odczyt: Niedostępna');
  assert.equal(formatEntityCheckObservation('freshness', 'unknown'), 'brak wiarygodnego czasu ostatniej aktualizacji');
});

test('monitoring uses current HA source names and preserves raw diagnostic identities', () => {
  const entities: EntityMap = {
    'sensor.entity_health_window': {
      state: 'unavailable',
      attributes: {
        entity_id: 'binary_sensor.window',
        entity_key: 'ExternalOpeningBedroomRightWindow',
        friendly_name: 'Stara nazwa',
        current_state: 'unavailable',
      },
    },
    'binary_sensor.window': { state: 'unavailable', attributes: { friendly_name: 'Okno sypialni — prawe' } },
  };
  const item = getMonitoredEntities(entities)[0];
  assert.equal(item.friendlyName, 'Okno sypialni — prawe');
  assert.equal(item.entityKey, 'ExternalOpeningBedroomRightWindow');
  const cause = 'EntityHealthFailureExternalOpeningBedroomRightWindowAvailability';
  assert.equal(coverageCauseLabel(cause, entities), 'Problem z odczytem: Okno sypialni — prawe');
  assert.equal(coverageSubjectName(cause, 'BedroomRightWindow', entities), 'Okno sypialni — prawe');
});

test('system component and evidence codes have Polish labels with honest fallbacks', () => {
  assert.equal(componentLabel('EntityMonitorComponent'), 'Monitoring wejść');
  assert.equal(componentLabel('NewComponent'), 'Inny komponent systemu');
  assert.equal(operatorCodeLabel('external_exposure'), 'Narażenie przez otwarte okna i drzwi');
  assert.equal(operatorExplanation('owner_unverified'), 'Oczekiwanie na aktualną ocenę funkcji bezpieczeństwa');
  assert.equal(evidenceSourceLabel('sensor.private_id'), 'Odczyt urządzenia');
  assert.equal(operatorExplanation('Nowy opis z backendu.'), 'Nowy opis z backendu.');
});
