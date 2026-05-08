import React, { useEffect, useState } from 'react';

export default function GoodbyeScreen({ session }) {
  const [show, setShow] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setShow(false), 5000);
    return () => clearTimeout(timer);
  }, []);

  if (!show) return null;

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100vh',
      backgroundColor: '#1a1a2e',
      color: '#eee',
      fontFamily: 'sans-serif'
    }}>
      <h1 style={{ fontSize: '3rem' }}>Goodbye! 👋</h1>
      {session?.name && (
        <p style={{ fontSize: '1.5rem', color: '#a0c4ff' }}>
          See you next time, {session.name}!
        </p>
      )}
      <p style={{ color: '#888', marginTop: '1rem' }}>
        Face no longer detected. Session ended.
      </p>
    </div>
  );
}