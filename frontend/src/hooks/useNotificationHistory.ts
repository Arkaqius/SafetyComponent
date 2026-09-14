import { useCallback, useEffect, useMemo, useState } from 'react';
import { useHass } from '@hakit/core';
import type { HassEvent } from 'home-assistant-js-websocket';
import {
  NOTIFICATION_HISTORY_RESPONSE_EVENT,
  notificationHistoryRequest,
  readNotificationHistory,
  readNotificationHistoryResponse,
  type NotificationEntry,
  type NotificationHistoryResponse,
  type NotificationHistoryStatus,
} from '../domain/notificationHistory.js';
import type { EntitySnapshot } from '../domain/safety.js';

const RESPONSE_TIMEOUT_MS = 8_000;

export function useNotificationHistory(legacyEntity?: EntitySnapshot) {
  const { useStore } = useHass();
  const connection = useStore(store => store.connection);
  const ready = useStore(store => store.ready);
  const cannotConnect = useStore(store => store.cannotConnect);
  const legacyEntries = useMemo(() => readNotificationHistory(legacyEntity), [legacyEntity]);
  const [entries, setEntries] = useState<NotificationEntry[]>(legacyEntries);
  const [total, setTotal] = useState(legacyEntries.length);
  const [status, setStatus] = useState<NotificationHistoryStatus>(
    connection ? 'loading' : legacyEntries.length && ready && !cannotConnect ? 'ready' : 'disconnected'
  );
  const [refreshSequence, setRefreshSequence] = useState(0);
  const refresh = useCallback(() => setRefreshSequence(sequence => sequence + 1), []);

  useEffect(() => {
    if (!connection || !ready || cannotConnect) {
      setEntries(current => (legacyEntries.length > 0 ? legacyEntries : current));
      setTotal(current => (legacyEntries.length > 0 ? legacyEntries.length : current));
      setStatus(legacyEntries.length > 0 && ready && !cannotConnect ? 'ready' : 'disconnected');
      return;
    }

    let cancelled = false;
    let unsubscribe: (() => Promise<void>) | undefined;
    const waiters = new Map<string, (response: NotificationHistoryResponse) => void>();
    const timers = new Map<string, number>();
    setStatus('loading');

    const requestPage = (cursor?: string, revision?: string): Promise<NotificationHistoryResponse> => {
      const requestId = createRequestId();
      return new Promise((resolve, reject) => {
        waiters.set(requestId, resolve);
        timers.set(
          requestId,
          window.setTimeout(() => {
            waiters.delete(requestId);
            timers.delete(requestId);
            reject(new Error('notification_history_timeout'));
          }, RESPONSE_TIMEOUT_MS)
        );
        void connection.sendMessagePromise<unknown>(notificationHistoryRequest(requestId, cursor, revision)).catch(error => {
          const timer = timers.get(requestId);
          if (timer !== undefined) window.clearTimeout(timer);
          timers.delete(requestId);
          waiters.delete(requestId);
          reject(error);
        });
      });
    };

    const load = async () => {
      try {
        const subscribed = await connection.subscribeEvents<HassEvent>(event => {
          const requestId = typeof event.data?.request_id === 'string' ? event.data.request_id : '';
          const response = readNotificationHistoryResponse(event.data, requestId);
          const resolve = waiters.get(requestId);
          if (!response || !resolve) return;
          const timer = timers.get(requestId);
          if (timer !== undefined) window.clearTimeout(timer);
          timers.delete(requestId);
          waiters.delete(requestId);
          resolve(response);
        }, NOTIFICATION_HISTORY_RESPONSE_EVENT);
        if (cancelled) {
          await subscribed();
          return;
        }
        unsubscribe = subscribed;

        const loaded: NotificationEntry[] = [];
        let cursor: string | undefined;
        let revision: string | undefined;
        let expectedTotal = 0;
        do {
          const response = await requestPage(cursor, revision);
          if (response.status === 'error') throw new Error(response.error);
          revision = revision ?? response.revision;
          if (response.revision !== revision) throw new Error('stale_revision');
          expectedTotal = response.total;
          loaded.push(...response.entries);
          cursor = response.next_cursor ?? undefined;
        } while (cursor && loaded.length < 100);

        if (!cancelled) {
          setEntries(deduplicateEntries(loaded));
          setTotal(expectedTotal);
          setStatus('ready');
        }
      } catch {
        if (!cancelled) {
          setEntries(current => (legacyEntries.length > 0 ? legacyEntries : current));
          setTotal(current => (legacyEntries.length > 0 ? legacyEntries.length : current));
          setStatus('error');
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
      for (const timer of timers.values()) window.clearTimeout(timer);
      timers.clear();
      waiters.clear();
      if (unsubscribe) void unsubscribe();
    };
  }, [cannotConnect, connection, legacyEntries, ready, refreshSequence]);

  return { entries, total, status, refresh };
}

function createRequestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return `request-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function deduplicateEntries(entries: NotificationEntry[]): NotificationEntry[] {
  const seen = new Set<string>();
  return entries.filter(entry => {
    if (seen.has(entry.id)) return false;
    seen.add(entry.id);
    return true;
  });
}
