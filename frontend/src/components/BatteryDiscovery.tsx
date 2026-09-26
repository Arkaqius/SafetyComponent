import { useCallback, useEffect, useState } from 'react';
import { MOCK_MODE } from '../config';
import { batterySourceLabel, setBatteryMonitored, type BatteryDevice } from '../domain/batteryDiscovery';

interface Props {
  enabled: boolean;
  excluded: string[];
  staleAfterSeconds: number;
  onEnabledChange: (enabled: boolean) => void;
  onExcludedChange: (excluded: string[]) => void;
}

export default function BatteryDiscovery({ enabled, excluded, staleAfterSeconds, onEnabledChange, onExcludedChange }: Props) {
  const [devices, setDevices] = useState<BatteryDevice[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [search, setSearch] = useState('');
  const load = useCallback(async () => {
    setStatus('loading');
    try {
      const response = MOCK_MODE ? null : await fetch('api/batteries', { cache: 'no-store' });
      const inventory = response ? await response.json() : { status: 'ready', devices: [] };
      if ((response && !response.ok) || inventory.status !== 'ready' || !Array.isArray(inventory.devices))
        throw new Error('inventory unavailable');
      setDevices(inventory.devices);
      setStatus('ready');
    } catch {
      setDevices([]);
      setStatus('error');
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  const visible = devices.filter(device =>
    `${device.friendly_name} ${device.sources.map(source => source.entity_id).join(' ')}`.toLowerCase().includes(search.toLowerCase())
  );
  const missingExclusions = status === 'ready' ? excluded.filter(id => !devices.some(device => device.device_id === id)) : [];
  return (
    <details className='battery-discovery'>
      <summary>
        Baterie urządzeń — {status === 'ready' ? `${devices.length} wykrytych` : status === 'error' ? 'lista niedostępna' : 'pobieranie…'}
      </summary>
      <p>
        Lista jest pobierana z Home Assistant i grupowana po urządzeniu. Domyślnie monitorujemy wszystkie wykryte urządzenia (L4).
        Wyłączenie zapisuje tylko identyfikator urządzenia na liście wykluczeń.
      </p>
      <label className='configuration-toggle'>
        <input type='checkbox' checked={enabled} onChange={event => onEnabledChange(event.target.checked)} />
        Automatycznie monitoruj baterie
      </label>
      <p>
        Zapisz konfigurację i uruchom aplikację ponownie, aby zastosować wyjątki i wykryć nowe urządzenia. Usunięcie urządzenia z HA i
        dodanie go ponownie może zmienić jego identyfikator.
      </p>
      <button className='secondary-button' type='button' disabled={status === 'loading'} onClick={() => void load()}>
        Pobierz urządzenia bateryjne
      </button>
      {status === 'error' ? (
        <p role='alert'>Nie udało się pobrać listy. To brak danych, nie potwierdzenie braku urządzeń bateryjnych. Spróbuj ponownie.</p>
      ) : null}
      {status === 'ready' && !devices.length ? (
        <p>Nie wykryto włączonych encji baterii przypisanych do urządzeń. Sprawdź encje diagnostyczne w Home Assistant.</p>
      ) : null}
      {devices.length ? (
        <label className='configuration-field'>
          Filtruj urządzenia
          <input type='search' value={search} onChange={event => setSearch(event.target.value)} />
        </label>
      ) : null}
      {visible.map(device => (
        <details key={device.device_id} className='battery-discovery'>
          <summary>
            {device.friendly_name} —{' '}
            {excluded.includes(device.device_id) ? 'Wykluczone' : enabled ? 'Monitorowane' : 'Monitoring wyłączony'}
          </summary>
          <label
            className='configuration-toggle'
            title='Domyślnie: monitoruj. Zmiana zacznie obowiązywać po zapisaniu i restarcie aplikacji.'
          >
            <input
              type='checkbox'
              aria-label={`Monitoruj ${device.friendly_name}`}
              checked={!excluded.includes(device.device_id)}
              onChange={event => onExcludedChange(setBatteryMonitored(excluded, device.device_id, event.target.checked))}
            />
            Monitoruj urządzenie
          </label>
          <ul>
            {device.sources.map(source => (
              <li key={source.entity_id}>
                {batterySourceLabel(source, staleAfterSeconds)} · <code>{source.entity_id}</code>
              </li>
            ))}
          </ul>
        </details>
      ))}
      {missingExclusions.length ? (
        <details>
          <summary>Wykluczenia urządzeń spoza aktualnej listy ({missingExclusions.length})</summary>
          {missingExclusions.map(id => (
            <p key={id}>
              <code>{id}</code>{' '}
              <button className='secondary-button' type='button' onClick={() => onExcludedChange(setBatteryMonitored(excluded, id, true))}>
                Usuń wykluczenie
              </button>
            </p>
          ))}
        </details>
      ) : null}
    </details>
  );
}
