import { type ReactNode } from 'react';
import { useHass, type Store } from '@hakit/core';
import { MOCK_ENTITIES } from './mockData';
import { type EntityMap } from '../domain/safety';
import { resetRoutineDemo, routineDemoResponse } from './mockSafetyRoutines';

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
    if (message.event_type === 'safety_routine_request') {
      queueMicrotask(() =>
        eventListeners
          .get('safety_routine_response')
          ?.forEach(listener => listener({ data: routineDemoResponse(message.event_data ?? {}) }))
      );
    }
    if (message.event_type === 'safety_notification_acknowledge') {
      const entities = structuredClone(useHass.getState().entities);
      const health = entities['sensor.notification_delivery_health'];
      if (health) health.attributes.acknowledged_tags = [message.event_data?.tag];
      useHass.setState({ entities });
    }
    if (message.event_type === 'safety_recovery_report') {
      const entities = structuredClone(useHass.getState().entities);
      for (const [entityId, entity] of Object.entries(entities)) {
        if (!entityId.startsWith('sensor.recovery_') || !Array.isArray(entity.attributes.proposals)) continue;
        for (const raw of entity.attributes.proposals) {
          const proposal = raw as Record<string, unknown>;
          if (
            !proposal.report_token ||
            proposal.reported_at ||
            proposal.status !== 'TO_PERFORM' ||
            proposal.proposal_id !== message.event_data?.proposal_id ||
            proposal.proposal_instance_id !== message.event_data?.proposal_instance_id ||
            proposal.report_token !== message.event_data?.report_token ||
            proposal.manual_report_allowed !== true
          )
            continue;
          // Demo receipt only: observed repairs deliberately remain pending and faults stay active.
          proposal.reported_at = new Date().toISOString();
          proposal.report_source = 'operator';
          proposal.report_status = proposal.completion_condition === 'operator_report' ? 'completed' : 'awaiting_evidence';
          proposal.report_token = '';
          if (proposal.completion_condition === 'operator_report') {
            proposal.status = 'CONFIRMED';
            entity.state = 'CONFIRMED';
          }
        }
      }
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
    resetRoutineDemo();
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
