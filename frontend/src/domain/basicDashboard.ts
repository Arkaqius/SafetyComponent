import { recoveryNeedsAttention, type FaultView, type RecoveryView } from './safety.js';

/** Prioritize the brief without losing the count of other active conditions. */
export function basicDashboardItems(faults: FaultView[], recoveries: RecoveryView[]) {
  const activeFaults = faults.filter(fault => fault.active === true);
  const unshadowed = activeFaults.filter(fault => fault.shadowedBy.length === 0);
  const primaryFault = [...(unshadowed.length > 0 ? unshadowed : activeFaults)].sort(
    (left, right) => (left.level ?? 0) - (right.level ?? 0)
  )[0];
  const attentionRecoveries = recoveries.filter(recoveryNeedsAttention);
  return {
    primaryFault,
    activeFaultCount: activeFaults.length,
    primaryRecovery: attentionRecoveries[0],
    attentionRecoveries,
  };
}
