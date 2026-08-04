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

export function useSafetyEntities() {
  const { useStore } = useHass();
  const rawEntities = useStore(store => store.entities);
  const cannotConnect = useStore(store => store.cannotConnect);
  const ready = useStore(store => store.ready);
  const lastUpdated = useStore(store => store.lastUpdated);
  const entities = rawEntities as unknown as EntityMap;

  return useMemo(() => {
    const faults = getFaults(entities);
    const recoveries = getRecoveries(entities);
    const temperatures = getMonitoredTemperatures(entities);
    const safetyDoors = getSafetyDoors(entities);
    const externalHazards = getExternalHazardMonitoring(entities);
    const healthEntity = entities[HEALTH_ENTITY_ID];
    const systemEntity = entities[SYSTEM_STATE_ENTITY_ID];

    return {
      entities,
      healthEntity,
      systemEntity,
      faults,
      recoveries,
      temperatures,
      safetyDoors,
      externalHazards,
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
