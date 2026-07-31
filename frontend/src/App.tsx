import { lazy, Suspense, useEffect, useState, type Dispatch, type ReactNode, type SetStateAction } from 'react';
import { HassConnect } from '@hakit/core';
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import { requestExternalAuthToken } from './auth/externalAuth';
import Layout from './components/Layout';
import { MOCK_MODE } from './config';
import Dashboard from './pages/Dashboard';
import Temperature from './pages/Temperature';
import LogPage from './pages/LogPage';
import SafetyDoors from './pages/SafetyDoors';

const MockHassProvider = import.meta.env.DEV ? lazy(() => import('./dev/MockHassProvider')) : null;

type ConnectionAuth =
  | { status: 'checking' }
  | { status: 'browser' }
  | { status: 'companion'; token: string }
  | { status: 'error'; message: string };

export default function App() {
  const hassUrl = import.meta.env.PROD ? window.location.origin : import.meta.env.VITE_HA_URL || window.location.origin;
  const [connectionAuth, setConnectionAuth] = useState<ConnectionAuth>({ status: 'checking' });
  const routes = (
    <HashRouter>
      <Routes>
        <Route path='/' element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path='temperature' element={<Temperature />} />
          <Route path='safety-doors' element={<SafetyDoors />} />
          <Route path='history' element={<LogPage />} />
          <Route path='logs' element={<Navigate replace to='/history' />} />
          <Route path='*' element={<Navigate replace to='/' />} />
        </Route>
      </Routes>
    </HashRouter>
  );

  if (MOCK_MODE && MockHassProvider) {
    return (
      <Suspense fallback={null}>
        <MockHassProvider>{routes}</MockHassProvider>
      </Suspense>
    );
  }

  return <HomeAssistantConnection auth={connectionAuth} hassUrl={hassUrl} routes={routes} setAuth={setConnectionAuth} />;
}

function HomeAssistantConnection({
  auth,
  hassUrl,
  routes,
  setAuth,
}: {
  auth: ConnectionAuth;
  hassUrl: string;
  routes: ReactNode;
  setAuth: Dispatch<SetStateAction<ConnectionAuth>>;
}) {
  useEffect(() => {
    let cancelled = false;
    let refreshHandle: number | undefined;

    const connect = async (force = false) => {
      const result = await requestExternalAuthToken(undefined, { force });
      if (cancelled) return;
      if (!result.supported) {
        setAuth({ status: 'browser' });
        return;
      }
      if ('error' in result) {
        setAuth({ status: 'error', message: result.error });
        return;
      }

      setAuth({ status: 'companion', token: result.token.accessToken });
      const refreshAfterSeconds = Math.max(30, result.token.expiresIn - 60);
      refreshHandle = window.setTimeout(() => void connect(true), refreshAfterSeconds * 1000);
    };

    void connect();
    return () => {
      cancelled = true;
      if (refreshHandle !== undefined) window.clearTimeout(refreshHandle);
    };
  }, [setAuth]);

  if (auth.status === 'checking') {
    return <ConnectionMessage message='Łączenie z Home Assistant…' />;
  }
  if (auth.status === 'error') {
    return <ConnectionMessage message={auth.message} />;
  }
  if (auth.status === 'companion') {
    return (
      <HassConnect hassToken={auth.token} hassUrl={hassUrl} key={auth.token}>
        {routes}
      </HassConnect>
    );
  }
  return <HassConnect hassUrl={hassUrl}>{routes}</HassConnect>;
}

function ConnectionMessage({ message }: { message: string }) {
  return (
    <main className='connection-message'>
      <strong>Safety Home</strong>
      <span>{message}</span>
    </main>
  );
}
