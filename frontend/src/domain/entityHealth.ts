import { friendlyEntityName, normalizeState, type EntityMap, type EntitySnapshot } from './safety.js';

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

export interface EntityRegistryView {
  entity_id: string;
  name: string | null;
  original_name?: string;
  device_id: string | null;
  area_id: string | null;
  disabled_by: string | null;
  hidden_by: string | null;
}

export interface DeviceRegistryView {
  id: string;
  name: string | null;
  name_by_user: string | null;
  manufacturer: string | null;
  model: string | null;
  area_id: string | null;
  disabled_by: string | null;
}

export interface AreaRegistryView {
  area_id: string;
  name: string;
}

export interface InventoryEntityView {
  entityId: string;
  friendlyName: string;
  state: string;
  domain: string;
  available: boolean;
  lastChanged?: string;
  lastUpdated?: string;
  deviceId?: string;
  deviceName?: string;
  areaId?: string;
  areaName?: string;
  disabledBy?: string;
  hiddenBy?: string;
  monitored?: MonitoredEntityView;
}

export interface InventoryDeviceView {
  deviceId: string;
  name: string;
  manufacturer?: string;
  model?: string;
  areaName?: string;
  disabledBy?: string;
  entities: InventoryEntityView[];
  unavailableCount: number;
  oldestUpdate?: string;
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

export function buildEntityInventory(
  states: EntityMap,
  registry: EntityRegistryView[],
  devices: DeviceRegistryView[],
  areas: AreaRegistryView[],
  monitored: MonitoredEntityView[]
): InventoryEntityView[] {
  const registryById = new Map(registry.map(entry => [entry.entity_id, entry]));
  const deviceById = new Map(devices.map(device => [device.id, device]));
  const areaById = new Map(areas.map(area => [area.area_id, area.name]));
  const monitoredById = new Map(monitored.map(entity => [entity.entityId, entity]));
  const ids = new Set([...Object.keys(states), ...registry.map(entry => entry.entity_id)]);

  return [...ids]
    .map(entityId => {
      const state = states[entityId];
      const registryEntry = registryById.get(entityId);
      const monitoredEntity = monitoredById.get(entityId);
      const device = registryEntry?.device_id ? deviceById.get(registryEntry.device_id) : undefined;
      const areaId = registryEntry?.area_id ?? device?.area_id ?? monitoredEntity?.areaId;
      const rawState = state?.state ?? 'unavailable';
      return {
        entityId,
        friendlyName: registryEntry?.name ?? (state ? friendlyEntityName(entityId, state) : registryEntry?.original_name) ?? entityId,
        state: rawState,
        domain: entityId.split('.', 1)[0] ?? '',
        available: !['unknown', 'unavailable', 'none', ''].includes(normalizeState(rawState)),
        lastChanged: state?.last_changed,
        lastUpdated: state?.last_updated,
        deviceId: device?.id,
        deviceName: device?.name_by_user ?? device?.name ?? undefined,
        areaId: areaId ?? undefined,
        areaName: areaId ? (areaById.get(areaId) ?? monitoredEntity?.areaName) : monitoredEntity?.areaName,
        disabledBy: registryEntry?.disabled_by ?? undefined,
        hiddenBy: registryEntry?.hidden_by ?? undefined,
        monitored: monitoredEntity,
      };
    })
    .sort((left, right) => left.friendlyName.localeCompare(right.friendlyName, 'pl'));
}

export function buildDeviceInventory(
  inventory: InventoryEntityView[],
  devices: DeviceRegistryView[],
  areas: AreaRegistryView[]
): InventoryDeviceView[] {
  const areaById = new Map(areas.map(area => [area.area_id, area.name]));
  const entitiesByDevice = new Map<string, InventoryEntityView[]>();
  for (const entity of inventory) {
    if (!entity.deviceId) continue;
    const entries = entitiesByDevice.get(entity.deviceId) ?? [];
    entries.push(entity);
    entitiesByDevice.set(entity.deviceId, entries);
  }
  return devices
    .map(device => {
      const entities = entitiesByDevice.get(device.id) ?? [];
      return {
        deviceId: device.id,
        name: device.name_by_user ?? device.name ?? device.id,
        manufacturer: device.manufacturer ?? undefined,
        model: device.model ?? undefined,
        areaName: device.area_id ? areaById.get(device.area_id) : undefined,
        disabledBy: device.disabled_by ?? undefined,
        entities,
        unavailableCount: entities.filter(entity => !entity.available).length,
        oldestUpdate: oldestTimestamp(entities.map(entity => entity.lastUpdated)),
      };
    })
    .sort((left, right) => left.name.localeCompare(right.name, 'pl'));
}

function monitoredEntity(diagnosticEntityId: string, entity: EntitySnapshot): MonitoredEntityView | null {
  const entityId = stringAttribute(entity, 'entity_id');
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

function oldestTimestamp(values: Array<string | undefined>): string | undefined {
  return values.filter((value): value is string => Boolean(value)).sort((left, right) => Date.parse(left) - Date.parse(right))[0];
}
