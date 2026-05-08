import React, { useEffect, useState } from 'react';

export default function IdleScreen() {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const hh = time.getHours().toString().padStart(2,'0');
  const mm = time.getMinutes().toString().padStart(2,'0');
  const ss = time.getSeconds().toString().padStart(2,'0');
  const date = time.toLocaleDateString('en-IN', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
  });

  return (
    <div className="idle-screen">
      <div className="idle-bg" />
      <div className="grid-overlay" />

      {/* Pulse rings */}
      <div className="ring ring1" />
      <div className="ring ring2" />
      <div className="ring ring3" />

      {/* Central RNS logo */}
      <div className="idle-center">
        <div className="logo-glow">
          <svg className="rns-logo" viewBox="0 0 240 80" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="logoGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%"   stopColor="#00e5ff" />
                <stop offset="50%"  stopColor="#2979ff" />
                <stop offset="100%" stopColor="#00b0ff" />
              </linearGradient>
              <filter id="glow">
                <feGaussianBlur stdDeviation="3" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>
            <text
              x="4" y="72"
              fontFamily="'Black Han Sans', 'Arial Black', sans-serif"
              fontSize="78"
              fontWeight="900"
              fill="url(#logoGrad)"
              filter="url(#glow)"
              letterSpacing="-2"
            >RNS</text>
          </svg>
        </div>

        <div className="idle-tagline">Institute of Technology</div>
        <div className="idle-subtitle">Digital Receptionist</div>

        {/* Listening bars */}
        <div className="idle-bars">
          {[1,2,3,4,5,6,7].map(i => (
            <div key={i} className={`ibar ibar${i}`} />
          ))}
        </div>

        <div className="idle-hint">Step closer to begin</div>
      </div>

      {/* Clock */}
      <div className="idle-clock">
        <div className="clock-time">{hh}:{mm}<span className="clock-sec">:{ss}</span></div>
        <div className="clock-date">{date}</div>
      </div>

      {/* Corner brand */}
      <div className="corner-brand">
        <div className="corner-dot" />
        <span>System Active</span>
      </div>
    </div>
  );
}