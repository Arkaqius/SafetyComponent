import { recoveriesForFault, recoveryNeedsAttention, type FaultView, type RecoveryView } from './safety.js';

/** Prioritize the brief without losing the count of other active conditions. */
export function basicDashboardItems(faults: FaultView[], recoveries: RecoveryView[]) {
  const activeFaults = faults.filter(fault => fault.active === true);
  const alarms = activeFaults.filter(fault => fault.level !== 4);
  const unshadowed = alarms.filter(fault => fault.shadowedBy.length === 0);
  const primaryFault = [...(unshadowed.length > 0 ? unshadowed : alarms)].sort((left, right) => (left.level ?? 0) - (right.level ?? 0))[0];
  const attentionRecoveries = recoveries.filter(recoveryNeedsAttention);
  const primaryFaultRecoveries = primaryFault ? recoveriesForFault(primaryFault, attentionRecoveries) : [];
  return {
    primaryFault,
    activeFaultCount: activeFaults.length,
    primaryRecovery: primaryFaultRecoveries[0] ?? attentionRecoveries[0],
    attentionRecoveries,
  };
}
