import type { EntityMap, StatusTone } from './safety.js';

export const COVERAGE_ENTITY_ID = 'sensor.safety_coverage_state';

export type CoverageCauseState = 'active' | 'unresolved' | 'invalid_binding' | 'unknown';

export interface CoverageRestriction {
  cause: string;
  causeState: CoverageCauseState;
  fault: string;
  symptom: string;
  capability: string;
  subject: string;
  effect: string;
}

export interface CoverageExclusion {
  symptom: string;
  reason: string;
}

export interface CoverageBindingError {
  source: string;
  reason: string;
}

export interface CoverageView {
  state: 'FULL' | 'PARTIAL' | 'DEGRADED' | 'UNKNOWN';
  label: string;
  detail: string;
  tone: StatusTone;
  baselineCount: number;
  unresolvedSymptoms: string[];
  exclusions: CoverageExclusion[];
  bindingErrors: CoverageBindingError[];
  restrictions: CoverageRestriction[];
  restrictionsOmitted: number;
}

function count(value: unknown): number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : 0;
}

export function getCoverageView(entities: EntityMap): CoverageView {
  const entity = entities[COVERAGE_ENTITY_ID];
  const raw = entity?.state?.trim().toUpperCase();
  const state = raw === 'FULL' || raw === 'PARTIAL' || raw === 'DEGRADED' ? raw : 'UNKNOWN';
  const attributes = entity?.attributes ?? {};
  const baselineCount = count(attributes.baseline_count);
  const affectedCount = count(attributes.affected_count);
  const unresolvedCount = count(attributes.unresolved_h_count);
  const unresolvedSymptoms = stringArray(attributes.unresolved_h_symptoms);
  const bindingErrors = stringRecordEntries(attributes.binding_errors).map(([source, reason]) => ({ source, reason }));
  const exclusions = stringRecordEntries(attributes.exclusions).map(([symptom, reason]) => ({ symptom, reason }));
  const restrictions = restrictionArray(attributes.affected);
  const restrictionsOmitted = count(attributes.affected_omitted);
  const common = {
    baselineCount,
    unresolvedSymptoms,
    exclusions,
    bindingErrors,
    restrictions,
    restrictionsOmitted,
  };

  if (state === 'FULL') {
    return { ...common, state, label: 'Pełne pokrycie', detail: 'Wymagane funkcje zostały ocenione.', tone: 'safe' };
  }
  if (state === 'DEGRADED') {
    return {
      ...common,
      state,
      label: 'Pokrycie zdegradowane',
      detail: `${affectedCount} ograniczeń technicznych w monitoringu lub recovery.`,
      tone: 'danger',
    };
  }
  if (state === 'PARTIAL') {
    const noun = exclusions.length === 1 ? 'wyłączenie' : 'wyłączeń';
    return {
      ...common,
      state,
      label: 'Pokrycie częściowe',
      detail: `${exclusions.length} ${noun} w wymaganym zakresie.`,
      tone: 'warning',
    };
  }
  return {
    ...common,
    state,
    label: 'Pokrycie nieustalone',
    detail:
      bindingErrors.length > 0
        ? `${bindingErrors.length} błędnych powiązań diagnostycznych; ${unresolvedCount} nieocenionych funkcji.`
        : `${unresolvedCount} nieocenionych funkcji lub brak danych o pokryciu.`,
    tone: 'muted',
  };
}

export function coverageEffectLabel(effect: string): string {
  const labels: Record<string, string> = {
    evaluation: 'Ocena zagrożenia',
    recovery: 'Działanie naprawcze',
    notification: 'Powiadomienie',
    publication: 'Publikacja stanu',
    durability: 'Trwałość danych',
  };
  return labels[effect.trim().toLowerCase()] ?? humanize(effect);
}

export function coverageCauseStateLabel(state: CoverageCauseState): string {
  const labels: Record<CoverageCauseState, string> = {
    active: 'Aktywna przyczyna',
    unresolved: 'Brak rozstrzygających danych',
    invalid_binding: 'Błędne powiązanie',
    unknown: 'Stan nieznany',
  };
  return labels[state];
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map(String)
    .map(item => item.trim())
    .filter(Boolean);
}

function stringRecordEntries(value: unknown): Array<[string, string]> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
  return Object.entries(value as Record<string, unknown>)
    .map(([key, item]) => [key.trim(), String(item ?? '').trim()] as [string, string])
    .filter(([key, item]) => Boolean(key && item));
}

function restrictionArray(value: unknown): CoverageRestriction[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap(item => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return [];
    const record = item as Record<string, unknown>;
    const cause = text(record.cause);
    const fault = text(record.fault);
    const symptom = text(record.symptom);
    if (!cause || !fault || !symptom) return [];
    const rawState = text(record.cause_state).toLowerCase();
    const causeState: CoverageCauseState = ['active', 'unresolved', 'invalid_binding'].includes(rawState)
      ? (rawState as CoverageCauseState)
      : 'unknown';
    return [
      {
        cause,
        causeState,
        fault,
        symptom,
        capability: text(record.capability),
        subject: text(record.subject),
        effect: text(record.effect),
      },
    ];
  });
}

function text(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value).trim() : '';
}

function humanize(value: string): string {
  return value
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^\w/, letter => letter.toUpperCase());
}
