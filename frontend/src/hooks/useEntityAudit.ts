import { useEffect, useMemo, useState } from 'react';
import {
  subscribeAreaRegistry,
  subscribeDeviceRegistry,
  subscribeEntityRegistry,
  useHass,
  type AreaRegistryEntry,
  type DeviceRegistryEntry,
  type EntityRegistryEntry,
} from '@hakit/core';
import { buildDeviceInventory, buildEntityInventory, getEntityMonitorSummary, getMonitoredEntities } from '../domain/entityHealth';
import type { EntityMap } from '../domain/safety';

export function useEntityAudit() {
  const { useStore } = useHass();
  const rawEntities = useStore(store => store.entities);
  const connection = useStore(store => store.connection);
  const [entityRegistry, setEntityRegistry] = useState<EntityRegistryEntry[]>([]);
  const [deviceRegistry, setDeviceRegistry] = useState<DeviceRegistryEntry[]>([]);
  const [areaRegistry, setAreaRegistry] = useState<AreaRegistryEntry[]>([]);

  useEffect(() => {
    if (!connection) return;
    const unsubscribers = [
      subscribeEntityRegistry(connection, setEntityRegistry),
      subscribeDeviceRegistry(connection, setDeviceRegistry),
      subscribeAreaRegistry(connection, setAreaRegistry),
    ];
    return () => {
      for (const unsubscribe of unsubscribers) {
        void unsubscribe();
      }
    };
  }, [connection]);

  const entities = rawEntities as unknown as EntityMap;
  return useMemo(() => {
    const monitored = getMonitoredEntities(entities);
    const inventory = buildEntityInventory(entities, entityRegistry, deviceRegistry, areaRegistry, monitored);
    return {
      monitored,
      summary: getEntityMonitorSummary(entities, monitored),
      inventory,
      devices: buildDeviceInventory(inventory, deviceRegistry, areaRegistry),
      registriesAvailable: Boolean(connection),
    };
  }, [areaRegistry, connection, deviceRegistry, entities, entityRegistry]);
}
