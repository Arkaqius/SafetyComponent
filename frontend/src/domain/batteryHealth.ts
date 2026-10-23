import type { SourceView } from './functionalSafety.js';

export type BatteryStatus = 'low' | 'unknown' | 'current';
export type BatteryFilter = 'all' | BatteryStatus;
export type BatterySort = 'attention' | 'percentage-asc' | 'percentage-desc' | 'name';

export interface BatteryRow {
  key: string;
  name: string;
  status: BatteryStatus;
  percentage: number | null;
  entityIds: string[];
  detail: string;
  evidence: string[];
}

export function getBatteryRows(sources: SourceView[]): BatteryRow[] {
  return sources
    .filter(source => source.group === 'batteries')
    .map(source => ({
      key: source.key,
      name: source.label.replace(/^Bateria: /, ''),
      status: source.status === 'low' || source.status === 'current' ? source.status : 'unknown',
      percentage:
        ['low', 'current'].includes(source.status) &&
        typeof source.percentage === 'number' &&
        Number.isFinite(source.percentage) &&
        source.percentage >= 0 &&
        source.percentage <= 100
          ? source.percentage
          : null,
      entityIds: source.sourceEntities ?? [],
      detail: source.detail,
      evidence: source.evidence,
    }));
}

/** Order missing levels last in both directions without inferring a charge. */
export function filterBatteryRows(rows: BatteryRow[], query: string, status: BatteryFilter, sort: BatterySort): BatteryRow[] {
  const normalized = query.trim().toLocaleLowerCase('pl');
  return rows
    .filter(
      row =>
        (status === 'all' || row.status === status) &&
        (!normalized || [row.name, row.key, ...row.entityIds].join(' ').toLocaleLowerCase('pl').includes(normalized))
    )
    .sort((a, b) => {
      const byName = a.name.localeCompare(b.name, 'pl') || a.key.localeCompare(b.key);
      if (sort === 'name') return byName;
      if (sort === 'attention') {
        const rank = { low: 0, unknown: 1, current: 2 };
        const byStatus = rank[a.status] - rank[b.status];
        if (byStatus) return byStatus;
      }
      if (a.percentage === null || b.percentage === null) {
        return a.percentage === b.percentage ? byName : a.percentage === null ? 1 : -1;
      }
      return (sort === 'percentage-desc' ? b.percentage - a.percentage : a.percentage - b.percentage) || byName;
    });
}
