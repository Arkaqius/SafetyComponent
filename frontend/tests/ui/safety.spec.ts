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

async function openMock(page: Page, route = '/', viewMode: 'basic' | 'advanced' | null = 'advanced') {
  await page.addInitScript(mode => {
    if (mode && !window.localStorage.getItem('safetyhome.view-mode')) window.localStorage.setItem('safetyhome.view-mode', mode);
  }, viewMode);
  // Keep every browser request on the local demo server, including failed runs.
  await page.route('**/*', routeHandler => {
    const url = new URL(routeHandler.request().url());
    return url.hostname === '127.0.0.1' ? routeHandler.continue() : routeHandler.abort();
  });
  await page.goto(`/#${route}`);
  await expect(page.locator('.topbar')).toBeVisible();
  await page.waitForFunction(() => Boolean(window.__safetyHomeMock));
}

test('generic heating inputs stay readable and retained values lose current status on disconnect', async ({ page }) => {
  await openMock(page, '/heating');
  await page.evaluate(() =>
    window.__safetyHomeMock.update({
      entities: {
        'sensor.heating_system_main': {
          state: 'degraded',
          attributes: {
            friendly_name: 'Kotłownia',
            phase_label: 'Nieznana faza pracy',
            coverage_label: 'Częściowe pokrycie',
            inputs: [
              {
                label: 'Temperatura zasilania',
                source_name: 'Kocioł — zasilanie',
                value_label: '35 °C',
                quality_label: 'Wiek pomiaru niepotwierdzony',
              },
            ],
            rules: [
              { label: 'Odpowiedź kotła', status: 'INHIBITED', active: false, reasons: ['Trwa podgrzewanie CWU'] },
              { label: 'Żądanie grzania', status: 'NOT_APPLICABLE', active: false, reasons: ['Brak potrzeby grzania'] },
              { label: 'Przegląd ogrzewania', level: 4, status: 'FAIL', active: true, reasons: ['Wymagany przegląd'] },
            ],
          },
        },
      },
      connectionStatus: 'connected',
      ready: true,
    })
  );
  await expect(page.getByRole('heading', { name: 'Kotłownia' })).toBeVisible();
  await expect(page.getByText('35 °C', { exact: true })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'Kocioł — zasilanie', exact: true })).toBeVisible();
  await expect(page.getByText('Ocena wstrzymana', { exact: true })).toBeVisible();
  await expect(page.getByText('Brak potrzeby tej kontroli', { exact: true })).toBeVisible();
  await expect(page.getByText('Informacja nadal aktualna', { exact: false })).toBeVisible();
  await expect(page.getByText('Wykryto nieprawidłowość', { exact: true })).toHaveCount(0);
  await page.evaluate(() => window.__safetyHomeMock.update({ connectionStatus: 'disconnected', ready: false }));
  await expect(page.getByText('35 °C', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Brak bieżących danych', { exact: true }).first()).toBeVisible();
});

test('large history inventories keep only one bounded page subscribed and reset filters', async ({ page }) => {
  await openMock(page, '/history');
  await page.evaluate(() => {
    const entities: EntityMap = {};
    for (let index = 0; index < 437; index++) {
      entities[`sensor.fault_bulk_${String(index).padStart(3, '0')}`] = {
        state: 'PASS',
        attributes: { friendly_name: `Czujnik ${String(index).padStart(3, '0')}`, active: false, level: 3 },
      };
    }
    window.__safetyHomeMock.update({ entities, connectionStatus: 'connected', ready: true });
  });
  await expect(page.locator('.history-card')).toHaveCount(20);
  await expect(page.getByRole('navigation', { name: 'Strony historii encji' })).toContainText('Encje 1–20 z 437');
  await page.getByRole('button', { name: 'Następne encje', exact: true }).click();
  await expect(page.locator('.history-card')).toHaveCount(20);
  await expect(page.locator('[data-entity-id="sensor.fault_bulk_000"]')).toHaveCount(0);
  await expect(page.locator('[data-entity-id="sensor.fault_bulk_020"]')).toBeVisible();
  await page.getByRole('button', { name: 'Usterki', exact: true }).click();
  await expect(page.getByRole('navigation', { name: 'Strony historii encji' })).toContainText('Encje 1–20 z 437');
  await page.getByRole('button', { name: 'System', exact: true }).click();
  await expect(page.locator('.history-card')).toHaveCount(0);
});

test('L4 stays informational while L3 warnings still change the overall state', async ({ page }, testInfo) => {
  await openMock(page);
  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    for (const id of Object.keys(entities)) {
      if (id.startsWith('sensor.fault_') || id.startsWith('sensor.recovery_')) delete entities[id];
    }
    entities['sensor.safety_app_health'] = { state: 'running', attributes: {} };
    entities['sensor.safetysystem_state'] = { state: 'information', attributes: {} };
    entities['sensor.fault_battery_notice'] = {
      state: 'FAIL',
      attributes: {
        fault_id: 'BatteryNotice',
        friendly_name: 'Bateria pilota',
        level: 4,
        active: true,
        category: 'D',
        latched: false,
        contributors: ['battery_reading'],
        active_contributors: ['battery_reading'],
      },
    };
    entities['sensor.recovery_battery_notice'] = {
      state: 'TO_PERFORM',
      attributes: {
        proposals: [{ proposal_id: 'battery', fault_id: 'BatteryNotice', status: 'TO_PERFORM', instruction: 'Sprawdź baterię pilota' }],
      },
    };
    window.__safetyHomeMock.update({ entities, connectionStatus: 'connected', ready: true });
  });
  const hero = page.locator('.safety-hero');
  const notice = page.locator('[data-entity-id="sensor.fault_battery_notice"]');
  await expect(hero).toHaveClass(/hero-safe/);
  await expect(hero).toContainText('System bezpieczny');
  await expect(hero).toContainText('1 informacja do sprawdzenia');
  await expect(hero.locator('.hero-incident')).toHaveCount(0);
  await expect(page.locator('.fault-panel .count-badge-alert')).toHaveCount(0);
  await expect(page.locator('.fault-panel .panel-header')).toContainText('1 informacja');
  await expect(notice).toHaveClass(/fault-info/);
  await expect(notice).toContainText('Informacja potwierdzona');
  await expect(notice.locator('summary .status-danger, summary .status-critical')).toHaveCount(0);
  await expect(notice.locator('.fault-contributor-active')).toHaveCSS('border-color', 'rgb(111, 181, 255)');
  await expect(notice).toContainText('Sprawdź baterię pilota');
  await page.screenshot({ path: testInfo.outputPath('information-only.png'), fullPage: true, scale: 'css' });

  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    entities['sensor.fault_update_warning'] = {
      state: 'FAIL',
      attributes: { friendly_name: 'Aktualizacja dostępna', level: 3, active: true, category: 'D' },
    };
    window.__safetyHomeMock.update({ entities });
  });
  await expect(hero).toHaveClass(/hero-warning/);
  await expect(hero.getByRole('heading')).toHaveText('Ostrzeżenie');
  await expect(notice).toHaveClass(/fault-info/);
});

test('device contact does not turn an unknown water alarm into a clear alarm', async ({ page }, testInfo) => {
  await openMock(page, '/internal-hazards');
  await page.evaluate(() => {
    const now = new Date().toISOString();
    const entities = window.__safetyHomeMock.snapshot();
    for (const id of Object.keys(entities)) {
      if (id.startsWith('sensor.internal_environment_')) delete entities[id];
    }
    entities['sensor.internal_environment_example_leak'] = {
      state: 'unavailable',
      last_updated: now,
      last_changed: now,
      attributes: {
        friendly_name: 'Example leak detector',
        hazard: 'water_leak',
        source_entity_id: 'binary_sensor.example_leak',
        classification: 'unavailable',
        current_state: 'unknown',
        alarm_active: false,
        health_fault_active: true,
      },
    };
    entities['sensor.entity_health_internal_environment_example_leak'] = {
      state: 'unavailable',
      last_updated: now,
      last_changed: now,
      attributes: { source_entity_id: 'binary_sensor.example_leak', last_contact_at: now },
    };
    window.__safetyHomeMock.update({ entities });
  });
  const card = page.locator('.internal-detector-card');
  await expect(card).toHaveCount(1);
  await expect(card).toContainText('Brak danych alarmowych');
  await expect(card.locator('dl > div').filter({ has: page.getByText('Alarm zagrożenia', { exact: true }) })).toContainText(
    'Nie można ocenić'
  );
  await expect(card.locator('dl > div').filter({ has: page.getByText('Ostatni kontakt urządzenia', { exact: true }) })).not.toContainText(
    'Brak potwierdzonych danych'
  );
  await expect(card).toContainText('Nie można potwierdzić braku zagrożenia');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('water-contact-unknown.png'), fullPage: true, scale: 'css' });
});

test('startup banner counts down on every page, keeps hazards visible and waits for backend completion', async ({ page }, testInfo) => {
  await openMock(page, '/', 'basic');
  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    entities['sensor.safety_evaluation_progress'] = {
      state: 'observed',
      attributes: {
        startup: {
          phase: 'settling',
          duration_seconds: 600,
          remaining_seconds: 600,
          reported_at: new Date().toISOString(),
        },
      },
    };
    window.__safetyHomeMock.update({ entities });
  });
  const banner = page.getByRole('complementary', { name: 'Rozruch monitoringu' });
  await expect(banner).toBeVisible();
  await expect(banner).toContainText('Wykrywanie zagrożeń działa od razu');
  await expect(page.locator('.basic-incident').first()).toBeVisible();
  await expect(banner.locator('.startup-countdown strong')).toHaveText(/^(10:00|9:5\d)$/);
  await page.screenshot({ path: testInfo.outputPath('startup-monitoring.png'), scale: 'css' });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
  await page.goto('/#/fault-management');
  await expect(banner).toBeVisible();
  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    const startup = entities['sensor.safety_evaluation_progress'].attributes.startup as Record<string, unknown>;
    startup.remaining_seconds = 0;
    startup.reported_at = new Date().toISOString();
    window.__safetyHomeMock.update({ entities });
  });
  await expect(banner).toContainText('Oczekiwanie na potwierdzenie');
  await page.evaluate(() => window.__safetyHomeMock.update({ connectionStatus: 'disconnected' }));
  await expect(banner).toContainText('brak aktualnych danych');
  await expect(banner.locator('.startup-countdown strong')).toHaveText('—');
  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    (entities['sensor.safety_evaluation_progress'].attributes.startup as Record<string, unknown>).phase = 'complete';
    window.__safetyHomeMock.update({ entities, connectionStatus: 'connected' });
  });
  await expect(banner).toHaveCount(0);
});

test('basic is the default, fits a phone screen and exposes only the essential brief', async ({ page }, testInfo) => {
  await openMock(page, '/', null);
  await expect(page.getByRole('button', { name: 'Podstawowy', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.basic-dashboard')).toBeVisible();
  await expect(page.locator('.sidebar')).toBeHidden();
  await expect(page.locator('.summary-grid')).toHaveCount(0);
  await expect(page.locator('.fault-card')).toHaveCount(0);
  await expect(page.locator('.basic-incident')).toBeVisible();
  await expect(page.locator('.basic-monitoring')).toBeVisible();
  expect(
    await page
      .locator('.basic-action p')
      .first()
      .evaluate(element => parseFloat(getComputedStyle(element).fontSize))
  ).toBeGreaterThanOrEqual(16);
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(page.viewportSize()!.height + 1);
  await page.screenshot({ path: testInfo.outputPath('basic-dashboard.png'), scale: 'css' });
});

test('configuration searches HA entity names, selects the ID and preserves manual missing bindings', async ({
  page,
  isMobile,
}, testInfo) => {
  await openMock(page, '/configuration/rooms');
  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    entities['sensor.office_demo_temperature'] = {
      state: 'unavailable',
      attributes: { friendly_name: 'Temperatura biura testowego' },
    };
    entities['binary_sensor.office_demo_window'] = {
      state: 'off',
      attributes: { friendly_name: 'Okno biura testowego' },
    };
    window.__safetyHomeMock.update({ entities });
  });
  await page.getByText('LivingRoom', { exact: true }).click();
  const input = page.getByRole('combobox', { name: 'Czujnik temperatury', exact: true });
  await input.fill('biura testowego');
  await expect(page.getByRole('option', { name: /Temperatura biura testowego/ })).toBeVisible();
  await expect(page.getByRole('option', { name: /Okno biura testowego/ })).toHaveCount(0);
  await page.getByRole('option', { name: /Temperatura biura testowego/ }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath('configuration-entity-picker.png'), scale: 'css' });
  await input.press('Enter');
  await expect(input).toHaveValue('sensor.office_demo_temperature');
  await expect(input).toHaveAttribute('aria-expanded', 'false');
  await input.fill('biura testowego');
  const choice = page.getByRole('option', { name: /Temperatura biura testowego/ });
  if (isMobile) await choice.tap();
  else await choice.click();
  await expect(input).toHaveValue('sensor.office_demo_temperature');
  await expect(input).toHaveAttribute('aria-expanded', 'false');
  await input.fill('sensor.not_yet_installed');
  await input.press('Escape');
  await expect(input).toHaveValue('sensor.not_yet_installed');
  await expect(input).toHaveAttribute('aria-expanded', 'false');
  expect(await page.evaluate(() => window.__safetyHomeMock.messages.filter(message => message.type === 'fire_event'))).toEqual([]);
});

test('view preference survives reload and diagnostic links open the expanded view', async ({ page }) => {
  await openMock(page, '/', null);
  await page.getByRole('button', { name: 'Rozszerzony', exact: true }).click();
  await expect(page.locator('.summary-grid')).toBeVisible();
  await page.reload();
  await expect(page.locator('.summary-grid')).toBeVisible();
  await page.getByRole('button', { name: 'Podstawowy', exact: true }).click();
  await page.reload();
  await expect(page.locator('.basic-dashboard')).toBeVisible();
  await page.getByRole('link', { name: 'Pomoc', exact: true }).click();
  await expect(page.locator('.help-page')).toBeVisible();
  await page.getByRole('link', { name: /Sprawdź źródła danych/ }).click();
  await expect(page.getByRole('button', { name: 'Rozszerzony', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Podstawowy', exact: true }).click();
  await expect(page.locator('.basic-dashboard')).toBeVisible();
  expect(await page.evaluate(() => window.__safetyHomeMock.messages.filter(message => message.type === 'fire_event'))).toEqual([]);
});

test('basic retains critical incidents and clearly invalidates cached assessment on suspension', async ({ page }) => {
  await openMock(page, '/', 'basic');
  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    entities['sensor.fault_critical'] = {
      state: 'FAIL',
      attributes: { friendly_name: 'Alarm krytyczny testowy', active: true, level: 1, area_name: 'Garaż' },
    };
    window.__safetyHomeMock.update({ entities });
  });
  await expect(page.locator('.basic-incident')).toContainText('Alarm krytyczny testowy');
  await expect(page.locator('.basic-incident')).toContainText('Garaż');
  await expect(page.locator('.basic-assessment')).toHaveClass(/basic-assessment-critical/);
  await page.evaluate(() => window.__safetyHomeMock.update({ connectionStatus: 'suspended', ready: true }));
  await expect(page.locator('.connection-banner')).toBeVisible();
  await expect(page.locator('.basic-assessment')).not.toHaveClass(/basic-assessment-safe/);
  await expect(page.locator('.basic-incident')).toContainText('Ostatnie znane zdarzenie');
  await expect(page.locator('.basic-monitoring')).toContainText('Odczyty z pamięci');
});

test('basic recommendations use the same expiry guard and modal keyboard boundary', async ({ page }) => {
  await openMock(page, '/', 'basic');
  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    for (const [id, entity] of Object.entries(entities))
      if (id.startsWith('sensor.recovery_')) {
        entity.state = 'DO_NOT_PERFORM';
        entity.attributes.proposals = [];
      }
    entities['sensor.recovery_testgate'] = {
      state: 'AWAITING_CONFIRMATION',
      attributes: {
        friendly_name: 'Zamknięcie bramy testowej',
        proposals: [
          {
            proposal_id: 'basic-proposal',
            status: 'AWAITING_CONFIRMATION',
            instruction: 'Zamknij bramę testową',
            execution_policy: 'user_confirmed',
            confirmation_token: 'basic-token',
            expires_at: Date.now() / 1000 - 1,
          },
        ],
      },
    };
    window.__safetyHomeMock.update({ entities });
  });
  await expect(page.locator('.basic-action')).toContainText('Zalecenie wygasło');
  const opener = page.getByRole('button', { name: 'Wszystkie zalecenia', exact: true });
  await opener.click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('dialog').getByRole('button', { name: 'Zezwól na wykonanie', exact: true })).toBeDisabled();
  for (let index = 0; index < 8; index++) {
    await page.keyboard.press('Tab');
    expect(await page.evaluate(() => !!document.activeElement?.closest('dialog'))).toBe(true);
  }
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(opener).toBeFocused();
  expect(
    await page.evaluate(() => window.__safetyHomeMock.messages.some(message => message.event_type === 'safety_recovery_confirm'))
  ).toBe(false);
});

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
  const toggleAtCurrentPosition = async () => {
    const position = await trigger.boundingBox();
    expect(position).not.toBeNull();
    const x = position!.x + position!.width / 2;
    const y = position!.y + position!.height / 2;
    // Locator auto-scrolling can dismiss the popover before a second tap.
    // Exercise the same visible target without moving the viewport.
    if (isMobile) await page.touchscreen.tap(x, y);
    else await page.mouse.click(x, y);
  };
  await toggleAtCurrentPosition();
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
  await toggleAtCurrentPosition();
  await expect(page.getByRole('tooltip')).toHaveCount(0);
  await toggleAtCurrentPosition();
  await expect(page.getByRole('tooltip')).toBeVisible();
  await page.locator('.temperature-reading').first().click();
  await expect(page.getByRole('tooltip')).toHaveCount(0);
  await toggleAtCurrentPosition();
  await expect(page.getByRole('tooltip')).toBeVisible();
  // Keep artifact capture after the interaction assertions.
  await page.screenshot({ path: testInfo.outputPath('tooltip.png'), scale: 'css' });
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
  await expect(page.getByRole('heading', { name: 'Zdrowie systemu', exact: true, level: 1 })).toBeVisible();
});

test('system health contains monitored entities and batteries without a general HA inventory', async ({ page, isMobile }, testInfo) => {
  await openMock(page, '/entities');
  await expect(page).toHaveURL(/#\/functional-safety$/);
  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    const template = entities['sensor.entity_health_common_outside_temp'];
    for (let index = 3; index < 45; index++) {
      entities[`sensor.entity_health_extra_${index}`] = {
        ...template,
        attributes: {
          ...template.attributes,
          entity_key: `extra_${index}`,
          entity_id: index === 3 ? 'sensor.example_outdoor_temperature' : `sensor.extra_${index}`,
          friendly_name: `Źródło testowe ${index}`,
        },
      };
    }
    entities['sensor.unrelated_unavailable'] = { state: 'unavailable', attributes: { friendly_name: 'Poza monitoringiem' } };
    entities['sensor.entity_monitor_summary'].attributes = { total: 45, healthy: 44, degraded: 0, stale: 1, unavailable: 0 };
    window.__safetyHomeMock.update({ entities });
  });
  await expect(page.getByRole('heading', { name: 'Monitorowane encje (45)', exact: true })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Wszystkie encje' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: /^Encje i urządzenia/ })).toHaveCount(0);
  const monitored = page.getByRole('region', { name: 'Monitorowane encje', exact: true });
  if (isMobile)
    expect(await monitored.locator('.search-field').evaluate(element => element.getBoundingClientRect().height)).toBeLessThan(100);
  await expect(monitored.locator('tbody tr')).toHaveCount(45);
  await expect(monitored).not.toContainText('Poza monitoringiem');
  await monitored.getByRole('button', { name: 'Temperatura zewnętrzna', exact: true }).nth(1).click();
  await expect(monitored.getByRole('heading', { name: 'Temperatura zewnętrzna', exact: true })).toBeVisible();
  await monitored.getByLabel('Wyszukaj', { exact: true }).fill('office');
  await expect(monitored.locator('tbody tr')).toHaveCount(1);
  await monitored.getByRole('button', { name: 'Example office temperature', exact: true }).click();
  await expect(monitored.getByText('Szczegóły monitoringu')).toBeVisible();
  await page.getByRole('tab', { name: /^Baterie/ }).click();
  const batteries = page.getByRole('region', { name: 'Baterie urządzeń', exact: true });
  await expect(batteries.getByRole('button', { name: /^Przykładowy pilot/ })).toBeVisible();
  await batteries.getByRole('button', { name: /^Przykładowy pilot/ }).click();
  await expect(batteries).toContainText('12%');
  await expect(batteries).toContainText('Niska bateria');
  await batteries.getByText('Zaawansowana diagnostyka baterii', { exact: true }).click();
  await expect(batteries.locator('code').filter({ hasText: 'sensor.example_remote_battery' })).toBeVisible();
  expect(await page.evaluate(() => window.__safetyHomeMock.messages.filter(message => message.type === 'fire_event'))).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath('system-health-batteries.png'), scale: 'css' });
  await page.getByRole('tab', { name: /^Monitorowane encje/ }).click();
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
  await page.screenshot({ path: testInfo.outputPath('system-health.png'), scale: 'css', fullPage: true });
  await page.screenshot({ path: testInfo.outputPath('system-health-monitored.png'), scale: 'css' });
  await page.evaluate(() => window.__safetyHomeMock.update({ connectionStatus: 'disconnected', ready: false }));
  await expect(page.getByText(/Poniżej ostatnie znane wyniki/)).toBeVisible();
  await expect(monitored.locator('tbody tr')).toHaveCount(1);
});

test('not evaluated faults remain visible in the attention view', async ({ page }) => {
  await openMock(page);
  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    entities['sensor.fault_pendingbattery'] = {
      state: 'NOT_EVALUATED',
      attributes: {
        friendly_name: 'Nieoceniona bateria testowa',
        active: false,
        fault_category: 'D',
      },
    };
    window.__safetyHomeMock.update({ entities });
  });
  await expect(page.locator('.fault-list').getByText('Nieoceniona bateria testowa', { exact: true })).toBeVisible();
  const card = page.locator('.fault-card').filter({ has: page.getByText('Nieoceniona bateria testowa', { exact: true }) });
  await card.locator(':scope > summary').click();
  await expect(card.locator('dd').getByText('Nieoceniona', { exact: true })).toBeVisible();
});

test('operator monitoring uses HA names and Polish states while raw IDs stay in diagnostics', async ({ page }, testInfo) => {
  await openMock(page, '/functional-safety');
  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    for (const id of Object.keys(entities)) {
      if (id.startsWith('sensor.entity_health_')) delete entities[id];
    }
    entities['binary_sensor.private_window_source'] = {
      state: 'unavailable',
      attributes: { friendly_name: 'Okno sypialni — prawe' },
    };
    entities['sensor.entity_health_private_window'] = {
      state: 'unavailable',
      attributes: {
        entity_id: 'binary_sensor.private_window_source',
        entity_key: 'ExternalOpeningBedroomRightWindow',
        friendly_name: 'Stara nazwa',
        current_state: 'unavailable',
        owners: ['EntityMonitorComponent'],
      },
    };
    window.__safetyHomeMock.update({ entities });
  });
  const monitored = page.getByRole('region', { name: 'Monitorowane encje', exact: true });
  const row = monitored.locator('tbody tr');
  await expect(row).toHaveCount(1);
  await expect(row).toContainText('Okno sypialni — prawe');
  await expect(row).toContainText('Niedostępna');
  await expect(row).not.toContainText('unavailable');
  await expect(row).not.toContainText('binary_sensor.private_window_source');
  await monitored.getByRole('button', { name: 'Okno sypialni — prawe', exact: true }).click();
  const details = monitored.locator('.entity-details-panel');
  await expect(details).toContainText('Monitoring wejść');
  const rawId = details.locator('code').filter({ hasText: 'binary_sensor.private_window_source' });
  await expect(rawId).toBeHidden();
  await page.screenshot({ path: testInfo.outputPath('operator-labels.png'), scale: 'css', fullPage: true });
  await details.getByText('Identyfikator techniczny', { exact: true }).click();
  await expect(rawId).toBeVisible();
  expect(await page.evaluate(() => window.__safetyHomeMock.messages.filter(message => message.type === 'fire_event'))).toEqual([]);
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
    await expect(page.locator('.page-stack').first()).toBeVisible();
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

test('coverage remains unknown until retained entities are ready', async ({ page }) => {
  await openMock(page, '/fault-management');
  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    entities['sensor.safety_coverage_state'] = { state: 'FULL', attributes: {} };
    window.__safetyHomeMock.update({ entities, connectionStatus: 'connected', ready: true });
  });
  const coverage = page.locator('.fault-management-intro .status-badge');
  await expect(coverage).toHaveClass(/status-safe/);
  await page.evaluate(() => window.__safetyHomeMock.update({ ready: false }));
  await expect(coverage).not.toHaveClass(/status-safe/);
  await expect(coverage).toHaveText('Pokrycie nieustalone');
  await page.evaluate(() => window.__safetyHomeMock.update({ connectionStatus: 'suspended', ready: true }));
  await expect(coverage).not.toHaveClass(/status-safe/);
});

test('dashboard puts readable incident and instructions before temperature statistics', async ({ page }, testInfo) => {
  await openMock(page);
  const instruction = page.locator('.dashboard-events > .recovery-panel .recovery-card-copy p').first();
  await expect(page.locator('.hero-incident')).toBeVisible();
  await expect(instruction).toBeVisible();
  const instructionBox = await instruction.boundingBox();
  const statisticsBox = await page.locator('.summary-grid').boundingBox();
  expect(instructionBox!.y).toBeLessThan(statisticsBox!.y);
  expect(await instruction.evaluate(element => Number.parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(16);
  if (!testInfo.project.name.startsWith('mobile')) {
    const eventsBox = await page.locator('.dashboard-events > .fault-panel').boundingBox();
    const actionsBox = await page.locator('.dashboard-events > .recovery-panel').boundingBox();
    expect(eventsBox!.x).toBeLessThan(actionsBox!.x);
    expect(eventsBox!.width).toBeGreaterThan(actionsBox!.width);
  }
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
            proposal_instance_id: 'test-current-incident',
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
  const confirm = page.getByRole('button', { name: 'Zezwól na wykonanie', exact: true });
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
    event_data: {
      proposal_id: 'test-current-proposal',
      proposal_instance_id: 'test-current-incident',
      confirmation_token: 'test-onetime-token',
    },
  });
  expect(await page.evaluate(() => window.__safetyHomeMock.messages.some(item => item.type === 'call_service'))).toBe(false);
});

test('collapsed notification history exposes the complete fault name and location on a phone', async ({ page }, testInfo) => {
  await openMock(page, '/history');
  const item = page.locator('.notification-item').first();
  const summary = item.locator('summary');
  await expect(summary).toContainText('Niebezpieczna temperatura');
  await expect(summary).toContainText('Lokalizacja: Biuro');
  await expect(item).not.toHaveAttribute('open');
  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    const entries = entities['sensor.notification_history'].attributes.entries as Array<Record<string, unknown>>;
    entries[0].message =
      'Wymaga uwagi: Prognoza niebezpiecznej temperatury w pomieszczeniach na górnym piętrze.\nLokalizacja: Garaż i łazienka na górnym piętrze';
    window.__safetyHomeMock.update({ entities });
  });
  await expect(summary).toContainText('Prognoza niebezpiecznej temperatury w pomieszczeniach na górnym piętrze');
  await expect(summary).toContainText('Lokalizacja: Garaż i łazienka na górnym piętrze');
  const name = summary.locator('.notification-fault-name');
  expect(await name.evaluate(element => getComputedStyle(element).whiteSpace)).toBe('normal');
  expect(await name.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  await summary.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath('history-identity.png'), scale: 'css' });
});

test('state history retains the recorded fault location instead of applying its current location backwards', async ({ page }, testInfo) => {
  await openMock(page, '/history');
  await page.evaluate(() => {
    const now = Date.now() / 1000;
    window.__safetyHomeMock.setHistory('sensor.fault_riskytemperatureforecast', {
      states: {
        'sensor.fault_riskytemperatureforecast': [
          { s: 'FAIL', lu: now - 1800, a: { friendly_name: 'Prognoza niebezpiecznej temperatury', location: 'Garaż', active: true } },
          {
            s: 'FAIL',
            lu: now - 1200,
            lc: now - 1800,
            a: { friendly_name: 'Prognoza niebezpiecznej temperatury', location: 'Kuchnia', active: true },
          },
          { s: 'PASS', lu: now - 600, a: { friendly_name: 'Prognoza niebezpiecznej temperatury', location: '', active: false } },
        ],
      },
    });
  });
  // Changing the range subscribes to the supplied Recorder stream.
  await page.getByRole('combobox', { name: /^Zakres/ }).selectOption('6');
  const card = page.locator('.history-card[data-entity-id="sensor.fault_riskytemperatureforecast"]');
  await expect(card.locator('.state-timeline')).toContainText('Lokalizacja przy wpisie: Garaż');
  await expect(card.locator('.state-timeline')).toContainText('Lokalizacja przy wpisie: Kuchnia');
  await expect(card.locator('.state-timeline li').first()).toContainText('Lokalizacja przy wpisie: Nie zapisano');
  await expect(card.locator('.state-timeline')).toContainText('Prognoza niebezpiecznej temperatury');
  await expect(card.getByText(/^Teraz:/)).toBeVisible();
  const recordedRows = card.locator('.history-fault-transition');
  const recordedTimes = await recordedRows
    .locator('time')
    .evaluateAll(elements => elements.map(element => element.getAttribute('datetime')));
  expect(new Set(recordedTimes).size).toBe(3);
  expect(await recordedRows.first().evaluate(element => getComputedStyle(element).flexDirection)).toBe('column');
  expect(
    await recordedRows
      .locator('.history-transition-name')
      .first()
      .evaluate(element => Number.parseFloat(getComputedStyle(element).fontSize))
  ).toBeGreaterThanOrEqual(16);
  await card.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath('state-history-identity.png'), scale: 'css' });
});

test('inactive unevaluable forecast is never labelled as an active event', async ({ page }) => {
  await openMock(page, '/fault-management');
  await page.evaluate(() => {
    const entities = window.__safetyHomeMock.snapshot();
    entities['sensor.fault_riskytemperatureforecast'].state = 'UNEVALUABLE';
    entities['sensor.fault_riskytemperatureforecast'].attributes.active = false;
    window.__safetyHomeMock.update({ entities });
  });
  const card = page.locator('.fault-card[data-entity-id="sensor.fault_riskytemperatureforecast"]');
  await expect(page.getByRole('heading', { name: /Zdarzenia i stan oceny/ })).toBeVisible();
  await expect(card.locator(':scope > summary')).toContainText('Nieaktywna');
  await expect(card.locator(':scope > summary')).toContainText('Brak wiarygodnej oceny');
  await expect(card.locator(':scope > summary').getByText('Aktywna', { exact: true })).toHaveCount(0);
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
