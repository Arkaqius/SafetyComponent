import { lazy, Suspense } from 'react';
import { HassConnect } from '@hakit/core';
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import { MOCK_MODE } from './config';
import Dashboard from './pages/Dashboard';
import Temperature from './pages/Temperature';
import LogPage from './pages/LogPage';
import SafetyDoors from './pages/SafetyDoors';

const MockHassProvider = import.meta.env.DEV ? lazy(() => import('./dev/MockHassProvider')) : null;

export default function App() {
  const hassUrl = import.meta.env.PROD ? window.location.origin : import.meta.env.VITE_HA_URL || window.location.origin;
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
  return <HassConnect hassUrl={hassUrl}>{routes}</HassConnect>;
}
