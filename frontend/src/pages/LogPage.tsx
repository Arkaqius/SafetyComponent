import React from 'react';
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

const LogPage: React.FC = () => {
  return (
    <div style={{ padding: '20px', backgroundColor: '#1e293b', borderRadius: '8px', color: '#fff' }}>
      <h1 style={{ marginBottom: '20px', fontSize: '1.5rem', color: '#3b82f6' }}>System Logs</h1>
      <LogList logs={logs} /> {/* Display all logs */}
    </div>
  );
};

export default LogPage;
