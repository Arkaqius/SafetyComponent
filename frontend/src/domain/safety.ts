export const HEALTH_ENTITY_ID = 'sensor.safety_app_health';
export const SYSTEM_STATE_ENTITY_ID = 'sensor.safetysystem_state';
export const FAULT_PREFIX = 'sensor.fault_';
export const RECOVERY_PREFIX = 'sensor.recovery_';
export const SAFETY_DOOR_PREFIX = 'sensor.safety_door_';
export const EXTERNAL_HAZARD_ENTITY_ID = 'sensor.external_hazard_state';
export const EXTERNAL_PROVIDER_PREFIX = 'sensor.external_provider_';

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
  roomName: string;
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
  return presentation ? { label: presentation.label, tone: presentation.tone } : { label: String(state ?? 'Stan nieznany'), tone: 'muted' };
}

export type ExternalHazardStatus = 'clear' | 'watch' | 'warning' | 'severe' | 'unavailable' | 'unknown';
export type ExternalProviderStatus = 'ok' | 'stale' | 'unavailable' | 'schema_error' | 'unknown';

export interface ExternalProviderView {
  entityId: string;
  name: string;
  provider: string;
  status: ExternalProviderStatus;
  state: string;
  lastAttemptAt?: string;
  lastSuccessAt?: string;
  consecutiveFailures: number;
  detailCode: string;
  observationCount: number;
  observations: ExternalObservationView[];
  warnings: ImgwWarningView[];
  lastUpdated?: string;
}

export interface ExternalObservationView {
  id: string;
  hazardType: string;
  providerLevel: string;
  observedAt?: string;
  validTo?: string;
  displayValue: string;
  displayUnit: string;
}

export interface AirQualityPresentation {
  label: string;
  detail: string;
  tone: StatusTone;
  sourceName: string;
}

export interface ImgwWarningView {
  id: string;
  eventName: string;
  degree: string;
  probability: string;
  validFrom?: string;
  validTo?: string;
  publishedAt?: string;
  regions: string[];
  content: string;
  comment: string;
  office: string;
  locallyApplicable: boolean;
}

export interface AdviceInhibitionView {
  reason: string;
  source: string;
  validUntil?: string;
}

export interface ExternalHazardView {
  entityId: string;
  status: ExternalHazardStatus;
  state: string;
  activeHazards: string[];
  affectedOpenings: string[];
  adviceInhibition: AdviceInhibitionView[];
  activeSymptomCount: number;
  notificationOnly: boolean;
  lastEvaluatedAt?: string;
  lastUpdated?: string;
  providers: ExternalProviderView[];
  imgwWarnings: ImgwWarningView[];
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
  return localizedTechnicalName(configuredName || fallback.replace(/^(fault|recovery)_/, ''));
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
      locations: splitLocations(entity.attributes.location).map(localizedRoomName),
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
          roomName: temperatureRoomName(sourceEntity, lowThresholdEntity, highThresholdEntity),
          state: numericState(sourceEntity.state),
          unit: stringAttribute(sourceEntity, 'unit_of_measurement') || '°C',
          rateEntityId,
          rate: numericState(rateEntity.state),
          accelerationEntityId,
          acceleration: numericState(entities[accelerationEntityId]?.state),
          lowThreshold: numericState(lowThresholdEntity?.state) ?? numericAttribute(rateEntity, 'low_temperature_threshold'),
          highThreshold: numericState(highThresholdEntity?.state) ?? numericAttribute(rateEntity, 'high_temperature_threshold'),
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
      const doorState: SafetyDoorView['doorState'] = rawDoorState === 'open' || rawDoorState === 'closed' ? rawDoorState : 'unavailable';
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
        doorState === 'open' && openedAt ? Math.max(reportedOpenDuration, elapsedSeconds(openedAt)) : reportedOpenDuration;
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
          status === 'blocked' || timeoutSeconds === null ? reportedRemainingSeconds : Math.max(0, timeoutSeconds - liveOpenDuration),
        conditionEntityId,
        conditionEntityName: conditionEntityId ? friendlyEntityName(conditionEntityId, entities[conditionEntityId]) : '',
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

export function getExternalHazardMonitoring(entities: EntityMap): ExternalHazardView {
  const aggregate = entities[EXTERNAL_HAZARD_ENTITY_ID];
  const normalizedState = normalizeState(aggregate?.state);
  const status: ExternalHazardStatus =
    normalizedState === 'clear' ||
    normalizedState === 'watch' ||
    normalizedState === 'warning' ||
    normalizedState === 'severe' ||
    normalizedState === 'unavailable'
      ? normalizedState
      : normalizedState
        ? 'unknown'
        : 'unavailable';
  const enabledProviders = new Set(stringArrayAttribute(aggregate, 'enabled_providers'));
  const providers = Object.entries(entities)
    .filter(
      ([entityId, entity]) =>
        entityId.startsWith(EXTERNAL_PROVIDER_PREFIX) &&
        (enabledProviders.size === 0 || enabledProviders.has(stringAttribute(entity, 'provider')))
    )
    .map(([entityId, entity]) => {
      const providerState = normalizeState(entity.state);
      const providerStatus: ExternalProviderStatus =
        providerState === 'ok' || providerState === 'stale' || providerState === 'unavailable' || providerState === 'schema_error'
          ? providerState
          : 'unknown';
      return {
        entityId,
        name: friendlyEntityName(entityId, entity),
        provider: stringAttribute(entity, 'provider'),
        status: providerStatus,
        state: entity.state,
        lastAttemptAt: optionalStringAttribute(entity, 'last_attempt_at'),
        lastSuccessAt: optionalStringAttribute(entity, 'last_success_at'),
        consecutiveFailures: numericAttribute(entity, 'consecutive_failures') ?? 0,
        detailCode: stringAttribute(entity, 'detail_code'),
        observationCount: numericAttribute(entity, 'observation_count') ?? 0,
        observations: externalObservationsAttribute(entity),
        warnings: imgwWarningsAttribute(entity),
        lastUpdated: entity.last_updated ?? entity.last_changed,
      };
    })
    .sort((left, right) => Number(left.status === 'ok') - Number(right.status === 'ok') || left.name.localeCompare(right.name, 'pl'));

  const imgwWarnings = providers.flatMap(provider => provider.warnings).filter(warning => warning.locallyApplicable);

  return {
    entityId: EXTERNAL_HAZARD_ENTITY_ID,
    status,
    state: aggregate?.state ?? 'unavailable',
    activeHazards: stringArrayAttribute(aggregate, 'active_hazards'),
    affectedOpenings: stringArrayAttribute(aggregate, 'affected_openings'),
    adviceInhibition: adviceInhibitionAttribute(aggregate),
    activeSymptomCount: numericAttribute(aggregate, 'active_symptom_count') ?? 0,
    notificationOnly: aggregate?.attributes.notification_only === true,
    lastEvaluatedAt: optionalStringAttribute(aggregate, 'last_evaluated_at'),
    lastUpdated: aggregate?.last_updated ?? aggregate?.last_changed,
    providers,
    imgwWarnings,
  };
}

export function getAirQualityPresentation(external: ExternalHazardView): AirQualityPresentation {
  const openMeteo = external.providers.find(provider => provider.provider === 'OpenMeteoAirQualityApiComponent');
  const openMeteoObservation = openMeteo?.observations.find(observation => observation.hazardType === 'outdoor_air_pollution');

  if (openMeteo && ['ok', 'stale'].includes(openMeteo.status) && openMeteoObservation?.displayValue) {
    const value = Number(openMeteoObservation.displayValue);
    const tone: StatusTone = Number.isFinite(value) ? (value <= 40 ? 'safe' : value <= 60 ? 'warning' : 'danger') : 'info';
    return {
      label: europeanAqiLabel(openMeteoObservation),
      detail: 'Bieżący model jakości powietrza dla współrzędnych domu.',
      tone,
      sourceName: 'Open-Meteo',
    };
  }

  return {
    label: 'Brak aktualnych danych',
    detail: 'Żadne źródło jakości powietrza nie przekazało bieżącego indeksu.',
    tone: 'muted',
    sourceName: '',
  };
}

function europeanAqiLabel(observation: ExternalObservationView): string {
  const unit = observation.displayUnit.trim();
  return unit.toUpperCase() === 'EAQI' ? `EAQI ${observation.displayValue}` : `EAQI ${observation.displayValue}${unit ? ` ${unit}` : ''}`;
}

export function observationDisplayName(observation: ExternalObservationView): string {
  const labels: Record<string, string> = {
    frost: 'Mróz i temperatura zewnętrzna',
    wind: 'Wiatr i porywy',
    rain: 'Opady',
    storm: 'Burze',
    official_warning: 'Oficjalne ostrzeżenia dla domu',
  };
  if (observation.hazardType === 'outdoor_air_pollution') {
    return 'Jakość powietrza dla współrzędnych domu';
  }
  return labels[observation.hazardType] ?? humanize(observation.hazardType);
}

export function localizedEntityState(entityId: string, state: unknown): string {
  const normalized = normalizeState(state);
  if (entityId.startsWith(FAULT_PREFIX)) {
    const labels: Record<FaultStatus, string> = {
      set: 'Aktywna',
      shadowed: 'Przesłonięta',
      cleared: 'Usunięta',
      not_tested: 'Niesprawdzona',
      unavailable: 'Niedostępna',
      unknown: 'Stan nieznany',
    };
    return labels[getFaultStatus(state)];
  }
  if (entityId.startsWith(RECOVERY_PREFIX)) {
    const labels: Record<RecoveryStatus, string> = {
      to_perform: 'Do wykonania',
      do_not_perform: 'Brak potrzeby działania',
      unavailable: 'Niedostępne',
      unknown: 'Stan nieznany',
    };
    return labels[getRecoveryStatus(state)];
  }
  if (entityId === SYSTEM_STATE_ENTITY_ID) return systemStatePresentation(state).label;
  if (entityId === HEALTH_ENTITY_ID) {
    const labels: Record<string, string> = {
      running: 'Działa',
      init: 'Uruchamianie',
      invalid_cfg: 'Błędna konfiguracja',
      stopped: 'Zatrzymany',
      unavailable: 'Niedostępny',
      unknown: 'Stan nieznany',
    };
    return labels[normalized] ?? humanize(normalized || 'stan nieznany');
  }
  return humanize(normalized || 'stan nieznany');
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

function stringArrayAttribute(entity: EntitySnapshot | undefined, key: string): string[] {
  const value = entity?.attributes[key];
  if (!Array.isArray(value)) return [];
  return value
    .map(String)
    .map(item => item.trim())
    .filter(Boolean);
}

function adviceInhibitionAttribute(entity: EntitySnapshot | undefined): AdviceInhibitionView[] {
  const value = entity?.attributes.advice_inhibition;
  if (!Array.isArray(value)) return [];
  return value.flatMap(item => {
    if (!item || typeof item !== 'object') return [];
    const record = item as Record<string, unknown>;
    const reason = typeof record.reason === 'string' ? record.reason : '';
    const source = typeof record.source === 'string' ? record.source : '';
    const validUntil = typeof record.valid_until === 'string' ? record.valid_until : undefined;
    return reason && source ? [{ reason, source, validUntil }] : [];
  });
}

function imgwWarningsAttribute(entity: EntitySnapshot | undefined): ImgwWarningView[] {
  const value = entity?.attributes.warnings;
  if (!Array.isArray(value)) return [];
  return value.flatMap(item => {
    if (!item || typeof item !== 'object') return [];
    const record = item as Record<string, unknown>;
    const id = typeof record.id === 'string' ? record.id.trim() : '';
    const eventName = typeof record.event_name === 'string' ? record.event_name.trim() : '';
    if (!id || !eventName) return [];
    return [
      {
        id,
        eventName,
        degree: String(record.degree ?? '').trim(),
        probability: String(record.probability ?? '').trim(),
        validFrom: typeof record.valid_from === 'string' ? record.valid_from : undefined,
        validTo: typeof record.valid_to === 'string' ? record.valid_to : undefined,
        publishedAt: typeof record.published_at === 'string' ? record.published_at : undefined,
        regions: Array.isArray(record.regions) ? record.regions.map(String) : [],
        content: typeof record.content === 'string' ? record.content : '',
        comment: typeof record.comment === 'string' ? record.comment : '',
        office: typeof record.office === 'string' ? record.office : '',
        locallyApplicable: record.locally_applicable === true,
      },
    ];
  });
}

function externalObservationsAttribute(entity: EntitySnapshot | undefined): ExternalObservationView[] {
  const value = entity?.attributes.observations;
  if (!Array.isArray(value)) return [];
  return value.flatMap(item => {
    if (!item || typeof item !== 'object') return [];
    const record = item as Record<string, unknown>;
    const id = typeof record.id === 'string' ? record.id.trim() : '';
    const hazardType = typeof record.hazard_type === 'string' ? record.hazard_type.trim() : '';
    if (!id || !hazardType) return [];
    return [
      {
        id,
        hazardType,
        providerLevel: String(record.provider_level ?? '').trim(),
        observedAt: typeof record.observed_at === 'string' ? record.observed_at : undefined,
        validTo: typeof record.valid_to === 'string' ? record.valid_to : undefined,
        displayValue: String(record.display_value ?? '').trim(),
        displayUnit: String(record.display_unit ?? '').trim(),
      },
    ];
  });
}

function temperatureRoomName(
  sourceEntity: EntitySnapshot,
  lowThresholdEntity: EntitySnapshot | undefined,
  highThresholdEntity: EntitySnapshot | undefined
): string {
  for (const thresholdEntity of [lowThresholdEntity, highThresholdEntity]) {
    const configuredName = stringAttribute(thresholdEntity, 'friendly_name');
    const roomMatch = configuredName.match(/[—–]\s*([^—–]+)$/);
    if (roomMatch?.[1]) return localizedRoomName(roomMatch[1]);
  }
  const sourceName = stringAttribute(sourceEntity, 'friendly_name');
  const prefix = sourceName.split(/\s+-\s+/, 1)[0]?.trim();
  if (prefix && prefix !== sourceName) return localizedRoomName(prefix);
  return localizedRoomName(
    sourceName.replace(/\s+(?:climate\s*sensor|czujnik\s+klimatu|heating\s+circuit).*$/i, '').replace(/\s+temperature$/i, '') || sourceName
  );
}

function localizedTechnicalName(value: string): string {
  const normalized = normalizeState(value).replace(/_/g, '');
  const labels: Record<string, string> = {
    riskytemperature: 'Niebezpieczna temperatura',
    riskytemperatureforecast: 'Ryzyko niebezpiecznej temperatury',
    safetydooropentimeout: 'Zbyt długo otwarte wejście',
    externalweatherexposure: 'Narażenie domu na pogodę',
    outdoorairqualityexposure: 'Narażenie na zanieczyszczone powietrze',
    externalhazarddataunavailable: 'Brak danych o warunkach zewnętrznych',
  };
  return labels[normalized] ?? localizedRoomName(value);
}

function localizedRoomName(value: string): string {
  const normalized = normalizeState(value).replace(/_/g, '');
  const labels: Record<string, string> = {
    bedroom: 'Sypialnia',
    entrance: 'Wejście',
    garage: 'Garaż',
    kidsroom: 'Pokój dziecięcy',
    kitchen: 'Kuchnia',
    livingroom: 'Salon',
    office: 'Biuro',
    upperbathroom: 'Łazienka na piętrze',
    heatingcircuittemperature: 'Kuchnia',
    thermostatcurrentroomtemperature: 'Kuchnia',
    safetyapphealth: 'Kondycja usługi',
    danepogodoweopenmeteo: 'Dane pogodowe Open-Meteo',
    jakoscpowietrzaopenmeteo: 'Jakość powietrza Open-Meteo',
  };
  return labels[normalized] ?? humanize(value);
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
