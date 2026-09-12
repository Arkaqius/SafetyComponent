import { useState } from 'react';
import {
  filterNotificationHistory,
  formatNotificationTime,
  notificationKind,
  notificationRecipient,
  notificationState,
  readNotificationHistory,
} from '../domain/notificationHistory.js';
import type { EntitySnapshot } from '../domain/safety.js';
import StatusBadge from './StatusBadge.js';

export default function NotificationHistory({ entity, connected }: { entity?: EntitySnapshot; connected: boolean }) {
  const [result, setResult] = useState('accepted_by_home_assistant');
  const [state, setState] = useState('all');
  const entries = readNotificationHistory(entity);
  const available =
    entity &&
    !['unavailable', 'unknown'].includes(entity.state) &&
    entity.attributes.version === 1 &&
    Array.isArray(entity.attributes.entries);
  const visible = filterNotificationHistory(entries, result, state);

  return (
    <section aria-labelledby='notification-history-title' className='panel notification-history'>
      <div className='entity-dialog-section-header'>
        <div>
          <span className='section-kicker'>Wiadomości do użytkowników</span>
          <h2 id='notification-history-title'>Historia powiadomień</h2>
          <p>Wysłanie oznacza przyjęcie przez Home Assistant. Odbiór na telefonie nie jest potwierdzany.</p>
        </div>
      </div>
      <div className='history-controls'>
        <label className='select-field compact-select'>
          <span>Wynik wysyłki</span>
          <select value={result} onChange={event => setResult(event.target.value)}>
            <option value='accepted_by_home_assistant'>Wysłane</option>
            <option value='failed'>Nieudane próby</option>
            <option value='all'>Wszystkie próby</option>
          </select>
        </label>
        <label className='select-field compact-select'>
          <span>Stan usterki w chwili wysyłki</span>
          <select value={state} onChange={event => setState(event.target.value)}>
            <option value='all'>Wszystkie stany</option>
            <option value='SET'>Usterka aktywna</option>
            <option value='CLEARED'>Usterka ustąpiła</option>
            <option value='SHADOWED'>Usterka przesłonięta</option>
          </select>
        </label>
      </div>
      {!connected || !available ? (
        <p role='status'>
          Historia powiadomień jest niedostępna.{' '}
          {entries.length > 0 ? 'Poniżej ostatnio odczytane wpisy.' : 'Oczekiwanie na dane z Home Assistanta.'}
        </p>
      ) : entries.length === 0 ? (
        <p>Brak zapisanych prób wysyłki. Historia obejmuje powiadomienia od uruchomienia rejestru.</p>
      ) : visible.length === 0 ? (
        <p>Brak powiadomień spełniających wybrane filtry.</p>
      ) : null}
      <div className='notification-list'>
        {visible.map(entry => (
          <details className='notification-item' key={entry.id}>
            <summary>
              <span className='notification-item-copy'>
                <strong>{entry.title || notificationKind(entry.kind)}</strong>
                <span className='notification-preview'>
                  {entry.message === 'clear_notification'
                    ? 'Wycofanie powiadomienia dla przesłoniętej usterki'
                    : entry.message.split('\n')[0]}
                </span>
                <span>Do: {notificationRecipient(entry.service)}</span>
                <time dateTime={entry.attempted_at}>{formatNotificationTime(entry.attempted_at)}</time>
              </span>
              <span className='notification-item-badges'>
                <StatusBadge tone={entry.fault_state === 'CLEARED' ? 'safe' : entry.fault_state === 'SET' ? 'danger' : 'muted'}>
                  {notificationState(entry.fault_state)}
                </StatusBadge>
                <StatusBadge tone={entry.result === 'failed' ? 'warning' : 'safe'}>
                  {entry.result === 'failed' ? 'Nieudana próba' : 'Wysłano do HA'}
                </StatusBadge>
                <small>Szczegóły</small>
              </span>
            </summary>
            <div className='notification-details'>
              <p className='notification-message'>
                {entry.message === 'clear_notification' ? 'Polecenie usunięcia powiadomienia z telefonu.' : entry.message}
              </p>
              {entry.text_truncated && <p>Zapis treści został skrócony do 2048 znaków.</p>}
              <dl className='entity-dialog-facts'>
                <div>
                  <dt>Odbiorca / grupa</dt>
                  <dd>
                    {notificationRecipient(entry.service)}
                    <br />
                    <code>{entry.service}</code>
                  </dd>
                </div>
                <div>
                  <dt>Rodzaj wiadomości</dt>
                  <dd>{notificationKind(entry.kind)}</dd>
                </div>
                <div>
                  <dt>Utworzono wiadomość</dt>
                  <dd>{formatNotificationTime(entry.created_at)}</dd>
                </div>
                <div>
                  <dt>Zakończono próbę wysyłki</dt>
                  <dd>{formatNotificationTime(entry.attempted_at)}</dd>
                </div>
                <div>
                  <dt>Poziom usterki</dt>
                  <dd>{entry.level}</dd>
                </div>
                <div>
                  <dt>Numer próby</dt>
                  <dd>{entry.attempt}</dd>
                </div>
                <div>
                  <dt>Przekroczony termin wysyłki</dt>
                  <dd>{entry.deadline_missed ? 'Tak' : 'Nie'}</dd>
                </div>
                <div>
                  <dt>Identyfikator usterki</dt>
                  <dd>
                    <code>{entry.tag}</code>
                  </dd>
                </div>
                <div>
                  <dt>Stan usterki przy wysyłce</dt>
                  <dd>{entry.fault_state}</dd>
                </div>
                <div>
                  <dt>Identyfikator wpisu</dt>
                  <dd>
                    <code>{entry.id}</code>
                  </dd>
                </div>
                <div>
                  <dt>Wynik</dt>
                  <dd>
                    {entry.result === 'failed'
                      ? 'Home Assistant nie potwierdził przyjęcia. Próba nie oznacza wysłanej wiadomości.'
                      : 'Przyjęto przez Home Assistant; brak potwierdzenia odbioru na telefonie.'}
                  </dd>
                </div>
              </dl>
              <p>Odbiorca odpowiada skonfigurowanej usłudze wysyłki. Skład grupy i osoba korzystająca z telefonu nie są potwierdzane.</p>
            </div>
          </details>
        ))}
      </div>
      <p className='notification-history-note'>
        Ostatnie {Math.min(Number(entity?.attributes.limit) || 100, 100)} prób, osobno dla każdego odbiorcy, od najnowszych. Daty i godziny
        w strefie czasowej przeglądarki. Starsze powiadomienia nie są odtwarzane z historii usterek.
      </p>
    </section>
  );
}
