import React from 'react';

const Temperature: React.FC = () => {
  // Stubbed data for testing
  const temperatureReadings = [
    {
      location: 'Living Room',
      value: 28,
      status: 'High',
      timestamp: '2025-01-14T12:00:00Z',
    },
    {
      location: 'Bedroom',
      value: 22,
      status: 'Normal',
      timestamp: '2025-01-14T12:05:00Z',
    },
    {
      location: 'Kitchen',
      value: 35,
      status: 'Critical',
      timestamp: '2025-01-14T12:10:00Z',
    },
  ];

  // Style configuration based on status
  const statusStyles: Record<string, React.CSSProperties> = {
    Normal: { color: '#10b981' }, // Green
    High: { color: '#facc15' }, // Yellow
    Critical: { color: '#ef4444' }, // Red
  };

  return (
    <div style={{ padding: '20px', backgroundColor: '#0f172a', borderRadius: '8px', color: '#fff' }}>
      <h1 style={{ marginBottom: '20px', fontSize: '2rem', color: '#3b82f6' }}>Temperature Monitoring</h1>

      {/* Temperature Readings */}
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '1.5rem', color: '#94a3b8', marginBottom: '10px' }}>Current Readings</h2>
        {temperatureReadings.map((reading, index) => (
          <div
            key={index}
            style={{
              borderLeft: `4px solid ${statusStyles[reading.status]?.color || '#94a3b8'}`,
              padding: '10px 15px',
              marginBottom: '15px',
              backgroundColor: '#1e293b',
              borderRadius: '4px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 'bold', color: '#fff' }}>{reading.location}</h3>
                <p style={{ margin: 0, color: '#9ca3af' }}>{new Date(reading.timestamp).toLocaleString()}</p>
              </div>
              <p
                style={{
                  margin: 0,
                  fontSize: '1.25rem',
                  fontWeight: 'bold',
                  ...statusStyles[reading.status],
                }}
              >
                {reading.value}°C
              </p>
            </div>
            <p style={{ margin: '5px 0', color: '#9ca3af' }}>Status: {reading.status}</p>
          </div>
        ))}
      </div>

      {/* Summary */}
      <div>
        <h2 style={{ fontSize: '1.5rem', color: '#94a3b8', marginBottom: '10px' }}>Summary</h2>
        <p style={{ color: '#d1d5db' }}>
          Monitoring temperature levels across key locations. Alerts will be issued for critical or high readings.
        </p>
      </div>
    </div>
  );
};

export default Temperature;
