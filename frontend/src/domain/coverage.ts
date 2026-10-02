import type { EntityMap, StatusTone } from './safety.js';

export const COVERAGE_ENTITY_ID = 'sensor.safety_coverage_state';

export interface CoverageView {
  state: 'FULL' | 'PARTIAL' | 'DEGRADED' | 'UNKNOWN';
  label: string;
  detail: string;
  tone: StatusTone;
}

function count(value: unknown): number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : 0;
}

export function getCoverageView(entities: EntityMap): CoverageView {
  const entity = entities[COVERAGE_ENTITY_ID];
  const raw = entity?.state?.trim().toUpperCase();
  const state = raw === 'FULL' || raw === 'PARTIAL' || raw === 'DEGRADED' ? raw : 'UNKNOWN';
  const attributes = entity?.attributes ?? {};
  const affectedCount = count(attributes.affected_count);
  const unresolvedCount = count(attributes.unresolved_h_count);
  const bindingErrors = attributes.binding_errors;
  const errorCount =
    bindingErrors && typeof bindingErrors === 'object' && !Array.isArray(bindingErrors) ? Object.keys(bindingErrors).length : 0;
  const exclusions = attributes.exclusions;
  const exclusionCount = exclusions && typeof exclusions === 'object' && !Array.isArray(exclusions) ? Object.keys(exclusions).length : 0;

  if (state === 'FULL') {
    return { state, label: 'Pełne pokrycie', detail: 'Wymagane funkcje zostały ocenione.', tone: 'safe' };
  }
  if (state === 'DEGRADED') {
    return {
      state,
      label: 'Pokrycie zdegradowane',
      detail: `${affectedCount} ograniczeń technicznych w monitoringu lub recovery.`,
      tone: 'danger',
    };
  }
  if (state === 'PARTIAL') {
    const noun = exclusionCount === 1 ? 'wyłączenie' : 'wyłączeń';
    return {
      state,
      label: 'Pokrycie częściowe',
      detail: `${exclusionCount} ${noun} w wymaganym zakresie.`,
      tone: 'warning',
    };
  }
  return {
    state,
    label: 'Pokrycie nieustalone',
    detail:
      errorCount > 0
        ? `${errorCount} błędnych powiązań diagnostycznych; ${unresolvedCount} nieocenionych funkcji.`
        : `${unresolvedCount} nieocenionych funkcji lub brak danych o pokryciu.`,
    tone: 'muted',
  };
}
