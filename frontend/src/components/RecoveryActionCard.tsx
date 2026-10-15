import { useState } from 'react';
import { useHass } from '@hakit/core';
import type { RecoveryView } from '../domain/safety';
import { recoveryConfirmationBlock, recoveryReportBlock, recoveryReportEvent } from '../domain/recoveryConfirmation';
import RecoveryCard, { type RecoveryRequest } from './RecoveryCard';

/** Send only current proposal capabilities through the authenticated HA connection. */
export default function RecoveryActionCard({
  recovery,
  onSelectEntity,
  compact = false,
}: {
  recovery: RecoveryView;
  onSelectEntity?: (entityId: string) => void;
  compact?: boolean;
}) {
  const connection = useHass(store => store.connection);
  const connected = useHass(store => store.connectionStatus === 'connected' && store.ready);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState<{ identity: string; request: RecoveryRequest }>();
  const [error, setError] = useState('');
  const identity = `${recovery.proposalId}:${recovery.proposalInstanceId ?? recovery.confirmationToken}`;

  const request = async (kind: RecoveryRequest): Promise<void> => {
    const guard = kind === 'report' ? recoveryReportBlock : recoveryConfirmationBlock;
    const block = guard(recovery, connected);
    if (!connection || block) {
      setError(block ?? 'Brak połączenia z Home Assistantem.');
      return;
    }
    const prompt =
      kind === 'report'
        ? `Czy wykonałeś opisane czynności? Zgłoszenie nie usuwa usterki.\n${recovery.instruction}`
        : `Czy zezwalasz systemowi na wykonanie tej akcji?\n${recovery.instruction}`;
    if (!window.confirm(prompt)) return;
    const current = useHass.getState();
    const afterConfirmation = guard(recovery, current.connectionStatus === 'connected' && current.ready);
    if (afterConfirmation) {
      setError(afterConfirmation);
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await connection.sendMessagePromise<unknown>(
        kind === 'report'
          ? recoveryReportEvent(recovery)
          : {
              type: 'fire_event',
              event_type: 'safety_recovery_confirm',
              event_data: {
                proposal_id: recovery.proposalId,
                proposal_instance_id: recovery.proposalInstanceId,
                confirmation_token: recovery.confirmationToken,
              },
            }
      );
      setSubmitted({ identity, request: kind });
    } catch {
      setError('Nie udało się wysłać zgłoszenia. Spróbuj ponownie.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <RecoveryCard
      compact={compact}
      connected={connected}
      error={error}
      onRequest={kind => void request(kind)}
      onSelectEntity={onSelectEntity}
      recovery={recovery}
      submitted={submitted?.identity === identity ? submitted.request : undefined}
      submitting={submitting}
    />
  );
}
