/** Recorder parsing and time-based presentation without inferred past evidence. */
export interface HistoryState {
  s: string;
  a: Record<string, unknown>;
  lu: number;
  lc?: number;
}

export interface HistoryPoint {
  state: string;
  state_localize: string;
  last_changed: number;
  last_updated?: number;
  attributes?: Record<string, unknown>;
}

/** Validate the requested stream only; empty Recorder results are valid. */
export function readHistoryStates(message: unknown, entityId: string): HistoryState[] {
  if (!message || typeof message !== 'object') throw new Error('invalid_history');
  const states = (message as Record<string, unknown>).states;
  if (!states || typeof states !== 'object' || Array.isArray(states)) throw new Error('invalid_history');
  const value = (states as Record<string, unknown>)[entityId];
  if (value === undefined) return [];
  if (!Array.isArray(value)) throw new Error('invalid_history');
  return value.map(raw => {
    if (!raw || typeof raw !== 'object') throw new Error('invalid_history');
    const item = raw as Record<string, unknown>;
    if (
      typeof item.s !== 'string' ||
      typeof item.lu !== 'number' ||
      !Number.isFinite(item.lu) ||
      !Number.isFinite(new Date(item.lu * 1000).getTime()) ||
      (item.lc !== undefined &&
        (typeof item.lc !== 'number' || !Number.isFinite(item.lc) || !Number.isFinite(new Date(item.lc * 1000).getTime())))
    ) {
      throw new Error('invalid_history');
    }
    if (item.a !== undefined && (!item.a || typeof item.a !== 'object' || Array.isArray(item.a))) throw new Error('invalid_history');
    return {
      s: item.s,
      lu: item.lu,
      ...(item.lc === undefined ? {} : { lc: item.lc as number }),
      a: (item.a ?? {}) as Record<string, unknown>,
    };
  });
}

/** Retain the boundary predecessor supplied by Recorder and bound stream memory. */
export function mergeHistoryStates(previous: HistoryState[], incoming: HistoryState[], start: number): HistoryState[] {
  const byTime = new Map<number, HistoryState>();
  for (const item of [...previous, ...incoming]) byTime.set(item.lu, item);
  const ordered = [...byTime.values()].sort((left, right) => left.lu - right.lu);
  const recent = ordered.filter(item => item.lu * 1000 >= start);
  const earlier = ordered.filter(item => item.lu * 1000 < start).at(-1);
  return [...(earlier ? [earlier] : []), ...recent].slice(-10000);
}

export function historyTimeline(states: HistoryState[]): HistoryPoint[] {
  return states.map(item => ({
    state: item.s,
    state_localize: item.s,
    last_changed: (item.lc ?? item.lu) * 1000,
    last_updated: item.lu * 1000,
    attributes: item.a,
  }));
}

/** Keep recorded identity and activation changes even when the raw state is unchanged. */
export function historyTransitions(timeline: HistoryPoint[]): HistoryPoint[] {
  const identity = (point: HistoryPoint) =>
    JSON.stringify(['friendly_name', 'area_name', 'location', 'active', 'latched'].map(key => point.attributes?.[key]));
  return timeline
    .filter((point, index) => index === 0 || point.state !== timeline[index - 1].state || identity(point) !== identity(timeline[index - 1]))
    .map(point => ({ ...point, last_changed: point.last_updated ?? point.last_changed }));
}

/** Unknown prefixes stay unknown until the first recorded state. */
export function historySegments(timeline: HistoryPoint[], start: number, end: number): Array<{ state: string | null; duration: number }> {
  const points = [...timeline]
    .filter(item => Number.isFinite(item.last_changed) && item.last_changed <= end)
    .sort((left, right) => left.last_changed - right.last_changed);
  const earlier = points.filter(item => item.last_changed <= start).at(-1);
  const relevant: Array<{ state: string | null; last_changed: number }> = [
    { state: earlier?.state ?? null, last_changed: start },
    ...points.filter(item => item.last_changed > start),
  ];
  return relevant.map((point, index) => ({
    state: point.state,
    duration: (relevant[index + 1]?.last_changed ?? end) - point.last_changed,
  }));
}

/** Preserve unavailable points as gaps instead of joining across missing data. */
export function numericHistory(states: HistoryState[]): Array<{ time: number; value: number | null }> {
  return states.map(item => ({
    time: item.lu * 1000,
    value: item.s.trim() && Number.isFinite(Number(item.s)) ? Number(item.s) : null,
  }));
}

export function chartSegments(
  points: Array<{ time: number; value: number | null }>,
  start: number,
  end: number,
  width: number
): Array<Array<{ x: number; value: number }>> {
  const segments: Array<Array<{ x: number; value: number }>> = [];
  let current: Array<{ x: number; value: number }> = [];
  for (const point of points) {
    if (point.time < start || point.time > end) continue;
    if (point.value === null) {
      if (current.length) segments.push(current);
      current = [];
    } else current.push({ x: ((point.time - start) / (end - start)) * width, value: point.value });
  }
  if (current.length) segments.push(current);
  return segments;
}
