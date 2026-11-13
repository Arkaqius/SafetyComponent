import { expect, test, type Page } from '@playwright/test';

const regional = {
  enabled: false,
  countries: ['DE'],
  capability: 'OfficialWeatherWarnings',
  hazards: ['wind'],
  display_name: 'Ostrzeżenia regionalne',
  description: 'Kontrolowane źródło regionalne.',
  parameter_schema: {
    type: 'object',
    additionalProperties: false,
    properties: { region_code: { type: 'string', title: 'Kod regionu', minLength: 2, maxLength: 16 } },
  },
  required_when_enabled: ['region_code'],
  parameter_defaults: {},
  legacy_parameter_paths: {},
};
const imgw = {
  ...regional,
  enabled: true,
  countries: ['PL'],
  display_name: 'Ostrzeżenia IMGW',
  parameter_schema: {
    type: 'object',
    additionalProperties: false,
    properties: {
      teryt_codes: {
        type: 'array',
        title: 'Kody powiatów',
        items: { type: 'string', pattern: '^[0-9]{4}$' },
        minItems: 1,
        maxItems: 10000,
        uniqueItems: true,
      },
    },
  },
  required_when_enabled: ['teryt_codes'],
  legacy_parameter_paths: { teryt_codes: ['installation', 'site', 'teryt_codes'] },
};

function fixture(country = 'DE') {
  return {
    revision: 'fixture-1',
    restart_required: false,
    setup_required: false,
    user_config: {
      model_version: 2,
      components_enabled: { ExternalHazardComponent: true },
      notification: { mobile: { services: ['notify/mobile_app_example'] } },
      installation: { site: { country_code: country, timezone: 'Europe/Berlin', ...(country === 'PL' ? { teryt_codes: ['0000'] } : {}) } },
    },
    system_defaults: {
      external_hazard: {
        provider_metadata_version: 1,
        provider_plugins: { RegionalWarningsApiComponent: regional, ImgwWarningsApiComponent: imgw },
      },
    },
  };
}

async function openConfiguration(page: Page, document: unknown) {
  await page.addInitScript(value => {
    localStorage.setItem('safetyhome.view-mode', 'advanced');
    (window as unknown as { __safetyHomeConfigurationSeed: unknown }).__safetyHomeConfigurationSeed = value;
  }, document);
  await page.route('**/*', request => (new URL(request.request().url()).hostname === '127.0.0.1' ? request.continue() : request.abort()));
  await page.goto('/#/configuration/general');
  await expect(page.getByRole('heading', { name: 'Ustawienia SafetyComponent' })).toBeVisible();
}

test('regional provider fields are configurable without Polish codes and retain explicit intent after save', async ({ page }) => {
  await openConfiguration(page, fixture());
  const provider = page.locator('[data-provider-id="RegionalWarningsApiComponent"]');
  await provider.getByLabel('Włączenie źródła').selectOption('enabled');
  await expect(provider.getByLabel('Kod regionu')).toBeVisible();
  await expect(page.getByLabel('Kody powiatów')).toHaveCount(0);
  await provider.getByLabel('Kod regionu').fill('BE');
  await page.getByRole('button', { name: 'Zapisz konfigurację', exact: true }).click();
  await expect(page.getByText('Konfiguracja została zapisana', { exact: false })).toBeVisible();
  await expect(provider.getByLabel('Włączenie źródła')).toHaveValue('enabled');
  await expect(provider.getByLabel('Kod regionu')).toHaveValue('BE');
  await provider.getByLabel('Kod regionu').fill('BB');
  await page.getByRole('button', { name: 'Odrzuć zmiany', exact: true }).click();
  await expect(provider.getByLabel('Kod regionu')).toHaveValue('BE');
  await expect(provider.getByLabel('Włączenie źródła')).toHaveValue('enabled');
});

test('missing regional parameter prevents save and identifies the field', async ({ page }) => {
  await openConfiguration(page, fixture());
  const provider = page.locator('[data-provider-id="RegionalWarningsApiComponent"]');
  await provider.getByLabel('Włączenie źródła').selectOption('enabled');
  await page.getByRole('button', { name: 'Zapisz konfigurację', exact: true }).click();
  await expect(provider.getByLabel('Kod regionu')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByText('Sprawdź parametry źródeł danych.')).toBeVisible();
  await provider.getByLabel('Kod regionu').fill('BE');
  await provider.getByLabel('Włączenie źródła').selectOption('disabled');
  await expect(provider.getByLabel('Kod regionu')).toHaveValue('BE');
});

test('country changes expose incompatible explicit choices and preserve the draft', async ({ page }) => {
  await openConfiguration(page, fixture());
  const provider = page.locator('[data-provider-id="RegionalWarningsApiComponent"]');
  await provider.getByLabel('Włączenie źródła').selectOption('enabled');
  await provider.getByLabel('Kod regionu').fill('BE');
  await page.getByRole('link', { name: 'Instalacja HA', exact: true }).click();
  await page.getByLabel('Kod kraju', { exact: false }).fill('PL');
  await page.getByRole('link', { name: 'Ogólne', exact: true }).click();
  await expect(provider).toBeVisible();
  await expect(provider.getByText('Źródło nie obsługuje wybranego kraju.')).toBeVisible();
  await expect(provider.getByLabel('Kod regionu')).toHaveValue('BE');
});

test('legacy county codes project without dirty state and edit their original binding', async ({ page }) => {
  await openConfiguration(page, fixture('PL'));
  const provider = page.locator('[data-provider-id="ImgwWarningsApiComponent"]');
  await expect(provider.getByLabel('Kody powiatów')).toHaveValue('0000');
  await expect(page.getByRole('button', { name: 'Zapisz konfigurację', exact: true })).toBeDisabled();
  await provider.getByLabel('Kody powiatów').fill('0001');
  await page.getByRole('button', { name: 'Zapisz konfigurację', exact: true }).click();
  const saved = await page.evaluate(() =>
    (
      window as unknown as {
        __safetyHomeConfigurationMock: {
          snapshot(): { user_config: { installation: { site: { teryt_codes: string[] } }; providers?: object } };
        };
      }
    ).__safetyHomeConfigurationMock.snapshot()
  );
  expect(saved.user_config.installation.site.teryt_codes).toEqual(['0001']);
  expect(saved.user_config.providers).toBeUndefined();
});

test('unknown metadata remains visible for explicit correction without granting eligibility', async ({ page }) => {
  const document = {
    ...fixture(),
    user_config: { ...fixture().user_config, providers: { Unknown: { enabled: true, parameters: { x: 'preserve' } } } },
  };
  await openConfiguration(page, document);
  const provider = page.locator('[data-provider-id="Unknown"]');
  await expect(provider).toBeVisible();
  await expect(provider.getByText('Brak poprawnych metadanych źródła.')).toBeVisible();
  await provider.getByRole('button', { name: 'Usuń wybór źródła' }).click();
  await expect(provider).toHaveCount(0);
});

test('provider fields fit a narrow screen and expose keyboard labels', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 760 });
  await openConfiguration(page, fixture());
  const provider = page.locator('[data-provider-id="RegionalWarningsApiComponent"]');
  await provider.getByLabel('Włączenie źródła').focus();
  await expect(provider.getByLabel('Włączenie źródła')).toBeFocused();
  await provider.getByLabel('Włączenie źródła').selectOption('enabled');
  await provider.getByLabel('Kod regionu').focus();
  await expect(provider.getByLabel('Kod regionu')).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
});

test('equal canonical and legacy fields update together and conflicts require a deliberate choice', async ({ page }) => {
  const document = {
    ...fixture('PL'),
    user_config: { ...fixture('PL').user_config, providers: { ImgwWarningsApiComponent: { parameters: { teryt_codes: ['0000'] } } } },
  };
  await openConfiguration(page, document);
  const provider = page.locator('[data-provider-id="ImgwWarningsApiComponent"]');
  await provider.getByLabel('Kody powiatów').fill('0002');
  await page.getByRole('button', { name: 'Zapisz konfigurację', exact: true }).click();
  await expect(page.getByText('Konfiguracja została zapisana', { exact: false })).toBeVisible();
  const saved = await page.evaluate(() => window.__safetyHomeConfigurationMock!.snapshot());
  expect((saved.user_config.providers as Record<string, { parameters: object }>).ImgwWarningsApiComponent.parameters).toEqual({
    teryt_codes: ['0002'],
  });
  expect((saved.user_config.installation as { site: { teryt_codes: string[] } }).site.teryt_codes).toEqual(['0002']);
});

test('conflicting alias values are visible until the user explicitly reconciles them', async ({ page }) => {
  const document = {
    ...fixture('PL'),
    user_config: { ...fixture('PL').user_config, providers: { ImgwWarningsApiComponent: { parameters: { teryt_codes: ['0001'] } } } },
  };
  await openConfiguration(page, document);
  const provider = page.locator('[data-provider-id="ImgwWarningsApiComponent"]');
  await expect(provider.getByLabel('Kody powiatów')).toBeDisabled();
  await expect(provider.getByText('["0000"]', { exact: false })).toBeVisible();
  await expect(provider.getByText('["0001"]', { exact: false })).toBeVisible();
  await provider.getByRole('button', { name: 'Użyj wartości parametru źródła' }).click();
  await expect(provider.getByLabel('Kody powiatów')).toBeEnabled();
  await expect(provider.getByLabel('Kody powiatów')).toHaveValue('0001');
});

test('server field errors and stale revision preserve the draft for correction and reload', async ({ page }) => {
  await openConfiguration(page, fixture());
  const provider = page.locator('[data-provider-id="RegionalWarningsApiComponent"]');
  await provider.getByLabel('Włączenie źródła').selectOption('enabled');
  await provider.getByLabel('Kod regionu').fill('BE');
  await page.evaluate(() =>
    window.__safetyHomeConfigurationMock!.failNext({
      error: 'invalid_configuration',
      message: 'Odrzucono konfigurację źródła.',
      status: 422,
      field_errors: [
        {
          path: ['user_config', 'providers', 'RegionalWarningsApiComponent', 'parameters', 'region_code'],
          code: 'invalid_region',
          message: 'Sprawdź kod regionu.',
        },
      ],
    })
  );
  await page.getByRole('button', { name: 'Zapisz konfigurację', exact: true }).click();
  await expect(provider.getByText('Sprawdź kod regionu.')).toBeVisible();
  await expect(provider.getByLabel('Kod regionu')).toHaveValue('BE');
  await page.evaluate(() =>
    window.__safetyHomeConfigurationMock!.failNext({
      error: 'revision_conflict',
      message: 'Konfiguracja zmieniła się. Wczytaj ją ponownie.',
      status: 409,
    })
  );
  await page.getByRole('button', { name: 'Zapisz konfigurację', exact: true }).click();
  await expect(page.getByText('Konfiguracja zmieniła się. Wczytaj ją ponownie.')).toBeVisible();
  await expect(provider.getByLabel('Kod regionu')).toHaveValue('BE');
  await page.getByRole('button', { name: 'Odrzuć zmiany', exact: true }).click();
  await expect(provider.getByLabel('Włączenie źródła')).toHaveValue('inherit');
});

test('new Polish parameters use canonical source fields and keep enablement inherited', async ({ page }) => {
  const document = fixture('PL');
  delete (document.user_config.installation.site as { teryt_codes?: string[] }).teryt_codes;
  await openConfiguration(page, document);
  const provider = page.locator('[data-provider-id="ImgwWarningsApiComponent"]');
  await provider.getByLabel('Kody powiatów').fill('0001');
  await page.getByRole('button', { name: 'Zapisz konfigurację', exact: true }).click();
  await expect(page.getByText('Konfiguracja została zapisana', { exact: false })).toBeVisible();
  const saved = await page.evaluate(() => window.__safetyHomeConfigurationMock!.snapshot());
  expect(saved.user_config.providers).toEqual({ ImgwWarningsApiComponent: { parameters: { teryt_codes: ['0001'] } } });
});

test('unsupported metadata cannot grant activation or silently discard saved values', async ({ page }) => {
  const document = fixture();
  const invalid = {
    ...document,
    system_defaults: { external_hazard: { provider_metadata_version: 2, provider_plugins: { RegionalWarningsApiComponent: regional } } },
    user_config: {
      ...document.user_config,
      providers: { RegionalWarningsApiComponent: { enabled: true, parameters: { region_code: 'BE' } } },
    },
  };
  await openConfiguration(page, invalid);
  const provider = page.locator('[data-provider-id="RegionalWarningsApiComponent"]');
  await expect(provider.getByText('Brak poprawnych metadanych źródła.')).toBeVisible();
  await expect(provider.getByLabel('Kod regionu')).toHaveCount(0);
  expect((await page.evaluate(() => window.__safetyHomeConfigurationMock!.snapshot())).user_config.providers).toEqual(
    invalid.user_config.providers
  );
});

test('unknown supplied parameters fail validation even when the source is disabled', async ({ page }) => {
  const document = {
    ...fixture(),
    user_config: {
      ...fixture().user_config,
      providers: { RegionalWarningsApiComponent: { enabled: false, parameters: { region_code: 'BE', unknown: 'preserved' } } },
    },
  };
  await openConfiguration(page, document);
  const provider = page.locator('[data-provider-id="RegionalWarningsApiComponent"]');
  await provider.getByLabel('Kod regionu').fill('BB');
  await page.getByRole('button', { name: 'Zapisz konfigurację', exact: true }).click();
  await expect(page.getByText('Sprawdź parametry źródeł danych.')).toBeVisible();
  await expect(provider.getByLabel('Kod regionu')).toHaveValue('BB');
  expect((await page.evaluate(() => window.__safetyHomeConfigurationMock!.snapshot())).revision).toBe('fixture-1');
});
