import { type RefObject } from 'react';
import { useLocation } from 'react-router-dom';
import { MOCK_MODE } from '../config';
import { formatRelativeTime, normalizeState } from '../domain/safety';
import { useSafetyEntities } from '../hooks/useSafetyEntities';
import Icon from './Icon';
import StatusBadge from './StatusBadge';

interface TopbarProps {
  menuButtonRef: RefObject<HTMLButtonElement>;
  navigationOpen: boolean;
  onMenuClick: () => void;
}

const pageLabels: Record<string, { eyebrow: string; title: string }> = {
  '/': { eyebrow: 'SafetyComponent', title: 'Przegląd systemu' },
  '/temperature': { eyebrow: 'Monitoring środowiska', title: 'Temperatury i trendy' },
  '/safety-doors': { eyebrow: 'Wejścia do domu', title: 'Drzwi i bramy' },
  '/external-hazards': { eyebrow: 'Otoczenie domu', title: 'Zagrożenia zewnętrzne' },
  '/history': { eyebrow: 'Diagnostyka', title: 'Historia stanów' },
};

export default function Topbar({ menuButtonRef, navigationOpen, onMenuClick }: TopbarProps) {
  const location = useLocation();
  const { healthEntity, summary, connection } = useSafetyEntities();
  const page = pageLabels[location.pathname] ?? pageLabels['/'];
  const healthState = normalizeState(healthEntity?.state);
  const isConnected = connection.ready && !connection.cannotConnect;
  const healthLabel =
    healthState === 'running'
      ? 'Usługa działa'
      : healthState === 'init'
        ? 'Uruchamianie'
        : healthState === 'invalid_cfg'
          ? 'Błąd konfiguracji'
          : 'Usługa niedostępna';

  return (
    <header className='topbar'>
      <div className='topbar-title'>
        <button
          aria-controls='primary-navigation'
          aria-expanded={navigationOpen}
          aria-label='Otwórz nawigację'
          className='icon-button mobile-menu-button'
          onClick={onMenuClick}
          ref={menuButtonRef}
          type='button'
        >
          <Icon name='menu' />
        </button>
        <div>
          <span className='eyebrow'>{page.eyebrow}</span>
          <h1>{page.title}</h1>
        </div>
      </div>

      <div aria-live='polite' className='topbar-statuses'>
        <div className='topbar-status-group'>
          <span className='topbar-status-label'>Bezpieczeństwo</span>
          <StatusBadge pulse={summary.tone === 'critical'} tone={summary.tone}>
            {summary.label}
          </StatusBadge>
        </div>
        <div className='topbar-status-group desktop-status'>
          <span className='topbar-status-label'>Usługa</span>
          <StatusBadge tone={healthState === 'running' && isConnected ? 'safe' : healthState === 'init' ? 'warning' : 'muted'}>
            {healthLabel}
          </StatusBadge>
        </div>
        <div className='connection-copy'>
          <span>{MOCK_MODE ? 'Tryb demonstracyjny' : isConnected ? 'Połączono z Home Assistant' : 'Brak połączenia'}</span>
          <small>{MOCK_MODE ? 'Lokalne dane testowe' : `Aktualizacja ${formatRelativeTime(connection.lastUpdated?.toISOString())}`}</small>
        </div>
      </div>
    </header>
  );
}
