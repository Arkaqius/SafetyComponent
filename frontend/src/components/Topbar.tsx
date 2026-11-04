import { type RefObject } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { MOCK_MODE } from '../config';
import { normalizeState, type StatusTone } from '../domain/safety';
import { getCoverageView } from '../domain/coverage';
import { EVALUATION_PROGRESS_ENTITY_ID } from '../domain/functionalSafety';
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
  '/safety-doors': { eyebrow: 'Monitoring otwarcia', title: 'Drzwi i bramy' },
  '/internal-hazards': { eyebrow: 'Bezpieczeństwo wewnątrz domu', title: 'Zagrożenia wewnętrzne' },
  '/heating': { eyebrow: 'Nadzór ogrzewania', title: 'Ogrzewanie' },
  '/external-hazards': { eyebrow: 'Otoczenie domu', title: 'Zagrożenia zewnętrzne' },
  '/history': { eyebrow: 'Diagnostyka', title: 'Historia powiadomień i stanów' },
  '/configuration': { eyebrow: 'Ustawienia aplikacji', title: 'Konfiguracja instalacji' },
  '/functional-safety': { eyebrow: 'Diagnostyka bezpieczeństwa', title: 'Zdrowie systemu' },
  '/help': { eyebrow: 'SafetyHome', title: 'Pomoc i objaśnienia' },
  '/safety-routines': { eyebrow: 'Kontrole na żądanie', title: 'Scenariusze bezpieczeństwa' },
};

export default function Topbar({ menuButtonRef, navigationOpen, onMenuClick, viewMode, onViewModeChange }: TopbarProps) {
  const location = useLocation();
  const { healthEntity, summary, connection, entities, internalEnvironment, externalHazards } = useSafetyEntities();
  const pagePath = location.pathname.startsWith('/configuration/') ? '/configuration' : location.pathname;
  const page = pageLabels[pagePath] ?? pageLabels['/'];
  const basic = viewMode === 'basic';
  const healthState = normalizeState(healthEntity?.state);
  const isConnected = connection.ready && !connection.cannotConnect;
  const coverage = getCoverageView(isConnected ? entities : {});
  const progress = isConnected ? entities[EVALUATION_PROGRESS_ENTITY_ID]?.state : undefined;
  const internal = isConnected ? internalEnvironment.status : 'unknown';
  const external = isConnected ? externalHazards.status : 'unknown';
  const internalLabels = {
    healthy: ['Bez alarmu', 'safe'],
    active_hazard: ['Alarm', 'critical'],
    degraded: ['Ograniczone', 'warning'],
    unavailable: ['Niedostępne', 'danger'],
    unknown: ['Brak danych', 'muted'],
  } as const;
  const externalLabels = {
    clear: ['Bez ekspozycji', 'safe'],
    watch: ['Obserwacja', 'warning'],
    warning: ['Ostrzeżenie', 'danger'],
    severe: ['Alarm', 'critical'],
    unavailable: ['Niedostępne', 'danger'],
    unknown: ['Brak danych', 'muted'],
  } as const;
  const overview: Array<{ name: string; label: string; tone: StatusTone; to: string }> = [
    {
      name: 'Oceny',
      label: progress === 'observed' ? 'Wykonane' : progress === 'attention' ? 'Wymagają uwagi' : 'Brak danych',
      tone: progress === 'observed' ? 'info' : progress === 'attention' ? 'danger' : 'muted',
      to: '/functional-safety?tab=platform',
    },
    {
      name: 'Pokrycie',
      label: { FULL: 'Pełne', PARTIAL: 'Częściowe', DEGRADED: 'Ograniczone', UNKNOWN: 'Nieustalone' }[coverage.state],
      tone: coverage.tone,
      to: '/functional-safety?tab=faults',
    },
    { name: 'Wewnątrz', label: internalLabels[internal][0], tone: internalLabels[internal][1], to: '/internal-hazards' },
    { name: 'Otoczenie', label: externalLabels[external][0], tone: externalLabels[external][1], to: '/external-hazards' },
  ];
  const showOverview = !basic && location.pathname === '/';
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
    <header className={`topbar${showOverview ? ' topbar-with-overview' : ''}`}>
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
            {MOCK_MODE && <small>Lokalne dane testowe</small>}
          </div>
        )}
      </div>
      {showOverview && (
        <nav className='topbar-overview' aria-label='Skrót monitoringu'>
          {overview.map(item => (
            <Link key={item.name} to={item.to}>
              <span>{item.name}</span>
              <StatusBadge tone={item.tone}>{item.label}</StatusBadge>
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}
