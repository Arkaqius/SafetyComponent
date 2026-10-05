import { useRef } from 'react';
import { formatNumeric, type TemperatureView } from '../domain/safety';
import Icon from './Icon';
import ModalDialog from './ModalDialog';

interface AverageTemperatureDialogProps {
  average: number | null;
  onClose: () => void;
  onSelectEntity: (entityId: string) => void;
  open: boolean;
  temperatures: TemperatureView[];
}

export default function AverageTemperatureDialog({ average, onClose, onSelectEntity, open, temperatures }: AverageTemperatureDialogProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  if (!open) return null;
  const available = temperatures.filter((temperature): temperature is TemperatureView & { state: number } => temperature.state !== null);

  return (
    <ModalDialog initialFocus={closeButtonRef} labelledBy='average-temperature-title' onClose={onClose} open={open}>
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
    </ModalDialog>
  );
}
