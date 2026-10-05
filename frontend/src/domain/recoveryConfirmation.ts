import type { RecoveryView } from './safety.js';

/** Frontend guard; the backend still validates proposal identity and expiry. */
export function recoveryConfirmationBlock(recovery: RecoveryView, connected: boolean, now = Date.now()): string | null {
  if (!connected) return 'Potwierdzenie wstrzymane: brak połączenia.';
  if (recovery.status !== 'awaiting_confirmation' || !recovery.confirmationToken) return 'Potwierdzenie niedostępne.';
  if (
    (recovery.expiresAt !== undefined && (!Number.isFinite(recovery.expiresAt) || recovery.expiresAt * 1000 <= now)) ||
    (recovery.validUntil !== undefined && (!Number.isFinite(Date.parse(recovery.validUntil)) || Date.parse(recovery.validUntil) <= now))
  )
    return 'Propozycja wygasła. Oczekiwanie na aktualne zalecenie.';
  return null;
}
