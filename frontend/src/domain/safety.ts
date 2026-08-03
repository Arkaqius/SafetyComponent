export const HEALTH_ENTITY_ID = 'sensor.safety_app_health';
export const SYSTEM_STATE_ENTITY_ID = 'sensor.safetysystem_state';
export const FAULT_PREFIX = 'sensor.fault_';
export const RECOVERY_PREFIX = 'sensor.recovery_';
export const SAFETY_DOOR_PREFIX = 'sensor.safety_door_';

export interface EntitySnapshot {
  state: string;
  attributes: Record<string, unknown>;
  last_changed?: string;
  last_updated?: string;
}

export type EntityMap = Record<string, EntitySnapshot>;

export type FaultStatus = 'set' | 'shadowed' | 'cleared' | 'not_tested' | 'unavailable' | 'unknown';
export type RecoveryStatus = 'to_perform' | 'do_not_perform' | 'unavailable' | 'unknown';
export type StatusTone = 'safe' | 'critical' | 'danger' | 'warning' | 'info' | 'muted';

export interface FaultView {
  entityId: string;
  name: string;
  description: string;
  locations: string[];
  level: number | null;
  state: string;
  status: FaultStatus;
  lastChanged?: string;
}

export interface RecoveryView {
  entityId: string;
  name: string;
  description: string;
  state: string;
  status: RecoveryStatus;
  lastChanged?: string;
}

export interface TemperatureView {
  entityId: string;
  name: string;
  state: number | null;
  unit: string;
  rateEntityId: string;
  rate: number | null;
  accelerationEntityId: string;
  acceleration: number | null;
  lowThreshold: number | null;
  highThreshold: number | null;
  lastUpdated?: string;
}

export type SafetyDoorStatus = 'active' | 'blocked' | 'inactive' | 'unavailable' | 'unknown';

export type SafetyDoorConditionResult = 'pass' | 'blocked' | 'unavailable' | 'not_configured' | 'unknown';

export interface SafetyDoorView {
  entityId: string;
  name: string;
  sourceEntityId: string;
  sourceEntityName: string;
  state: string;
  status: SafetyDoorStatus;
  doorState: 'open' | 'closed' | 'unavailable';
  timeoutSeconds: number | null;
  openDurationSeconds: number;
  remainingSeconds: number;
  conditionEntityId: string;
  conditionEntityName: string;
  conditionState: string;
  conditionResult: SafetyDoorConditionResult;
  openedAt?: string;
  lastUpdated?: string;
}

export interface ActivityItem {
  entityId: string;
  name: string;
  state: string;
  category: 'system' | 'fault' | 'recovery';
  timestamp?: string;
}

export interface SafetySummary {
  label: string;
  detail: string;
  tone: StatusTone;
  effectiveLevel: number | null;
  activeFaultCount: number;
  shadowedFaultCount: number;
  actionableRecoveryCount: number;
}

export const LEVEL_PRESENTATION: Record<number, { label: string; shortLabel: string; tone: StatusTone }> = {
  1: { label: 'Alarm krytyczny', shortLabel: 'L1', tone: 'critical' },
  2: { label: 'Zagrożenie', shortLabel: 'L2', tone: 'danger' },
  3: { label: 'Ostrzeżenie', shortLabel: 'L3', tone: 'warning' },
  4: { label: 'Informacja', shortLabel: 'L4', tone: 'info' },
};

const SYSTEM_LEVEL_BY_STATE: Record<string, number> = {
  no_faults: 0,
  working: 0,
  emergency: 1,
  hazard: 2,
  warning: 3,
  information: 4,
};

export function systemStatePresentation(state: unknown): { label: string; tone: StatusTone } {
  const normalized = normalizeState(state);
  if (normalized === 'no_faults' || normalized === 'working' || normalized === 'safe' || normalized === '0') {
    return { label: 'Brak aktywnych usterek', tone: 'safe' };
  }
  if (normalized === 'stopped') return { label: 'Zatrzymany', tone: 'critical' };
  const level = parseSystemLevel(normalized);
  const presentation = level === null ? undefined : LEVEL_PRESENTATION[level];
  return presentation
    ? { label: presentation.label, tone: presentation.tone }
    : { label: String(state ?? 'Stan nieznany'), tone: 'muted' };
}

const UNAVAILABLE_STATES = new Set(['unavailable', 'unknown', 'none', '']);

export function normalizeState(value: unknown): string {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_');
}

export function isUnavailable(entity: EntitySnapshot | undefined): boolean {
  return !entity || UNAVAILABLE_STATES.has(normalizeState(entity.state));
}

export function getFaultStatus(state: unknown): FaultStatus {
  const normalized = normalizeState(state);
  if (normalized === 'set') return 'set';
  if (normalized === 'shadowed') return 'shadowed';
  if (normalized === 'cleared') return 'cleared';
  if (normalized === 'not_tested' || normalized === 'nottested') return 'not_tested';
  if (UNAVAILABLE_STATES.has(normalized)) return 'unavailable';
  return 'unknown';
}

export function getRecoveryStatus(state: unknown): RecoveryStatus {
  const normalized = normalizeState(state);
  if (normalized === 'to_perform') return 'to_perform';
  if (normalized === 'do_not_perform') return 'do_not_perform';
  if (UNAVAILABLE_STATES.has(normalized)) return 'unavailable';
  return 'unknown';
}

export function getFaultLevel(entity: EntitySnapshot): number | null {
  const rawLevel = entity.attributes.level;
  const match = String(rawLevel ?? '').match(/(?:level_)?([1-4])$/i);
  return match ? Number(match[1]) : null;
}

export function friendlyEntityName(entityId: string, entity?: EntitySnapshot): string {
  const configuredName = stringAttribute(entity, 'friendly_name')
    .replace(/^Safety Component\s*/i, '')
    .replace(/^Fault:\s*/i, '')
    .replace(/^Recovery\s*/i, '')
    .replace(/^Safety Door:\s*/i, '')
    .replace(/^ManipulateWindow\s*/i, '');
  const fallback = entityId.split('.', 2)[1] ?? entityId;
  return humanize(configuredName || fallback.replace(/^(fault|recovery)_/, ''));
}

export function getFaults(entities: EntityMap): FaultView[] {
  const statusPriority: Record<FaultStatus, number> = {
    set: 0,
    shadowed: 1,
    unavailable: 2,
    unknown: 3,
    not_tested: 4,
    cleared: 5,
  };

  return Object.entries(entities)
    .filter(([entityId]) => entityId.startsWith(FAULT_PREFIX))
    .map(([entityId, entity]) => ({
      entityId,
      name: friendlyEntityName(entityId, entity),
      description: stringAttribute(entity, 'description'),
      locations: splitLocations(entity.attributes.location),
      level: getFaultLevel(entity),
      state: entity.state,
      status: getFaultStatus(entity.state),
      lastChanged: entity.last_changed,
    }))
    .sort(
      (left, right) =>
        statusPriority[left.status] - statusPriority[right.status] ||
        (left.level ?? 99) - (right.level ?? 99) ||
        left.name.localeCompare(right.name, 'pl')
    );
}

export function getRecoveries(entities: EntityMap): RecoveryView[] {
  const statusPriority: Record<RecoveryStatus, number> = {
    to_perform: 0,
    unavailable: 1,
    unknown: 2,
    do_not_perform: 3,
  };

  return Object.entries(entities)
    .filter(([entityId]) => entityId.startsWith(RECOVERY_PREFIX))
    .map(([entityId, entity]) => ({
      entityId,
      name: friendlyEntityName(entityId, entity),
      description: stringAttribute(entity, 'description'),
      state: entity.state,
      status: getRecoveryStatus(entity.state),
      lastChanged: entity.last_changed,
    }))
    .sort((left, right) => statusPriority[left.status] - statusPriority[right.status] || left.name.localeCompare(right.name, 'pl'));
}

/** Returns true when a recovery sensor needs an action or diagnostic attention. */
export function recoveryNeedsAttention(recovery: RecoveryView): boolean {
  return recovery.status !== 'do_not_perform';
}

export function getMonitoredTemperatures(entities: EntityMap): TemperatureView[] {
  return Object.entries(entities)
    .filter(([entityId, entity]) => isSafetyRateEntity(entityId, entity))
    .flatMap(([rateEntityId, rateEntity]) => {
      const entityId = rateEntityId.slice(0, -'_rate'.length);
      const accelerationEntityId = `${entityId}_rateofrate`;
      const sourceEntity = entities[entityId];
      if (!sourceEntity) return [];
      const lowThresholdEntity = entities[`${entityId}_low_threshold`];
      const highThresholdEntity = entities[`${entityId}_high_threshold`];

      return [
        {
          entityId,
          name: friendlyEntityName(entityId, sourceEntity),
          state: numericState(sourceEntity.state),
          unit: stringAttribute(sourceEntity, 'unit_of_measurement') || '°C',
          rateEntityId,
          rate: numericState(rateEntity.state),
          accelerationEntityId,
          acceleration: numericState(entities[accelerationEntityId]?.state),
          lowThreshold:
            numericState(lowThresholdEntity?.state) ??
            numericAttribute(rateEntity, 'low_temperature_threshold'),
          highThreshold:
            numericState(highThresholdEntity?.state) ??
            numericAttribute(rateEntity, 'high_temperature_threshold'),
          lastUpdated: latestTimestamp(
            sourceEntity.last_updated,
            rateEntity.last_updated,
            lowThresholdEntity?.last_updated,
            highThresholdEntity?.last_updated
          ),
        },
      ];
    })
    .sort((left, right) => left.name.localeCompare(right.name, 'pl'));
}

export function getSafetyDoors(entities: EntityMap): SafetyDoorView[] {
  const statusPriority: Record<SafetyDoorStatus, number> = {
    active: 0,
    blocked: 1,
    unavailable: 2,
    unknown: 3,
    inactive: 4,
  };

  return Object.entries(entities)
    .filter(([entityId]) => entityId.startsWith(SAFETY_DOOR_PREFIX))
    .map(([entityId, entity]) => {
      const normalizedState = normalizeState(entity.state);
      const rawDoorState = normalizeState(entity.attributes.door_state);
      const doorState: SafetyDoorView['doorState'] =
        rawDoorState === 'open' || rawDoorState === 'closed' ? rawDoorState : 'unavailable';
      const status: SafetyDoorStatus =
        normalizedState === 'active'
          ? 'active'
          : normalizedState === 'blocked'
            ? 'blocked'
          : normalizedState === 'inactive'
            ? 'inactive'
            : UNAVAILABLE_STATES.has(normalizedState)
              ? 'unavailable'
              : 'unknown';
      const openedAt = optionalStringAttribute(entity, 'opened_at');
      const reportedOpenDuration = numericAttribute(entity, 'open_duration_seconds') ?? 0;
      const liveOpenDuration =
        doorState === 'open' && openedAt
          ? Math.max(reportedOpenDuration, elapsedSeconds(openedAt))
          : reportedOpenDuration;
      const timeoutSeconds = numericAttribute(entity, 'timeout_seconds');
      const rawConditionResult = normalizeState(entity.attributes.condition_result);
      const conditionResult: SafetyDoorConditionResult =
        rawConditionResult === 'pass' ||
        rawConditionResult === 'blocked' ||
        rawConditionResult === 'unavailable' ||
        rawConditionResult === 'not_configured'
          ? rawConditionResult
          : 'unknown';
      const reportedRemainingSeconds = numericAttribute(entity, 'remaining_seconds') ?? 0;
      const sourceEntityId = stringAttribute(entity, 'source_entity');
      const conditionEntityId = stringAttribute(entity, 'condition_entity');

      return {
        entityId,
        name: friendlyEntityName(entityId, entity),
        sourceEntityId,
        sourceEntityName: sourceEntityId
          ? friendlyEntityName(sourceEntityId, entities[sourceEntityId])
          : friendlyEntityName(entityId, entity),
        state: entity.state,
        status,
        doorState,
        timeoutSeconds,
        openDurationSeconds: liveOpenDuration,
        remainingSeconds:
          status === 'blocked' || timeoutSeconds === null
            ? reportedRemainingSeconds
            : Math.max(0, timeoutSeconds - liveOpenDuration),
        conditionEntityId,
        conditionEntityName: conditionEntityId
          ? friendlyEntityName(conditionEntityId, entities[conditionEntityId])
          : '',
        conditionState: stringAttribute(entity, 'condition_state'),
        conditionResult,
        openedAt,
        lastUpdated: entity.last_updated ?? entity.last_changed,
      };
    })
    .sort(
      (left, right) =>
        statusPriority[left.status] - statusPriority[right.status] ||
        Number(right.doorState === 'open') - Number(left.doorState === 'open') ||
        left.name.localeCompare(right.name, 'pl')
    );
}

export function getRecentActivity(entities: EntityMap, limit = 8): ActivityItem[] {
  return Object.entries(entities)
    .filter(
      ([entityId]) =>
        [HEALTH_ENTITY_ID, SYSTEM_STATE_ENTITY_ID].includes(entityId) ||
        entityId.startsWith(FAULT_PREFIX) ||
        entityId.startsWith(RECOVERY_PREFIX)
    )
    .map(([entityId, entity]) => ({
      entityId,
      name: friendlyEntityName(entityId, entity),
      state: entity.state,
      category: activityCategory(entityId),
      timestamp: entity.last_changed ?? entity.last_updated,
    }))
    .sort((left, right) => timestampValue(right.timestamp) - timestampValue(left.timestamp))
    .slice(0, limit);
}

export function getSafetySummary(
  healthEntity: EntitySnapshot | undefined,
  systemEntity: EntitySnapshot | undefined,
  faults: FaultView[],
  recoveries: RecoveryView[]
): SafetySummary {
  const activeFaults = faults.filter(fault => fault.status === 'set');
  const shadowedFaults = faults.filter(fault => fault.status === 'shadowed');
  const uncertainFaults = faults.filter(fault => ['unavailable', 'unknown', 'not_tested'].includes(fault.status));
  const actionableRecoveries = recoveries.filter(recovery => recovery.status === 'to_perform');
  const uncertainRecoveries = recoveries.filter(recovery => ['unavailable', 'unknown'].includes(recovery.status));
  const base = {
    activeFaultCount: activeFaults.length,
    shadowedFaultCount: shadowedFaults.length,
    actionableRecoveryCount: actionableRecoveries.length,
  };

  if (isUnavailable(healthEntity) || isUnavailable(systemEntity)) {
    return {
      ...base,
      label: 'Dane niedostępne',
      detail: 'Brak aktualnego połączenia z encjami SafetyComponent',
      tone: 'muted',
      effectiveLevel: null,
    };
  }

  const healthState = normalizeState(healthEntity?.state);
  if (healthState !== 'running') {
    const healthLabels: Record<string, string> = {
      init: 'System uruchamia się',
      invalid_cfg: 'Błędna konfiguracja',
      stopped: 'System zatrzymany',
    };
    return {
      ...base,
      label: healthLabels[healthState] ?? 'Stan systemu nieznany',
      detail: stringAttribute(healthEntity, 'configuration_error') || `Stan usługi: ${healthEntity?.state}`,
      tone: healthState === 'init' ? 'warning' : 'critical',
      effectiveLevel: null,
    };
  }

  const knownActiveLevels = activeFaults.map(fault => fault.level).filter((level): level is number => level !== null);
  const hasUnknownActiveLevel = activeFaults.some(fault => fault.level === null);
  const reportedLevel = parseSystemLevel(systemEntity?.state);
  const uncertainEntityCount = uncertainFaults.length + uncertainRecoveries.length + (reportedLevel === null ? 1 : 0);
  const hasReportedFault = reportedLevel !== null && reportedLevel > 0;

  if (uncertainEntityCount > 0) {
    if (activeFaults.length > 0 || hasReportedFault) {
      const activeDetail =
        activeFaults.length > 0
          ? `${activeFaults.length} ${polishCount(activeFaults.length, 'aktywna usterka', 'aktywne usterki', 'aktywnych usterek')}`
          : `Raportowany poziom systemu: ${reportedLevel}`;

      return {
        ...base,
        label: 'Aktywna usterka · dane niepełne',
        detail: `${activeDetail} · ${uncertainEntityCount} ${polishCount(
          uncertainEntityCount,
          'encja wymaga weryfikacji',
          'encje wymagają weryfikacji',
          'encji wymaga weryfikacji'
        )}`,
        tone: 'critical',
        effectiveLevel: null,
      };
    }

    return {
      ...base,
      label: 'Dane niepełne',
      detail: `${uncertainEntityCount} ${polishCount(
        uncertainEntityCount,
        'encja wymaga weryfikacji',
        'encje wymagają weryfikacji',
        'encji wymaga weryfikacji'
      )}`,
      tone: 'muted',
      effectiveLevel: null,
    };
  }

  const effectiveLevel =
    activeFaults.length > 0 ? (hasUnknownActiveLevel ? null : Math.min(...knownActiveLevels)) : hasReportedFault ? reportedLevel : null;

  if (activeFaults.length > 0 || hasReportedFault) {
    const presentation = effectiveLevel ? LEVEL_PRESENTATION[effectiveLevel] : undefined;
    return {
      ...base,
      label: presentation?.label ?? 'Aktywna usterka',
      detail:
        activeFaults.length > 0
          ? `${activeFaults.length} ${polishCount(activeFaults.length, 'aktywna usterka', 'aktywne usterki', 'aktywnych usterek')}${
              hasUnknownActiveLevel ? ' · poziom wymaga weryfikacji' : ''
            }`
          : `Raportowany poziom systemu: ${reportedLevel}`,
      tone: presentation?.tone ?? 'danger',
      effectiveLevel,
    };
  }

  return {
    ...base,
    label: 'System bezpieczny',
    detail: 'Brak aktywnych usterek',
    tone: 'safe',
    effectiveLevel: 0,
  };
}

export function formatRelativeTime(timestamp?: string, now = Date.now()): string {
  if (!timestamp) return 'brak danych';
  const value = Date.parse(timestamp);
  if (Number.isNaN(value)) return 'brak danych';

  const seconds = Math.max(0, Math.round((now - value) / 1000));
  if (seconds < 10) return 'przed chwilą';
  if (seconds < 60) return `${seconds} s temu`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min temu`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} godz. temu`;
  const days = Math.floor(hours / 24);
  return `${days} ${polishCount(days, 'dzień', 'dni', 'dni')} temu`;
}

export function formatNumeric(value: number | null, digits = 2): string {
  if (value === null || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat('pl-PL', {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  }).format(value);
}

export function trendPresentation(rate: number | null): { label: string; className: string; symbol: string } {
  if (rate === null) return { label: 'Brak trendu', className: 'trend-unknown', symbol: '–' };
  if (Math.abs(rate) < 0.005) return { label: 'Stabilna', className: 'trend-stable', symbol: '→' };
  if (rate > 0) return { label: 'Rośnie', className: 'trend-rising', symbol: '↗' };
  return { label: 'Spada', className: 'trend-falling', symbol: '↘' };
}

function stringAttribute(entity: EntitySnapshot | undefined, key: string): string {
  const value = entity?.attributes[key];
  return typeof value === 'string' || typeof value === 'number' ? String(value).trim() : '';
}

function optionalStringAttribute(entity: EntitySnapshot | undefined, key: string): string | undefined {
  const value = stringAttribute(entity, key);
  return value || undefined;
}

function numericAttribute(entity: EntitySnapshot | undefined, key: string): number | null {
  return numericState(entity?.attributes[key]);
}

function splitLocations(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map(String)
      .map(item => item.trim())
      .filter(Boolean);
  }
  if (typeof value !== 'string') return [];
  return value
    .split(',')
    .map(item => item.trim())
    .filter(Boolean);
}

function humanize(value: string): string {
  return value
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^\w/, letter => letter.toUpperCase());
}

function numericState(value: unknown): number | null {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function isSafetyRateEntity(entityId: string, entity: EntitySnapshot): boolean {
  if (!entityId.endsWith('_rate') || entityId.endsWith('_rateofrate')) return false;
  const unit = stringAttribute(entity, 'unit_of_measurement');
  const attribution = stringAttribute(entity, 'attribution');
  return unit === '°C/min' || attribution === 'Data provided by SafetyFunction';
}

function latestTimestamp(...timestamps: Array<string | undefined>): string | undefined {
  return timestamps
    .filter((timestamp): timestamp is string => Boolean(timestamp))
    .sort((left, right) => timestampValue(right) - timestampValue(left))[0];
}

function timestampValue(timestamp?: string): number {
  if (!timestamp) return 0;
  const value = Date.parse(timestamp);
  return Number.isNaN(value) ? 0 : value;
}

function elapsedSeconds(timestamp: string): number {
  const value = timestampValue(timestamp);
  return value === 0 ? 0 : Math.max(0, Math.floor((Date.now() - value) / 1000));
}

function activityCategory(entityId: string): ActivityItem['category'] {
  if (entityId.startsWith(FAULT_PREFIX)) return 'fault';
  if (entityId.startsWith(RECOVERY_PREFIX)) return 'recovery';
  return 'system';
}

function parseSystemLevel(value: unknown): number | null {
  const normalized = normalizeState(value);
  if (normalized === 'safe') return 0;
  if (normalized in SYSTEM_LEVEL_BY_STATE) return SYSTEM_LEVEL_BY_STATE[normalized];
  const level = Number(normalized.replace(/^level_/, ''));
  return Number.isInteger(level) && level >= 0 && level <= 4 ? level : null;
}

function polishCount(value: number, singular: string, plural: string, pluralGenitive: string): string {
  if (value === 1) return singular;
  const lastTwo = value % 100;
  const last = value % 10;
  if (last >= 2 && last <= 4 && !(lastTwo >= 12 && lastTwo <= 14)) return plural;
  return pluralGenitive;
}
