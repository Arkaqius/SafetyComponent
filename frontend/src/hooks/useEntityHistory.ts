import { useEffect, useMemo, useState } from 'react';
import { useHass } from '@hakit/core';
import { MOCK_MODE } from '../config';
import { historyTimeline, mergeHistoryStates, readHistoryStates, type HistoryState, type HistoryPoint } from '../domain/history';

interface HistoryOptions {
  disable?: boolean;
  hoursToShow?: number;
  minimalResponse?: boolean;
  significantChangesOnly?: boolean;
}
export type HistoryStatus = 'disabled' | 'loading' | 'ready' | 'error' | 'disconnected';
interface HistoryResult {
  timeline: HistoryPoint[];
  entityHistory: HistoryState[];
  coordinates: number[][];
  loading: boolean;
  status: HistoryStatus;
  error: string | null;
}
type Timeline = HistoryPoint[];

/**
 * Reads Home Assistant history and supplies deterministic samples in local
 * mock mode so every frontend state can be reviewed without HA credentials.
 */
export function useEntityHistory(entityId: string, options: HistoryOptions = {}): HistoryResult {
  const currentState = useHass(store => store.entities[entityId]?.state);
  const connection = useHass(store => store.connection);
  const connectionStatus = useHass(store => store.connectionStatus);
  const ready = useHass(store => store.ready);
  const synthetic = MOCK_MODE && !connection;
  const hours = options.hoursToShow ?? 24;
  const minimalResponse = options.minimalResponse ?? true;
  const significantChangesOnly = options.significantChangesOnly ?? true;
  const disable = Boolean(options.disable);
  const key = JSON.stringify([entityId, hours, minimalResponse, significantChangesOnly, disable]);
  const [snapshot, setSnapshot] = useState<{ key: string; connection: typeof connection; history: HistoryResult } | null>(null);
  useEffect(() => {
    setSnapshot(null);
    if (synthetic || disable || !connection || !ready || connectionStatus !== 'connected') return;
    let cancelled = false;
    let unsubscribe: (() => void | Promise<void>) | undefined;
    let states: HistoryState[] = [];
    const timer = window.setTimeout(() => publish('error', 'Historia nie odpowiedziała w wymaganym czasie.'), 8_000);
    const publish = (status: HistoryStatus, error: string | null = null) => {
      if (!cancelled)
        setSnapshot({
          key,
          connection,
          history: {
            timeline: historyTimeline(states),
            entityHistory: states,
            coordinates: [],
            loading: status === 'loading',
            status,
            error,
          },
        });
    };
    publish('loading');
    void connection
      .subscribeMessage<unknown>(
        message => {
          if (cancelled) return;
          window.clearTimeout(timer);
          try {
            states = mergeHistoryStates(states, readHistoryStates(message, entityId), Date.now() - hours * 3_600_000);
            publish('ready');
          } catch {
            states = [];
            publish('error', 'Rejestrator zwrócił nieprawidłowe dane historii.');
          }
        },
        {
          type: 'history/stream',
          entity_ids: [entityId],
          start_time: new Date(Date.now() - hours * 3_600_000).toISOString(),
          minimal_response: minimalResponse,
          significant_changes_only: significantChangesOnly,
        }
      )
      .then(stop => {
        if (cancelled) void stop();
        else unsubscribe = stop;
      })
      .catch(() => {
        window.clearTimeout(timer);
        publish('error', 'Nie udało się odczytać historii.');
      });
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      if (unsubscribe) void unsubscribe();
    };
  }, [connection, connectionStatus, disable, entityId, hours, key, minimalResponse, ready, significantChangesOnly, synthetic]);
  const mockTimeline = useMemo(
    () => createMockTimeline(entityId, currentState ?? 'unknown', options.hoursToShow ?? 24),
    [currentState, entityId, options.hoursToShow]
  );
  const mockEntityHistory = useMemo(
    () =>
      mockTimeline.map(item => ({
        s: item.state,
        a: {},
        lc: item.last_changed / 1000,
        lu: item.last_changed / 1000,
      })),
    [mockTimeline]
  );

  const status: HistoryStatus = disable
    ? 'disabled'
    : !connection || !ready || connectionStatus !== 'connected'
      ? 'disconnected'
      : 'loading';
  const liveHistory: HistoryResult =
    snapshot?.key === key && snapshot.connection === connection && status === 'loading'
      ? snapshot.history
      : { timeline: [], entityHistory: [], coordinates: [], loading: status === 'loading', status, error: null };
  return synthetic && !disable
    ? {
        ...liveHistory,
        entityHistory: mockEntityHistory,
        loading: false,
        timeline: mockTimeline,
        status: 'ready',
        error: null,
      }
    : liveHistory;
}

function createMockTimeline(entityId: string, currentState: string, hoursToShow: number): Timeline {
  const now = Date.now();
  const point = (state: string, fraction: number) => ({
    state,
    state_localize: state,
    last_changed: now - hoursToShow * fraction * 3_600_000,
  });
  if (entityId.includes('temperature') && !entityId.endsWith('_rate') && !entityId.endsWith('_rateofrate')) {
    const currentValue = Number(currentState);
    if (Number.isFinite(currentValue)) {
      const values = [currentValue - 0.4, currentValue - 0.2, currentValue - 0.3, currentValue, currentValue + 0.1, currentValue];
      return values.map((value, index) => point(value.toFixed(2), 1 - index / values.length));
    }
  }

  if (entityId === 'sensor.fault_riskytemperature') {
    return [point('PASS', 0.9), point('FAIL', 0.16)];
  }
  if (entityId === 'sensor.fault_riskytemperatureforecast') {
    return [point('PASS', 0.8), point('FAIL', 0.3)];
  }
  if (entityId === 'sensor.recovery_manipulatewindowoffice') {
    return [point('DO_NOT_PERFORM', 0.8), point('TO_PERFORM', 0.18)];
  }
  if (entityId === 'sensor.safetysystem_state') {
    return [point('no_faults', 0.9), point('hazard', 0.17)];
  }

  if (entityId.startsWith('binary_sensor.')) {
    const normalized = String(currentState).toLowerCase();
    const minutePoint = (state: string, minutesAgo: number) => ({
      state,
      state_localize: state,
      last_changed: now - minutesAgo * 60_000,
    });
    if (['on', 'open', 'opened'].includes(normalized)) {
      return [minutePoint('off', 300), minutePoint('on', 260), minutePoint('off', 248), minutePoint('on', 20)];
    }
    return [minutePoint('off', 300), minutePoint('on', 185), minutePoint('off', 169)];
  }

  return [point(currentState, 0.5)];
}
