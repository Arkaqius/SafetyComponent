import { normalizeState, type EntityMap, type EntitySnapshot } from './safety.js';

export const ENTITY_HEALTH_PREFIX = 'sensor.entity_health_';
export const ENTITY_MONITOR_SUMMARY_ID = 'sensor.entity_monitor_summary';

export type EntityHealth = 'healthy' | 'degraded' | 'stale' | 'unavailable';
export type EntitySourceGroup = 'explicit' | 'component';

export interface EntityCheckView {
  check: string;
  result: string;
  reason: string;
  observedValue: unknown;
  evaluatedAt?: string;
  calibration: Record<string, unknown>;
}

export function formatEntityCheckObservation(check: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  if (check !== 'freshness') return `odczyt: ${String(value)}`;

  const seconds = Number(value);
  if (!Number.isFinite(seconds)) return `czas od ostatniej aktualizacji: ${String(value)}`;
  const totalSeconds = Math.max(0, Math.round(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const remainingSeconds = totalSeconds % 60;
  return `czas od ostatniej aktualizacji: ${hours} godz. ${minutes} min ${remainingSeconds} s`;
}

export interface MonitoredEntityView {
  diagnosticEntityId: string;
  entityId: string;
  entityKey: string;
  friendlyName: string;
  health: EntityHealth;
  currentState: string;
  sourceGroups: EntitySourceGroup[];
  owners: string[];
  purposes: string[];
  faultOwner: string;
  faultName?: string;
  areaId?: string;
  areaName?: string;
  deviceId?: string;
  lastChanged?: string;
  lastUpdated?: string;
  lastValidValue?: unknown;
  lastValidAt?: string;
  failureDebounceSeconds: number;
  recoveryDebounceSeconds: number;
  detectionBudgetSeconds?: number;
  checks: EntityCheckView[];
}

export interface EntityMonitorSummary {
  health: EntityHealth;
  total: number;
  healthy: number;
  degraded: number;
  stale: number;
  unavailable: number;
}

const HEALTH_STATES = new Set<EntityHealth>(['healthy', 'degraded', 'stale', 'unavailable']);

export function getMonitoredEntities(entities: EntityMap): MonitoredEntityView[] {
  return Object.entries(entities)
    .filter(([entityId]) => entityId.startsWith(ENTITY_HEALTH_PREFIX))
    .map(([diagnosticEntityId, entity]) => monitoredEntity(diagnosticEntityId, entity))
    .filter((entity): entity is MonitoredEntityView => entity !== null)
    .sort((left, right) => healthRank(right.health) - healthRank(left.health) || left.friendlyName.localeCompare(right.friendlyName, 'pl'));
}

export function getEntityMonitorSummary(entities: EntityMap, monitored = getMonitoredEntities(entities)): EntityMonitorSummary {
  const entity = entities[ENTITY_MONITOR_SUMMARY_ID];
  const counts = {
    healthy: numericAttribute(entity, 'healthy'),
    degraded: numericAttribute(entity, 'degraded'),
    stale: numericAttribute(entity, 'stale'),
    unavailable: numericAttribute(entity, 'unavailable'),
  };
  const fallback = {
    healthy: monitored.filter(item => item.health === 'healthy').length,
    degraded: monitored.filter(item => item.health === 'degraded').length,
    stale: monitored.filter(item => item.health === 'stale').length,
    unavailable: monitored.filter(item => item.health === 'unavailable').length,
  };
  const health = healthValue(entity?.state) ?? worstHealth(monitored.map(item => item.health));
  return {
    health,
    total: numericAttribute(entity, 'total') ?? monitored.length,
    healthy: counts.healthy ?? fallback.healthy,
    degraded: counts.degraded ?? fallback.degraded,
    stale: counts.stale ?? fallback.stale,
    unavailable: counts.unavailable ?? fallback.unavailable,
  };
}

function monitoredEntity(diagnosticEntityId: string, entity: EntitySnapshot): MonitoredEntityView | null {
  const entityId = stringAttribute(entity, 'source_entity_id') ?? stringAttribute(entity, 'entity_id');
  const entityKey = stringAttribute(entity, 'entity_key');
  if (!entityId || !entityKey) return null;
  return {
    diagnosticEntityId,
    entityId,
    entityKey,
    friendlyName: stringAttribute(entity, 'friendly_name') ?? entityKey,
    health: healthValue(entity.state) ?? 'unavailable',
    currentState: stringAttribute(entity, 'current_state') ?? 'unavailable',
    sourceGroups: stringArrayAttribute(entity, 'source_groups').filter(
      (source): source is EntitySourceGroup => source === 'explicit' || source === 'component'
    ),
    owners: stringArrayAttribute(entity, 'owners'),
    purposes: stringArrayAttribute(entity, 'purposes'),
    faultOwner: stringAttribute(entity, 'fault_owner') ?? 'none',
    faultName: stringAttribute(entity, 'fault_name') ?? undefined,
    areaId: stringAttribute(entity, 'area_id') ?? undefined,
    areaName: stringAttribute(entity, 'area_name') ?? undefined,
    deviceId: stringAttribute(entity, 'device_id') ?? undefined,
    lastChanged: stringAttribute(entity, 'last_changed') ?? undefined,
    lastUpdated: stringAttribute(entity, 'last_updated') ?? undefined,
    lastValidValue: entity.attributes.last_valid_value,
    lastValidAt: stringAttribute(entity, 'last_valid_at') ?? undefined,
    failureDebounceSeconds: numericAttribute(entity, 'failure_debounce_seconds') ?? 0,
    recoveryDebounceSeconds: numericAttribute(entity, 'recovery_debounce_seconds') ?? 0,
    detectionBudgetSeconds: numericAttribute(entity, 'detection_budget_seconds') ?? undefined,
    checks: checksAttribute(entity),
  };
}

function checksAttribute(entity: EntitySnapshot): EntityCheckView[] {
  const value = entity.attributes.checks;
  if (!Array.isArray(value)) return [];
  return value.flatMap(item => {
    if (!item || typeof item !== 'object') return [];
    const check = item as Record<string, unknown>;
    if (typeof check.check !== 'string') return [];
    return [
      {
        check: check.check,
        result: typeof check.result === 'string' ? check.result : 'not_tested',
        reason: typeof check.reason === 'string' ? check.reason : 'not_evaluated',
        observedValue: check.observed_value,
        evaluatedAt: typeof check.evaluated_at === 'string' ? check.evaluated_at : undefined,
        calibration: check.calibration && typeof check.calibration === 'object' ? (check.calibration as Record<string, unknown>) : {},
      },
    ];
  });
}

function stringAttribute(entity: EntitySnapshot | undefined, key: string): string | null {
  const value = entity?.attributes[key];
  return typeof value === 'string' && value.trim() ? value : null;
}

function stringArrayAttribute(entity: EntitySnapshot, key: string): string[] {
  const value = entity.attributes[key];
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function numericAttribute(entity: EntitySnapshot | undefined, key: string): number | null {
  const value = Number(entity?.attributes[key]);
  return Number.isFinite(value) ? value : null;
}

function healthValue(value: unknown): EntityHealth | null {
  const normalized = normalizeState(value);
  return HEALTH_STATES.has(normalized as EntityHealth) ? (normalized as EntityHealth) : null;
}

function healthRank(health: EntityHealth): number {
  return { healthy: 0, degraded: 1, stale: 2, unavailable: 3 }[health];
}

function worstHealth(health: EntityHealth[]): EntityHealth {
  return health.sort((left, right) => healthRank(right) - healthRank(left))[0] ?? 'healthy';
}
