import React from 'react';
import { useHass } from '@hakit/core';

interface Action {
  id: string;
  title: string;
  description: string;
  status: 'pending' | 'in-progress' | 'completed';
}

const statusStyles: Record<Action['status'], React.CSSProperties> = {
  pending: { backgroundColor: '#7c2d12', color: '#fde68a' },
  'in-progress': { backgroundColor: '#1e3a8a', color: '#bfdbfe' },
  completed: { backgroundColor: '#065f46', color: '#d1fae5' },
};

const ActionCard: React.FC<{ action: Action }> = ({ action }) => (
  <div
    style={{
      backgroundColor: '#374151',
      padding: '15px',
      borderRadius: '8px',
      boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
      marginBottom: '15px',
      color: '#f3f4f6',
    }}
  >
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
      <div>
        <h3 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 'bold', color: '#f3f4f6' }}>{action.title}</h3>
        <p style={{ margin: '5px 0 0', color: '#9ca3af' }}>{action.description}</p>
      </div>
      <span
        style={{
          padding: '5px 10px',
          borderRadius: '16px',
          fontSize: '0.875rem',
          fontWeight: 'bold',
          whiteSpace: 'nowrap',
          ...statusStyles[action.status],
        }}
      >
        {action.status}
      </span>
    </div>
  </div>
);

interface BackendRecoveryAction {
  name?: string;
  params?: Record<string, unknown>;
  status?: string;
}

const ActionsList: React.FC = () => {
  const { getAllEntities } = useHass();
  const entities = getAllEntities();

  const appHealthEntity = entities['sensor.safety_app_health'];
  const recoveryActions = appHealthEntity?.attributes?.recovery_actions as Record<string, BackendRecoveryAction> | undefined;
  const actions: Action[] = Object.entries(recoveryActions || {}).map(([id, action]) => {
    const description = Object.entries(action.params || {})
      .map(([key, value]) => `${key}: ${String(value)}`)
      .join(', ');
    return {
      id,
      title: action.name || id,
      description: description || 'No parameters',
      status: action.status === 'TO_PERFORM' ? 'in-progress' : 'pending',
    };
  });

  return (
    <div style={{ padding: '20px', backgroundColor: '#1e293b', borderRadius: '8px' }}>
      <h1 style={{ marginBottom: '20px', fontSize: '1.5rem', color: '#3b82f6' }}>Actions</h1>
      {actions.length > 0 ? (
        actions.map(action => <ActionCard key={action.id} action={action} />)
      ) : (
        <p style={{ color: '#9ca3af' }}>No recovery actions available.</p>
      )}
    </div>
  );
};

export default ActionsList;
