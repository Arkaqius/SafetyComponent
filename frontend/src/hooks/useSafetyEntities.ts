import { useEffect, useMemo, useState } from 'react';
import { useHass } from '@hakit/core';
import {
  getFaults,
  getExternalHazardMonitoring,
  getAirQualityPresentation,
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
  const [clock, setClock] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  const rawEntities = useHass(store => store.entities);
  const connectionStatus = useHass(store => store.connectionStatus);
  const ready = useHass(store => store.ready);
  const cannotConnect = connectionStatus !== 'connected';
  const lastUpdated = useMemo(() => latestEntityUpdate(rawEntities), [rawEntities]);
  const entities = rawEntities as unknown as EntityMap;

  return useMemo(() => {
    const faults = getFaults(entities);
    const recoveries = getRecoveries(entities);
    const monitoredEntities = getMonitoredEntities(entities);
    const temperatures = getMonitoredTemperatures(entities).map(temperature => {
      const areaName = monitoredEntities.find(entity => entity.entityId === temperature.entityId)?.areaName;
      return areaName ? { ...temperature, roomName: areaName } : temperature;
    });
    const safetyDoors = getSafetyDoors(entities);
    const externalHazards = getExternalHazardMonitoring(entities);
    if (cannotConnect || !ready) {
      externalHazards.providers = externalHazards.providers.map(provider =>
        provider.status === 'ok' ? { ...provider, status: 'stale' } : provider
      );
      if (externalHazards.status === 'clear') externalHazards.status = 'unavailable';
    }
    const internalEnvironment = getInternalEnvironmentMonitoring(entities);
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
      airQuality: getAirQualityPresentation(externalHazards, clock),
      internalEnvironment,
      monitoredEntities,
      entityMonitorSummary: getEntityMonitorSummary(entities, monitoredEntities),
      recentActivity: getRecentActivity(entities),
      summary: getSafetySummary(healthEntity, systemEntity, faults, recoveries, cannotConnect || !ready ? 'disconnected' : 'connected'),
      connection: {
        cannotConnect,
        status: connectionStatus,
        ready,
        lastUpdated,
      },
    };
  }, [cannotConnect, clock, connectionStatus, entities, lastUpdated, ready]);
}

function latestEntityUpdate(entities: ReturnType<typeof useHass.getState>['entities']): Date | undefined {
  let latestTimestamp = 0;
  for (const [entityId, entity] of Object.entries(entities)) {
    if (entityId !== HEALTH_ENTITY_ID && entityId !== SYSTEM_STATE_ENTITY_ID) continue;
    const timestamp = Date.parse(entity.last_updated);
    if (Number.isFinite(timestamp)) latestTimestamp = Math.max(latestTimestamp, timestamp);
  }
  return latestTimestamp > 0 ? new Date(latestTimestamp) : undefined;
}
