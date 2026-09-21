import { useEffect, useRef } from 'react';
import { formatNumeric, type TemperatureView } from '../domain/safety';
import Icon from './Icon';

interface AverageTemperatureDialogProps {
  average: number | null;
  onClose: () => void;
  onSelectEntity: (entityId: string) => void;
  open: boolean;
  temperatures: TemperatureView[];
}

export default function AverageTemperatureDialog({ average, onClose, onSelectEntity, open, temperatures }: AverageTemperatureDialogProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeButtonRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', closeOnEscape);
      previousFocus?.focus();
    };
  }, [onClose, open]);

  if (!open) return null;
  const available = temperatures.filter((temperature): temperature is TemperatureView & { state: number } => temperature.state !== null);

  return (
    <div
      className='entity-dialog-backdrop'
      onMouseDown={event => {
        if (event.target === event.currentTarget) onClose();
      }}
      role='presentation'
    >
      <section aria-labelledby='average-temperature-title' aria-modal='true' className='entity-dialog' role='dialog'>
        <header className='entity-dialog-header'>
          <div className='entity-dialog-heading'>
            <span className='section-kicker'>Podsumowanie pomiarów</span>
            <h2 id='average-temperature-title'>Średnia temperatura</h2>
            <p>
              {average === null ? 'Brak dostępnych pomiarów' : `${formatNumeric(average, 1)} °C`} · {available.length}/{temperatures.length}{' '}
              źródeł
            </p>
          </div>
          <button
            aria-label='Zamknij szczegóły średniej temperatury'
            className='icon-button entity-dialog-close'
            onClick={onClose}
            ref={closeButtonRef}
            type='button'
          >
            <Icon name='close' size={20} />
          </button>
        </header>
        <div className='entity-dialog-scroll'>
          <p>Średnia jest obliczana z aktualnie dostępnych pomiarów. Wybierz pomieszczenie, aby zobaczyć stan encji i jej historię.</p>
          <div className='average-temperature-list'>
            {temperatures.map(temperature => (
              <button
                className='entity-name-button'
                disabled={temperature.state === null}
                key={temperature.entityId}
                onClick={() => {
                  onClose();
                  onSelectEntity(temperature.entityId);
                }}
                title={temperature.entityId}
                type='button'
              >
                <strong>{temperature.roomName}</strong>
                <small>{temperature.state === null ? 'Brak danych' : `${formatNumeric(temperature.state, 1)} °C`}</small>
              </button>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
