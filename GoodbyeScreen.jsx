import React from 'react';

export default function GoodbyeScreen({ session }) {
  const visitorName = session?.user_name || 'Guest';
  const visitCount = session?.visit_count || 1;

  return (
    <div className="goodbye-screen">
      <div className="idle-bg" />
      <div className="grid-overlay" />
      <div className="goodbye-center">
        <svg className="goodbye-logo" viewBox="0 0 240 80" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="goodbye-logo-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#00e5ff" />
              <stop offset="50%" stopColor="#2979ff" />
              <stop offset="100%" stopColor="#00b0ff" />
            </linearGradient>
          </defs>
          <text x="4" y="72" fontFamily="'Black Han Sans', 'Arial Black', sans-serif" fontSize="78" fontWeight="900" fill="url(#goodbye-logo-gradient)">RNS</text>
        </svg>
        <div className="goodbye-wave">👋</div>
        <div className="goodbye-title">Goodbye, {visitorName}!</div>
        <div className="goodbye-sub">Thank you for visiting RNS Institute of Technology.</div>
        <div className="goodbye-pill">
          <span className="goodbye-pill-label">VISIT</span>
          <span className="goodbye-pill-visits">#{visitCount}</span>
        </div>
        <div className="goodbye-bar-track">
          <div className="goodbye-bar-fill" style={{ width: '100%' }} />
        </div>
        <div className="goodbye-returning">We look forward to seeing you again</div>
      </div>
    </div>
  );
}