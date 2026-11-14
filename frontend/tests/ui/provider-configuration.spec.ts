import { expect, test, type Page } from '@playwright/test';

const dummy = {
  countries: ['DE'],
  capability: 'OfficialWeatherWarnings',
  hazards: ['wind'],
  display_name: 'Niemcy — źródło testowe',
  description: 'Źródło testowe — dane syntetyczne.',
  data_kind: 'synthetic',
  transport_kind: 'none',
  parameter_schema: {
    type: 'object',
    additionalProperties: false,
    properties: {
      region_code: { type: 'string', title: 'Kod regionu', minLength: 1, maxLength: 32, pattern: '^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$' },
      scenario: { type: 'string', title: 'Scenariusz testowy', enum: ['empty', 'warning', 'unavailable', 'stale'], default: 'empty' },
    },
  },
  required_when_selected: ['region_code'],
  parameter_defaults: { scenario: 'empty' },
};
const imgw = {
  ...dummy,
  countries: ['PL'],
  hazards: ['frost', 'wind', 'rain', 'storm'],
  display_name: 'Ostrzeżenia IMGW',
  description: 'Ostrzeżenia urzędowe dla wybranych powiatów.',
  data_kind: 'live',
  transport_kind: 'http',
  parameter_schema: {
    type: 'object',
    additionalProperties: false,
    properties: {
      teryt_codes: {
        type: 'array',
        title: 'Kody powiatów',
        items: { type: 'string', pattern: '^[0-9]{4}$' },
        maxItems: 10000,
        uniqueItems: true,
      },
    },
  },
  required_when_selected: ['teryt_codes'],
  parameter_defaults: {},
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
      external_sources: { WeatherPointModel: null, OfficialWeatherWarnings: null, OutdoorAirQuality: null } as Record<
        string,
        string | null
      >,
      provider_parameters: {} as Record<string, Record<string, unknown>>,
      installation: { site: { country_code: country, timezone: country === 'PL' ? 'Europe/Warsaw' : 'Europe/Berlin' } },
    },
    system_defaults: {
      external_hazard: {
        provider_metadata_version: 2,
        provider_plugins: { GermanyDummyWarningsApiComponent: dummy, ImgwWarningsApiComponent: imgw },
      },
    },
  };
}
async function openConfiguration(page: Page, document: unknown) {
  await page.addInitScript(value => {
    localStorage.setItem('safetyhome.view-mode', 'advanced');
    window.__safetyHomeConfigurationSeed = value;
  }, document);
  await page.route('**/*', route => (new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort()));
  await page.goto('/#/configuration/general');
  await expect(page.getByRole('heading', { name: 'Ustawienia SafetyComponent' })).toBeVisible();
}
const official = (page: Page) => page.locator('[data-capability="OfficialWeatherWarnings"]');
const selector = (page: Page) => official(page).getByRole('combobox').first();

test('selects a German test source or disabled with conditional fields and clean save/reopen', async ({ page }) => {
  await openConfiguration(page, fixture());
  await expect(page.locator('[data-capability]')).toHaveCount(3);
  await expect(selector(page)).toHaveValue('');
  await expect(official(page).getByLabel('Kod regionu')).toHaveCount(0);
  await expect(selector(page).locator('option')).toHaveText(['Wyłączone', 'Niemcy — źródło testowe']);
  await selector(page).selectOption('GermanyDummyWarningsApiComponent');
  await official(page).getByLabel('Kod regionu').fill('BE');
  await expect(official(page).getByLabel('Scenariusz testowy')).toHaveValue('empty');
  await expect(page.getByLabel('Kody powiatów')).toHaveCount(0);
  await selector(page).selectOption('');
  await expect(official(page).getByLabel('Kod regionu')).toHaveCount(0);
  await selector(page).selectOption('GermanyDummyWarningsApiComponent');
  await expect(official(page).getByLabel('Kod regionu')).toHaveValue('BE');
  await page.getByRole('button', { name: 'Zapisz konfigurację', exact: true }).click();
  await expect(page.getByText('Konfiguracja została zapisana', { exact: false })).toBeVisible();
  const saved = await page.evaluate(() => window.__safetyHomeConfigurationMock!.snapshot());
  expect(saved.user_config.external_sources).toEqual({
    WeatherPointModel: null,
    OfficialWeatherWarnings: 'GermanyDummyWarningsApiComponent',
    OutdoorAirQuality: null,
  });
  expect(saved.user_config.provider_parameters).toEqual({ GermanyDummyWarningsApiComponent: { region_code: 'BE' } });
  await page.getByRole('link', { name: 'Instalacja HA', exact: true }).click();
  await page.getByRole('link', { name: 'Ogólne', exact: true }).click();
  await expect(official(page).getByLabel('Kod regionu')).toHaveValue('BE');
});

test('missing required selected parameter blocks save; disabling keeps a valid incomplete draft', async ({ page }) => {
  await openConfiguration(page, fixture());
  await selector(page).selectOption('GermanyDummyWarningsApiComponent');
  await page.getByRole('button', { name: 'Zapisz konfigurację', exact: true }).click();
  await expect(official(page).getByText('Wypełnij wymagany parametr źródła.')).toBeVisible();
  expect((await page.evaluate(() => window.__safetyHomeConfigurationMock!.snapshot())).revision).toBe('fixture-1');
  await selector(page).selectOption('');
  await page.getByRole('button', { name: 'Zapisz konfigurację', exact: true }).click();
  await expect(page.getByText('Konfiguracja została zapisana', { exact: false })).toBeVisible();
});

test('Polish selection exposes only canonical county parameters and no default or inheritance choices', async ({ page }) => {
  const document = fixture('PL');
  document.user_config.external_sources.OfficialWeatherWarnings = 'ImgwWarningsApiComponent';
  document.user_config.provider_parameters.ImgwWarningsApiComponent = { teryt_codes: ['0000'] };
  await openConfiguration(page, document);
  await expect(official(page).getByLabel('Kody powiatów')).toHaveValue('0000');
  await expect(selector(page).locator('option')).toHaveText(['Wyłączone', 'Ostrzeżenia IMGW']);
  await official(page).getByLabel('Kody powiatów').fill('0001');
  await page.getByRole('button', { name: 'Zapisz konfigurację', exact: true }).click();
  await expect(page.getByText('Konfiguracja została zapisana', { exact: false })).toBeVisible();
  expect((await page.evaluate(() => window.__safetyHomeConfigurationMock!.snapshot())).user_config.provider_parameters).toEqual({
    ImgwWarningsApiComponent: { teryt_codes: ['0001'] },
  });
});

test('country changes preserve incompatible choice and draft until explicit correction', async ({ page }) => {
  const document = fixture();
  document.user_config.external_sources.OfficialWeatherWarnings = 'GermanyDummyWarningsApiComponent';
  document.user_config.provider_parameters.GermanyDummyWarningsApiComponent = { region_code: 'BE' };
  await openConfiguration(page, document);
  await page.getByRole('link', { name: 'Instalacja HA', exact: true }).click();
  await page.getByRole('textbox', { name: 'Kod kraju', exact: false }).fill('PL');
  await page.getByRole('link', { name: 'Ogólne', exact: true }).click();
  await expect(selector(page)).toHaveValue('GermanyDummyWarningsApiComponent');
  await expect(official(page).getByText('Źródło nie obsługuje wybranego kraju.')).toBeVisible();
  await expect(official(page).getByLabel('Kod regionu')).toHaveValue('BE');
  await selector(page).selectOption('');
  await expect(official(page).getByLabel('Kod regionu')).toHaveCount(0);
});

test('invalid metadata and unknown selections remain visible without automatic source replacement', async ({ page }) => {
  const document = fixture();
  document.user_config.external_sources.OfficialWeatherWarnings = 'Unknown';
  await openConfiguration(page, document);
  await expect(selector(page)).toHaveValue('Unknown');
  await expect(official(page).getByText('Brak poprawnych metadanych źródła.')).toBeVisible();
  await selector(page).selectOption('');
  await expect(selector(page)).toHaveValue('');
});

test('422 and 409 responses retain draft and field errors until explicit reload', async ({ page }) => {
  await openConfiguration(page, fixture());
  await selector(page).selectOption('GermanyDummyWarningsApiComponent');
  await official(page).getByLabel('Kod regionu').fill('BE');
  await page.evaluate(() =>
    window.__safetyHomeConfigurationMock!.failNext({
      error: 'invalid_configuration',
      message: 'Odrzucono konfigurację.',
      status: 422,
      field_errors: [
        {
          path: ['user_config', 'provider_parameters', 'GermanyDummyWarningsApiComponent', 'region_code'],
          code: 'invalid_region',
          message: 'Sprawdź kod regionu.',
        },
      ],
    })
  );
  await page.getByRole('button', { name: 'Zapisz konfigurację', exact: true }).click();
  await expect(official(page).getByText('Sprawdź kod regionu.')).toBeVisible();
  await page.evaluate(() =>
    window.__safetyHomeConfigurationMock!.failNext({
      error: 'revision_conflict',
      message: 'Konfiguracja zmieniła się. Wczytaj ją ponownie.',
      status: 409,
    })
  );
  await page.getByRole('button', { name: 'Zapisz konfigurację', exact: true }).click();
  await expect(page.getByText('Konfiguracja zmieniła się. Wczytaj ją ponownie.')).toBeVisible();
  await expect(official(page).getByLabel('Kod regionu')).toHaveValue('BE');
  await page.getByRole('button', { name: 'Odrzuć zmiany', exact: true }).click();
  await expect(selector(page)).toHaveValue('');
});

test('keyboard labels and narrow layout stay usable', async ({ page }) => {
  await openConfiguration(page, fixture());
  await selector(page).focus();
  await expect(selector(page)).toBeFocused();
  await selector(page).selectOption('GermanyDummyWarningsApiComponent');
  await official(page).getByLabel('Kod regionu').focus();
  await expect(official(page).getByLabel('Kod regionu')).toBeFocused();
  const bounds = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
    overflow: Array.from(document.querySelectorAll('body *'))
      .flatMap(element => {
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.right > window.innerWidth + 1
          ? [{ tag: element.tagName, class: element.className, right: rect.right }]
          : [];
      })
      .slice(0, 8),
  }));
  expect(bounds.width, JSON.stringify(bounds)).toBeLessThanOrEqual(bounds.viewport + 1);
});
