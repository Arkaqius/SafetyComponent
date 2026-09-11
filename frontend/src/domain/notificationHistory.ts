import type { EntitySnapshot } from './safety.js';

export const NOTIFICATION_HISTORY_ENTITY_ID = 'sensor.notification_history';

export interface NotificationEntry {
  id: string;
  tag: string;
  kind: 'new' | 'update' | 'repeat' | 'resolved' | 'clear';
  fault_state: 'SET' | 'CLEARED' | 'SHADOWED';
  level: number;
  title: string;
  message: string;
  text_truncated: boolean;
  created_at: string;
  attempted_at: string;
  attempt: number;
  service: string;
  result: 'accepted_by_home_assistant' | 'failed';
  deadline_missed: boolean;
}

const states: Record<NotificationEntry['kind'], NotificationEntry['fault_state']> = {
  new: 'SET',
  update: 'SET',
  repeat: 'SET',
  resolved: 'CLEARED',
  clear: 'SHADOWED',
};

export function readNotificationHistory(entity?: EntitySnapshot): NotificationEntry[] {
  if (entity?.attributes.version !== 1 || !Array.isArray(entity.attributes.entries)) return [];
  return entity.attributes.entries
    .filter(isNotificationEntry)
    .slice(0, 100)
    .sort((left, right) => Date.parse(right.attempted_at) - Date.parse(left.attempted_at));
}

function isNotificationEntry(value: unknown): value is NotificationEntry {
  if (!value || typeof value !== 'object') return false;
  const entry = value as Record<string, unknown>;
  const textKeys = ['id', 'tag', 'title', 'message', 'service', 'created_at', 'attempted_at'];
  if (!textKeys.every(key => typeof entry[key] === 'string')) return false;
  return (
    Boolean(entry.id) &&
    Object.prototype.hasOwnProperty.call(states, String(entry.kind)) &&
    states[entry.kind as NotificationEntry['kind']] === entry.fault_state &&
    [1, 2, 3].includes(Number(entry.level)) &&
    typeof entry.level === 'number' &&
    Number.isInteger(entry.attempt) &&
    Number(entry.attempt) > 0 &&
    ['accepted_by_home_assistant', 'failed'].includes(String(entry.result)) &&
    typeof entry.deadline_missed === 'boolean' &&
    typeof entry.text_truncated === 'boolean' &&
    Number.isFinite(Date.parse(String(entry.created_at))) &&
    Number.isFinite(Date.parse(String(entry.attempted_at)))
  );
}

export function notificationRecipient(service: string): string {
  if (service === 'notify/all_phones') return 'Wszystkie telefony (grupa)';
  return service
    .replace(/^notify\//, '')
    .replace(/^mobile_app_/, '')
    .replace(/_/g, ' ');
}

export function notificationKind(kind: NotificationEntry['kind']): string {
  return {
    new: 'Nowe zgłoszenie',
    update: 'Aktualizacja',
    repeat: 'Przypomnienie',
    resolved: 'Usterka ustąpiła',
    clear: 'Usunięcie powiadomienia',
  }[kind];
}

export function notificationState(state: NotificationEntry['fault_state']): string {
  return { SET: 'Usterka aktywna', CLEARED: 'Usterka ustąpiła', SHADOWED: 'Usterka przesłonięta' }[state];
}
