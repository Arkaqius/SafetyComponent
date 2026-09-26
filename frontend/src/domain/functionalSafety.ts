import type { EntityMap } from './safety.js';

export const EVALUATION_PROGRESS_ENTITY_ID = 'sensor.safety_evaluation_progress';
export const NOTIFICATION_HEALTH_ENTITY_ID = 'sensor.notification_delivery_health';
export const DETECTOR_TESTS_ENTITY_ID = 'sensor.safety_detector_tests';
export const DETECTOR_TEST_RESULT_EVENT = 'safety_detector_test_result';
export const FUNCTIONAL_SAFETY_SOURCES_ENTITY_ID = 'sensor.functional_safety_sources';
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
}

export function getFunctionalSafetySources(entities: EntityMap): SourceView[] {
  const entity = entities[FUNCTIONAL_SAFETY_SOURCES_ENTITY_ID];
  if (!entity || !['observed', 'attention', 'unknown'].includes(entity.state)) return [];
  const attributes = entity.attributes;
  const rows: SourceView[] = [];
  const add = (key: string, label: string, value: unknown, detail = '') => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return;
    const item = value as Record<string, unknown>;
    if (typeof item.status !== 'string') return;
    rows.push({ key, label, status: item.status, detail: detail || (typeof item.reason === 'string' ? item.reason : '') });
  };
  add('memory', 'Pamięć hosta', attributes.memory);
  add('cpu', 'CPU hosta', attributes.cpu);
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
