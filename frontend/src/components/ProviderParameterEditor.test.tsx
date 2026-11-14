import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { decodeProviderCatalogue } from '../domain/providerConfiguration.js';
import ProviderParameterEditor from './ProviderParameterEditor.js';

const catalogue = decodeProviderCatalogue({
  provider_metadata_version: 2,
  provider_plugins: {
    RegionalWarningsApiComponent: {
      data_kind: 'synthetic',
      transport_kind: 'none',
      countries: ['DE'],
      capability: 'OfficialWeatherWarnings',
      hazards: ['wind'],
      display_name: 'Ostrzeżenia regionalne',
      description: 'Dane dla wybranego regionu.',
      required_when_selected: ['region_code'],
      parameter_defaults: {},
      parameter_schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          region_code: { type: 'string', title: 'Kod regionu', description: 'Wpisz kod właściwego regionu.', minLength: 2, maxLength: 16 },
          regions: { type: 'array', title: 'Dodatkowe regiony', items: { type: 'string' }, maxItems: 8 },
          detailed: { type: 'boolean', title: 'Szczegóły' },
          profile: { type: 'string', title: 'Profil', enum: ['standard', 'extended'] },
        },
      },
    },
  },
});

test('renders provider-owned typed fields, requirements, help and field errors', () => {
  const html = renderToStaticMarkup(
    <ProviderParameterEditor
      plugin={catalogue.providers.RegionalWarningsApiComponent}
      values={{ region_code: 'BE', regions: ['A', 'B'], detailed: false, profile: 'standard' }}
      active
      errors={[
        {
          path: ['user_config', 'provider_parameters', 'RegionalWarningsApiComponent', 'region_code'],
          code: 'invalid',
          message: 'Nieprawidłowy region.',
        },
      ]}
      onChange={() => undefined}
    />
  );
  assert.match(html, /Kod regionu/);
  assert.match(html, /Wpisz kod właściwego regionu/);
  assert.match(html, /Nieprawidłowy region/);
  assert.match(html, /aria-invalid="true"/);
  assert.match(html, /<select/);
  assert.match(html, /<textarea/);
  assert.match(html, /type="checkbox"/);
  assert.doesNotMatch(html, /Dodaj pole|Nowe pole/);
});

test('renders finite numbers and nullable optional defaults while disabled values remain readable', () => {
  const plugin = structuredClone(catalogue.providers.RegionalWarningsApiComponent);
  plugin.fields.count = {
    kind: 'integer',
    title: 'Liczba regionów',
    description: 'Do pięciu.',
    nullable: false,
    required: false,
    minimum: 1,
    maximum: 5,
  };
  plugin.fields.threshold = { kind: 'number', title: 'Próg', description: '', nullable: true, required: false };
  const html = renderToStaticMarkup(
    <ProviderParameterEditor
      plugin={plugin}
      values={{ region_code: 'BE', count: 3, threshold: null, regions: ['A', 'B'] }}
      active={false}
      disabled
      onChange={() => undefined}
    />
  );
  assert.match(html, /type="number" value="3"|type="number"[^>]*value="3"/);
  assert.match(html, /min="1" max="5" step="1"/);
  assert.match(html, /disabled=""/);
  assert.match(html, /value="BE"/);
  assert.match(html, /A\nB/);
  assert.doesNotMatch(html, /aria-required="true"/);
});
