import { expect, test } from '@playwright/test';

test('configuration provides a disabled scenario and nested check editor', async ({ page }) => {
  await page.goto('/#/configuration/safety_routines');
  const section = page.locator('.configuration-section:visible');
  await section.getByLabel('Nowy identyfikator: Scenariusze bezpieczeństwa').fill('Bedtime');
  await section.getByRole('button', { name: '+ Dodaj obiekt', exact: true }).click();
  await section.locator('summary').filter({ hasText: 'Bedtime' }).click();
  await expect(section.getByRole('combobox', { name: /^Scenariusz włączony/ })).toHaveValue('false');
  await section.getByLabel('Nazwa scenariusza').fill('Przed snem');
  await expect(section.getByLabel('Nowy identyfikator: Sprawdzenia')).toBeVisible();
  await expect(
    page.getByRole('navigation', { name: 'Podstrony konfiguracji' }).getByRole('link', { name: 'Scenariusze bezpieczeństwa' })
  ).toHaveAttribute('aria-current', 'page');
});

test('manual routines preserve reports and distinguish problems from unavailable evidence', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/#/safety-routines');
  await expect(page.getByRole('button', { name: 'Sprawdź teraz' })).toBeEnabled();
  await page.getByRole('button', { name: 'Sprawdź teraz' }).click();
  const report = page.getByRole('region', { name: 'Przed snem' });
  await expect(report.getByRole('heading', { name: 'Wykryto problem' })).toBeVisible();
  const reportTitle = report.getByRole('heading', { name: 'Przed snem' });
  await expect
    .poll(() =>
      reportTitle.evaluate(
        title => title.getBoundingClientRect().top - (document.querySelector('.topbar')?.getBoundingClientRect().bottom ?? 0)
      )
    )
    .toBeGreaterThanOrEqual(0);
  await expect(report.getByText('Źródło jest niedostępne', { exact: true }).first()).toBeVisible();
  await expect(report.getByText('Domownicy nie śpią', { exact: true })).toBeVisible();
  const entityId = report.getByText('sensor.demo_activity', { exact: true });
  await expect(entityId).toBeHidden();
  const sleepCheck = report.locator('summary').filter({ hasText: 'Domownicy śpią' });
  await sleepCheck.focus();
  await sleepCheck.press('Enter');
  await expect(entityId).toBeVisible();
  await sleepCheck.press('Enter');
  const power = report.locator('summary').getByText('499 W', { exact: true });
  await expect(power).toBeHidden();
  await report.locator('summary').filter({ hasText: 'Zgodne z oczekiwaniem' }).click();
  await expect(power).toBeVisible();
  await expect(page.getByRole('button', { name: 'Pokaż raport' })).toHaveCount(1);
  await page.getByRole('button', { name: 'Sprawdź teraz' }).click();
  await expect(page.getByRole('button', { name: 'Pokaż raport' })).toHaveCount(2);
  await page.getByRole('button', { name: 'Pokaż raport' }).last().click();
  await expect(report.getByText('Źródło jest niedostępne', { exact: true }).first()).toBeVisible();
  await page.evaluate(() => window.__safetyHomeMock.update({ connectionStatus: 'disconnected', ready: false }));
  await expect(page.getByRole('button', { name: 'Sprawdź teraz' })).toBeDisabled();
  await expect(page.getByText('Brak połączenia. Widoczne raporty są zapisami wcześniejszych kontroli.')).toBeVisible();
  await expect(report.getByText('Źródło jest niedostępne', { exact: true }).first()).toBeVisible();
  if (testInfo.project.name.startsWith('desktop')) await page.setViewportSize({ width: 1100, height: 900 });
  expect(await page.locator('.topbar').evaluate(header => header.scrollWidth <= header.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await report.locator('.routine-report-results').screenshot({ path: testInfo.outputPath('safety-routines.png') });
  expect(errors).toEqual([]);
});

test('transport failure is explicit and never creates a success report', async ({ page }) => {
  await page.goto('/#/safety-routines');
  await expect(page.getByRole('button', { name: 'Sprawdź teraz' })).toBeEnabled();
  await page.evaluate(() => window.__safetyHomeMock.failNextMessage());
  await page.getByRole('button', { name: 'Sprawdź teraz' }).click();
  await expect(page.getByRole('alert')).toContainText('Nie udało się potwierdzić');
  await expect(page.getByRole('button', { name: 'Pokaż raport' })).toHaveCount(0);
});
