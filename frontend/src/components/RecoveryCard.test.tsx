import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { getRecoveries, recoveryNeedsAttention, type RecoveryView } from '../domain/safety.js';
import RecoveryCard from './RecoveryCard.js';

function recovery(overrides: Record<string, unknown> = {}): RecoveryView {
  return getRecoveries({
    'sensor.recovery_battery': {
      state: 'TO_PERFORM',
      attributes: {
        friendly_name: 'Bateria',
        proposals: [
          {
            proposal_id: 'battery',
            status: 'TO_PERFORM',
            execution_policy: 'manual',
            instruction: 'Wymień baterię.',
            completion_condition: 'observed',
            manual_report_allowed: true,
            report_token: 'secret-capability',
            proposal_instance_id: 'incident-2',
            ...overrides,
          },
        ],
      },
    },
  })[0];
}

const render = (value: RecoveryView, connected = true) =>
  renderToStaticMarkup(<RecoveryCard recovery={value} connected={connected} onRequest={() => undefined} />);

test('manual instructions show work report separately from consent and never expose capability tokens', () => {
  const markup = render(recovery());
  assert.match(markup, /Zgłoś wykonanie/);
  assert.doesNotMatch(markup, /Zezwól na wykonanie|Potwierdź powiadomienie|secret-capability/);
  assert.match(render(recovery({ manual_report_allowed: false })), /Wymień baterię/);
  assert.doesNotMatch(render(recovery({ manual_report_allowed: false })), /Zgłoś wykonanie/);
  const advisory = render(recovery({ completion_condition: 'advisory' }));
  assert.match(advisory, /System nie potwierdza jej wykonania/);
  assert.doesNotMatch(advisory, /Zgłoś wykonanie/);
});

test('reported repair waits for evidence and displays receipt and observation provenance', () => {
  const markup = render(
    recovery({
      report_status: 'awaiting_evidence',
      reported_at: '2026-10-12T10:00:00Z',
      report_source: 'operator',
      evidence_at: '2026-10-12T10:01:00Z',
      evidence_source: 'sensor.battery',
    })
  );
  assert.match(markup, /nadal czeka na potwierdzenie rezultatu/);
  assert.match(markup, /Zgłoszenie użytkownika/);
  assert.match(markup, /Dowód rezultatu/);
  assert.match(markup, /sensor\.battery/);
  assert.match(markup, /disabled=""[^>]*>Wykonanie zgłoszone/);
  assert.doesNotMatch(markup, />Potwierdzone</);
});

test('generic command consent and blocked reasons apply to every actuator', () => {
  const markup = render(
    recovery({
      status: 'AWAITING_CONFIRMATION',
      execution_policy: 'user_confirmed',
      confirmation_token: 'token',
      manual_report_allowed: false,
      blocked_reason: 'Cel działania jest niedostępny',
    })
  );
  assert.match(markup, /Zezwól na wykonanie/);
  assert.match(markup, /Cel działania jest niedostępny/);
  assert.match(markup, /disabled=""[^>]*>Zezwól na wykonanie/);
  assert.doesNotMatch(markup, /Potwierdź zamknięcie/);
  assert.match(render(recovery(), false), /brak połączenia/);
});

test('historical observation cannot masquerade as current proposal evidence', () => {
  const value = recovery();
  value.latestOutcome = {
    outcome: 'completed',
    recordedAt: '2026-10-11T10:00:00Z',
    evidenceAt: '2026-10-11T09:59:00Z',
    evidenceSource: 'sensor.old',
  };
  const markup = render(value);
  assert.match(markup, /Dowód ostatniego wyniku/);
  assert.doesNotMatch(markup, /Dowód rezultatu:/);
});

test('blocked inactive proposals remain visible as withheld instructions without actionable buttons', () => {
  const value = recovery({ status: 'DO_NOT_PERFORM', blocked_reason: 'Aktualny odczyt jest niedostępny' });
  assert.equal(recoveryNeedsAttention(value), true);
  const markup = render(value);
  assert.match(markup, />Wstrzymane</);
  assert.match(markup, /Aktualny odczyt jest niedostępny/);
  assert.doesNotMatch(markup, /Zgłoś wykonanie|Zezwól na wykonanie|>Brak potrzeby</);
});

test('procedural completion identifies the operator report rather than claiming observed safety recovery', () => {
  const markup = render(
    recovery({
      status: 'CONFIRMED',
      completion_condition: 'operator_report',
      report_status: 'completed',
      reported_at: '2026-10-12T10:00:00Z',
      report_source: 'operator',
    })
  );
  assert.match(markup, /System nie sprawdza jej samodzielnie/);
  assert.match(markup, /zgłoszenie nie usuwa usterki/);
  assert.doesNotMatch(markup, /Dowód rezultatu|nadal czeka/);
});

test('expired or uncertain advice in the basic shared card is not presented as current work instruction', () => {
  const expired = render(recovery({ expires_at: 1 }));
  assert.match(expired, /Zalecenie wygasło/);
  assert.doesNotMatch(expired, /Wymień baterię/);
  const unknown = render(recovery({ status: 'unavailable' }));
  assert.match(unknown, /Nie można potwierdzić aktualnego zalecenia/);
  assert.doesNotMatch(unknown, /Wymień baterię/);
  const completed = render(recovery({ status: 'CONFIRMED', expires_at: 1 }));
  assert.match(completed, />Potwierdzone</);
  assert.doesNotMatch(completed, /Zalecenie wygasło/);
});

test('compact brief keeps blocked and pending evidence states visible and requires full details before a report', () => {
  const brief = (value: RecoveryView) =>
    renderToStaticMarkup(<RecoveryCard compact recovery={value} connected onRequest={() => undefined} />);
  assert.match(brief(recovery()), /Wymień baterię/);
  assert.doesNotMatch(brief(recovery()), /Zgłoś wykonanie|Zezwól na wykonanie|secret-capability/);
  assert.match(brief(recovery({ blocked_reason: 'Brak aktualnego odczytu' })), /Wstrzymane|Brak aktualnego odczytu/);
  assert.match(brief(recovery({ report_status: 'awaiting_evidence' })), /nadal czeka na potwierdzenie rezultatu/);
  const expired = brief(recovery({ expires_at: 1 }));
  assert.match(expired, /Zalecenie wygasło/);
  assert.doesNotMatch(expired, /Wymień baterię/);
});
