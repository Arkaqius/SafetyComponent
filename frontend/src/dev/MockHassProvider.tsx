import { type ReactNode } from 'react';
import { useHass, type Store } from '@hakit/core';
import { MOCK_ENTITIES } from './mockData';
import { type EntityMap } from '../domain/safety';

type MockMessage = { type: string; event_type?: string; event_data?: Record<string, unknown>; entity_ids?: string[] };
const messages: MockMessage[] = [];
const eventListeners = new Map<string, Set<(event: { data: unknown }) => void>>();
const historyResponses = new Map<string, unknown>();
let failNext = false;
const connection = {
  addEventListener() {},
  removeEventListener() {},
  async sendMessagePromise(message: MockMessage) {
    if (message.type.startsWith('config/')) return [];
    messages.push(structuredClone(message));
    if (failNext) {
      failNext = false;
      throw new Error('Mock transport failure');
    }
    if (message.event_type === 'safetyhome_notification_history_request') {
      queueMicrotask(() => {
        const entries = useHass.getState().entities['sensor.notification_history']?.attributes.entries ?? [];
        eventListeners.get('safetyhome_notification_history_response')?.forEach(listener =>
          listener({
            data: {
              version: 1,
              status: 'ok',
              request_id: message.event_data?.request_id,
              revision: 'mock-1',
              total: Array.isArray(entries) ? entries.length : 0,
              entries,
              next_cursor: null,
            },
          })
        );
      });
    }
    if (message.event_type === 'safety_notification_acknowledge') {
      const entities = structuredClone(useHass.getState().entities);
      const health = entities['sensor.notification_delivery_health'];
      if (health) health.attributes.acknowledged_tags = [message.event_data?.tag];
      useHass.setState({ entities });
    }
    return {};
  },
  async subscribeEvents(callback: (event: { data: unknown }) => void, eventType: string) {
    const listeners = eventListeners.get(eventType) ?? new Set();
    eventListeners.set(eventType, listeners);
    listeners.add(callback);
    return () => {
      listeners.delete(callback);
    };
  },
  async subscribeMessage(callback: (value: unknown) => void, message: MockMessage) {
    const entityId = message.entity_ids?.[0] ?? '';
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      callback(
        historyResponses.has(entityId)
          ? historyResponses.get(entityId)
          : { states: { [entityId]: [{ s: useHass.getState().entities[entityId]?.state ?? 'unknown', lu: Date.now() / 1000 - 3600 }] } }
      );
    });
    return () => {
      active = false;
    };
  },
};

const mockStore = {
  entities: MOCK_ENTITIES as unknown as Store['entities'],
  connection: connection as unknown as Store['connection'],
  connectionStatus: 'connected',
  ready: true,
  hassUrl: 'mock://home-assistant',
} satisfies Partial<Store>;

useHass.setState(mockStore);

/** Isolated DEV-only controls; no message leaves this local provider. */
const mockControls = {
  messages,
  snapshot: (): EntityMap => structuredClone(useHass.getState().entities) as unknown as EntityMap,
  update: (value: { entities?: EntityMap; connectionStatus?: Store['connectionStatus']; ready?: boolean }) =>
    useHass.setState(value as Partial<Store>),
  failNextMessage: () => {
    failNext = true;
  },
  setHistory: (entityId: string, payload: unknown) => {
    historyResponses.set(entityId, payload);
  },
  reset: () => {
    messages.length = 0;
    historyResponses.clear();
    failNext = false;
    useHass.setState(mockStore);
  },
};
declare global {
  interface Window {
    __safetyHomeMock: typeof mockControls;
  }
}
window.__safetyHomeMock = mockControls;

/**
 * Provides deterministic SafetyComponent data for local visual development.
 * It is only selected when Vite runs in development mode with VITE_HA_MOCK=true.
 */
export default function MockHassProvider({ children }: { children: ReactNode }) {
  return children;
}
