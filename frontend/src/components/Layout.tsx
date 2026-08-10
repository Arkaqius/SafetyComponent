import { useCallback, useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import Topbar from './Topbar';
import Icon, { type IconName } from './Icon';

const MOBILE_NAVIGATION_QUERY = '(max-width: 980px)';
const menuItems: Array<{ title: string; path: string; icon: IconName; description: string }> = [
  {
    title: 'Przegląd',
    path: '/',
    icon: 'dashboard',
    description: 'Stan systemu i aktywne zdarzenia',
  },
  {
    title: 'Temperatury',
    path: '/temperature',
    icon: 'temperature',
    description: 'Odczyty i trendy pomiarów',
  },
  {
    title: 'Wejścia',
    path: '/safety-doors',
    icon: 'door',
    description: 'Czas otwarcia drzwi i bram',
  },
  {
    title: 'Zagrożenia zewnętrzne',
    path: '/external-hazards',
    icon: 'environment',
    description: 'Pogoda, powietrze i promieniowanie',
  },
  {
    title: 'Historia',
    path: '/history',
    icon: 'history',
    description: 'Zmiany stanu encji bezpieczeństwa',
  },
];

export default function Layout() {
  const location = useLocation();
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [compactNavigation, setCompactNavigation] = useState(() => window.matchMedia(MOBILE_NAVIGATION_QUERY).matches);
  const [currentTime, setCurrentTime] = useState(new Date());
  const sidebarRef = useRef<HTMLElement>(null);
  const appMainRef = useRef<HTMLDivElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const previousPathname = useRef(location.pathname);
  const sidebarHidden = compactNavigation && !navigationOpen;
  const backgroundHidden = compactNavigation && navigationOpen;

  const closeNavigation = useCallback(
    (restoreFocus = true) => {
      setNavigationOpen(false);
      if (restoreFocus && compactNavigation) {
        window.requestAnimationFrame(() => menuButtonRef.current?.focus());
      }
    },
    [compactNavigation]
  );

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(new Date());
    }, 30_000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const mediaQuery = window.matchMedia(MOBILE_NAVIGATION_QUERY);
    const handleChange = (event: MediaQueryListEvent) => {
      setCompactNavigation(event.matches);
      if (!event.matches) setNavigationOpen(false);
    };
    setCompactNavigation(mediaQuery.matches);
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, []);

  useEffect(() => {
    sidebarRef.current?.toggleAttribute('inert', sidebarHidden);
    appMainRef.current?.toggleAttribute('inert', backgroundHidden);
  }, [backgroundHidden, sidebarHidden]);

  useEffect(() => {
    if (!backgroundHidden) return;
    const frame = window.requestAnimationFrame(() => {
      const activeLink = sidebarRef.current?.querySelector<HTMLElement>('.navigation-item-active');
      const firstLink = sidebarRef.current?.querySelector<HTMLElement>('.navigation-item');
      (activeLink ?? firstLink)?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [backgroundHidden]);

  useEffect(() => {
    if (!backgroundHidden) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeNavigation();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [backgroundHidden, closeNavigation]);

  useEffect(() => {
    if (previousPathname.current === location.pathname) return;
    previousPathname.current = location.pathname;
    window.scrollTo({ top: 0, behavior: 'auto' });
    if (navigationOpen) closeNavigation();
  }, [closeNavigation, location.pathname, navigationOpen]);

  return (
    <div className='app-shell'>
      <aside className={`sidebar${navigationOpen ? ' sidebar-open' : ''}`} id='primary-navigation' ref={sidebarRef}>
        <div className='brand'>
          <div className='brand-mark'>
            <Icon name='shield' size={25} />
          </div>
          <div>
            <strong>SafetyHome</strong>
            <span>Centrum bezpieczeństwa</span>
          </div>
          <button aria-label='Zamknij nawigację' className='icon-button sidebar-close' onClick={() => closeNavigation()} type='button'>
            <Icon name='close' />
          </button>
        </div>

        <nav aria-label='Główna nawigacja' className='main-navigation'>
          <span className='navigation-label'>Monitorowanie</span>
          {menuItems.map(item => (
            <NavLink
              className={({ isActive }) => `navigation-item${isActive ? ' navigation-item-active' : ''}`}
              end={item.path === '/'}
              key={item.path}
              onClick={() => {
                if (compactNavigation) closeNavigation();
              }}
              to={item.path}
            >
              <span className='navigation-icon'>
                <Icon name={item.icon} size={20} />
              </span>
              <span>
                <strong>{item.title}</strong>
                <small>{item.description}</small>
              </span>
              <Icon className='navigation-chevron' name='chevron' size={16} />
            </NavLink>
          ))}
        </nav>

        <div className='sidebar-footer'>
          <span>{currentTime.toLocaleDateString('pl-PL', { weekday: 'long', day: 'numeric', month: 'long' })}</span>
          <strong>{currentTime.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' })}</strong>
          <small>Dane aktualizują się automatycznie</small>
        </div>
      </aside>

      {navigationOpen && (
        <button
          aria-label='Zamknij nawigację'
          className='navigation-backdrop'
          onClick={() => closeNavigation()}
          tabIndex={-1}
          type='button'
        />
      )}

      <div className='app-main' ref={appMainRef}>
        <Topbar menuButtonRef={menuButtonRef} navigationOpen={navigationOpen} onMenuClick={() => setNavigationOpen(true)} />
        <main className='page-content'>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
