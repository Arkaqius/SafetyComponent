import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  decodeProviderCatalogue,
  decodeProviderFieldErrors,
  providerRows,
  readProviderParameters,
  reconcileProviderParameter,
  setProviderIntent,
  setProviderParameter,
  validateProviderDraft,
} from './providerConfiguration.js';

const imgw = {
  enabled: true,
  countries: ['PL'],
  capability: 'OfficialWeatherWarnings',
  hazards: ['frost', 'wind', 'rain', 'storm'],
  display_name: 'Ostrzeżenia IMGW',
  description: 'Ostrzeżenia urzędowe',
  parameter_schema: {
    type: 'object',
    additionalProperties: false,
    properties: {
      teryt_codes: {
        type: 'array',
        title: 'Kody powiatów',
        description: 'Czterocyfrowe kody powiatów.',
        items: { type: 'string', pattern: '^[0-9]{4}$' },
        minItems: 1,
        maxItems: 10000,
        uniqueItems: true,
      },
    },
  },
  required_when_enabled: ['teryt_codes'],
  parameter_defaults: {},
  legacy_parameter_paths: { teryt_codes: ['installation', 'site', 'teryt_codes'] },
};

const regional = {
  enabled: false,
  countries: ['DE'],
  capability: 'OfficialWeatherWarnings',
  hazards: ['wind'],
  display_name: 'Regionalne ostrzeżenia testowe',
  description: 'Kontrolowane źródło regionalne',
  parameter_schema: {
    type: 'object',
    additionalProperties: false,
    properties: { region_code: { type: 'string', title: 'Region', minLength: 2, maxLength: 16 } },
  },
  required_when_enabled: ['region_code'],
  parameter_defaults: {},
  legacy_parameter_paths: {},
};

function catalogue(extra: Record<string, unknown> = {}) {
  return decodeProviderCatalogue({
    provider_metadata_version: 1,
    provider_plugins: { ImgwWarningsApiComponent: imgw, RegionalWarningsApiComponent: regional, ...extra },
  });
}

test('decodes registered provider fields and keeps unknown metadata ineligible', () => {
  const decoded = catalogue({ Unknown: { enabled: true } });
  assert.equal(decoded.providers.RegionalWarningsApiComponent.hazards[0], 'wind');
  assert.equal(decoded.providers.ImgwWarningsApiComponent.fields.teryt_codes.kind, 'string_array');
  assert.ok(decoded.errors.Unknown);
  assert.equal(decoded.providers.Unknown, undefined);
  const rows = providerRows(decoded, { providers: { Unknown: { enabled: true } } }, 'PL');
  assert.equal(rows.find(row => row.id === 'Unknown')?.effectiveEnabled, false);
  assert.ok(rows.find(row => row.id === 'Unknown')?.error);
});

test('displaying inherited defaults does not create an explicit override', () => {
  const draft = { installation: { site: { country_code: 'PL' } } };
  const before = structuredClone(draft);
  const row = providerRows(catalogue(), draft, 'PL').find(item => item.id === 'ImgwWarningsApiComponent');
  assert.equal(row?.intent, 'inherit');
  assert.equal(row?.effectiveEnabled, true);
  assert.deepEqual(draft, before);
  const disabled = setProviderIntent(draft, 'ImgwWarningsApiComponent', 'disabled');
  assert.deepEqual(disabled.providers, { ImgwWarningsApiComponent: { enabled: false } });
  const inherited = setProviderIntent(disabled, 'ImgwWarningsApiComponent', 'inherit');
  assert.equal(Object.prototype.hasOwnProperty.call((inherited.providers as Record<string, object>)?.ImgwWarningsApiComponent ?? {}, 'enabled'), false);
});

test('country changes keep explicit incompatible selections visible with their values', () => {
  const draft = { providers: { RegionalWarningsApiComponent: { enabled: true, parameters: { region_code: 'BE' } } } };
  const row = providerRows(catalogue(), draft, 'PL').find(item => item.id === 'RegionalWarningsApiComponent');
  assert.equal(row?.applicable, false);
  assert.equal(row?.effectiveEnabled, false);
  assert.ok(row?.error);
  assert.deepEqual(draft.providers.RegionalWarningsApiComponent.parameters, { region_code: 'BE' });
});

test('legacy-only parameters project without mutation and explicit edits retain their source path', () => {
  const draft = { installation: { site: { teryt_codes: ['0000'] } } };
  const plugin = catalogue().providers.ImgwWarningsApiComponent;
  const original = structuredClone(draft);
  assert.deepEqual(readProviderParameters(draft, plugin).values, { teryt_codes: ['0000'] });
  assert.deepEqual(draft, original);
  const changed = setProviderParameter(draft, plugin, 'teryt_codes', ['0001']);
  assert.deepEqual(changed.installation, { site: { teryt_codes: ['0001'] } });
  assert.equal(changed.providers, undefined);
});

test('new canonical inputs and equal aliases update atomically while conflicts require reconciliation', () => {
  const plugin = catalogue().providers.ImgwWarningsApiComponent;
  const canonical = setProviderParameter({}, plugin, 'teryt_codes', ['0001']);
  assert.deepEqual(canonical.providers, { ImgwWarningsApiComponent: { parameters: { teryt_codes: ['0001'] } } });
  const equal = { ...canonical, installation: { site: { teryt_codes: ['0001'] } } };
  const changed = setProviderParameter(equal, plugin, 'teryt_codes', ['0002']);
  assert.deepEqual((changed.installation as { site: object }).site, { teryt_codes: ['0002'] });
  assert.deepEqual((changed.providers as Record<string, { parameters: object }>).ImgwWarningsApiComponent.parameters, { teryt_codes: ['0002'] });
  const conflicting = { ...canonical, installation: { site: { teryt_codes: ['0002'] } } };
  assert.ok(readProviderParameters(conflicting, plugin).conflicts.teryt_codes);
  assert.throws(() => setProviderParameter(conflicting, plugin, 'teryt_codes', ['0003']), /uzgodnij/i);
  const reconciled = reconcileProviderParameter(conflicting, plugin, 'teryt_codes', 'canonical');
  assert.deepEqual((reconciled.installation as { site: object }).site, { teryt_codes: ['0001'] });
});

test('required activation parameters are conditional but supplied malformed values always fail', () => {
  const disabled = { providers: { RegionalWarningsApiComponent: { enabled: false } } };
  assert.deepEqual(validateProviderDraft(catalogue(), disabled, 'DE'), []);
  const enabled = { providers: { RegionalWarningsApiComponent: { enabled: true } } };
  assert.ok(validateProviderDraft(catalogue(), enabled, 'DE').some(error => error.path.at(-1) === 'region_code'));
  const malformed = { providers: { RegionalWarningsApiComponent: { enabled: false, parameters: { region_code: 42 } } } };
  assert.ok(validateProviderDraft(catalogue(), malformed, 'DE').length);
});

test('field error decoding is bounded and preserves source paths', () => {
  const item = { path: ['user_config', 'providers', 'RegionalWarningsApiComponent', 'parameters', 'region_code'], code: 'required', message: 'Podaj region.' };
  assert.deepEqual(decodeProviderFieldErrors([item]), [item]);
  assert.equal(decodeProviderFieldErrors(Array.from({ length: 33 }, () => item)).length, 32);
  assert.deepEqual(decodeProviderFieldErrors([{ ...item, path: Array(17).fill('x') }]), []);
  assert.deepEqual(decodeProviderFieldErrors([{ ...item, message: 'x'.repeat(513) }]), []);
});

test('rejects unsupported versions, cyclic/external references, malformed applicability and unsafe alias paths', () => {
  assert.ok(Object.keys(decodeProviderCatalogue({ provider_metadata_version: 2, provider_plugins: {} }).errors).length);
  for (const schema of [{ $ref: 'https://example.invalid/schema' }, { type: 'object', additionalProperties: false, properties: { x: { $ref: '#/$defs/Loop' } }, $defs: { Loop: { $ref: '#/$defs/Loop' } } }]) {
    assert.ok(catalogue({ Bad: { ...regional, parameter_schema: schema } }).errors.Bad);
  }
  assert.ok(catalogue({ Bad: { ...regional, countries: undefined } }).errors.Bad);
  assert.ok(catalogue({ Bad: { ...regional, legacy_parameter_paths: { region_code: ['runtime_cfg', 'providers'] } } }).errors.Bad);
});

test('enforces metadata text/property/definition/depth/enum budgets', () => {
  const cases = [
    { display_name: 'x'.repeat(257) },
    { description: 'x'.repeat(2049) },
    { parameter_schema: { type: 'object', additionalProperties: false, properties: Object.fromEntries(Array.from({ length: 65 }, (_, i) => [`p${i}`, { type: 'string' }])) } },
    { parameter_schema: { type: 'object', additionalProperties: false, properties: { region_code: { type: 'string', enum: Array.from({ length: 1025 }, (_, i) => String(i)) } } } },
    { parameter_schema: { type: 'object', additionalProperties: false, properties: { region_code: { type: 'string', pattern: 'x'.repeat(257) } } } },
  ];
  for (const value of cases) assert.ok(catalogue({ Bad: { ...regional, ...value } }).errors.Bad);
});

test('supports finite scalar constraints, nullable optional fields and controlled local schema references', () => {
  const decoded = catalogue({
    Scalars: {
      ...regional,
      required_when_enabled: [],
      parameter_schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          count: { type: 'integer', minimum: 1, maximum: 5 },
          value: { type: 'number', exclusiveMinimum: 0, exclusiveMaximum: 10 },
          label: { anyOf: [{ type: 'string', minLength: 2 }, { type: 'null' }] },
          enabled_option: { type: 'boolean' },
          region_code: { $ref: '#/$defs/Region' },
        },
        $defs: { Region: { type: 'string', enum: ['BE', 'BB'] } },
      },
    },
  });
  assert.equal(decoded.errors.Scalars, undefined);
  const draft = { providers: { Scalars: { enabled: true, parameters: { count: 3, value: 1.5, label: null, enabled_option: false, region_code: 'BE' } } } };
  assert.deepEqual(validateProviderDraft(decoded, draft, 'DE'), []);
  for (const [field, value] of [['count', 1.5], ['count', 6], ['value', Number.NaN], ['value', 0], ['value', 10], ['label', 'a'], ['enabled_option', 'false'], ['region_code', 'XX']]) {
    const changed = structuredClone(draft);
    (changed.providers.Scalars.parameters as Record<string, unknown>)[field as string] = value;
    assert.ok(validateProviderDraft(decoded, changed, 'DE').length, String(field));
  }
});

test('applies requiredness only to an applicable enabled component and retains malformed disabled errors', () => {
  const selected = { components_enabled: { ExternalHazardComponent: false }, providers: { RegionalWarningsApiComponent: { enabled: true } } };
  assert.deepEqual(validateProviderDraft(catalogue(), selected, 'DE'), []);
  const invalid = { ...selected, providers: { RegionalWarningsApiComponent: { enabled: false, parameters: { unknown_parameter: 'x' } } } };
  assert.ok(validateProviderDraft(catalogue(), invalid, 'DE').some(error => error.path.at(-1) === 'unknown_parameter'));
});

test('accepts the provider-count boundary and rejects excess providers without guessing applicability', () => {
  const definitions = Object.fromEntries(Array.from({ length: 64 }, (_, index) => [`Provider${index}`, regional]));
  const accepted = decodeProviderCatalogue({ provider_metadata_version: 1, provider_plugins: definitions });
  assert.equal(Object.keys(accepted.providers).length, 64);
  const rejected = decodeProviderCatalogue({ provider_metadata_version: 1, provider_plugins: { ...definitions, Extra: regional } });
  assert.equal(Object.keys(rejected.providers).length, 0);
  assert.ok(Object.keys(rejected.errors).length);
});

test('rejects unsafe schema shapes, derived unknown fields and source-path traversal', () => {
  for (const schema of [
    { type: 'object', properties: {}, additionalProperties: true },
    { type: 'object', additionalProperties: false, properties: { region_code: { type: 'object', properties: {} } } },
    { type: 'object', additionalProperties: false, properties: { region_code: { type: 'string', enum: [1] } } },
    { type: 'object', additionalProperties: false, properties: { region_code: { type: 'string', pattern: '(a+)+' } } },
  ]) assert.ok(catalogue({ Bad: { ...regional, parameter_schema: schema } }).errors.Bad);
  for (const path of [['installation', '__proto__', 'polluted'], ['installation', 'constructor', 'prototype'], ['runtime_cfg', 'providers'], Array.from({ length: 17 }, () => 'installation')]) {
    assert.ok(catalogue({ Bad: { ...regional, legacy_parameter_paths: { region_code: path } } }).errors.Bad);
  }
  const draft = { providers: { RegionalWarningsApiComponent: { enabled: true, parameters: { region_code: 'BE', unknown: 'value' } } } };
  assert.ok(validateProviderDraft(catalogue(), draft, 'DE').some(error => error.path.at(-1) === 'unknown'));
});

test('decodes the same sanitized catalogue fixture exported by the backend', () => {
  const fixture = JSON.parse(readFileSync(resolve('..', 'backend/tests/fixtures/external_apis/provider_contract.json'), 'utf8'));
  const decoded = decodeProviderCatalogue(fixture);
  assert.deepEqual(decoded.errors, {});
  assert.equal(Object.keys(decoded.providers).length, 5);
  assert.deepEqual(decoded.providers.RegionalWarningsApiComponent.hazards, ['wind']);
  assert.deepEqual(decoded.providers.ImgwWarningsApiComponent.legacyPaths.teryt_codes, ['installation', 'site', 'teryt_codes']);
  const draft = { providers: { RegionalWarningsApiComponent: { enabled: true, parameters: { region_code: 'BE' } }, PeerRegionalWarningsApiComponent: { enabled: true, parameters: { region_code: 'BE' } } } };
  assert.deepEqual(validateProviderDraft(decoded, draft, 'DE'), []);
});
