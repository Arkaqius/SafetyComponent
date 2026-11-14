import { useEffect, useMemo, useState } from 'react';
import { useHass } from '@hakit/core';
import {
  getFaults,
  getExternalHazardMonitoring,
  invalidateExternalMonitoring,
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
import { getStartupView } from '../domain/startup';

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
    let externalHazards = getExternalHazardMonitoring(entities, Math.max(clock, Date.now()));
    if (cannotConnect || !ready) {
      externalHazards = invalidateExternalMonitoring(externalHazards);
    }
    const internalEnvironment = getInternalEnvironmentMonitoring(entities);
    const healthEntity = entities[HEALTH_ENTITY_ID];
    const systemEntity = entities[SYSTEM_STATE_ENTITY_ID];
    const startup = getStartupView(entities, clock, !cannotConnect && ready);
    const summary = getSafetySummary(
      healthEntity,
      systemEntity,
      faults,
      recoveries,
      cannotConnect || !ready ? 'disconnected' : 'connected'
    );
    if (startup && summary.activeFaultCount === 0 && summary.tone !== 'critical' && summary.effectiveLevel === null) {
      summary.label = startup.label;
      summary.detail = startup.available
        ? 'Diagnostyka stabilizuje się po restarcie. Pełna ocena dostępności źródeł nie jest jeszcze gotowa.'
        : startup.detail;
      summary.tone = 'warning';
    }

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
      summary,
      connection: {
        cannotConnect,
        status: connectionStatus,
        ready,
      },
    };
  }, [cannotConnect, clock, connectionStatus, entities, ready]);
}
