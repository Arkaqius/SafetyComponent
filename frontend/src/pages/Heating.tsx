import { useState } from 'react';
import EntityDetailsDialog from '../components/EntityDetailsDialog';
import StatusBadge from '../components/StatusBadge';
import { getHeatingSystems } from '../domain/heating';
import { type StatusTone } from '../domain/safety';
import { useSafetyEntities } from '../hooks/useSafetyEntities';

const statuses: Record<string, { label: string; tone: StatusTone }> = {
  NOT_EVALUATED: { label: 'Jeszcze nie oceniono', tone: 'muted' },
  PASS: { label: 'Bez wykrytej nieprawidłowości', tone: 'safe' },
  PENDING_FAILURE: { label: 'Potwierdzanie nieprawidłowości', tone: 'warning' },
  FAIL: { label: 'Wykryto nieprawidłowość', tone: 'warning' },
  PENDING_RECOVERY: { label: 'Potwierdzanie poprawy', tone: 'warning' },
  UNEVALUABLE: { label: 'Brak danych do oceny', tone: 'muted' },
  INHIBITED: { label: 'Ocena wstrzymana', tone: 'muted' },
  DISABLED: { label: 'Kontrola niewłączona', tone: 'muted' },
};

export default function Heating() {
  const { entities, connection } = useSafetyEntities();
  const connected = connection.ready && !connection.cannotConnect && connection.status === 'connected';
  const systems = getHeatingSystems(entities, connected);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  return (
    <div className='page-stack'>
      <section className='page-introduction'>
        <div>
          <span className='section-kicker'>Nadzór ogrzewania</span>
          <h2>Ogrzewanie</h2>
          <p>Odczyty urządzeń, faza pracy i zakres kontroli. Dostępność danych nie potwierdza, że ciepło dociera do pomieszczeń.</p>
        </div>
      </section>
      {systems.length === 0 && (
        <section className='panel'>
          <h3>{connected ? 'Brak skonfigurowanego monitoringu ogrzewania' : 'Brak bieżących danych ogrzewania'}</h3>
          <p>{connected ? 'Przypisz wejścia instalacji w konfiguracji monitora.' : 'Oczekiwanie na połączenie z Home Assistant.'}</p>
        </section>
      )}
      {systems.map(system => (
        <section className='panel' key={system.entityId}>
          <div className='section-heading'>
            <div>
              <h3>{system.name}</h3>
              <p>{system.phase}</p>
            </div>
            <StatusBadge tone={system.available ? 'warning' : 'muted'}>{system.coverage}</StatusBadge>
          </div>
          <button className='text-link' onClick={() => setSelectedEntityId(system.entityId)}>
            Szczegóły diagnostyczne
          </button>
          <h4>Wejścia</h4>
          <div className='table-scroll'>
            <table>
              <thead>
                <tr>
                  <th>Wielkość</th>
                  <th>Źródło</th>
                  <th>Wartość</th>
                  <th>Jakość danych</th>
                </tr>
              </thead>
              <tbody>
                {system.inputs.map((input, index) => (
                  <tr key={index}>
                    <td>{input.name}</td>
                    <td>{input.sourceName}</td>
                    <td>{input.value}</td>
                    <td>{input.quality}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h4>Zakres kontroli</h4>
          <div className='table-scroll'>
            <table>
              <thead>
                <tr>
                  <th>Kontrola</th>
                  <th>Wynik</th>
                  <th>Informacja</th>
                </tr>
              </thead>
              <tbody>
                {system.rules.map((rule, index) => {
                  const status = statuses[rule.status] ?? statuses.UNEVALUABLE;
                  return (
                    <tr key={index}>
                      <td>
                        {rule.name}
                        {rule.active && <small> · Usterka nadal aktywna</small>}
                      </td>
                      <td>
                        <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
                      </td>
                      <td>{rule.reasons.join('; ')}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      ))}
      <EntityDetailsDialog entityId={selectedEntityId} entities={entities} onClose={() => setSelectedEntityId(null)} />
    </div>
  );
}
