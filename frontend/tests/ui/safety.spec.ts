import { expect, test, type Page } from '@playwright/test';
import type { EntityMap } from '../../src/domain/safety';

interface MockMessage {
  type: string;
  event_type?: string;
  event_data?: Record<string, unknown>;
}

interface MockApi {
  snapshot(): EntityMap;
  update(values: { entities?: EntityMap; connectionStatus?: string; ready?: boolean }): void;
  messages: MockMessage[];
  failNextMessage(): void;
  setHistory(entityId: string, payload: unknown): void;
}

declare global {
  interface Window {
    __safetyHomeMock: MockApi;
  }
}

async function openMock(page: Page, route = '/') {
  // Keep every browser request on the local demo server, including failed runs.
  await page.route('**/*', routeHandler => {
    const url = new URL(routeHandler.request().url());
    return url.hostname === '127.0.0.1' ? routeHandler.continue() : routeHandler.abort();
  });
  await page.goto(`/#${route}`);
  await expect(page.locator('.topbar')).toBeVisible();
  await page.waitForFunction(() => Boolean(window.__safetyHomeMock));
}

test('help follows hover and keyboard focus without activating adjacent controls', async ({ page, isMobile }) => {
  await openMock(page);
  const trigger = page.getByRole('button', { name: 'Wyjaśnienie: Pokrycie monitoringu', exact: true });
  if (!isMobile) {
    await trigger.hover();
    const panel = page.getByRole('tooltip');
    await expect(panel).toContainText('Nie jest liczbą wszystkich urządzeń');
    await panel.hover();
    await expect(panel).toBeVisible();
    await page.mouse.move(0, 0);
    await expect(panel).toBeHidden();
  }
  await trigger.focus();
  await expect(page.getByRole('tooltip')).toBeVisible();
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');
  await expect(trigger).toHaveAttribute('aria-describedby', /.+/);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('tooltip')).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await page.keyboard.press('Space');
  await expect(page.getByRole('tooltip')).toBeVisible();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('tooltip')).toHaveCount(0);

  const averageHelp = page.getByRole('button', { name: 'Wyjaśnienie: Średnia temperatura', exact: true });
  await averageHelp.click();
  await expect(page.getByRole('tooltip')).toContainText('Średnia arytmetyczna');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(await page.evaluate(() => window.__safetyHomeMock.messages.filter(message => message.type === 'fire_event'))).toEqual([]);
  expect(await page.locator('button button').count()).toBe(0);
});

test('help supports tap, light dismissal and viewport boundaries', async ({ page, isMobile }, testInfo) => {
  await openMock(page, '/temperature');
  const trigger = page.getByRole('button', { name: 'Wyjaśnienie: Tempo zmiany temperatury', exact: true }).first();
  await trigger.scrollIntoViewIfNeeded();
  if (isMobile) await trigger.tap();
  else await trigger.click();
  await expect(page.getByRole('tooltip')).toContainText('°C/min');
  const bounds = await page.getByRole('tooltip').boundingBox();
  const viewport = page.viewportSize()!;
  expect(bounds!.x).toBeGreaterThanOrEqual(12);
  expect(bounds!.y).toBeGreaterThanOrEqual(12);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width - 12);
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(viewport.height - 12);
  if (isMobile) {
    const target = await trigger.boundingBox();
    expect(target!.width).toBeGreaterThanOrEqual(44);
    expect(target!.height).toBeGreaterThanOrEqual(44);
  }
  await page.screenshot({ path: testInfo.outputPath('tooltip.png'), scale: 'css' });
  if (isMobile) await trigger.tap();
  else await trigger.click();
  await expect(page.getByRole('tooltip')).toHaveCount(0);
  if (isMobile) await trigger.tap();
  else await trigger.click();
  await expect(page.getByRole('tooltip')).toBeVisible();
  await page.locator('.temperature-reading').first().click();
  await expect(page.getByRole('tooltip')).toHaveCount(0);
});

test('source observations use the same accessible help and scrolling dismisses it', async ({ page, isMobile }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await openMock(page, '/external-hazards');
  const trigger = page.getByRole('button', { name: /^Wyjaśnienie: Monitorowane dane:/ }).first();
  if (isMobile) await trigger.tap();
  else await trigger.click();
  await expect(page.getByRole('tooltip')).toBeVisible();
  await expect(page.getByRole('tooltip')).not.toContainText('sensor.');
  await page.evaluate(() => window.scrollBy(0, -100));
  await expect(page.getByRole('tooltip')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('help is reachable from navigation and explains confirmations without sending an action', async ({ page, isMobile }, testInfo) => {
  await openMock(page);
  await expect(page.locator('.topbar')).not.toContainText('Tryb demonstracyjny');
  await expect(page.locator('.topbar')).not.toContainText('Lokalne dane testowe');
  if (isMobile) await page.getByRole('button', { name: 'Otwórz nawigację', exact: true }).click();
  await page.getByRole('link', { name: /^Pomoc Statusy/ }).click();
  await expect(page.getByRole('heading', { name: 'Pomoc i objaśnienia', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Poziomy pilności', exact: true })).toBeVisible();
  await expect(page.locator('.help-demo-note')).toContainText('lokalnych danych testowych');
  const question = page
    .locator('.help-question')
    .filter({ has: page.locator('summary', { hasText: 'Co robi „Potwierdź powiadomienie”?' }) });
  await question.locator('summary').focus();
  await page.keyboard.press('Enter');
  await expect(question.locator('p')).toBeVisible();
  await expect(question).toContainText('Nie usuwa usterki');
  expect(await page.evaluate(() => window.__safetyHomeMock.messages.filter(message => message.type === 'fire_event'))).toEqual([]);
  expect(await page.locator('.help-page').evaluate(element => element.scrollWidth > element.clientWidth)).toBe(false);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
  await page.screenshot({ path: testInfo.outputPath('help.png'), scale: 'css', fullPage: true });
  await page.getByRole('link', { name: 'Sprawdź źródła danych' }).click();
  await expect(page.getByRole('heading', { name: 'Encje i urządzenia', exact: true, level: 1 })).toBeVisible();
});

test('entity modal traps keyboard focus and restores its trigger', async ({ page }) => {
  await openMock(page);
  const trigger = page.locator('.safety-hero');
  await trigger.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Zamknij szczegóły encji' })).toBeFocused();
  for (let index = 0; index < 12; index++) {
    await page.keyboard.press('Tab');
    expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press('Shift+Tab');
  expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test('all monitoring pages render without an unhandled exception', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  for (const route of [
    '/temperature',
    '/safety-doors',
    '/internal-hazards',
    '/external-hazards',
    '/entities',
    '/history',
    '/help',
    '/fault-management',
  ]) {
    await openMock(page, route);
    await expect(page.locator('.page-stack')).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test('topbar reflects aggregate hazard and incomplete evidence even without an active fault card', async ({ page }) => {
  await openMock(page);
  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    for (const [id, entity] of Object.entries(entities)) {
      if (id.startsWith('sensor.fault_')) {
        entity.state = 'PASS';
        entity.attributes.active = false;
        entity.attributes.shadowed_by = [];
      }
      if (id.startsWith('sensor.recovery_')) {
        entity.state = 'DO_NOT_PERFORM';
        entity.attributes.proposals = [];
      }
    }
    entities['sensor.safetysystem_state'].state = 'hazard';
    window.__safetyHomeMock.update({ entities });
  });
  const safety = page.locator('.topbar .status-badge').first();
  await expect(safety).not.toHaveClass(/status-safe/);
  await expect(safety).not.toHaveText('Brak aktywnych usterek');
  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    entities['sensor.safetysystem_state'].state = 'no_faults';
    entities['sensor.fault_riskytemperature'].state = 'unknown';
    window.__safetyHomeMock.update({ entities });
  });
  await expect(safety).toContainText(/niepełne/i);
  await expect(safety).not.toHaveClass(/status-safe/);
});

test('disconnect and suspended connection label retained readings as cached evidence', async ({ page }) => {
  await openMock(page, '/temperature');
  const reading = page.locator('.temperature-reading').first();
  await expect(reading).toBeVisible();
  const retained = (await reading.textContent()) ?? '';
  await page.evaluate(() => window.__safetyHomeMock.update({ connectionStatus: 'disconnected', ready: false }));
  await expect(page.locator('.topbar')).toContainText(/brak połączenia|rozłączono/i);
  await expect(page.locator('.connection-banner')).toBeVisible();
  await expect(reading).toHaveText(retained);
  await expect(page.locator('.topbar .status-safe')).toHaveCount(0);
  await page.evaluate(() => window.__safetyHomeMock.update({ connectionStatus: 'connected', ready: false }));
  await expect(page.locator('.connection-banner')).toBeVisible();
  await page.evaluate(() => window.__safetyHomeMock.update({ connectionStatus: 'suspended', ready: true }));
  await expect(page.locator('.connection-banner')).toContainText('Połączenie wstrzymane');
  await expect(page.locator('.topbar .status-safe')).toHaveCount(0);
  await expect(page.locator('.connection-banner')).toBeVisible();
  await expect(reading).toHaveText(retained);
});

test('dashboard puts readable incident and instructions before temperature statistics', async ({ page }, testInfo) => {
  await openMock(page);
  const instruction = page.locator('.recovery-card-copy p').first();
  await expect(page.locator('.hero-incident')).toBeVisible();
  await expect(instruction).toBeVisible();
  const instructionBox = await instruction.boundingBox();
  const statisticsBox = await page.locator('.summary-grid').boundingBox();
  expect(instructionBox!.y).toBeLessThan(statisticsBox!.y);
  expect(await instruction.evaluate(element => Number.parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(16);
  if (testInfo.project.name.startsWith('mobile')) expect(instructionBox!.y + instructionBox!.height).toBeLessThan(844);
  await page.screenshot({ path: testInfo.outputPath('dashboard.png'), scale: 'css' });
});

test('acknowledgement retries an event failure and never clears the fault', async ({ page }) => {
  await openMock(page);
  const fault = page.locator('.fault-card[data-entity-id="sensor.fault_riskytemperature"]');
  const button = fault.getByRole('button', { name: 'Potwierdź powiadomienie', exact: true });
  await page.evaluate(() => window.__safetyHomeMock.failNextMessage());
  await button.click();
  await expect(fault).toContainText('Nie udało się wysłać potwierdzenia');
  await expect(button).toBeEnabled();
  await button.click();
  await expect(fault.getByRole('button', { name: /Potwierdzono|Potwierdzenie wysłane/ })).toBeDisabled();
  expect(await page.evaluate(() => window.__safetyHomeMock.snapshot()['sensor.fault_riskytemperature'].state)).toBe('FAIL');
  expect(await page.evaluate(() => window.__safetyHomeMock.snapshot()['sensor.fault_riskytemperature'].attributes.active)).toBe(true);
  const acknowledgements = await page.evaluate(() =>
    window.__safetyHomeMock.messages.filter(message => message.event_type === 'safety_notification_acknowledge')
  );
  expect(acknowledgements.length).toBeGreaterThanOrEqual(1);
  expect(acknowledgements.at(-1)?.event_data).toEqual({ tag: 'demo-active-temperature' });
});

test('gate confirmation sends only current proposal ID and token after explicit confirmation', async ({ page }) => {
  await openMock(page);
  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    entities['sensor.recovery_testgate'] = {
      state: 'AWAITING_CONFIRMATION',
      attributes: {
        friendly_name: 'Zamknięcie bramy testowej',
        proposals: [
          {
            proposal_id: 'test-current-proposal',
            status: 'AWAITING_CONFIRMATION',
            instruction: 'Zamknij bramę testową',
            execution_policy: 'user_confirmed',
            confirmation_token: 'test-onetime-token',
            expires_at: Date.now() / 1000 + 600,
          },
        ],
      },
    };
    window.__safetyHomeMock.update({ entities });
  });
  const confirm = page.getByRole('button', { name: 'Potwierdź zamknięcie', exact: true });
  page.once('dialog', dialog => dialog.dismiss());
  await confirm.click();
  expect(
    await page.evaluate(() => window.__safetyHomeMock.messages.filter(message => message.event_type === 'safety_recovery_confirm'))
  ).toHaveLength(0);
  page.once('dialog', dialog => dialog.accept());
  await confirm.click();
  await expect
    .poll(() =>
      page.evaluate(() => window.__safetyHomeMock.messages.filter(message => message.event_type === 'safety_recovery_confirm').length)
    )
    .toBe(1);
  const message = await page.evaluate(() => window.__safetyHomeMock.messages.find(item => item.event_type === 'safety_recovery_confirm'));
  expect(message).toEqual({
    type: 'fire_event',
    event_type: 'safety_recovery_confirm',
    event_data: { proposal_id: 'test-current-proposal', confirmation_token: 'test-onetime-token' },
  });
  expect(await page.evaluate(() => window.__safetyHomeMock.messages.some(item => item.type === 'call_service'))).toBe(false);
});

test('history changes category and range without carrying another entity state across cards', async ({ page }) => {
  await openMock(page, '/history');
  const history = page.locator('.history-grid');
  await expect(history).toBeVisible();
  await page.getByRole('group', { name: 'Kategoria historii' }).getByRole('button', { name: 'Działania', exact: true }).click();
  await expect(history.locator('.history-card')).not.toHaveCount(0);
  await expect(history.locator('.history-fault')).toHaveCount(0);
  await page.getByRole('combobox', { name: /^Zakres/ }).selectOption('6');
  await expect(page.getByRole('combobox', { name: /^Zakres/ })).toHaveValue('6');
  await page.getByRole('group', { name: 'Kategoria historii' }).getByRole('button', { name: 'System', exact: true }).click();
  await expect(history.locator('.history-recovery')).toHaveCount(0);
  await expect(history.locator('.history-system')).not.toHaveCount(0);
  await expect(page.locator('.notification-history')).toBeVisible();
});

test('empty history stays empty and malformed history remains an error after a range change', async ({ page }) => {
  await openMock(page);
  await page.evaluate(() => window.__safetyHomeMock.setHistory('sensor.safetysystem_state', { states: {} }));
  await page.locator('.safety-hero').click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.locator('.history-empty')).toBeVisible();
  await expect(dialog.locator('.entity-history-segment')).toHaveCount(0);
  await page.evaluate(() => {
    window.__safetyHomeMock.setHistory('sensor.safetysystem_state', {
      states: { 'sensor.safetysystem_state': [{ s: 'no_faults', lu: 'invalid timestamp' }] },
    });
  });
  await dialog.locator('select').selectOption('6');
  await expect(dialog.getByRole('status')).toContainText(/nieprawidłow|błędn/i);
  await expect(dialog.locator('.entity-history-segment')).toHaveCount(0);
  await expect(dialog.locator('.history-empty')).toHaveCount(0);
});

test('switching entities starts a new history stream without another entity past state', async ({ page }) => {
  await openMock(page);
  await page.evaluate(() => {
    window.__safetyHomeMock.setHistory('sensor.safetysystem_state', {
      states: { 'sensor.safetysystem_state': [{ s: 'historical-only-system', lu: Date.now() / 1000 - 3600 }] },
    });
    window.__safetyHomeMock.setHistory('sensor.fault_riskytemperature', { states: {} });
  });
  await page.locator('.safety-hero').click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('historical-only-system');
  await page.keyboard.press('Escape');
  await page
    .locator('.fault-card[data-entity-id="sensor.fault_riskytemperature"]')
    .getByRole('button', { name: /Pełne szczegóły/ })
    .click();
  await expect(dialog.locator('.history-empty')).toBeVisible();
  await expect(dialog).not.toContainText('historical-only-system');
  await expect(dialog.locator('.entity-history-segment')).toHaveCount(0);
});
