import { expect, test, type Page } from '@playwright/test';

async function show(page: Page, mode: string) {
  await page.addInitScript(() => localStorage.setItem('safetyhome.view-mode', 'advanced'));
  await page.route('**/*', route => (new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort()));
  await page.goto('/#/external-hazards');
  await page.waitForFunction(() => Boolean(window.__safetyHomeMock));
  await page.evaluate(mode => {
    const entities = window.__safetyHomeMock.snapshot();
    for (const id of Object.keys(entities))
      if (id.startsWith('sensor.external_provider_') || id.startsWith('sensor.fault_')) delete entities[id];
    const synthetic = ['empty', 'warning', 'test-unavailable', 'test-stale'].includes(mode);
    const provider =
      mode === 'disabled' || mode === 'component-off' || mode === 'retained'
        ? null
        : synthetic
          ? 'GermanyDummyWarningsApiComponent'
          : 'RegionalWarningsApiComponent';
    entities['sensor.external_source_selection'] = {
      state: 'ready',
      attributes: {
        schema_version: 1,
        runtime_id: 'current-boot',
        component_enabled: mode !== 'component-off',
        selections: {
          WeatherPointModel: { provider: 'Weather', data_kind: 'live', hazards: ['wind'] },
          OfficialWeatherWarnings: {
            provider,
            data_kind: provider ? (synthetic ? 'synthetic' : 'live') : null,
            hazards: provider ? ['wind'] : [],
          },
          OutdoorAirQuality: { provider: null, data_kind: null, hazards: [] },
        },
      },
    };
    const now = new Date().toISOString();
    entities['sensor.external_hazard_state'] = {
      state: mode === 'active' ? 'warning' : 'clear',
      attributes: {
        runtime_id: 'current-boot',
        active_hazards: mode === 'active' ? ['wind'] : [],
        active_symptom_count: mode === 'active' ? 1 : 0,
        coverage_details: [
          { capability: 'WeatherPointModel', hazard: 'wind', providers: ['Weather'], status: 'available' },
          {
            capability: 'OfficialWeatherWarnings',
            hazard: 'wind',
            providers: provider ? [provider] : [],
            status: mode === 'unavailable' ? 'unavailable' : mode === 'active' ? 'available' : 'no_current_warnings',
          },
          { capability: 'OfficialWeatherWarnings', hazard: 'frost', providers: provider ? [provider] : [], status: 'unsupported' },
        ],
      },
    };
    entities['sensor.external_provider_weather'] = {
      state: 'ok',
      attributes: {
        runtime_id: 'current-boot',
        provider: 'Weather',
        capability: 'WeatherPointModel',
        data_kind: 'live',
        hazards: ['wind'],
        last_success_at: now,
        stale_after_seconds: 180,
        observation_count: 1,
        observations: [],
      },
    };
    entities['sensor.external_provider_regional'] = {
      state: mode === 'unavailable' ? 'unavailable' : mode === 'stale' ? 'stale' : 'ok',
      attributes: {
        runtime_id: mode === 'awaiting_evidence' ? 'old-boot' : 'current-boot',
        provider: 'RegionalWarningsApiComponent',
        provider_name: 'Ostrzeżenia regionalne',
        capability: 'OfficialWeatherWarnings',
        data_kind: 'live',
        hazards: ['wind'],
        last_success_at: now,
        stale_after_seconds: 180,
        observation_count: mode === 'active' ? 1 : 0,
        warnings:
          mode === 'active'
            ? [
                {
                  id: 'wind',
                  event_name: 'Silny wiatr w regionie',
                  locally_applicable: true,
                  valid_to: new Date(Date.now() + 180000).toISOString(),
                },
              ]
            : [],
      },
    };
    if (mode === 'all-disabled' || mode === 'retained') {
      const attrs = entities['sensor.external_source_selection'].attributes;
      attrs.selections = {
        WeatherPointModel: { provider: null, data_kind: null, hazards: [] },
        OfficialWeatherWarnings: { provider: null, data_kind: null, hazards: [] },
        OutdoorAirQuality: { provider: null, data_kind: null, hazards: [] },
      };
    }
    if (mode === 'retained') {
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
    }
    if (mode === 'unknown') delete entities['sensor.external_source_selection'];
    if (synthetic) {
      const scenario = mode.replace('test-', '');
      entities['sensor.external_hazard_test_state'] = {
        state: scenario === 'unavailable' ? 'unavailable' : scenario === 'stale' ? 'stale' : 'ok',
        attributes: {
          schema_version: 1,
          runtime_id: 'current-boot',
          provider: 'GermanyDummyWarningsApiComponent',
          provider_name: 'Niemcy — źródło testowe',
          data_kind: 'synthetic',
          scenario,
          health: scenario === 'unavailable' ? 'unavailable' : scenario === 'stale' ? 'stale' : 'ok',
          count: scenario === 'warning' ? 1 : 0,
          observations: scenario === 'warning' ? [{ id: 'dummy-wind', hazard_type: 'wind', provider_level: 'test' }] : [],
          warnings: [],
        },
      };
    }
    window.__safetyHomeMock.update({ entities, connectionStatus: 'connected', ready: true });
  }, mode);
}
const official = (page: Page) => page.getByRole('region', { name: 'Oficjalne ostrzeżenia pogodowe', exact: true });

test('disabled source is muted with no current zero despite retained healthy telemetry', async ({ page }) => {
  await show(page, 'disabled');
  await expect(official(page)).toHaveClass(/provider-muted/);
  await expect(official(page).locator('.official-warning-count')).toHaveText('—');
  await expect(official(page).getByText('Wyłączone', { exact: true })).toBeVisible();
  await expect(page.locator('[data-capability="WeatherPointModel"]').getByText('Dane dostępne', { exact: true })).toBeVisible();
});
test('all-disabled and component-off monitoring never show a green clear summary', async ({ page }) => {
  for (const mode of ['all-disabled', 'component-off']) {
    await show(page, mode);
    await expect(page.locator('.external-introduction')).toHaveClass(/external-muted/);
    await expect(page.getByRole('region', { name: 'Podsumowanie zagrożeń zewnętrznych' }).getByText('0', { exact: true })).toHaveCount(0);
  }
});
for (const [mode, message] of [
  ['unknown', 'Brak aktualnego stanu konfiguracji'],
  ['awaiting_evidence', 'Oczekiwanie na dane'],
  ['unavailable', 'Brak wiarygodnych danych'],
  ['stale', 'Dane nieaktualne'],
])
  test(`distinguishes ${mode} from disabled and healthy zero`, async ({ page }) => {
    await show(page, mode);
    await expect(official(page).getByText(message, { exact: true })).toBeVisible();
    await expect(official(page).locator('.official-warning-count')).toHaveText('—');
  });
test('fresh healthy empty warning feed allows a scoped numerical zero', async ({ page }) => {
  await show(page, 'healthy');
  await expect(official(page).locator('.official-warning-count')).toHaveText('0');
  await expect(official(page).getByText('Brak aktualnych ostrzeżeń w obsługiwanym zakresie', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('region', { name: 'Zakres danych zewnętrznych' }).getByText('Zagrożenie poza zakresem źródła', { exact: false })
  ).toBeVisible();
});
test('active real warning retains its actual provider attribution', async ({ page }) => {
  await show(page, 'active');
  await expect(page.getByRole('heading', { name: 'Silny wiatr w regionie' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Warunki wymagające uwagi' })).toBeVisible();
});
for (const mode of ['empty', 'warning', 'test-unavailable', 'test-stale'])
  test(`synthetic scenario ${mode} stays separate from real coverage and counts`, async ({ page }) => {
    await show(page, mode);
    const preview = page.getByRole('region', { name: 'Podgląd źródła testowego' });
    await expect(preview.getByText('Źródło testowe — dane syntetyczne', { exact: true })).toBeVisible();
    await expect(preview.getByText(mode.replace('test-', ''), { exact: true })).toBeVisible();
    await expect(official(page).locator('.official-warning-count')).toHaveText('—');
    await expect(page.getByRole('region', { name: 'Podsumowanie zagrożeń zewnętrznych' }).getByText('1 aktywnych warunków')).toHaveCount(0);
  });
test('retained checkpoint danger survives disabled monitoring without a CEXT aggregate', async ({ page }) => {
  await show(page, 'retained');
  await expect(page.getByRole('heading', { name: 'Warunki wymagające uwagi' })).toBeVisible();
  await expect(page.getByText('Zachowane rzeczywiste zagrożenie', { exact: false })).toBeVisible();
  await expect(page.getByText('Okno biura', { exact: true })).toBeVisible();
  await expect(official(page).locator('.official-warning-count')).toHaveText('—');
});
test('disconnect invalidates current categories and synthetic preview', async ({ page }) => {
  await show(page, 'warning');
  await page.evaluate(() => window.__safetyHomeMock.update({ connectionStatus: 'disconnected', ready: false }));
  await expect(official(page).getByText('Brak aktualnego stanu konfiguracji', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Podgląd źródła testowego' })).toHaveCount(0);
});
