import React, { useEffect, useState } from 'react';

export default function GoodbyeScreen({ session }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setTimeout(() => setVisible(true), 100);
  }, []);

  return (
    <div style={{ minHeight: '100vh', background: '#ffffff', fontFamily: "'Segoe UI', Arial, sans-serif", display: 'flex', flexDirection: 'column' }}>

      <div style={{ background: '#1a237e', height: '6px', width: '100%' }} />

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '32px', padding: '40px' }}>

        <img src="/rnslogo.webp" alt="RNSIT Logo" style={{
          height: '80px', objectFit: 'contain',
          opacity: visible ? 1 : 0,
          transition: 'all 0.6s ease'
        }} />

        <div style={{
          background: '#f8f9ff',
          border: '1.5px solid #e8eaf6',
          borderRadius: '20px',
          padding: '48px',
          textAlign: 'center',
          boxShadow: '0 4px 24px rgba(26,35,126,0.10)',
          maxWidth: '480px',
          opacity: visible ? 1 : 0,
          transform: visible ? 'translateY(0)' : 'translateY(20px)',
          transition: 'all 0.7s ease 0.2s'
        }}>
          <div style={{ fontSize: '56px', marginBottom: '16px' }}>👋</div>
          <div style={{ fontSize: '26px', fontWeight: '800', color: '#1a237e', marginBottom: '8px' }}>
            Thank you for visiting!
          </div>
          {session?.user_name && session.user_name !== 'Guest' && (
            <div style={{ fontSize: '16px', color: '#555', marginBottom: '8px' }}>
              Goodbye, <strong>{session.user_name}</strong>. Have a great day!
            </div>
          )}
          <div style={{ fontSize: '14px', color: '#888', marginTop: '12px' }}>
            Your session has ended. The kiosk will return to standby shortly.
          </div>
          <div style={{ width: '50px', height: '3px', background: 'linear-gradient(90deg, #1a237e, #42a5f5)', borderRadius: '2px', margin: '20px auto 0' }} />
        </div>
      </div>

      <div style={{ background: '#1a237e', color: '#fff', padding: '12px 32px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '12px', opacity: 0.8 }}>RNSIT Digital Receptionist System</span>
        <span style={{ fontSize: '12px', opacity: 0.8 }}>Bengaluru — 560098</span>
      </div>
    </div>
  );
}