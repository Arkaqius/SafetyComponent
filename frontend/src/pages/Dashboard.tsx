import React from 'react';
import { Column } from '@hakit/components';
import FaultSection from '../components/FaultSection'; // FaultSection component
import ActionsList from '../components/ActionsList'; // ActionsList component
import LogList from '../components/LogList'; // Reusable LogList component

// Sample logs
const logs = [
  {
    timestamp: '2025-01-14T12:00:00Z',
    type: 'info',
    message: 'System started successfully.',
    category: 'System',
  },
  {
    timestamp: '2025-01-14T12:05:00Z',
    type: 'warning',
    message: 'Temperature threshold exceeded in Living Room.',
    category: 'Temperature',
  },
  {
    timestamp: '2025-01-14T12:10:00Z',
    type: 'error',
    message: 'Gas leak detected in Kitchen!',
    category: 'Safety',
  },
  {
    timestamp: '2025-01-14T12:20:00Z',
    type: 'info',
    message: 'New sensor added to the system.',
    category: 'System',
  },
  {
    timestamp: '2025-01-14T12:30:00Z',
    type: 'warning',
    message: 'Humidity levels are above normal in Basement.',
    category: 'Environment',
  },
];

export default function Dashboard() {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        padding: '20px',
        backgroundColor: '#0f172a',
        color: '#fff',
      }}
    >
      {/* Dashboard Header */}
      <h1 style={{ marginBottom: '20px', fontSize: '2rem', color: '#3b82f6' }}>Dashboard</h1>

      {/* Main Content: Active Faults and Recovery Actions */}
      <div
        style={{
          display: 'flex',
          flex: 1,
          gap: '20px',
        }}
      >
        {/* Fault Section */}
        <FaultSection />

        {/* Recovery Actions */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <h2 style={{ fontSize: '1.5rem', color: '#94a3b8', marginBottom: '10px' }}>Recovery Actions</h2>
          <ActionsList />
        </div>
      </div>

      {/* Recent Activity */}
      <div style={{ marginTop: '20px' }}>
        <h2 style={{ fontSize: '1.5rem', color: '#94a3b8', marginBottom: '10px' }}>Recent Activity</h2>
        <div
          style={{
            backgroundColor: '#1e293b',
            padding: '15px',
            borderRadius: '8px',
            overflowY: 'auto',
            maxHeight: '200px',
          }}
        >
          <LogList logs={logs} limit={5} /> {/* Display latest 5 logs */}
        </div>
      </div>
    </div>
  );
}
