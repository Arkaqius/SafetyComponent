import { type RefObject } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { MOCK_MODE } from '../config';
import { formatRelativeTime, normalizeState } from '../domain/safety';
import { useSafetyEntities } from '../hooks/useSafetyEntities';
import Icon from './Icon';
import StatusBadge from './StatusBadge';
import HelpTooltip from './HelpTooltip';
import ViewModeSwitch, { type ViewModeContext } from './ViewModeSwitch';

interface TopbarProps extends ViewModeContext {
  menuButtonRef: RefObject<HTMLButtonElement | null>;
  navigationOpen: boolean;
  onMenuClick: () => void;
}

const pageLabels: Record<string, { eyebrow: string; title: string }> = {
  '/': { eyebrow: 'SafetyComponent', title: 'Przegląd systemu' },
  '/temperature': { eyebrow: 'Monitoring środowiska', title: 'Temperatury i trendy' },
  '/safety-doors': { eyebrow: 'Wejścia do domu', title: 'Drzwi i bramy' },
  '/internal-hazards': { eyebrow: 'Bezpieczeństwo wewnątrz domu', title: 'Zagrożenia wewnętrzne' },
  '/external-hazards': { eyebrow: 'Otoczenie domu', title: 'Zagrożenia zewnętrzne' },
  '/entities': { eyebrow: 'Diagnostyka danych', title: 'Encje i urządzenia' },
  '/history': { eyebrow: 'Diagnostyka', title: 'Historia powiadomień i stanów' },
  '/configuration': { eyebrow: 'Ustawienia aplikacji', title: 'Konfiguracja instalacji' },
  '/functional-safety': { eyebrow: 'Diagnostyka bezpieczeństwa', title: 'Zdrowie funkcji bezpieczeństwa' },
  '/help': { eyebrow: 'SafetyHome', title: 'Pomoc i objaśnienia' },
  '/fault-management': { eyebrow: 'Diagnostyka bezpieczeństwa', title: 'Fault Management' },
};

export default function Topbar({ menuButtonRef, navigationOpen, onMenuClick, viewMode, onViewModeChange }: TopbarProps) {
  const location = useLocation();
  const { healthEntity, summary, connection } = useSafetyEntities();
  const pagePath = location.pathname.startsWith('/configuration/') ? '/configuration' : location.pathname;
  const page = pageLabels[pagePath] ?? pageLabels['/'];
  const basic = viewMode === 'basic';
  const healthState = normalizeState(healthEntity?.state);
  const isConnected = connection.ready && !connection.cannotConnect;
  const safetyLabel = summary.label;
  const safetyTone = summary.tone;
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
        {!basic && (
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
        )}
        <div>
          {!basic && <span className='eyebrow'>{page.eyebrow}</span>}
          <h1>{basic && location.pathname === '/' ? 'SafetyHome' : page.title}</h1>
        </div>
      </div>

      <div className='topbar-view-controls'>
        <ViewModeSwitch viewMode={viewMode} onViewModeChange={onViewModeChange} />
        {basic && (
          <Link className='basic-help-link' to={location.pathname === '/help' ? '/' : '/help'}>
            {location.pathname === '/help' ? 'Dom' : 'Pomoc'}
          </Link>
        )}
      </div>

      <div aria-live='polite' className='topbar-statuses'>
        {!basic && (
          <div className='topbar-status-group'>
            <span className='topbar-status-label'>Bezpieczeństwo</span>
            <div className='status-with-help'>
              <StatusBadge pulse={summary.activeFaultCount > 0 && summary.tone === 'critical'} tone={safetyTone}>
                {safetyLabel}
              </StatusBadge>
              <HelpTooltip
                label='Ocena bezpieczeństwa'
                text={`${summary.detail} Ocena uwzględnia zgłoszony stan systemu, usterki oraz dostępność danych. Brak połączenia oznacza ostatni znany stan, a nie bieżące potwierdzenie bezpieczeństwa.`}
              />
            </div>
          </div>
        )}
        {!basic && (
          <div className='topbar-status-group desktop-status'>
            <span className='topbar-status-label'>Usługa</span>
            <div className='status-with-help'>
              <StatusBadge tone={healthState === 'running' && isConnected ? 'safe' : healthState === 'init' ? 'warning' : 'muted'}>
                {healthLabel}
              </StatusBadge>
              <HelpTooltip
                label='Stan usługi'
                text='Informuje o działaniu usługi SafetyComponent. Działająca usługa nie oznacza, że wszystkie czujniki są dostępne lub że dom jest wolny od zagrożeń.'
              />
            </div>
          </div>
        )}
        {(!isConnected || (!basic && (!MOCK_MODE || location.pathname !== '/'))) && (
          <div className={`connection-copy${!isConnected ? ' connection-banner' : ''}`}>
            <span>
              {!isConnected
                ? connection.status === 'suspended'
                  ? 'Połączenie wstrzymane · dane z pamięci'
                  : 'Brak połączenia · dane z pamięci'
                : MOCK_MODE
                  ? 'Tryb demonstracyjny'
                  : 'Połączono z Home Assistant'}
            </span>
            <small>
              {MOCK_MODE ? 'Lokalne dane testowe' : `Aktualizacja ${formatRelativeTime(connection.lastUpdated?.toISOString())}`}
            </small>
          </div>
        )}
      </div>
    </header>
  );
}
