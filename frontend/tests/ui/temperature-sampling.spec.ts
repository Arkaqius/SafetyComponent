import { expect, test } from '@playwright/test';
import type { EntityMap } from '../../src/domain/safety';

test('temperature sampling does not add a second global startup notice', async ({ page }) => {
  await page.route('**/*', route => (new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort()));
  await page.goto('/');
  await expect(page.locator('.topbar')).toBeVisible();
  await page.evaluate(() => {
    const api = (window as unknown as { __safetyHomeMock: { snapshot(): EntityMap; update(value: { entities: EntityMap }): void } })
      .__safetyHomeMock;
    const entities = api.snapshot();
    entities['sensor.safety_app_health'] = { state: 'unavailable', attributes: {} };
    entities['sensor.safety_evaluation_progress'] = { state: 'unavailable', attributes: {} };
    entities['sensor.fault_startup_placeholder'] = { state: 'unavailable', attributes: { friendly_name: 'Testowy wpis rozruchu' } };
    entities['sensor.fault_startup_cpu'] = {
      state: 'UNEVALUABLE',
      attributes: { friendly_name: 'Testowa diagnostyka CPU', category: 'D', level: 3, active: false },
    };
    api.update({ entities });
    window.location.hash = '#/fault-management';
  });
  const startupBanner = page.getByRole('complementary', { name: 'Rozruch monitoringu' });
  await expect(startupBanner).toContainText('Oczekiwanie na dane monitoringu');
  await expect(startupBanner.locator('.startup-countdown')).toHaveCount(0);
  await expect(page.getByText('Testowy wpis rozruchu', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Testowa diagnostyka CPU', { exact: true })).toHaveCount(0);
  await page.evaluate(() => {
    const api = (window as unknown as { __safetyHomeMock: { snapshot(): EntityMap; update(value: { entities: EntityMap }): void } })
      .__safetyHomeMock;
    const entities = api.snapshot();
    const now = new Date().toISOString();
    entities['sensor.safety_app_health'] = { state: 'running', attributes: {} };
    entities['sensor.safety_evaluation_progress'] = {
      state: 'observed',
      attributes: { startup: { phase: 'settling', duration_seconds: 600, remaining_seconds: 600, reported_at: now } },
    };
    entities['sensor.sampling_diagnostic'] = {
      state: 'unavailable',
      attributes: { entity_key: 'TemperatureForecastOffice', source_entity_id: 'sensor.sampling_temperature_rate' },
    };
    entities['sensor.sampling_temperature'] = { state: '22', attributes: {} };
    entities['sensor.sampling_temperature_rate'] = {
      state: 'unknown',
      attributes: { sampling_status: 'waiting_for_samples', source_entity_id: 'sensor.sampling_temperature', sample_interval_seconds: 900 },
    };
    api.update({ entities });
  });
  const banner = page.getByRole('complementary', { name: 'Gotowość prognozy temperatury' });
  const oldNotice = page.getByText('Prognoza temperatury · oczekiwanie na próbki', { exact: true });
  await expect(banner).toHaveCount(0);
  await expect(oldNotice).toHaveCount(0);
  await expect(startupBanner).toBeVisible();
  await page.evaluate(() => {
    window.location.hash = '#/temperature';
  });
  await expect(startupBanner).toBeVisible();
  await page.evaluate(() => {
    const api = (window as unknown as { __safetyHomeMock: { snapshot(): EntityMap; update(value: { entities: EntityMap }): void } })
      .__safetyHomeMock;
    const entities = api.snapshot();
    entities['sensor.safety_evaluation_progress'].attributes.startup = {
      phase: 'complete',
      duration_seconds: 600,
      remaining_seconds: 0,
      reported_at: new Date().toISOString(),
    };
    api.update({ entities });
  });
  await expect(banner).toHaveCount(0);
  await expect(oldNotice).toHaveCount(0);
  await expect(startupBanner).toHaveCount(0);
});
