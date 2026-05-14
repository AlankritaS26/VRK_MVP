import React, { useEffect, useState } from 'react';

export default function IdleScreen() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setTimeout(() => setVisible(true), 100);
  }, []);

  return (
    <div style={{ minHeight: '100vh', background: '#ffffff', fontFamily: "'Segoe UI', Arial, sans-serif", display: 'flex', flexDirection: 'column' }}>

      {/* Top bar */}
      <div style={{ background: '#1a237e', height: '6px', width: '100%' }} />

      {/* Main content */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '40px', padding: '40px' }}>

        {/* Logo with animation */}
        <div style={{
          opacity: visible ? 1 : 0,
          transform: visible ? 'scale(1)' : 'scale(0.8)',
          transition: 'all 0.8s cubic-bezier(0.34, 1.56, 0.64, 1)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '24px'
        }}>
          <div style={{
            background: '#ffffff',
            borderRadius: '20px',
            padding: '24px',
            boxShadow: '0 8px 40px rgba(26,35,126,0.15)',
            border: '1.5px solid #e8eaf6'
          }}>
            <img src="/rnslogo.webp" alt="RNSIT Logo" style={{ height: '120px', objectFit: 'contain', display: 'block' }} />
          </div>

          {/* College name */}
          <div style={{ textAlign: 'center' }}>
            <div style={{
              fontSize: '32px', fontWeight: '800', color: '#1a237e',
              letterSpacing: '0.5px', lineHeight: '1.2',
              opacity: visible ? 1 : 0,
              transform: visible ? 'translateY(0)' : 'translateY(20px)',
              transition: 'all 0.8s ease 0.3s'
            }}>
              RNS Institute of Technology
            </div>
            <div style={{
              fontSize: '15px', color: '#555', marginTop: '6px',
              letterSpacing: '2px', textTransform: 'uppercase',
              opacity: visible ? 1 : 0,
              transition: 'all 0.8s ease 0.5s'
            }}>
              Autonomous Institution
            </div>
            <div style={{
              width: '60px', height: '3px',
              background: 'linear-gradient(90deg, #1a237e, #42a5f5)',
              borderRadius: '2px', margin: '12px auto 0',
              opacity: visible ? 1 : 0,
              transition: 'all 0.8s ease 0.6s'
            }} />
          </div>
        </div>

        {/* Kiosk card */}
        <div style={{
          background: '#f8f9ff',
          border: '1.5px solid #e8eaf6',
          borderRadius: '16px',
          padding: '32px 48px',
          textAlign: 'center',
          boxShadow: '0 4px 20px rgba(26,35,126,0.08)',
          opacity: visible ? 1 : 0,
          transform: visible ? 'translateY(0)' : 'translateY(30px)',
          transition: 'all 0.8s ease 0.7s',
          maxWidth: '480px'
        }}>
          <div style={{ fontSize: '40px', marginBottom: '16px' }}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#1a237e" strokeWidth="1.5">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
          </div>
          <div style={{ fontSize: '18px', fontWeight: '700', color: '#1a237e', marginBottom: '8px' }}>
            Digital Receptionist
          </div>
          <div style={{ fontSize: '14px', color: '#666', lineHeight: '1.6' }}>
            Please stand in front of the camera.<br/>
            The system will detect and greet you automatically.
          </div>

          {/* Animated dots */}
          <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', marginTop: '20px' }}>
            {[0,1,2].map(i => (
              <div key={i} style={{
                width: '8px', height: '8px', borderRadius: '50%',
                background: '#1a237e',
                animation: 'bounce 1.4s infinite ease-in-out',
                animationDelay: i * 0.2 + 's'
              }} />
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div style={{ background: '#1a237e', color: '#fff', padding: '12px 32px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '12px', opacity: 0.8 }}>RNSIT Digital Receptionist System</span>
        <span style={{ fontSize: '12px', opacity: 0.8 }}>Bengaluru — 560098</span>
      </div>

      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
          40% { transform: scale(1); opacity: 1; }
        }
      `}</style>
    </div>
  );
}