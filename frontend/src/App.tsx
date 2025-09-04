import { HassConnect } from '@hakit/core';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Temperature from './pages/Temperature';
import LogPage from './pages/LogPage';

export default function App() {
  return (
    <HassConnect hassUrl={import.meta.env.VITE_HA_URL} hassToken={import.meta.env.VITE_HA_TOKEN}>
      <Router basename='/local/SafetyHome/'>
        <Routes>
          <Route path='/' element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path='temperature' element={<Temperature />} />
            <Route path='logs' element={<LogPage />} />
          </Route>
        </Routes>
      </Router>
    </HassConnect>
  );
}
