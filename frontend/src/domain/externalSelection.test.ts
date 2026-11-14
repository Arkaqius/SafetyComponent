import assert from 'node:assert/strict';
import test from 'node:test';
import {
  categoryRows,
  decodeProviderCatalogue,
  readProviderParameters,
  setCategoryProvider,
  setProviderParameter,
  validateProviderDraft,
} from './providerConfiguration.js';

const metadata = {
  provider_metadata_version: 2,
  provider_plugins: {
    GermanyDummyWarningsApiComponent: {
      countries: ['DE'],
      capability: 'OfficialWeatherWarnings',
      hazards: ['wind'],
      display_name: 'Niemcy — źródło testowe',
      description: 'Dane syntetyczne.',
      data_kind: 'synthetic',
      transport_kind: 'none',
      parameter_schema: {
        type: 'object',
        additionalProperties: false,
        properties: { region_code: { type: 'string', minLength: 1, maxLength: 32 } },
      },
      required_when_selected: ['region_code'],
      parameter_defaults: {},
    },
  },
};
const draft = {
  external_sources: { WeatherPointModel: null, OfficialWeatherWarnings: null, OutdoorAirQuality: null },
  provider_parameters: {},
};

test('target catalogue accepts trusted synthetic declarations and rejects v1', () => {
  const catalogue = decodeProviderCatalogue(metadata);
  assert.equal(catalogue.providers.GermanyDummyWarningsApiComponent.dataKind, 'synthetic');
  assert.ok(decodeProviderCatalogue({ ...metadata, provider_metadata_version: 1 }).error);
});
test('three category choices have explicit null and no inherited controls', () => {
  const rows = categoryRows(decodeProviderCatalogue(metadata), draft, 'DE');
  assert.equal(rows.length, 3);
  assert.ok(rows.every(row => row.selected === null));
  assert.equal(rows.find(row => row.capability === 'OfficialWeatherWarnings')?.options.length, 1);
});
test('selection and canonical parameter edits preserve inactive drafts immutably', () => {
  const catalogue = decodeProviderCatalogue(metadata);
  const plugin = catalogue.providers.GermanyDummyWarningsApiComponent;
  const selected = setCategoryProvider(draft, 'OfficialWeatherWarnings', plugin.id);
  const filled = setProviderParameter(selected, plugin, 'region_code', 'BE');
  const disabled = setCategoryProvider(filled, 'OfficialWeatherWarnings', null);
  assert.equal(readProviderParameters(disabled, plugin).region_code, 'BE');
  assert.equal(draft.external_sources.OfficialWeatherWarnings, null);
  assert.deepEqual(draft.provider_parameters, {});
  assert.deepEqual(validateProviderDraft(catalogue, disabled, 'DE'), []);
});
test('required fields apply only to selected active source; malformed values always fail', () => {
  const catalogue = decodeProviderCatalogue(metadata);
  const plugin = catalogue.providers.GermanyDummyWarningsApiComponent;
  const selected = setCategoryProvider(draft, 'OfficialWeatherWarnings', plugin.id);
  assert.ok(validateProviderDraft(catalogue, selected, 'DE').some(error => error.code === 'required_when_selected'));
  const invalid = { ...draft, provider_parameters: { [plugin.id]: { region_code: 1 } } };
  assert.ok(validateProviderDraft(catalogue, invalid, 'DE').length);
});
test('obsolete source and site aliases are rejected instead of reconciled', () => {
  const catalogue = decodeProviderCatalogue(metadata);
  assert.ok(validateProviderDraft(catalogue, { ...draft, providers: {} }, 'DE').length);
  assert.ok(validateProviderDraft(catalogue, { ...draft, installation: { site: { teryt_codes: ['0000'] } } }, 'DE').length);
  assert.ok(validateProviderDraft(catalogue, { ...draft, external_sources: {} }, 'DE').length);
});
