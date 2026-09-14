import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import NotificationHistory from './NotificationHistory.js';
import { formatNotificationTime, type NotificationEntry } from '../domain/notificationHistory.js';

const entries: NotificationEntry[] = [
  {
    id: 'active',
    tag: 'tag-active',
    kind: 'new',
    fault_state: 'SET',
    level: 2,
    title: 'Aktywne zagrożenie',
    message: 'Wymaga uwagi: Czujnik dymu.\nLokalizacja: Kuchnia',
    text_truncated: false,
    created_at: '2026-09-10T08:00:00+00:00',
    attempted_at: '2026-09-10T08:00:01+00:00',
    attempt: 1,
    service: 'notify/all_phones',
    result: 'accepted_by_home_assistant',
    deadline_missed: false,
  },
  {
    id: 'failed',
    tag: 'tag-failed',
    kind: 'resolved',
    fault_state: 'CLEARED',
    level: 2,
    title: 'Usterka ustąpiła',
    message: 'Czujnik działa prawidłowo.',
    text_truncated: false,
    created_at: '2026-09-10T09:00:00+00:00',
    attempted_at: '2026-09-10T09:00:01+00:00',
    attempt: 2,
    service: 'notify/mobile_app_phone',
    result: 'failed',
    deadline_missed: true,
  },
];

test('renders accepted notification content, recipient and diagnostic details', () => {
  const markup = renderToStaticMarkup(<NotificationHistory entries={entries} onRefresh={() => undefined} status='ready' total={2} />);

  assert.match(markup, /Historia powiadomień/);
  assert.match(markup, /Aktywne zagrożenie/);
  assert.match(markup, /Wszystkie telefony \(grupa\)/);
  assert.match(markup, /Numer próby/);
  assert.match(markup, /Przyjęto przez Home Assistant/);
  assert.doesNotMatch(markup, /Czujnik działa prawidłowo/);
});

test('shows disconnected state while retaining already read entries', () => {
  const markup = renderToStaticMarkup(
    <NotificationHistory entries={entries} onRefresh={() => undefined} status='disconnected' total={2} />
  );

  assert.match(markup, /Historia powiadomień jest niedostępna/);
  assert.match(markup, /Poniżej ostatnio odczytane wpisy/);
  assert.match(markup, /Aktywne zagrożenie/);
});

test('formats both date and time in the Polish browser presentation', () => {
  const formatted = formatNotificationTime('2026-09-10T08:00:01+00:00');

  assert.match(formatted, /2026/);
  assert.match(formatted, /\d{1,2}:\d{2}:\d{2}/);
});
