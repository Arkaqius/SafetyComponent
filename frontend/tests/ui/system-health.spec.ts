import { expect, test } from '@playwright/test';

test('battery tabs support deep links, status filtering, sorting, paging and back navigation', async ({ page }, testInfo) => {
  await page.route('**/api/functional-safety', route =>
    route.fulfill({
      json: {
        schema_version: 1,
        generated_at: new Date().toISOString(),
        overall_state: 'attention',
        diagnostics: {
          remote_batteries: Object.fromEntries(
            Array.from({ length: 56 }, (_, index) => [
              `device-${index}`,
              {
                friendly_name: index === 0 ? 'Zepsuty odczyt' : `Czujnik ${String(index).padStart(2, '0')}`,
                status: index === 0 ? 'unknown' : index === 1 ? 'low' : 'current',
                percentage: index === 0 ? null : index === 1 ? 1 : index + 16,
                source_entities: [`sensor.test_${index}_battery`],
                sources: [
                  {
                    entity_id: `sensor.test_${index}_battery`,
                    state: index === 0 ? 'unavailable' : String(index === 1 ? 1 : index + 16),
                    unit: '%',
                  },
                ],
              },
            ])
          ),
        },
      },
    })
  );
  await page.goto('/#/functional-safety?tab=batteries');
  const batteries = page.getByRole('tabpanel', { name: /^Baterie/ });
  await expect(batteries.getByRole('heading', { name: 'Baterie urządzeń' })).toBeVisible();
  await expect(batteries).toContainText('Pełna diagnostyka z backendu');
  const names = batteries.locator('tbody tr:not([hidden]) .entity-name-button strong');
  await expect(names).toHaveCount(50);
  await expect(names.nth(0)).toHaveText('Czujnik 01');
  await expect(names.nth(1)).toHaveText('Zepsuty odczyt');
  await batteries.getByRole('button', { name: 'Następna', exact: true }).click();
  await expect(names).toHaveCount(6);
  await batteries.getByRole('button', { name: 'Brak oceny (1)', exact: true }).click();
  await expect(names).toHaveCount(1);
  await expect(names.first()).toHaveText('Zepsuty odczyt');
  await expect(batteries.locator('.battery-level')).toHaveText('—');
  await batteries.getByRole('button', { name: 'Wszystkie (56)', exact: true }).click();
  await batteries.getByLabel('Sortowanie baterii').selectOption('percentage-desc');
  await expect(names.first()).toHaveText('Czujnik 55');
  await batteries.getByLabel('Szukaj baterii').fill('test_55_battery');
  await expect(names).toHaveCount(1);
  await names.first().click();
  await expect(batteries.getByRole('region', { name: 'Szczegóły baterii: Czujnik 55' })).toContainText('sensor.test_55_battery');
  await page.getByRole('tab', { name: /^Monitorowane encje/ }).click();
  await expect(batteries).toBeHidden();
  await page.goBack();
  await expect(batteries.getByLabel('Szukaj baterii')).toHaveValue('test_55_battery');
  await expect(names).toHaveCount(1);
  await page.getByRole('tab', { name: /^Baterie/ }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: 'Platforma', exact: true })).toBeFocused();
  await expect(page.getByRole('tabpanel', { name: 'Platforma', exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('tab', { name: 'Platforma', exact: true })).toHaveAttribute('aria-selected', 'true');
  await page.getByRole('tab', { name: /^Baterie/ }).click();
  await page.screenshot({ path: testInfo.outputPath('battery-list.png'), fullPage: true, scale: 'css' });
  await page.screenshot({ path: testInfo.outputPath('battery-list-viewport.png'), scale: 'css' });
});

test('missing full diagnostics keeps omission warning visible through empty battery filters', async ({ page }) => {
  await page.route('**/api/functional-safety', route => route.fulfill({ status: 503 }));
  await page.goto('/#/functional-safety?tab=batteries');
  await page.waitForFunction(() => Boolean(window.__safetyHomeMock));
  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    entities['sensor.functional_safety_sources'].attributes.remote_battery_count = 56;
    entities['sensor.functional_safety_sources'].attributes.remote_battery_omitted_count = 55;
    window.__safetyHomeMock.update({ entities });
  });
  const panel = page.getByRole('tabpanel', { name: /^Baterie/ });
  await expect(panel).toContainText('Pominięte baterie: 55 z 56');
  await panel.getByLabel('Szukaj baterii').fill('nieistniejąca');
  await expect(panel).toContainText('Brak baterii spełniających filtry');
  await expect(panel).toContainText('Pominięte baterie: 55 z 56');
  expect(await page.evaluate(() => window.__safetyHomeMock.messages.filter(message => message.type === 'fire_event'))).toEqual([]);
});
