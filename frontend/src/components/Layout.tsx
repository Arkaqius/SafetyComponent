import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import Topbar from './Topbar';
import { useState, useEffect } from 'react';

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();

  // Menu Items
  const menuItems = [
    {
      title: 'Dashboard',
      path: '/',
      icon: 'mdi-view-dashboard',
    },
    {
      title: 'Temperature',
      path: '/temperature',
      icon: 'mdi-thermometer',
    },
    {
      title: 'Logs',
      path: '/logs',
      icon: 'mdi-clipboard-text',
    },
  ];

  // Current Time
  const [currentTime, setCurrentTime] = useState(new Date().toLocaleTimeString());

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(new Date().toLocaleTimeString());
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ display: 'flex', height: '100vh', backgroundColor: '#1e293b' }}>
      {/* Sidebar */}
      <div
        style={{
          width: '250px',
          backgroundColor: '#111827',
          color: '#fff',
          display: 'flex',
          flexDirection: 'column',
          padding: '20px',
          borderRight: '1px solid #334155',
        }}
      >
        {/* Menu Items */}
        {menuItems.map(item => (
          <div
            key={item.path}
            onClick={() => navigate(item.path)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '10px 15px',
              marginBottom: '10px',
              borderRadius: '8px',
              cursor: 'pointer',
              backgroundColor: location.pathname === item.path ? '#2563eb' : 'transparent',
              color: location.pathname === item.path ? '#fff' : '#9ca3af',
              transition: 'background-color 0.2s, color 0.2s',
            }}
            onMouseEnter={e => {
              if (location.pathname !== item.path) {
                e.currentTarget.style.backgroundColor = '#1e293b';
                e.currentTarget.style.color = '#fff';
              }
            }}
            onMouseLeave={e => {
              if (location.pathname !== item.path) {
                e.currentTarget.style.backgroundColor = 'transparent';
                e.currentTarget.style.color = '#9ca3af';
              }
            }}
          >
            {/* Icon */}
            <span
              className={`mdi ${item.icon}`}
              style={{
                fontSize: '20px',
              }}
            ></span>
            {/* Title */}
            <span style={{ fontSize: '16px' }}>{item.title}</span>
          </div>
        ))}

        {/* Current Time */}
        <div
          style={{
            marginTop: 'auto',
            fontSize: '14px',
            color: '#9ca3af',
            textAlign: 'center',
            padding: '10px 0',
            borderTop: '1px solid #334155',
          }}
        >
          <p>Current Time</p>
          <p style={{ fontSize: '18px', color: '#fff', margin: 0 }}>{currentTime}</p>
        </div>
      </div>

      {/* Main Content */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          padding: '20px',
          backgroundColor: '#0f172a',
          color: '#fff',
        }}
      >
        <Topbar />
        <div
          style={{
            marginTop: '20px',
            flex: 1,
            backgroundColor: '#1e293b',
            padding: '20px',
            borderRadius: '8px',
            boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
          }}
        >
          <Outlet />
        </div>
      </div>
    </div>
  );
}
