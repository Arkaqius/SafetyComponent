import { useEffect, useState } from 'react';
import { useSafetyEntities } from '../hooks/useSafetyEntities';
import { getStartupView } from '../domain/startup';
import Icon from './Icon';

export default function StartupBanner() {
  const { entities, connection } = useSafetyEntities();
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const startup = getStartupView(entities, now, connection.ready && !connection.cannotConnect);
  if (!startup) return null;
  return (
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
  );
}
