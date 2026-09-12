import assert from 'node:assert/strict';
import test from 'node:test';
import {
  notificationKind,
  notificationRecipient,
  notificationState,
  readNotificationHistory,
  type NotificationEntry,
} from './notificationHistory.js';

const entry: NotificationEntry = {
  id: 'first',
  tag: 'temperature',
  kind: 'new',
  fault_state: 'SET',
  level: 2,
  title: 'Usterka',
  message: 'Biuro',
  text_truncated: false,
  created_at: '2026-09-10T08:00:00+00:00',
  attempted_at: '2026-09-10T08:00:01+00:00',
  attempt: 1,
  service: 'notify/all_phones',
  result: 'accepted_by_home_assistant',
  deadline_missed: false,
};

test('keeps set, healed and failure entries distinct and newest first', () => {
  const healed = { ...entry, id: 'healed', kind: 'resolved', fault_state: 'CLEARED', attempted_at: '2026-09-10T09:00:00+00:00' };
  const failed = { ...entry, id: 'failed', result: 'failed' };
  const actual = readNotificationHistory({ state: '3', attributes: { version: 1, entries: [entry, failed, healed] } });
  assert.deepEqual(
    actual.map(e => e.id),
    ['healed', 'first', 'failed']
  );
  assert.equal(actual.filter(e => e.result === 'accepted_by_home_assistant').length, 2);
});

test('rejects unavailable shapes, malformed dates and inconsistent fault states', () => {
  assert.deepEqual(readNotificationHistory(), []);
  assert.deepEqual(readNotificationHistory({ state: '0', attributes: {} }), []);
  const actual = readNotificationHistory({
    state: '5',
    attributes: {
      version: 1,
      entries: [null, {}, { ...entry, attempted_at: 'invalid' }, { ...entry, kind: 'clear', fault_state: 'CLEARED' }, entry],
    },
  });
  assert.deepEqual(actual, [entry]);
  assert.deepEqual(readNotificationHistory({ state: '1', attributes: { version: 2, entries: [entry] } }), []);
});

test('renders recipient groups without inventing a person and distinguishes shadowing', () => {
  assert.equal(notificationRecipient('notify/all_phones'), 'Wszystkie telefony (grupa)');
  assert.equal(notificationRecipient('notify/mobile_app_test_phone'), 'test phone');
  assert.equal(notificationState('SHADOWED'), 'Usterka przesłonięta');
  assert.equal(notificationState('CLEARED'), 'Usterka ustąpiła');
  assert.equal(notificationKind('acknowledged'), 'Potwierdzenie użytkownika');
});
