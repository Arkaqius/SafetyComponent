import { friendlyEntityName, type EntityMap } from './safety.js';

export interface HeatingInputView {
  name: string;
  sourceName: string;
  value: string;
  quality: string;
}

export interface HeatingRuleView {
  name: string;
  status: string;
  active: boolean;
  reasons: string[];
}

export interface HeatingSystemView {
  entityId: string;
  name: string;
  phase: string;
  coverage: string;
  available: boolean;
  inputs: HeatingInputView[];
  rules: HeatingRuleView[];
}

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function text(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim() ? value : fallback;
}

function rows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(record) : [];
}

export function getHeatingSystems(entities: EntityMap, connected = true): HeatingSystemView[] {
  return Object.entries(entities)
    .filter(([id]) => id.startsWith('sensor.heating_system_'))
    .map(([entityId, entity]) => {
      const attrs = entity.attributes;
      const available =
        connected && entity.state !== 'unavailable' && entity.state !== 'unknown' && typeof attrs.coverage_label === 'string';
      return {
        entityId,
        name: typeof attrs.friendly_name === 'string' ? friendlyEntityName(entityId, entity) : 'Ogrzewanie',
        available,
        phase: available ? text(attrs.phase_label, 'Nieznana faza pracy') : 'Brak bieżących danych',
        coverage: available ? text(attrs.coverage_label, 'Niepotwierdzone pokrycie') : 'Niepotwierdzone pokrycie',
        inputs: rows(attrs.inputs).map(input => ({
          name: text(input.label, 'Wejście ogrzewania'),
          sourceName: text(input.source_name, 'Nieznane źródło'),
          value: available ? text(input.value_label, 'Brak danych') : 'Brak bieżących danych',
          quality: available ? text(input.quality_label, 'Jakość niepotwierdzona') : 'Niedostępne',
        })),
        rules: rows(attrs.rules).map(rule => ({
          name: text(rule.label, 'Kontrola ogrzewania'),
          status: available ? text(rule.status, 'UNEVALUABLE') : 'UNEVALUABLE',
          active: rule.active === true,
          reasons:
            available && Array.isArray(rule.reasons)
              ? rule.reasons.filter((value): value is string => typeof value === 'string')
              : ['Brak bieżących danych'],
        })),
      };
    });
}
