import type { Connection, HassEvent } from 'home-assistant-js-websocket';

export type CheckStatus = 'pass' | 'problem' | 'unknown' | 'skipped';
export type RunStatus = CheckStatus | 'not_applicable';
export interface RoutineSummary {
  routine_id: string;
  name: string;
  enabled: boolean;
  check_count: number;
}
export interface RoutineResult {
  check_id: string;
  name: string;
  entity_id: string;
  status: CheckStatus;
  reason_label: string;
  value: string | number | boolean | null;
  observed_at: string | null;
  expected_states: string[] | null;
  minimum: number | null;
  maximum: number | null;
  unit: string | null;
}
export interface RoutineRun {
  run_id: string;
  routine_id: string;
  name: string;
  state: 'waiting' | 'running' | 'completed' | 'interrupted' | 'cancelled';
  status: RunStatus;
  started_at: string;
  finished_at: string | null;
  due_at: string;
  sample_count: number;
  observation_seconds: number;
  evidence_incomplete: boolean;
  counts: Record<CheckStatus, number>;
  results?: RoutineResult[];
}
export interface RoutineResponse {
  version: 1;
  request_id: string;
  storage_available: boolean;
  error?: string;
  routines?: RoutineSummary[];
  runs?: RoutineRun[];
  run?: RoutineRun;
}
const statuses: CheckStatus[] = ['pass', 'problem', 'unknown', 'skipped'];
const record = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
const date = (value: unknown) => typeof value === 'string' && Number.isFinite(Date.parse(value));
const count = (value: unknown) => typeof value === 'number' && Number.isInteger(value) && value >= 0;

function validRun(value: unknown, detail = false): value is RoutineRun {
  const run = record(value);
  if (!run || !['run_id', 'routine_id', 'name'].every(key => typeof run[key] === 'string')) return false;
  if (!['waiting', 'running', 'completed', 'interrupted', 'cancelled'].includes(String(run.state))) return false;
  if (!date(run.started_at) || !date(run.due_at) || !(run.finished_at === null || date(run.finished_at))) return false;
  if (!count(run.sample_count) || !count(run.observation_seconds)) return false;
  if (typeof run.evidence_incomplete !== 'boolean') return false;
  const counts = record(run.counts);
  if (!counts || !statuses.every(key => count(counts[key]))) return false;
  const total = statuses.reduce((sum, key) => sum + (counts[key] as number), 0);
  if (total > 24) return false;
  const expected = counts.problem ? 'problem' : counts.unknown ? 'unknown' : counts.pass ? 'pass' : 'not_applicable';
  if (run.state === 'completed' ? total === 0 || run.status !== expected || !date(run.finished_at) : run.status !== 'unknown') return false;
  if (!detail) return true;
  if (!Array.isArray(run.results) || run.results.length !== total) return false;
  for (const value of run.results) {
    const item = record(value);
    if (!item || !['check_id', 'name', 'entity_id', 'reason_label'].every(key => typeof item[key] === 'string')) return false;
    if (!statuses.includes(item.status as CheckStatus) || !(item.observed_at === null || date(item.observed_at))) return false;
    if (
      !(
        item.value === null ||
        ['string', 'boolean'].includes(typeof item.value) ||
        (typeof item.value === 'number' && Number.isFinite(item.value))
      )
    )
      return false;
    if (
      !(
        item.expected_states === null ||
        (Array.isArray(item.expected_states) && item.expected_states.every(state => typeof state === 'string'))
      )
    )
      return false;
    if (![item.minimum, item.maximum].every(bound => bound === null || (typeof bound === 'number' && Number.isFinite(bound)))) return false;
    if (!(item.unit === null || typeof item.unit === 'string')) return false;
  }
  return statuses.every(key => (run.results as RoutineResult[]).filter(item => item.status === key).length === counts[key]);
}

export function parseRoutineResponse(value: unknown, requestId: string): RoutineResponse | null {
  const data = record(value);
  if (!data || data.version !== 1 || data.request_id !== requestId || typeof data.storage_available !== 'boolean') return null;
  if (typeof data.error === 'string') return data as unknown as RoutineResponse;
  if (data.run !== undefined) return validRun(data.run, true) ? (data as unknown as RoutineResponse) : null;
  if (!Array.isArray(data.routines) || data.routines.length > 16 || !Array.isArray(data.runs) || data.runs.length > 20) return null;
  if (
    !data.routines.every(value => {
      const item = record(value);
      return (
        item &&
        typeof item.routine_id === 'string' &&
        typeof item.name === 'string' &&
        typeof item.enabled === 'boolean' &&
        count(item.check_count)
      );
    }) ||
    !data.runs.every(run => validRun(run))
  )
    return null;
  return data as unknown as RoutineResponse;
}

export function routineRequest(requestId: string, action: string, routineId?: string, runId?: string) {
  return {
    type: 'fire_event',
    event_type: 'safety_routine_request',
    event_data: {
      request_id: requestId,
      action,
      ...(routineId ? { routine_id: routineId } : {}),
      ...(runId ? { run_id: runId } : {}),
    },
  };
}

export function requestRoutine(
  connection: Connection,
  action: string,
  signal: AbortSignal,
  routineId?: string,
  runId?: string
): Promise<RoutineResponse> {
  const requestId = crypto.randomUUID();
  return new Promise((resolve, reject) => {
    let finished = false;
    let unsubscribe: (() => Promise<void>) | undefined;
    const finish = (response?: RoutineResponse, error?: string) => {
      if (finished) return;
      finished = true;
      window.clearTimeout(timer);
      signal.removeEventListener('abort', abort);
      if (unsubscribe) void Promise.resolve(unsubscribe()).catch(() => {});
      if (response) resolve(response);
      else reject(new Error(error));
    };
    const abort = () => finish(undefined, 'disconnected');
    const timer = window.setTimeout(() => finish(undefined, 'timeout'), 8000);
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) {
      abort();
      return;
    }
    void connection
      .subscribeEvents<HassEvent>(event => {
        const response = parseRoutineResponse(event.data, requestId);
        if (response) finish(response);
      }, 'safety_routine_response')
      .then(async cancel => {
        if (finished) {
          await cancel();
          return;
        }
        unsubscribe = cancel;
        await connection.sendMessagePromise(routineRequest(requestId, action, routineId, runId));
      })
      .catch(() => finish(undefined, 'connection_error'));
  });
}

export function routineRunLabel(run: RoutineRun): string {
  if (run.state === 'waiting') return 'Oczekiwanie na rozpoczęcie';
  if (run.state === 'running') return 'Kontrola w toku';
  if (run.state === 'interrupted') return 'Kontrola przerwana';
  if (run.state === 'cancelled') return 'Kontrola anulowana';
  return routineStatusLabel(run.status);
}
export function routineStatusLabel(status: RunStatus): string {
  return {
    pass: 'OK w chwili kontroli',
    problem: 'Wykryto problem',
    unknown: 'Nie można ocenić',
    skipped: 'Pominięte',
    not_applicable: 'Brak kontroli mających zastosowanie',
  }[status];
}
