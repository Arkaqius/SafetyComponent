import { useEntity } from '@hakit/core';

export default function Topbar() {
  const safetyState = useEntity('sensor.safetysystem_state');
  const healthState = useEntity('sensor.safety_app_health');

  // Configuration for Safety Status
  const statusConfig = {
    level_4: {
      label: 'Critical Alert',
      bgColor: 'from-red-500 to-red-700',
      textColor: 'text-white',
      animation: 'animate-pulse', // Pulsating animation for critical state
    },
    level_3: {
      label: 'High Alert',
      bgColor: 'from-orange-500 to-orange-700',
      textColor: 'text-white',
      animation: 'animate-pulse', // Pulsating animation for high alert
    },
    level_2: {
      label: 'Warning',
      bgColor: 'from-yellow-400 to-yellow-600',
      textColor: 'text-black',
      animation: '', // No animation
    },
    level_1: {
      label: 'Caution',
      bgColor: 'from-blue-400 to-blue-600',
      textColor: 'text-white',
      animation: '', // No animation
    },
    cleared: {
      label: 'System Safe',
      bgColor: 'from-green-500 to-green-700',
      textColor: 'text-white',
      animation: '', // No animation
    },
  };

  // Configuration for System Health
  const healthConfig = {
    running: {
      label: 'System Running',
      bgColor: 'from-green-400 to-green-600',
      textColor: 'text-white',
      animation: '', // No animation
    },
    stopped: {
      label: 'System Stopped',
      bgColor: 'from-red-500 to-red-700',
      textColor: 'text-white',
      animation: 'animate-pulse', // Pulsating animation for stopped state
    },
  };

  // Current configurations
  const currentStatus = statusConfig[safetyState] || statusConfig.cleared;
  const currentHealth = healthConfig[healthState] || healthConfig.running;

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'flex-start',
        alignItems: 'center',
        padding: '15px 20px',
        background: 'linear-gradient(to right, #0f172a, #1e293b)',
        borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
        gap: '40px',
      }}
    >
      {/* Left Section: Title */}
      <div>
        <h1
          style={{
            margin: 0,
            fontSize: '2rem',
            fontFamily: 'Poppins, sans-serif',
            color: '#3b82f6',
            fontWeight: 'bold',
            textShadow: '1px 1px 4px rgba(0, 0, 0, 0.5)',
          }}
        >
          Home Safety System
        </h1>
        <p
          style={{
            margin: 0,
            fontSize: '1rem',
            color: '#94a3b8',
            fontFamily: 'Roboto, sans-serif',
          }}
        >
          Comprehensive Monitoring & Protection
        </p>
      </div>

      {/* Safety Status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <h3 style={{ margin: 0, fontSize: '1rem', color: '#94a3b8' }}>Safety Status:</h3>
        <div
          className={`px-4 py-2 rounded-full text-sm font-medium inline-flex items-center bg-gradient-to-r ${currentStatus.bgColor} ${currentStatus.textColor} ${currentStatus.animation}`}
          style={{
            boxShadow: '0px 4px 8px rgba(0, 0, 0, 0.2)',
            cursor: 'pointer',
          }}
        >
          <span>{currentStatus.label}</span>
        </div>
      </div>

      {/* System Health */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <h3 style={{ margin: 0, fontSize: '1rem', color: '#94a3b8' }}>System Health:</h3>
        <div
          className={`px-4 py-2 rounded-full text-sm font-medium inline-flex items-center bg-gradient-to-r ${currentHealth.bgColor} ${currentHealth.textColor} ${currentHealth.animation}`}
          style={{
            boxShadow: '0px 4px 8px rgba(0, 0, 0, 0.2)',
            cursor: 'pointer',
          }}
        >
          <span>{currentHealth.label}</span>
        </div>
      </div>
    </div>
  );
}
