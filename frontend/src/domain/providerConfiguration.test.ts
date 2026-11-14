import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  decodeProviderCatalogue,
  decodeProviderFieldErrors,
  providerFieldErrors,
  categoryRows,
  validateProviderDraft,
} from './providerConfiguration.js';

const regional = {
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
    properties: { region_code: { type: 'string', title: 'Region', minLength: 2, maxLength: 16 } },
  },
  required_when_selected: ['region_code'],
  parameter_defaults: {},
};
function catalogue(extra: Record<string, unknown> = {}) {
  return decodeProviderCatalogue({ provider_metadata_version: 2, provider_plugins: { RegionalWarningsApiComponent: regional, ...extra } });
}

test('rejects metadata version 1, malformed trusted kinds, country applicability and unsafe IDs', () => {
  assert.ok(decodeProviderCatalogue({ provider_metadata_version: 1, provider_plugins: {} }).error);
  for (const change of [{ data_kind: 'fake' }, { transport_kind: 'socket' }, { countries: ['de'] }, { hazards: [] }]) {
    assert.ok(catalogue({ Bad: { ...regional, ...change } }).errors.Bad);
  }
  for (const id of ['__proto__', 'constructor', 'prototype']) {
    const decoded = decodeProviderCatalogue({ provider_metadata_version: 2, provider_plugins: JSON.parse(`{"${id}":{}}`) });
    assert.ok(Object.prototype.hasOwnProperty.call(decoded.errors, id));
    const draft = { external_sources: { WeatherPointModel: null, OfficialWeatherWarnings: id, OutdoorAirQuality: null } };
    assert.ok(categoryRows(decoded, draft, 'DE')[1].error);
  }
});

test('rejects unsupported field vocabulary and cyclic or external references', () => {
  for (const field of [
    { type: 'object', properties: {} },
    { type: 'string', pattern: '(a+)+' },
    { $ref: 'https://example.invalid/schema' },
    { $ref: '#/$defs/Cycle' },
    { type: 'array', items: { type: 'number' } },
  ]) {
    assert.ok(
      catalogue({
        Bad: {
          ...regional,
          parameter_schema: {
            type: 'object',
            additionalProperties: false,
            properties: { region_code: field },
            $defs: { Cycle: { $ref: '#/$defs/Cycle' } },
          },
        },
      }).errors.Bad
    );
  }
});

test('canonical field errors use the sole provider_parameters path', () => {
  const plugin = catalogue().providers.RegionalWarningsApiComponent;
  const canonical = {
    path: ['user_config', 'provider_parameters', plugin.id, 'region_code', 0],
    code: 'invalid',
    message: 'Nieprawidłowy region.',
  };
  const old = { path: ['user_config', 'installation', 'site', 'region_code'], code: 'invalid', message: 'Obsolete.' };
  assert.deepEqual(providerFieldErrors([canonical, old], plugin, 'region_code'), [canonical]);
  assert.equal(
    decodeProviderFieldErrors([{ path: Array(16).fill('x'.repeat(128)), code: 'x'.repeat(128), message: 'x'.repeat(512) }]).length,
    1
  );
  assert.deepEqual(decodeProviderFieldErrors([{ ...canonical, path: ['x'.repeat(129)] }]), []);
});

test('decodes the shared authoritative backend catalogue without legacy/default metadata', () => {
  const fixture = JSON.parse(readFileSync(resolve('..', 'backend/tests/fixtures/external_apis/provider_contract.json'), 'utf8'));
  const decoded = decodeProviderCatalogue(fixture);
  assert.deepEqual(decoded.errors, {});
  assert.ok(decoded.providers.ImgwWarningsApiComponent);
  assert.equal(decoded.providers.GermanyDummyWarningsApiComponent.dataKind, 'synthetic');
  assert.deepEqual(decoded.providers.GermanyDummyWarningsApiComponent.hazards, ['wind']);
});
test('field error decoding is bounded and preserves source paths', () => {
  const item = {
    path: ['user_config', 'providers', 'RegionalWarningsApiComponent', 'parameters', 'region_code'],
    code: 'required',
    message: 'Podaj region.',
  };
  assert.deepEqual(decodeProviderFieldErrors([item]), [item]);
  assert.equal(decodeProviderFieldErrors(Array.from({ length: 33 }, () => item)).length, 32);
  assert.deepEqual(decodeProviderFieldErrors([{ ...item, path: Array(17).fill('x') }]), []);
  assert.deepEqual(decodeProviderFieldErrors([{ ...item, message: 'x'.repeat(513) }]), []);
});

test('enforces metadata text/property/definition/depth/enum budgets', () => {
  const cases = [
    { display_name: 'x'.repeat(257) },
    { description: 'x'.repeat(2049) },
    {
      parameter_schema: {
        type: 'object',
        additionalProperties: false,
        properties: Object.fromEntries(Array.from({ length: 65 }, (_, i) => [`p${i}`, { type: 'string' }])),
      },
    },
    {
      parameter_schema: {
        type: 'object',
        additionalProperties: false,
        properties: { region_code: { type: 'string', enum: Array.from({ length: 1025 }, (_, i) => String(i)) } },
      },
    },
    {
      parameter_schema: {
        type: 'object',
        additionalProperties: false,
        properties: { region_code: { type: 'string', pattern: 'x'.repeat(257) } },
      },
    },
  ];
  for (const value of cases) assert.ok(catalogue({ Bad: { ...regional, ...value } }).errors.Bad);
});

test('supports finite scalar constraints, nullable optional fields and controlled local schema references', () => {
  const decoded = catalogue({
    Scalars: {
      ...regional,
      required_when_selected: [],
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
  const draft = {
    external_sources: { WeatherPointModel: null, OfficialWeatherWarnings: 'Scalars', OutdoorAirQuality: null },
    provider_parameters: { Scalars: { count: 3, value: 1.5, label: null, enabled_option: false, region_code: 'BE' } },
  };
  assert.deepEqual(validateProviderDraft(decoded, draft, 'DE'), []);
  for (const [field, value] of [
    ['count', 1.5],
    ['count', 6],
    ['value', Number.NaN],
    ['value', 0],
    ['value', 10],
    ['label', 'a'],
    ['enabled_option', 'false'],
    ['region_code', 'XX'],
  ]) {
    const changed = structuredClone(draft);
    (changed.provider_parameters.Scalars as Record<string, unknown>)[field as string] = value;
    assert.ok(validateProviderDraft(decoded, changed, 'DE').length, String(field));
  }
});

test('accepts the provider-count boundary and rejects excess providers without guessing applicability', () => {
  const definitions = Object.fromEntries(Array.from({ length: 64 }, (_, index) => [`Provider${index}`, regional]));
  const accepted = decodeProviderCatalogue({ provider_metadata_version: 2, provider_plugins: definitions });
  assert.equal(Object.keys(accepted.providers).length, 64);
  const rejected = decodeProviderCatalogue({ provider_metadata_version: 2, provider_plugins: { ...definitions, Extra: regional } });
  assert.equal(Object.keys(rejected.providers).length, 0);
  assert.ok(Object.keys(rejected.errors).length);
});

test('accepts exact schema text, enum, property and definition boundaries and rejects one over', () => {
  const decode = (schema: object) =>
    catalogue({
      Boundary: { ...regional, required_when_selected: [], parameter_schema: { type: 'object', additionalProperties: false, ...schema } },
    });
  for (const [name, size] of [
    ['title', 256],
    ['description', 2048],
    ['pattern', 256],
  ] as const) {
    assert.ok(decode({ properties: { region_code: { type: 'string', [name]: 'x'.repeat(size) } } }).providers.Boundary);
    assert.ok(decode({ properties: { region_code: { type: 'string', [name]: 'x'.repeat(size + 1) } } }).errors.Boundary);
  }
  for (const [name, count] of [
    ['properties', 64],
    ['$defs', 128],
  ] as const) {
    const entries = Object.fromEntries(Array.from({ length: count }, (_, index) => [`p${index}`, { type: 'string' }]));
    assert.ok(decode({ [name]: entries }).providers.Boundary);
    assert.ok(decode({ [name]: { ...entries, extra: { type: 'string' } } }).errors.Boundary);
  }
  const choices = Array.from({ length: 1024 }, (_, index) => `option${index}`);
  assert.ok(decode({ properties: { region_code: { type: 'string', enum: choices } } }).providers.Boundary);
  assert.ok(decode({ properties: { region_code: { type: 'string', enum: [...choices, 'extra'] } } }).errors.Boundary);
  assert.ok(decode({ properties: { region_code: { type: 'string', enum: ['x'.repeat(256)] } } }).providers.Boundary);
  assert.ok(decode({ properties: { region_code: { type: 'string', enum: ['x'.repeat(257)] } } }).errors.Boundary);
});

test('enforces exact UTF-8 byte, nesting and local-reference-hop budgets', () => {
  const schema: Record<string, unknown> = { type: 'object', additionalProperties: false, properties: {}, 'x-extra': '' };
  const schemaBytes = new TextEncoder().encode(JSON.stringify(schema)).length;
  schema['x-extra'] = 'x'.repeat(65536 - schemaBytes);
  const metadata = { ...regional, required_when_selected: [], parameter_schema: schema };
  assert.ok(catalogue({ Boundary: metadata }).providers.Boundary);
  assert.ok(catalogue({ Boundary: { ...metadata, parameter_schema: { ...schema, 'x-extra': `${schema['x-extra']}x` } } }).errors.Boundary);
  const plugins: Record<string, unknown> = { Boundary: { ...regional, padding: '' } };
  const catalogueBytes = new TextEncoder().encode(JSON.stringify(plugins)).length;
  (plugins.Boundary as Record<string, unknown>).padding = 'x'.repeat(1048576 - catalogueBytes);
  assert.ok(decodeProviderCatalogue({ provider_metadata_version: 2, provider_plugins: plugins }).providers.Boundary);
  (plugins.Boundary as Record<string, unknown>).padding += 'é';
  assert.ok(decodeProviderCatalogue({ provider_metadata_version: 2, provider_plugins: plugins }).error);
  let nested: object = {};
  for (let index = 0; index < 7; index++) nested = { child: nested };
  const bounded = { type: 'object', additionalProperties: false, properties: {}, 'x-extra': nested };
  assert.ok(catalogue({ Boundary: { ...metadata, parameter_schema: bounded } }).providers.Boundary);
  assert.ok(catalogue({ Boundary: { ...metadata, parameter_schema: { ...bounded, 'x-extra': { child: nested } } } }).errors.Boundary);
  for (const count of [16, 17]) {
    const definitions = Object.fromEntries(
      Array.from({ length: count }, (_, index) => [
        `R${index}`,
        index === count - 1 ? { type: 'string' } : { $ref: `#/$defs/R${index + 1}` },
      ])
    );
    const result = catalogue({
      Boundary: {
        ...regional,
        parameter_schema: {
          type: 'object',
          additionalProperties: false,
          properties: { region_code: { $ref: '#/$defs/R0' } },
          $defs: definitions,
        },
      },
    });
    assert.equal(Boolean(result.providers.Boundary), count === 16);
  }
});
