import { expect, test } from '@playwright/test';
import type { EntityMap } from '../../src/domain/safety';

test('temperature sample notice persists across pages after startup, then ends on rate data', async ({ page }, testInfo) => {
  await page.route('**/*', route => (new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort()));
  await page.goto('/');
  await expect(page.locator('.topbar')).toBeVisible();
  await page.evaluate(() => {
    const api = (window as unknown as { __safetyHomeMock: { snapshot(): EntityMap; update(value: { entities: EntityMap }): void } })
      .__safetyHomeMock;
    const entities = api.snapshot();
    const now = new Date().toISOString();
    entities['sensor.safety_app_health'] = { state: 'running', attributes: {} };
    entities['sensor.safety_evaluation_progress'] = {
      state: 'observed',
      attributes: { startup: { phase: 'complete', duration_seconds: 600, remaining_seconds: 0, reported_at: now } },
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
  await expect(banner).toContainText('oczekiwanie na próbki');
  await expect(banner).toContainText('15 min');
  await expect(page.getByRole('complementary', { name: 'Rozruch monitoringu' })).toHaveCount(0);
  await page.evaluate(() => {
    window.location.hash = '#/temperature';
  });
  await expect(banner).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('temperature-sampling.png'), fullPage: true });
  await page.evaluate(() => {
    const api = (window as unknown as { __safetyHomeMock: { snapshot(): EntityMap; update(value: { entities: EntityMap }): void } })
      .__safetyHomeMock;
    const entities = api.snapshot();
    entities['sensor.sampling_temperature_rate'] = { state: '0', attributes: { sampling_status: 'ready' } };
    api.update({ entities });
  });
  await expect(banner).toHaveCount(0);
});
