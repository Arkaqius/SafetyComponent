import type { EntityMap } from './safety.js';

export const EVALUATION_PROGRESS_ENTITY_ID = 'sensor.safety_evaluation_progress';
export const NOTIFICATION_HEALTH_ENTITY_ID = 'sensor.notification_delivery_health';
export const DETECTOR_TESTS_ENTITY_ID = 'sensor.safety_detector_tests';
export const DETECTOR_TEST_RESULT_EVENT = 'safety_detector_test_result';
export const PERIODIC_TESTS_ENTITY_ID = 'sensor.safety_periodic_tests';
export const PERIODIC_TEST_RESULT_EVENT = 'safety_periodic_test_result';
export const FUNCTIONAL_SAFETY_SOURCES_ENTITY_ID = 'sensor.functional_safety_sources';
export const TEST_NOTIFICATION_EVENT = 'safety_notification_test';
export const RESET_NOTIFICATIONS_EVENT = 'safety_notification_reset';

export function notificationOperatorMessage(action: 'test' | 'reset') {
  return {
    type: 'fire_event',
    event_type: action === 'test' ? TEST_NOTIFICATION_EVENT : RESET_NOTIFICATIONS_EVENT,
    event_data: { confirmed: true },
  };
}
const updateProductNames: Record<string, string> = {
  home_assistant_core: 'Home Assistant Core',
  home_assistant_os: 'Home Assistant OS',
  home_assistant_supervisor: 'Home Assistant Supervisor',
  safety_component: 'SafetyComponent App',
};

export interface SourceView {
  key: string;
  label: string;
  status: string;
  detail: string;
  group: 'host' | 'wan' | 'updates' | 'batteries' | 'inventory';
  evidence: string[];
}

export function getFunctionalSafetySources(entities: EntityMap, fullDiagnostics?: Record<string, unknown> | null): SourceView[] {
  const entity = entities[FUNCTIONAL_SAFETY_SOURCES_ENTITY_ID];
  if (!entity || !['observed', 'attention', 'unknown'].includes(entity.state)) return [];
  const attributes = fullDiagnostics ?? entity.attributes;
  const rows: SourceView[] = [];
  const add = (key: string, label: string, value: unknown, detail = '') => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return;
    const item = value as Record<string, unknown>;
    if (typeof item.status !== 'string') return;
    const reasons: Record<string, string> = {
      not_configured: 'Źródło nie zostało skonfigurowane',
      unavailable: 'Źródło niedostępne',
      stale: 'Odczyt nieaktualny',
      invalid_value: 'Nieprawidłowy odczyt',
      invalid_unit: 'Nieobsługiwana jednostka',
      invalid_timestamp: 'Nieprawidłowa data kopii',
      backup_failure: 'Błąd tworzenia kopii',
      failure_source_unavailable: 'Źródło błędów backupu niedostępne',
      inventory_unavailable: 'Lista urządzeń niedostępna',
    };
    rows.push({
      key,
      label,
      status: item.status,
      detail: detail || (typeof item.reason === 'string' ? (reasons[item.reason] ?? 'Brak wiarygodnych danych') : ''),
      group: key.startsWith('update-')
        ? 'updates'
        : key.startsWith('battery-') && key !== 'battery-discovery'
          ? 'batteries'
          : key === 'battery-discovery'
            ? 'inventory'
            : key === 'wan'
              ? 'wan'
              : 'host',
      evidence: sourceEvidence(item),
    });
  };
  const memory = attributes.memory as Record<string, unknown> | undefined;
  const cpu = attributes.cpu as Record<string, unknown> | undefined;
  add(
    'memory',
    'Pamięć hosta',
    attributes.memory,
    memory ? `Dostępna: ${numberOrNull(memory.available_mib) ?? '—'} MiB · PSI: ${numberOrNull(memory.psi_percent) ?? '—'}%` : ''
  );
  add('cpu', 'CPU hosta', attributes.cpu, cpu ? `${numberOrNull(cpu.percent) ?? '—'}%` : '');
  const metricDetail = (value: unknown, field: string, unit: string) => {
    const item = value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
    const number = numberOrNull(item[field]);
    return number === null ? '' : `${number.toLocaleString('pl-PL')} ${unit}`;
  };
  const metricEvidence = (value: unknown, field: string) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return value;
    const item = value as Record<string, unknown>;
    return ['normal', 'high', 'low', 'active', 'qualifying', 'recovering'].includes(String(item.status)) &&
      (numberOrNull(item[field]) === null || (field === 'free_mib' && Number(item[field]) < 0))
      ? { ...item, status: 'unknown', reason: 'invalid_value' }
      : item;
  };
  add(
    'disk',
    'Wolne miejsce na dysku hosta',
    metricEvidence(attributes.disk, 'free_mib'),
    metricDetail(attributes.disk, 'free_mib', 'MiB')
  );
  add(
    'host-temperature',
    'Temperatura hosta',
    metricEvidence(attributes.host_temperature, 'temperature_c'),
    metricDetail(attributes.host_temperature, 'temperature_c', '°C')
  );
  const backup = attributes.backup;
  const backupItem = backup && typeof backup === 'object' ? (backup as Record<string, unknown>) : {};
  const backupTime = validDate(backupItem.last_success_at);
  add(
    'backup',
    'Kopie zapasowe',
    ['current', 'overdue'].includes(String(backupItem.status)) &&
      (!backupTime || numberOrNull(backupItem.age_hours) === null || Number(backupItem.age_hours) < 0)
      ? { ...backupItem, status: 'unknown' }
      : backup,
    backupTime ? `Ostatnia udana kopia: ${new Date(backupTime).toLocaleString('pl-PL')}` : 'Brak wiarygodnej daty ostatniej udanej kopii'
  );
  add('wan', 'Łączność WAN', attributes.wan);
  add('battery-discovery', 'Wykrywanie urządzeń bateryjnych', attributes.battery_discovery);
  const updates = attributes.updates;
  if (updates && typeof updates === 'object' && !Array.isArray(updates)) {
    Object.entries(updates).forEach(([key, value]) => add(`update-${key}`, `Aktualizacja: ${updateProductNames[key] ?? key}`, value));
  }
  const batteries = attributes.remote_batteries;
  if (batteries && typeof batteries === 'object' && !Array.isArray(batteries)) {
    Object.entries(batteries).forEach(([key, value]) => {
      const item = value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
      add(`battery-${key}`, `Bateria: ${typeof item.friendly_name === 'string' ? item.friendly_name : key}`, value);
    });
  }
  return rows;
}

function sourceEvidence(item: Record<string, unknown>): string[] {
  const lines: string[] = [];
  const time = (label: string, value: unknown) => {
    const date = validDate(value);
    lines.push(`${label}: ${date ? new Date(date).toLocaleString('pl-PL') : 'brak danych'}`);
  };
  if ('installed_version' in item) {
    lines.push(`Zainstalowana: ${typeof item.installed_version === 'string' ? item.installed_version : '—'}`);
    const latest = typeof item.latest_version === 'string' ? item.latest_version : '';
    lines.push(`Najnowsza wg encji HA: ${latest || '—'}`);
    const stable = item.stable_release && typeof item.stable_release === 'object' ? (item.stable_release as Record<string, unknown>) : {};
    lines.push(
      `Najnowsza stabilna wg wydawcy: ${stable.status === 'current' && typeof stable.version === 'string' ? stable.version : 'brak wiarygodnych danych'}`
    );
    time('Sprawdzenie stabilnego wydania', stable.checked_at);
    time('Ostatni raport źródła', item.observed_at);
  }
  if (Array.isArray(item.sources))
    for (const raw of item.sources) {
      if (!raw || typeof raw !== 'object') continue;
      const source = raw as Record<string, unknown>;
      lines.push(
        `${String(source.entity_id ?? 'Źródło')}: ${String(source.state ?? 'brak danych')}${typeof source.unit === 'string' ? ` ${source.unit}` : ''} (odczyt źródłowy)`
      );
      time('Ostatni raport', source.last_reported);
      time('Ostatnia zmiana wartości/atrybutów', source.last_updated);
    }
  if ('checked_at' in item) time('Ostatnia ocena monitora', item.checked_at);
  if ('percentage' in item) lines.unshift(`Wiarygodny poziom baterii: ${numberOrNull(item.percentage) ?? '—'}%`);
  if ('device_count' in item)
    lines.push(`Urządzenia w inwentarzu: ${numberOrNull(item.device_count) ?? '—'} (wykrywanie nie jest monitorem stanu baterii)`);
  return lines;
}

export type PeriodicTestKey = 'notification_delivery' | 'backup_restore';
export interface PeriodicTestView {
  testKey: PeriodicTestKey;
  friendlyName: string;
  status: 'current' | 'due' | 'overdue' | 'failed' | 'unknown';
  lastTestAt: string | null;
  dueAt: string | null;
  lastResult: 'passed' | 'failed' | null;
  intervalDays: number | null;
}

function validDate(value: unknown): string | null {
  return typeof value === 'string' && Number.isFinite(Date.parse(value)) ? value : null;
}

export function getPeriodicTests(entities: EntityMap): PeriodicTestView[] {
  const entity = entities[PERIODIC_TESTS_ENTITY_ID];
  if (!entity || !['current', 'attention', 'unknown', 'not_configured'].includes(entity.state)) return [];
  if (!Array.isArray(entity.attributes.tests)) return [];
  return entity.attributes.tests.flatMap(value => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
    const item = value as Record<string, unknown>;
    if (item.test_key !== 'notification_delivery' && item.test_key !== 'backup_restore') return [];
    const status = item.status;
    const allowed = ['current', 'due', 'overdue', 'failed', 'unknown'].includes(String(status));
    const lastTestAt = validDate(item.last_test_at);
    const dueAt = validDate(item.due_at);
    const lastResult = item.last_result === 'passed' || item.last_result === 'failed' ? item.last_result : null;
    const interval = numberOrNull(item.interval_days);
    const validEvidence =
      item.source === 'operator_attestation' &&
      interval !== null &&
      interval > 0 &&
      (status !== 'current' || (lastTestAt !== null && dueAt !== null && lastResult === 'passed')) &&
      (status !== 'failed' || (lastTestAt !== null && lastResult === 'failed'));
    return [
      {
        testKey: item.test_key,
        friendlyName: item.test_key === 'notification_delivery' ? 'Dostarczenie powiadomień' : 'Odtworzenie kopii zapasowej',
        status: allowed && validEvidence ? (status as PeriodicTestView['status']) : 'unknown',
        lastTestAt,
        dueAt,
        lastResult,
        intervalDays: interval,
      },
    ];
  });
}

export function periodicTestResultMessage(testKey: PeriodicTestKey, outcome: 'passed' | 'failed') {
  return { type: 'fire_event', event_type: PERIODIC_TEST_RESULT_EVENT, event_data: { test_key: testKey, outcome } };
}

export interface ComponentProgressView {
  name: string;
  status: 'observed' | 'unknown' | 'overdue' | 'error';
  lastCompletedAt: string | null;
  expectedIntervalSeconds: number | null;
  ageSeconds: number | null;
  completedCount: number;
  missedDeadlineCount: number;
  evaluationMode: 'periodic' | 'event_driven';
}

export interface DetectorTestView {
  detectorKey: string;
  friendlyName: string;
  hazard: 'smoke' | 'flammable_gas' | 'carbon_monoxide';
  status: 'current' | 'due' | 'overdue' | 'failed' | 'unknown';
  lastTestAt: string | null;
  dueAt: string | null;
}

export function getDetectorTests(entities: EntityMap): DetectorTestView[] {
  const entity = entities[DETECTOR_TESTS_ENTITY_ID];
  if (!entity || !['current', 'attention', 'unknown', 'not_configured'].includes(entity.state)) return [];
  const raw = entity.attributes.tests;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap(value => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
    const item = value as Record<string, unknown>;
    if (typeof item.detector_key !== 'string' || typeof item.friendly_name !== 'string') return [];
    if (item.hazard !== 'smoke' && item.hazard !== 'flammable_gas' && item.hazard !== 'carbon_monoxide') return [];
    if (
      item.status !== 'current' &&
      item.status !== 'due' &&
      item.status !== 'overdue' &&
      item.status !== 'failed' &&
      item.status !== 'unknown'
    )
      return [];
    return [
      {
        detectorKey: item.detector_key,
        friendlyName: item.friendly_name,
        hazard: item.hazard,
        status: item.status,
        lastTestAt: typeof item.last_test_at === 'string' ? item.last_test_at : null,
        dueAt: typeof item.due_at === 'string' ? item.due_at : null,
      },
    ];
  });
}

export function getComponentProgress(entities: EntityMap): ComponentProgressView[] {
  const entity = entities[EVALUATION_PROGRESS_ENTITY_ID];
  if (!entity || !['observed', 'attention', 'unknown'].includes(entity.state)) return [];
  const raw = entity.attributes.components;
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return [];
  return Object.entries(raw)
    .flatMap(([name, value]) => {
      if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
      const item = value as Record<string, unknown>;
      const status = item.status;
      if (status !== 'observed' && status !== 'unknown' && status !== 'overdue' && status !== 'error') return [];
      const normalizedStatus: ComponentProgressView['status'] = status;
      return [
        {
          name,
          status: normalizedStatus,
          lastCompletedAt: typeof item.last_completed_at === 'string' ? item.last_completed_at : null,
          expectedIntervalSeconds: numberOrNull(item.expected_interval_seconds),
          ageSeconds: numberOrNull(item.age_seconds),
          completedCount: numberOrNull(item.completed_count) ?? 0,
          missedDeadlineCount: numberOrNull(item.missed_deadline_count) ?? 0,
          evaluationMode: item.evaluation_mode === 'periodic' ? ('periodic' as const) : ('event_driven' as const),
        },
      ];
    })
    .sort((a, b) => a.name.localeCompare(b.name));
}

function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}
