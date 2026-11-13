import { expect, test, type Page } from '@playwright/test';

async function showCoverage(page: Page, status: string, options: { active?: boolean; peerFailed?: boolean; providers?: string[] } = {}) {
  await page.addInitScript(() => localStorage.setItem('safetyhome.view-mode', 'advanced'));
  await page.route('**/*', route => (new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort()));
  await page.goto('/#/external-hazards');
  await page.waitForFunction(() => Boolean(window.__safetyHomeMock));
  await page.evaluate(
    ({ status, options }) => {
      const entities = window.__safetyHomeMock.snapshot();
      for (const id of Object.keys(entities)) if (id.startsWith('sensor.external_provider_')) delete entities[id];
      entities['sensor.external_hazard_state'] = {
        state: options.active ? 'warning' : status === 'unavailable' ? 'unavailable' : 'clear',
        attributes: {
          enabled_providers: ['RegionalWarningsApiComponent', ...(options.peerFailed ? ['PeerRegionalWarningsApiComponent'] : [])],
          official_warnings_configured: status !== 'not_configured',
          active_hazards: options.active ? ['wind'] : [],
          coverage_details: [
            { capability: 'WeatherPointModel', hazard: 'wind', providers: ['Weather'], status: 'available' },
            {
              capability: 'OfficialWeatherWarnings',
              hazard: 'wind',
              providers: options.providers ?? ['RegionalWarningsApiComponent'],
              status,
            },
          ],
        },
      };
      if (status !== 'not_configured')
        entities['sensor.external_provider_regional'] = {
          state: status === 'unavailable' ? 'unavailable' : status === 'awaiting_evidence' ? 'stale' : 'ok',
          attributes: {
            friendly_name: 'Ostrzeżenia regionalne',
            provider: 'RegionalWarningsApiComponent',
            capability: 'OfficialWeatherWarnings',
            hazards: ['wind'],
            warnings: options.active
              ? [
                  {
                    id: 'regional-wind',
                    event_name: 'Silny wiatr w regionie',
                    content: 'Zabezpiecz otwarte wejścia.',
                    locally_applicable: true,
                    regions: ['BE'],
                    degree: '2',
                  },
                ]
              : [],
          },
        };
      if (options.peerFailed)
        entities['sensor.external_provider_peer'] = {
          state: 'schema_error',
          attributes: {
            friendly_name: 'Drugie źródło regionalne',
            provider: 'PeerRegionalWarningsApiComponent',
            capability: 'OfficialWeatherWarnings',
            hazards: ['wind'],
            warnings: [],
          },
        };
      window.__safetyHomeMock.update({ entities, connectionStatus: 'connected', ready: true });
    },
    { status, options }
  );
}

for (const [status, label] of [
  ['not_configured', 'Nie skonfigurowano źródła'],
  ['unsupported', 'Zagrożenie poza zakresem źródła'],
  ['awaiting_evidence', 'Oczekiwanie na dane'],
  ['unavailable', 'Brak wiarygodnych danych'],
  ['available', 'Dane dostępne'],
  ['no_current_warnings', 'Brak bieżących ostrzeżeń w obsługiwanym zakresie'],
])
  test(`coverage presents ${status} independently of model weather`, async ({ page }) => {
    await showCoverage(page, status, { providers: status === 'not_configured' ? [] : undefined });
    const coverage = page.getByRole('region', { name: 'Zakres danych zewnętrznych' });
    await expect(coverage.getByText(label, { exact: false }).last()).toBeVisible();
    await expect(coverage.getByText('Dane dostępne', { exact: false }).first()).toBeVisible();
  });

test('active regional warnings remain visible alongside failed same-capability peer', async ({ page }) => {
  await showCoverage(page, 'available', {
    active: true,
    peerFailed: true,
    providers: ['RegionalWarningsApiComponent', 'PeerRegionalWarningsApiComponent'],
  });
  await expect(page.getByRole('heading', { name: 'Warunki wymagające uwagi' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Silny wiatr w regionie' })).toBeVisible();
  await expect(page.getByText('Drugie źródło regionalne', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Zakres danych zewnętrznych' }).getByText('Dane dostępne', { exact: false })).toHaveCount(
    2
  );
  await expect(page.getByText('Brak bieżących ostrzeżeń w obsługiwanym zakresie', { exact: false })).toHaveCount(0);
});
