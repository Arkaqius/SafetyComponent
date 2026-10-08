import assert from 'node:assert/strict';
import test from 'node:test';
import { notificationIdentity, type NotificationEntry } from './notificationHistory.js';

const entry: NotificationEntry = {
  id: 'one',
  tag: 'forecast',
  kind: 'new',
  fault_state: 'SET',
  level: 3,
  title: 'Sprawdź, co dzieje się w domu',
  message: '',
  text_truncated: false,
  created_at: '2026-10-05T16:20:00Z',
  attempted_at: '2026-10-05T16:20:00Z',
  attempt: 1,
  service: 'notify/test',
  result: 'accepted_by_home_assistant',
  deadline_missed: false,
};

test('identity is taken from each recorded localized message rather than its generic title', () => {
  for (const message of [
    'Wymaga uwagi: Prognoza temperatury.\nLokalizacja: Garaż',
    'Dobra wiadomość - problem „Prognoza temperatury” został rozwiązany.\nLokalizacja: Garaż',
    'Prognoza temperatury needs your attention.\nLocation: Garaż',
    'Good news - Prognoza temperatury is no longer active.\nLocation: Garaż',
    'Prognoza temperatury erfordert Ihre Aufmerksamkeit.\nOrt: Garaż',
    'Gute Nachricht – Prognoza temperatury ist nicht mehr aktiv.\nOrt: Garaż',
  ])
    assert.deepEqual(notificationIdentity({ ...entry, message }), {
      faultName: 'Prognoza temperatury',
      location: 'Garaż',
      inherited: false,
    });
});

test('clear commands reuse only earlier recorded identity for the same tag and mark it as historical', () => {
  const clear: NotificationEntry = {
    ...entry,
    id: 'clear',
    kind: 'clear',
    fault_state: 'SHADOWED',
    message: 'clear_notification',
    attempted_at: '2026-10-05T16:30:00Z',
  };
  const older = { ...entry, message: 'Wymaga uwagi: Prognoza temperatury.\nLokalizacja: Garaż' };
  const future = { ...older, id: 'future', message: 'Wymaga uwagi: Inna nazwa.\nLokalizacja: Biuro', attempted_at: '2026-10-05T17:00:00Z' };
  const unrelated = { ...older, tag: 'unrelated', message: 'Wymaga uwagi: Inna usterka.\nLokalizacja: Kuchnia' };
  assert.deepEqual(notificationIdentity(clear, [future, unrelated, older]), {
    faultName: 'Prognoza temperatury',
    location: 'Garaż',
    inherited: true,
  });
  assert.deepEqual(notificationIdentity(clear, [future, unrelated]), { faultName: '', location: '', inherited: false });
});

test('missing historical identity stays missing instead of treating a generic title as the fault', () => {
  assert.deepEqual(notificationIdentity({ ...entry, message: 'Wymaga uwagi' }), { faultName: '', location: '', inherited: false });
  assert.equal(
    notificationIdentity({ ...entry, message: 'Wymaga uwagi: Prognoza.\nLokalizacja:\nPróg bezpieczeństwa: 28 °C' }).location,
    ''
  );
});
