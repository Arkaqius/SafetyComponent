export interface BatterySource {
  entity_id: string;
  kind: 'percentage' | 'low';
  state: string;
  last_reported: string;
}

export interface BatteryDevice {
  device_id: string;
  key: string;
  friendly_name: string;
  sources: BatterySource[];
}

export function setBatteryMonitored(excluded: string[], deviceId: string, monitored: boolean): string[] {
  return monitored ? excluded.filter(id => id !== deviceId) : [...new Set([...excluded, deviceId])];
}

export function batterySourceLabel(source: BatterySource, maxAgeSeconds: number, now = Date.now()): string {
  const age = (now - Date.parse(source.last_reported)) / 1000;
  if (!Number.isFinite(age) || age < 0 || age > maxAgeSeconds) return 'Odczyt nieaktualny';
  if (source.kind === 'low')
    return source.state === 'on' ? 'Niska bateria' : source.state === 'off' ? 'Brak alarmu niskiej baterii' : 'Brak wiarygodnego odczytu';
  const value = source.state.trim() ? Number(source.state) : NaN;
  return Number.isFinite(value) && value >= 0 && value <= 100 ? `${value}%` : 'Brak wiarygodnego odczytu';
}
