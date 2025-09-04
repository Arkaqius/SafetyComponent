import React from 'react';

interface Log {
  timestamp: string;
  type: 'info' | 'warning' | 'error';
  message: string;
  category: string;
}

const typeStyles: Record<Log['type'], string> = {
  info: 'text-blue-400',
  warning: 'text-yellow-400',
  error: 'text-red-400',
};

interface LogListProps {
  logs: Log[];
  limit?: number; // Optional limit on the number of logs to display
}

const LogList: React.FC<LogListProps> = ({ logs, limit }) => {
  // Optionally limit the number of logs
  const displayedLogs = limit ? logs.slice(0, limit) : logs;

  return (
    <div>
      {displayedLogs.map((log, index) => (
        <div
          key={index}
          style={{
            borderLeft: '4px solid #334155',
            padding: '10px 15px',
            marginBottom: '15px',
            backgroundColor: '#111827',
            borderRadius: '4px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            {/* Log Type and Timestamp */}
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
              <span className={`${typeStyles[log.type]} text-sm`} style={{ fontWeight: 'bold' }}>
                {log.type.toUpperCase()}
              </span>
              <span className='text-gray-400 text-sm'>{new Date(log.timestamp).toLocaleString()}</span>
            </div>
            {/* Category */}
            <span className='text-gray-500 text-sm'>{log.category}</span>
          </div>
          {/* Message */}
          <p className='text-gray-200 mt-2' style={{ marginTop: '10px' }}>
            {log.message}
          </p>
        </div>
      ))}
    </div>
  );
};

export default LogList;
