import { expect, test, type Page } from '@playwright/test';

const regional = {
  enabled: false,
  countries: ['DE'],
  capability: 'OfficialWeatherWarnings',
  hazards: ['wind'],
  display_name: 'Ostrzeżenia regionalne',
  description: 'Kontrolowane źródło regionalne.',
  parameter_schema: { type: 'object', additionalProperties: false, properties: { region_code: { type: 'string', title: 'Kod regionu', minLength: 2, maxLength: 16 } } },
  required_when_enabled: ['region_code'],
  parameter_defaults: {},
  legacy_parameter_paths: {},
};
const imgw = {
  ...regional,
  enabled: true,
  countries: ['PL'],
  display_name: 'Ostrzeżenia IMGW',
  parameter_schema: { type: 'object', additionalProperties: false, properties: { teryt_codes: { type: 'array', title: 'Kody powiatów', items: { type: 'string', pattern: '^[0-9]{4}$' }, minItems: 1, maxItems: 10000, uniqueItems: true } } },
  required_when_enabled: ['teryt_codes'],
  legacy_parameter_paths: { teryt_codes: ['installation', 'site', 'teryt_codes'] },
};

function fixture(country = 'DE') {
  return {
    revision: 'fixture-1', restart_required: false, setup_required: false,
    user_config: {
      model_version: 2,
      components_enabled: { ExternalHazardComponent: true },
      notification: { mobile: { services: ['notify/mobile_app_example'] } },
      installation: { site: { country_code: country, timezone: 'Europe/Berlin', ...(country === 'PL' ? { teryt_codes: ['0000'] } : {}) } },
    },
    system_defaults: { external_hazard: { provider_metadata_version: 1, provider_plugins: { RegionalWarningsApiComponent: regional, ImgwWarningsApiComponent: imgw } } },
  };
}

async function openConfiguration(page: Page, document: unknown) {
  await page.addInitScript(value => {
    localStorage.setItem('safetyhome.view-mode', 'advanced');
    (window as unknown as { __safetyHomeConfigurationSeed: unknown }).__safetyHomeConfigurationSeed = value;
  }, document);
  await page.route('**/*', request => new URL(request.request().url()).hostname === '127.0.0.1' ? request.continue() : request.abort());
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
  await page.getByLabel('Kod kraju', { exact: true }).fill('PL');
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
  const saved = await page.evaluate(() => (window as unknown as { __safetyHomeConfigurationMock: { snapshot(): { user_config: { installation: { site: { teryt_codes: string[] } }; providers?: object } } } }).__safetyHomeConfigurationMock.snapshot());
  expect(saved.user_config.installation.site.teryt_codes).toEqual(['0001']);
  expect(saved.user_config.providers).toBeUndefined();
});

test('unknown metadata remains visible for explicit correction without granting eligibility', async ({ page }) => {
  const document = { ...fixture(), user_config: { ...fixture().user_config, providers: { Unknown: { enabled: true, parameters: { x: 'preserve' } } } } };
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
