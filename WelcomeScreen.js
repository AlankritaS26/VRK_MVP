import React, { useEffect, useRef, useState } from 'react';

const BACKEND = process.env.REACT_APP_BACKEND_URL || 'http://127.0.0.1:8000';

export default function WelcomeScreen({ session, messages, askingName }) {
  const scrollRef   = useRef(null);
  const inputRef    = useRef(null);

  const [name,        setName]        = useState('');
  const [saveData,    setSaveData]    = useState(true);
  const [submitted,   setSubmitted]   = useState(false);
  const [deleteMode,  setDeleteMode]  = useState(false);
  const [deleteName,  setDeleteName]  = useState('');
  const [deleted,     setDeleted]     = useState(false);

  const visitorName  = session?.user_name    || 'Guest';
  const isReturning  = session?.is_returning || false;
  const visitCount   = session?.visit_count  || 1;

  const greeting = isReturning
    ? visitCount > 2
      ? `Great to see you again, ${visitorName}! 🌟`
      : `Hey ${visitorName}! Welcome back! 👋`
    : `Hello, ${visitorName}! Welcome to RNS Institute! 🎓`;

  // Auto-scroll chat
  useEffect(() => {
    if (scrollRef.current)
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  // Focus name input when ask form appears
  useEffect(() => {
    if (askingName) {
      setSubmitted(false);
      setName('');
      setSaveData(true);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [askingName]);

  // ── Submit name ────────────────────────────────────────────────────────────
  const handleSubmitName = async (overrideName, overrideSave) => {
    const finalName = (overrideName ?? name).trim() || 'Guest';
    const finalSave = overrideSave ?? saveData;
    setSubmitted(true);
    try {
      await fetch(
        `${BACKEND}/visitor/submit_name?name=${encodeURIComponent(finalName)}&save=${finalSave}`,
        { method: 'POST' }
      );
    } catch (e) { console.error(e); }
  };

  // ── Delete data ────────────────────────────────────────────────────────────
  const handleDeleteData = async () => {
    const trimmed = deleteName.trim();
    if (!trimmed) return;
    try {
      await fetch(
        `${BACKEND}/visitor/delete_my_data?name=${encodeURIComponent(trimmed)}`,
        { method: 'POST' }
      );
      setDeleted(true);
      setTimeout(() => { setDeleteMode(false); setDeleted(false); setDeleteName(''); }, 3500);
    } catch (e) { console.error(e); }
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="welcome-screen">
      <div className="welcome-bg" />
      <div className="grid-overlay" />

      {/* ── HEADER ──────────────────────────────────────────────────────── */}
      <header className="welcome-header">
        <div className="header-logo-row">
          <svg className="header-rns" viewBox="0 0 200 60" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="hGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%"   stopColor="#00e5ff" />
                <stop offset="100%" stopColor="#2979ff" />
              </linearGradient>
            </defs>
            <text x="2" y="55"
              fontFamily="'Black Han Sans','Arial Black',sans-serif"
              fontSize="58" fontWeight="900"
              fill="url(#hGrad)" letterSpacing="-1">RNS</text>
          </svg>
          <div className="header-titles">
            <div className="header-main">Digital Receptionist</div>
            <div className="header-sub">RNS Institute of Technology</div>
          </div>
        </div>

        {!askingName && (
          <div className="greeting-banner">
            <span className="greeting-wave">👋</span>
            <span className="greeting-text">{greeting}</span>
          </div>
        )}

        <div className="header-bottom">
          <div className="session-pill">
            <span className="session-dot" />
            <span>Session Active</span>
            <span className="session-id">
              {session?.session_id ? session.session_id : 'pending...'}
            </span>
          </div>
          <button className="privacy-btn" onClick={() => setDeleteMode(d => !d)}>
            🗑 Delete My Data
          </button>
        </div>
      </header>

      {/* ── DELETE DATA MODAL ────────────────────────────────────────────── */}
      {deleteMode && (
        <div className="modal-overlay" onClick={e => e.target === e.currentTarget && setDeleteMode(false)}>
          <div className="modal-card">
            {deleted ? (
              <div className="modal-success">
                <div className="modal-icon">✅</div>
                <div className="modal-title">Data Deleted</div>
                <p className="modal-sub">Your face data has been permanently removed.</p>
              </div>
            ) : (
              <>
                <div className="modal-icon">🗑️</div>
                <div className="modal-title">Delete My Data</div>
                <p className="modal-sub">
                  Enter your name to permanently remove your face data from our system.
                  You will no longer be recognized on future visits.
                </p>
                <input
                  className="modal-input"
                  placeholder="Enter your name…"
                  value={deleteName}
                  onChange={e => setDeleteName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleDeleteData()}
                  autoFocus
                />
                <div className="modal-buttons">
                  <button className="btn-secondary" onClick={() => setDeleteMode(false)}>Cancel</button>
                  <button className="btn-danger"    onClick={handleDeleteData}>Delete Permanently</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── ASK NAME MODAL (unknown visitor) ─────────────────────────────── */}
      {askingName && !deleteMode && (
        <div className="modal-overlay">
          <div className="modal-card">
            {submitted ? (
              <div className="modal-success">
                <div className="modal-icon">{saveData ? '✅' : '👤'}</div>
                <div className="modal-title">
                  {saveData ? `Nice to meet you, ${name || 'Guest'}!` : 'Welcome, Guest!'}
                </div>
                <p className="modal-sub">
                  {saveData
                    ? "I've saved your face. I'll recognize you next time! 😊"
                    : 'No data saved. Enjoy your visit!'}
                </p>
              </div>
            ) : (
              <>
                <div className="modal-icon">👋</div>
                <div className="modal-title">Hello! I don't think we've met.</div>
                <p className="modal-sub">What's your name?</p>

                <input
                  ref={inputRef}
                  className="modal-input"
                  placeholder="Type your name…"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSubmitName()}
                  autoFocus
                />

                <label className="privacy-toggle">
                  <div className={`toggle-track ${saveData ? 'on' : 'off'}`}
                       onClick={() => setSaveData(s => !s)}>
                    <div className="toggle-thumb" />
                  </div>
                  <span className="toggle-label">
                    {saveData ? '🔒 Remember me for next time' : '🚫 Don\'t save my info'}
                  </span>
                </label>

                {!saveData && (
                  <p className="privacy-note">
                    ℹ️ You'll be greeted as a Guest. No face data will be stored.
                  </p>
                )}

                <div className="modal-buttons">
                  <button className="btn-secondary"
                    onClick={() => handleSubmitName('Guest', false)}>
                    Skip
                  </button>
                  <button className="btn-primary" onClick={() => handleSubmitName()}>
                    {saveData ? 'Remember Me ✓' : 'Continue as Guest'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── CHAT AREA ────────────────────────────────────────────────────── */}
      <div className="chat-area" ref={scrollRef}>
        {messages.length === 0 ? (
          <div className="chat-empty">
            <div className="listen-bars">
              {[1,2,3,4,5].map(i => <div key={i} className={`bar bar${i}`} />)}
            </div>
            <p>Listening…</p>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div key={i} className={`bubble ${msg.speaker === 'kiosk' ? 'bubble-kiosk' : 'bubble-user'}`}>
              <div className="bubble-speaker">
                {msg.speaker === 'kiosk' ? '🤖 Kiosk' : `🧑 ${visitorName}`}
              </div>
              <div className="bubble-text">{msg.text}</div>
              <div className="bubble-time">{msg.timestamp}</div>
            </div>
          ))
        )}
      </div>

      {/* ── FOOTER ───────────────────────────────────────────────────────── */}
      <footer className="welcome-footer">
        <span className="footer-hint">Speak naturally — I'm listening</span>
        <div className="footer-bars">
          {[1,2,3,4,5].map(i => <div key={i} className={`bar bar${i}`} />)}
        </div>
      </footer>
    </div>
  );
}