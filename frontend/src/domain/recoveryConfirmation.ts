import type { RecoveryView } from './safety.js';

/** Frontend guard; the backend still validates proposal identity and expiry. */
export function recoveryConfirmationBlock(recovery: RecoveryView, connected: boolean, now = Date.now()): string | null {
  if (!connected) return 'Potwierdzenie wstrzymane: brak połączenia.';
  if (recovery.blockedReason) return recovery.blockedReason;
  if (recovery.status !== 'awaiting_confirmation' || !recovery.confirmationToken) return 'Potwierdzenie niedostępne.';
  if (
    (recovery.expiresAt !== undefined && (!Number.isFinite(recovery.expiresAt) || recovery.expiresAt * 1000 <= now)) ||
    (recovery.validUntil !== undefined && (!Number.isFinite(Date.parse(recovery.validUntil)) || Date.parse(recovery.validUntil) <= now))
  )
    return 'Propozycja wygasła. Oczekiwanie na aktualne zalecenie.';
  return null;
}

/** A manual report is an authenticated work report, never consent or fault clear. */
export function recoveryReportBlock(recovery: RecoveryView, connected: boolean, now = Date.now()): string | null {
  if (!connected) return 'Zgłoszenie wstrzymane: brak połączenia.';
  if (recovery.blockedReason) return recovery.blockedReason;
  if (
    recovery.executionPolicy !== 'manual' ||
    recovery.manualReportAllowed !== true ||
    !recovery.reportToken ||
    !recovery.proposalInstanceId ||
    recovery.completionCondition === 'advisory' ||
    !['to_perform', 'executing'].includes(recovery.status) ||
    Boolean(recovery.reportedAt) ||
    (recovery.reportStatus !== undefined && !['', 'not_reported'].includes(recovery.reportStatus))
  )
    return 'Zgłoszenie wykonania niedostępne.';
  if (
    (recovery.expiresAt !== undefined && (!Number.isFinite(recovery.expiresAt) || recovery.expiresAt * 1000 <= now)) ||
    (recovery.validUntil !== undefined && (!Number.isFinite(Date.parse(recovery.validUntil)) || Date.parse(recovery.validUntil) <= now))
  )
    return 'Propozycja wygasła. Oczekiwanie na aktualne zalecenie.';
  return null;
}

/** Home Assistant provides the authenticated user and server receipt time. */
export function recoveryReportEvent(recovery: RecoveryView) {
  return {
    type: 'fire_event',
    event_type: 'safety_recovery_report',
    event_data: {
      proposal_id: recovery.proposalId,
      proposal_instance_id: recovery.proposalInstanceId,
      report_token: recovery.reportToken,
    },
  };
}

/** Capability tokens authorize actions and must never appear in diagnostic copy. */
export function publicRecoveryAttributes(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(publicRecoveryAttributes);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => !['confirmation_token', 'report_token', 'report_user_id'].includes(key))
        .map(([key, child]) => [key, publicRecoveryAttributes(child)])
    );
  }
  return value;
}
