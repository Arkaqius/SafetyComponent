import { type EntityMap } from './safety.js';

export const INTERNAL_ENVIRONMENT_SUMMARY_ID = 'sensor.internal_environment_summary';
export const INTERNAL_ENVIRONMENT_DETECTOR_PREFIX = 'sensor.internal_environment_';

export type InternalEnvironmentStatus = 'active_hazard' | 'healthy' | 'degraded' | 'unavailable' | 'unknown';
export type InternalDetectorStatus = 'alarm' | 'healthy' | 'degraded' | 'unavailable';

export interface InternalDetectorView {
  entityId: string;
  healthEntityId?: string;
  sourceEntityId: string;
  name: string;
  areaName: string;
  hazard: string;
  gasIdentity?: string;
  status: InternalDetectorStatus;
  currentState: string;
  classification: string;
  alarmActive: boolean;
  healthFaultActive: boolean;
  gasSwitchingInhibited: boolean;
  pendingAlarmClear: boolean;
  lastObservedAt?: string;
  lastAuthoritativeClearAt?: string;
  lastUpdated?: string;
}

export interface InternalEnvironmentView {
  entityId: string;
  status: InternalEnvironmentStatus;
  detectors: InternalDetectorView[];
  monitoredDetectors: number;
  activeHazards: number;
  unavailableDetectors: number;
  gasSwitchingInhibited: boolean;
  persistenceError?: string;
  lastUpdated?: string;
}

export function getInternalEnvironmentMonitoring(entities: EntityMap): InternalEnvironmentView {
  const summary = entities[INTERNAL_ENVIRONMENT_SUMMARY_ID];
  const detectors = Object.entries(entities)
    .filter(([entityId]) => entityId.startsWith(INTERNAL_ENVIRONMENT_DETECTOR_PREFIX) && entityId !== INTERNAL_ENVIRONMENT_SUMMARY_ID)
    .map(([entityId, entity]): InternalDetectorView => {
      const alarmActive = booleanAttribute(entity.attributes.alarm_active);
      const healthFaultActive = booleanAttribute(entity.attributes.health_fault_active);
      const classification = stringAttribute(entity.attributes.classification) || 'unknown';
      const sourceEntityId = stringAttribute(entity.attributes.source_entity_id);
      const healthEntityId = findHealthEntityId(entities, sourceEntityId);
      const status: InternalDetectorStatus = alarmActive
        ? 'alarm'
        : healthFaultActive
          ? 'unavailable'
          : ['unavailable', 'unevaluable'].includes(classification)
            ? 'degraded'
            : 'healthy';

      return {
        entityId,
        healthEntityId,
        sourceEntityId,
        name: stringAttribute(entity.attributes.friendly_name) || friendlyFallback(entityId),
        areaName: stringAttribute(entity.attributes.area_name) || stringAttribute(entity.attributes.area_id) || 'Brak lokalizacji',
        hazard: stringAttribute(entity.attributes.hazard) || 'unknown',
        gasIdentity: optionalStringAttribute(entity.attributes.gas_identity),
        status,
        currentState: stringAttribute(entity.attributes.current_state) || 'unknown',
        classification,
        alarmActive,
        healthFaultActive,
        gasSwitchingInhibited: booleanAttribute(entity.attributes.gas_switching_inhibited),
        pendingAlarmClear: booleanAttribute(entity.attributes.pending_alarm_clear),
        lastObservedAt: optionalStringAttribute(entity.attributes.last_observed_at),
        lastAuthoritativeClearAt: optionalStringAttribute(entity.attributes.last_authoritative_clear_at),
        lastUpdated: entity.last_updated,
      };
    })
    .sort((left, right) => hazardPriority(left.hazard) - hazardPriority(right.hazard) || left.name.localeCompare(right.name, 'pl'));

  const fallbackActive = detectors.filter(detector => detector.alarmActive).length;
  const fallbackUnavailable = detectors.filter(detector => detector.healthFaultActive).length;
  const activeHazards = numericAttribute(summary?.attributes.active_hazards) ?? fallbackActive;
  const unavailableDetectors = numericAttribute(summary?.attributes.unavailable_detectors) ?? fallbackUnavailable;
  const status = internalEnvironmentStatus(summary?.state, detectors, activeHazards, unavailableDetectors);

  return {
    entityId: INTERNAL_ENVIRONMENT_SUMMARY_ID,
    status,
    detectors,
    monitoredDetectors: numericAttribute(summary?.attributes.monitored_detectors) ?? detectors.length,
    activeHazards,
    unavailableDetectors,
    gasSwitchingInhibited:
      booleanAttribute(summary?.attributes.gas_switching_inhibited) || detectors.some(detector => detector.gasSwitchingInhibited),
    persistenceError: optionalStringAttribute(summary?.attributes.persistence_error),
    lastUpdated: summary?.last_updated ?? latestDetectorUpdate(detectors),
  };
}

function findHealthEntityId(entities: EntityMap, sourceEntityId: string): string | undefined {
  if (!sourceEntityId) return undefined;
  return Object.entries(entities).find(
    ([entityId, entity]) =>
      entityId.startsWith('sensor.entity_health_internal_environment_') &&
      stringAttribute(entity.attributes.source_entity_id) === sourceEntityId
  )?.[0];
}

function internalEnvironmentStatus(
  state: unknown,
  detectors: InternalDetectorView[],
  activeHazards: number,
  unavailableDetectors: number
): InternalEnvironmentStatus {
  const normalized = String(state ?? '')
    .trim()
    .toLowerCase();
  if (normalized === 'active_hazard' || activeHazards > 0) return 'active_hazard';
  if (normalized === 'unavailable' || unavailableDetectors > 0) return 'unavailable';
  if (normalized === 'degraded' || detectors.some(detector => detector.status === 'degraded')) return 'degraded';
  if (normalized === 'healthy' || detectors.length > 0) return 'healthy';
  return 'unknown';
}

function hazardPriority(hazard: string): number {
  return { smoke: 0, flammable_gas: 1, carbon_monoxide: 2 }[hazard] ?? 3;
}

function latestDetectorUpdate(detectors: InternalDetectorView[]): string | undefined {
  return detectors
    .map(detector => detector.lastUpdated)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1);
}

function booleanAttribute(value: unknown): boolean {
  return (
    value === true ||
    String(value ?? '')
      .trim()
      .toLowerCase() === 'true'
  );
}

function numericAttribute(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function stringAttribute(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function optionalStringAttribute(value: unknown): string | undefined {
  const parsed = stringAttribute(value);
  return parsed || undefined;
}

function friendlyFallback(entityId: string): string {
  return entityId
    .slice(INTERNAL_ENVIRONMENT_DETECTOR_PREFIX.length)
    .split('_')
    .filter(Boolean)
    .map(part => part.charAt(0).toLocaleUpperCase('pl') + part.slice(1))
    .join(' ');
}
