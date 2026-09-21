import { useMemo } from 'react';
import { useHass } from '@hakit/core';
import {
  getFaults,
  getExternalHazardMonitoring,
  getMonitoredTemperatures,
  getRecentActivity,
  getRecoveries,
  getSafetyDoors,
  getSafetySummary,
  HEALTH_ENTITY_ID,
  SYSTEM_STATE_ENTITY_ID,
  type EntityMap,
} from '../domain/safety';
import { getEntityMonitorSummary, getMonitoredEntities } from '../domain/entityHealth';
import { getInternalEnvironmentMonitoring } from '../domain/internalHazards';

export function useSafetyEntities() {
  const rawEntities = useHass(store => store.entities);
  const connectionStatus = useHass(store => store.connectionStatus);
  const ready = useHass(store => store.ready);
  const cannotConnect = connectionStatus === 'disconnected';
  const lastUpdated = useMemo(() => latestEntityUpdate(rawEntities), [rawEntities]);
  const entities = rawEntities as unknown as EntityMap;

  return useMemo(() => {
    const faults = getFaults(entities);
    const recoveries = getRecoveries(entities);
    const temperatures = getMonitoredTemperatures(entities);
    const safetyDoors = getSafetyDoors(entities);
    const externalHazards = getExternalHazardMonitoring(entities);
    const internalEnvironment = getInternalEnvironmentMonitoring(entities);
    const healthEntity = entities[HEALTH_ENTITY_ID];
    const systemEntity = entities[SYSTEM_STATE_ENTITY_ID];
    const monitoredEntities = getMonitoredEntities(entities);

    return {
      entities,
      healthEntity,
      systemEntity,
      faults,
      recoveries,
      temperatures,
      safetyDoors,
      externalHazards,
      internalEnvironment,
      monitoredEntities,
      entityMonitorSummary: getEntityMonitorSummary(entities, monitoredEntities),
      recentActivity: getRecentActivity(entities),
      summary: getSafetySummary(healthEntity, systemEntity, faults, recoveries),
      connection: {
        cannotConnect,
        ready,
        lastUpdated,
      },
    };
  }, [cannotConnect, entities, lastUpdated, ready]);
}

function latestEntityUpdate(entities: ReturnType<typeof useHass.getState>['entities']): Date | undefined {
  let latestTimestamp = 0;
  for (const entity of Object.values(entities)) {
    const timestamp = Date.parse(entity.last_updated);
    if (Number.isFinite(timestamp)) latestTimestamp = Math.max(latestTimestamp, timestamp);
  }
  return latestTimestamp > 0 ? new Date(latestTimestamp) : undefined;
}
