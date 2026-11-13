import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { decodeProviderCatalogue } from '../domain/providerConfiguration.js';
import ProviderParameterEditor from './ProviderParameterEditor.js';

const catalogue = decodeProviderCatalogue({
  provider_metadata_version: 1,
  provider_plugins: {
    RegionalWarningsApiComponent: {
      enabled: false,
      countries: ['DE'],
      capability: 'OfficialWeatherWarnings',
      hazards: ['wind'],
      display_name: 'Ostrzeżenia regionalne',
      description: 'Dane dla wybranego regionu.',
      required_when_enabled: ['region_code'],
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
      errors={[{ path: ['user_config', 'providers', 'RegionalWarningsApiComponent', 'parameters', 'region_code'], code: 'invalid', message: 'Nieprawidłowy region.' }]}
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
