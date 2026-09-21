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

export type RegistryStatus = 'disconnected' | 'loading' | 'ready' | 'error';

export function useEntityAudit() {
  const rawEntities = useHass(store => store.entities);
  const connection = useHass(store => store.connection);
  const [entityRegistry, setEntityRegistry] = useState<EntityRegistryEntry[]>([]);
  const [deviceRegistry, setDeviceRegistry] = useState<DeviceRegistryEntry[]>([]);
  const [areaRegistry, setAreaRegistry] = useState<AreaRegistryEntry[]>([]);
  const [registryStatus, setRegistryStatus] = useState<RegistryStatus>('disconnected');

  useEffect(() => {
    if (!connection) {
      setRegistryStatus('disconnected');
      return;
    }
    let cancelled = false;
    setRegistryStatus('loading');
    void Promise.all([
      connection.sendMessagePromise<EntityRegistryEntry[]>({ type: 'config/entity_registry/list' }),
      connection.sendMessagePromise<DeviceRegistryEntry[]>({ type: 'config/device_registry/list' }),
      connection.sendMessagePromise<AreaRegistryEntry[]>({ type: 'config/area_registry/list' }),
    ])
      .then(([entities, devices, areas]) => {
        if (cancelled) return;
        setEntityRegistry(entities);
        setDeviceRegistry(devices);
        setAreaRegistry(areas);
        setRegistryStatus('ready');
      })
      .catch(() => {
        if (!cancelled) setRegistryStatus('error');
      });

    const unsubscribers = [
      subscribeEntityRegistry(connection, setEntityRegistry),
      subscribeDeviceRegistry(connection, setDeviceRegistry),
      subscribeAreaRegistry(connection, setAreaRegistry),
    ];
    return () => {
      cancelled = true;
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
      registryStatus,
    };
  }, [areaRegistry, deviceRegistry, entities, entityRegistry, registryStatus]);
}
