import { useMemo } from 'react';
import { useHass, useHistory, type EntityName } from '@hakit/core';
import { MOCK_MODE } from '../config';

type HistoryOptions = NonNullable<Parameters<typeof useHistory>[1]>;
type HistoryResult = ReturnType<typeof useHistory>;
type Timeline = HistoryResult['timeline'];

/**
 * Reads Home Assistant history and supplies deterministic samples in local
 * mock mode so every frontend state can be reviewed without HA credentials.
 */
export function useEntityHistory(entityId: string, options: HistoryOptions = {}): HistoryResult {
  const { useStore } = useHass();
  const currentState = useStore(store => store.entities[entityId]?.state);
  const liveHistory = useHistory(entityId as EntityName, {
    ...options,
    disable: MOCK_MODE || options.disable,
  });
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

  return MOCK_MODE
    ? {
        ...liveHistory,
        entityHistory: mockEntityHistory,
        loading: false,
        timeline: mockTimeline,
      }
    : liveHistory;
}

function createMockTimeline(entityId: string, currentState: string, hoursToShow: number): Timeline {
  const now = Date.now();
  const point = (state: string, fraction: number) => ({
    state,
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
    return [point('Cleared', 0.9), point('Set', 0.16)];
  }
  if (entityId === 'sensor.fault_riskytemperatureforecast') {
    return [point('Cleared', 0.8), point('Set', 0.3), point('Shadowed', 0.22)];
  }
  if (entityId === 'sensor.recovery_manipulatewindowoffice') {
    return [point('DO_NOT_PERFORM', 0.8), point('TO_PERFORM', 0.18)];
  }
  if (entityId === 'sensor.safetysystem_state') {
    return [point('0', 0.9), point('2', 0.17)];
  }

  return [point(currentState, 0.5)];
}
