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

test('concise alert titles preserve recorded identity without guessing a dash-separated location', () => {
  assert.deepEqual(
    notificationIdentity({ ...entry, title: 'Brak odczytu: Okno sypialni — prawe', message: 'Sprawdź zasilanie i łączność czujnika.' }),
    {
      faultName: 'Brak odczytu: Okno sypialni — prawe',
      location: '',
      inherited: false,
    }
  );
  assert.deepEqual(notificationIdentity({ ...entry, title: 'PILNE: Czujnik dymu — Salon', message: 'Opuść zagrożone miejsce.' }), {
    faultName: 'Czujnik dymu — Salon',
    location: '',
    inherited: false,
  });
});

test('concise resolved subjects and clear inheritance use only stored content', () => {
  const resolved: NotificationEntry = {
    ...entry,
    kind: 'resolved',
    fault_state: 'CLEARED',
    title: 'Problem ustąpił',
    message: 'Okno sypialni — prawe.\nSypialnia',
  };
  assert.deepEqual(notificationIdentity(resolved), { faultName: 'Okno sypialni — prawe', location: 'Sypialnia', inherited: false });
  const clear: NotificationEntry = {
    ...entry,
    kind: 'clear',
    fault_state: 'SHADOWED',
    message: 'clear_notification',
    attempted_at: '2026-10-05T16:30:00Z',
  };
  assert.deepEqual(notificationIdentity(clear, [resolved]), { faultName: 'Okno sypialni — prawe', location: 'Sypialnia', inherited: true });
});

test('legacy generic titles without recorded identity remain unknown in all languages', () => {
  for (const title of ['Sprawdź, co dzieje się w domu', 'Please check your home', 'Bitte prüfen Sie Ihr Zuhause'])
    assert.deepEqual(notificationIdentity({ ...entry, title, message: 'Brak zapisanego opisu' }), {
      faultName: '',
      location: '',
      inherited: false,
    });
});
