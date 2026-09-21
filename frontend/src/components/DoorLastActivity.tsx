import { formatRelativeTime, normalizeState, type SafetyDoorView } from '../domain/safety';
import { useEntityHistory } from '../hooks/useEntityHistory';

interface DoorHistoryPoint {
  state: string;
  last_changed: number;
}

interface DoorSession {
  openedAt: number;
  closedAt?: number;
  durationSeconds: number;
  current: boolean;
}

function findLastDoorSession(
  timeline: DoorHistoryPoint[],
  currentDoorState: SafetyDoorView['doorState'],
  openedAt?: string,
  currentDurationSeconds = 0
): DoorSession | null {
  const points = [...timeline].sort((left, right) => left.last_changed - right.last_changed);
  let activeOpenedAt: number | null = null;
  let completed: DoorSession | null = null;

  for (const point of points) {
    const state = normalizeState(point.state);
    if (['on', 'open', 'opened'].includes(state)) {
      activeOpenedAt ??= point.last_changed;
      continue;
    }
    if (['off', 'closed'].includes(state) && activeOpenedAt !== null) {
      completed = {
        openedAt: activeOpenedAt,
        closedAt: point.last_changed,
        durationSeconds: Math.max(0, Math.round((point.last_changed - activeOpenedAt) / 1000)),
        current: false,
      };
      activeOpenedAt = null;
    }
  }

  if (currentDoorState === 'open') {
    const reportedOpenedAt = openedAt ? Date.parse(openedAt) : Number.NaN;
    const sessionOpenedAt = Number.isFinite(reportedOpenedAt) ? reportedOpenedAt : activeOpenedAt;
    if (sessionOpenedAt !== null) {
      return {
        openedAt: sessionOpenedAt,
        durationSeconds: Math.max(currentDurationSeconds, Math.round((Date.now() - sessionOpenedAt) / 1000)),
        current: true,
      };
    }
  }

  return completed;
}

export default function DoorLastActivity({ door, compact = false }: { door: SafetyDoorView; compact?: boolean }) {
  const history = useEntityHistory(door.sourceEntityId || door.entityId, {
    hoursToShow: 168,
    minimalResponse: true,
    significantChangesOnly: true,
  });
  const session = findLastDoorSession(history.timeline, door.doorState, door.openedAt, door.openDurationSeconds);

  if (history.loading && !session) {
    return <span className='door-last-activity door-last-activity-muted'>Wczytywanie ostatniego otwarcia…</span>;
  }
  if (!session) {
    return <span className='door-last-activity door-last-activity-muted'>Brak otwarcia w historii 7 dni</span>;
  }

  const openedIso = new Date(session.openedAt).toISOString();
  const label = session.current ? 'Otwarte' : 'Ostatnio otwarte';
  return (
    <span className={`door-last-activity${compact ? ' door-last-activity-compact' : ''}`}>
      <span>
        {label} <time dateTime={openedIso}>{formatRelativeTime(openedIso)}</time>
      </span>
      <strong>{formatDoorDuration(session.durationSeconds)}</strong>
    </span>
  );
}

function formatDoorDuration(seconds: number): string {
  const safeSeconds = Math.max(0, Math.round(seconds));
  if (safeSeconds < 60) return `${safeSeconds} s`;
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  if (hours > 0) return minutes > 0 ? `${hours} godz. ${minutes} min` : `${hours} godz.`;
  return `${minutes} min`;
}
