import assert from 'node:assert/strict';
import test from 'node:test';
import { getExternalHazardMonitoring, type EntityMap } from './safety.js';

const now = new Date().toISOString();
const snapshot = (selection: string | null = null, kind = 'live', enabled = true): EntityMap => ({
  'sensor.external_source_selection': {
    state: 'ready',
    attributes: {
      schema_version: 1,
      runtime_id: 'boot-2',
      component_enabled: enabled,
      selections: {
        WeatherPointModel: { provider: null, data_kind: null, hazards: [] },
        OfficialWeatherWarnings: { provider: selection, data_kind: selection ? kind : null, hazards: selection ? ['wind'] : [] },
        OutdoorAirQuality: { provider: null, data_kind: null, hazards: [] },
      },
    },
  },
  'sensor.external_hazard_state': { state: 'clear', attributes: { runtime_id: 'boot-2', active_hazards: [], active_symptom_count: 0 } },
  'sensor.external_provider_old': {
    state: 'ok',
    attributes: { runtime_id: 'boot-1', provider: 'Old', capability: 'OfficialWeatherWarnings', observation_count: 0 },
  },
});

test('explicit applied null stays disabled despite retained healthy provider and clear aggregate', () => {
  const view = getExternalHazardMonitoring(snapshot());
  assert.equal(view.categories.find(item => item.capability === 'OfficialWeatherWarnings')?.selectionState, 'disabled');
  assert.equal(view.categories.find(item => item.capability === 'OfficialWeatherWarnings')?.currentCount, null);
  assert.equal(view.monitoringActive, false);
});
test('missing applied truth stays unknown; previous-generation health cannot create a healthy zero', () => {
  assert.ok(getExternalHazardMonitoring({}).categories.every(item => item.selectionState === 'unknown'));
  const view = getExternalHazardMonitoring(snapshot('Old'));
  assert.equal(view.categories.find(item => item.capability === 'OfficialWeatherWarnings')?.evidenceState, 'awaiting_evidence');
  assert.equal(view.officialWarnings.length, 0);
});
test('same-generation fresh complete healthy warning feed alone may show zero', () => {
  const entities = snapshot('Regional');
  entities['sensor.external_provider_regional'] = {
    state: 'ok',
    attributes: {
      runtime_id: 'boot-2',
      provider: 'Regional',
      capability: 'OfficialWeatherWarnings',
      hazards: ['wind'],
      data_kind: 'live',
      last_success_at: now,
      stale_after_seconds: 180,
      observation_count: 0,
      warnings: [],
    },
  };
  const category = getExternalHazardMonitoring(entities).categories.find(item => item.capability === 'OfficialWeatherWarnings');
  assert.equal(category?.evidenceState, 'healthy_empty');
  assert.equal(category?.currentCount, 0);
});
test('synthetic preview never enters real warning or exposure totals', () => {
  const entities = snapshot('GermanyDummyWarningsApiComponent', 'synthetic');
  entities['sensor.external_hazard_test_state'] = {
    state: 'ok',
    attributes: {
      schema_version: 1,
      runtime_id: 'boot-2',
      provider: 'GermanyDummyWarningsApiComponent',
      data_kind: 'synthetic',
      scenario: 'warning',
      health: 'ok',
      count: 1,
      observations: [{ id: 'test-wind', hazard_type: 'wind', provider_level: '1' }],
    },
  };
  const view = getExternalHazardMonitoring(entities);
  assert.equal(view.testPreview?.count, 1);
  assert.equal(view.officialWarnings.length, 0);
  assert.equal(view.activeHazards.length, 0);
  assert.equal(view.monitoringActive, false);
});
test('disabled component overrides selections without hiding retained real danger', () => {
  const entities = snapshot('Regional', 'live', false);
  entities['sensor.external_hazard_state'] = {
    state: 'warning',
    attributes: { runtime_id: 'boot-2', active_hazards: ['wind'], active_symptom_count: 1 },
  };
  const view = getExternalHazardMonitoring(entities);
  assert.equal(view.categories[1].selectionState, 'component_disabled');
  assert.deepEqual(view.activeHazards, ['wind']);
});

test('retained fault assertions remain visible with C-EXT off and no aggregate', () => {
  const entities = snapshot(null, 'live', false);
  delete entities['sensor.external_hazard_state'];
  entities['sensor.fault_externalweatherexposure'] = {
    state: 'UNEVALUABLE',
    attributes: {
      active: true,
      fault_id: 'ExternalWeatherExposure',
      retained_assertions: [
        {
          symptom_id: 'WindWindow',
          fault_id: 'ExternalWeatherExposure',
          opening: 'Window',
          hazard: 'wind',
          source: 'Regional',
          asserted_at: now,
          context: { opening_name: 'Okno biura' },
        },
      ],
    },
  };
  const view = getExternalHazardMonitoring(entities);
  assert.deepEqual(view.activeHazards, ['wind']);
  assert.deepEqual(view.affectedOpenings, ['Okno biura']);
  assert.equal(view.activeSymptomCount, 1);
  assert.equal(view.retainedDanger, true);
});

test('uncertain retained journal evidence cannot become an empty green view', () => {
  const entities = snapshot();
  entities['sensor.fault_externalweatherexposure'] = {
    state: 'UNEVALUABLE',
    attributes: { active: true, fault_id: 'ExternalWeatherExposure', retained_hazard_unknown: true },
  };
  const view = getExternalHazardMonitoring(entities);
  assert.equal(view.retainedDanger, true);
  assert.ok(view.activeHazards.length > 0);
  assert.notEqual(view.status, 'clear');
});

test('cleared retention markers do not create an additional retained danger', () => {
  const entities = snapshot('Regional');
  entities['sensor.external_provider_regional'] = {
    state: 'ok',
    attributes: {
      runtime_id: 'boot-2',
      provider: 'Regional',
      capability: 'OfficialWeatherWarnings',
      data_kind: 'live',
      last_success_at: now,
      stale_after_seconds: 180,
      observation_count: 0,
      warnings: [],
    },
  };
  entities['sensor.fault_externalweatherexposure'] = {
    state: 'D',
    attributes: { active: true, fault_id: 'ExternalWeatherExposure', retained_assertions: [] },
  };
  const view = getExternalHazardMonitoring(entities);
  assert.equal(view.retainedDanger, false);
  assert.deepEqual(view.activeHazards, []);
});

test('aged raw ok health is presented as stale in the category diagnostic', () => {
  const entities = snapshot('Regional');
  entities['sensor.external_provider_regional'] = {
    state: 'ok',
    attributes: {
      runtime_id: 'boot-2',
      provider: 'Regional',
      capability: 'OfficialWeatherWarnings',
      data_kind: 'live',
      last_success_at: '2000-01-01T00:00:00Z',
      stale_after_seconds: 180,
      observation_count: 0,
      warnings: [],
    },
  };
  const category = getExternalHazardMonitoring(entities).categories[1];
  assert.equal(category.evidenceState, 'stale');
  assert.equal(category.diagnostic?.status, 'stale');
  assert.equal(category.currentCount, null);
});

test('malformed warning payload cannot prove a fresh healthy zero', () => {
  for (const warnings of [undefined, {}, [null], [{ id: 'invalid' }]]) {
    const entities = snapshot('Regional');
    entities['sensor.external_provider_regional'] = {
      state: 'ok',
      attributes: {
        runtime_id: 'boot-2',
        provider: 'Regional',
        capability: 'OfficialWeatherWarnings',
        data_kind: 'live',
        last_success_at: now,
        stale_after_seconds: 180,
        observation_count: 0,
        warnings,
      },
    };
    const category = getExternalHazardMonitoring(entities).categories[1];
    assert.equal(category.evidenceState, 'awaiting_evidence');
    assert.equal(category.currentCount, null);
  }
});
