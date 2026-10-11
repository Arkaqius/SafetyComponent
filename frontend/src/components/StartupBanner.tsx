import { useEffect, useState } from 'react';
import { useSafetyEntities } from '../hooks/useSafetyEntities';
import { getStartupView } from '../domain/startup';
import { getTemperatureSamplingView } from '../domain/temperatureSampling';
import Icon from './Icon';

export default function StartupBanner() {
  const { entities, connection } = useSafetyEntities();
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const startup = getStartupView(entities, now, connection.ready && !connection.cannotConnect);
  const sampling = getTemperatureSamplingView(entities, now, connection.ready && !connection.cannotConnect);
  if (!startup && !sampling) return null;
  return (
    <>
      {startup && (
        <aside className={`startup-banner${startup.available ? '' : ' startup-banner-unavailable'}`} aria-label='Rozruch monitoringu'>
          <Icon name='activity' size={24} />
          <div>
            <strong>{startup.label}</strong>
            <p>{startup.detail}</p>
          </div>
          <div className='startup-countdown' aria-live='off'>
            <small>{startup.available ? 'Pozostały czas' : 'Odliczanie niedostępne'}</small>
            <strong>{startup.countdown}</strong>
          </div>
        </aside>
      )}
      {sampling && (
        <aside className='startup-banner' aria-label='Gotowość prognozy temperatury'>
          <Icon name='temperature' size={24} />
          <div>
            <strong>{sampling.label}</strong>
            <p>{sampling.detail}</p>
          </div>
        </aside>
      )}
    </>
  );
}
