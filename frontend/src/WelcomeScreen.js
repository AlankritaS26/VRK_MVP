import React, { useEffect, useRef, useState, useCallback } from 'react';

const BACKEND = process.env.REACT_APP_BACKEND_URL || 'http://127.0.0.1:8000';

export default function WelcomeScreen({ session, messages, setMessages, askingName }) {
  const scrollRef     = useRef(null);
  const inputRef      = useRef(null);
  const isMounted     = useRef(true);
  const isSpeaking    = useRef(false);
  const isListening   = useRef(false);
  const lastTranscript = useRef('');

  const [name,       setName]       = useState('');
  const [saveData,   setSaveData]   = useState(true);
  const [submitted,  setSubmitted]  = useState(false);
  const [deleteMode, setDeleteMode] = useState(false);
  const [deleteName, setDeleteName] = useState('');
  const [deleted,    setDeleted]    = useState(false);
  const [liveText,   setLiveText]   = useState('');
  const [listening,  setListening]  = useState(false);

  const visitorName = session?.user_name || 'Guest';
  const isReturning = session?.is_returning || false;
  const visitCount  = session?.visit_count  || 1;

  const greeting = isReturning
    ? visitCount > 2
      ? 'Great to see you again, ' + visitorName + '!'
      : 'Hey ' + visitorName + '! Welcome back!'
    : 'Hello, ' + visitorName + '! Welcome to RNS Institute!';

  useEffect(() => {
    if (scrollRef.current)
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  useEffect(() => {
    isMounted.current = true;
    return () => { isMounted.current = false; };
  }, []);

  useEffect(() => {
    if (askingName) {
      setSubmitted(false); setName(''); setSaveData(true);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [askingName]);

  const addMessage = useCallback((text, speaker) => {
    setMessages(prev => [...prev, {
      text,
      speaker,
      timestamp: new Date().toLocaleTimeString()
    }]);
  }, [setMessages]);

  const startListening = useCallback(() => {
    if (!isMounted.current) return;
    if (isListening.current) return;
    if (isSpeaking.current) return;

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;

    const recog           = new SR();
    recog.lang            = 'en-US';
    recog.continuous      = false;
    recog.interimResults  = true;
    recog.onsoundstart = () => { if (isMounted.current) setListening(true); };
    recog.maxAlternatives = 1;

    recog.onstart = () => {
      isListening.current = true;
      lastTranscript.current = '';
      if (isMounted.current) { setListening(true); setLiveText(''); }
    };

    recog.onresult = (e) => {
      let interim = '';
      let final   = '';
      for (let i = 0; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) final += t;
        else interim += t;
      }
      const display = final || interim;
      lastTranscript.current = display;
      if (isMounted.current) setLiveText(display);
    };

    recog.onerror = (e) => {
      isListening.current = false;
      if (isMounted.current) { setListening(false); }
      if (e.error !== 'no-speech' && e.error !== 'aborted') {
        console.error('[STT]', e.error);
      }
      if (!isSpeaking.current && isMounted.current) {
        setTimeout(startListening, 400);
      }
    };

    recog.onend = () => {
      isListening.current = false;
      if (isMounted.current) setListening(false);
      const heard = lastTranscript.current.trim();
      if (heard && !isSpeaking.current) {
        sendToBackend(heard);
      } else if (!isSpeaking.current && isMounted.current) {
        setTimeout(startListening, 400);
      }
    };

    try { recog.start(); } catch(e) { console.error(e); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sendToBackend = useCallback(async (text) => {
    if (!text) return;
    lastTranscript.current = '';
    setLiveText('');
    const sid = session?.session_id || 'guest';
    addMessage(text, 'user');
    try {
      const [, askRes] = await Promise.all([
        fetch(BACKEND + '/message', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sid, text, speaker: 'user' })
        }),
        fetch(BACKEND + '/ask?question=' + encodeURIComponent(text))
      ]);
      const data   = await askRes.json();
      const answer = data.answer || 'Sorry, I do not have that information.';
      addMessage(answer, 'kiosk');
      fetch(BACKEND + '/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sid, text: answer, speaker: 'kiosk' })
      });
      speak(answer);
    } catch(e) {
      console.error('[sendToBackend]', e);
      isSpeaking.current = false;
      if (isMounted.current) startListening();
    }
  }, [session, addMessage]);

  const speak = useCallback((text) => {
    window.speechSynthesis.cancel();
    isSpeaking.current = true;
    const utter  = new SpeechSynthesisUtterance(text);
    utter.lang   = 'en-US';
    utter.rate   = 1.1;
    utter.volume = 1;
    utter.onend = () => {
      isSpeaking.current = false;
      if (isMounted.current) startListening();
    };
    utter.onerror = () => {
      isSpeaking.current = false;
      if (isMounted.current) startListening();
    };
    window.speechSynthesis.speak(utter);
  }, [startListening]);

  useEffect(() => {
    if (askingName) return;
    const t = setTimeout(startListening, 400);
    return () => clearTimeout(t);
  }, [askingName, startListening]);

  const handleSubmitName = async (overrideName, overrideSave) => {
    const finalName = (overrideName ?? name).trim() || 'Guest';
    const finalSave = overrideSave ?? saveData;
    setSubmitted(true);
    try {
      await fetch(BACKEND + '/visitor/submit_name?name=' + encodeURIComponent(finalName) + '&save=' + finalSave, { method: 'POST' });
    } catch(e) { console.error(e); }
  };

  const handleDeleteData = async () => {
    const trimmed = deleteName.trim();
    if (!trimmed) return;
    try {
      await fetch(BACKEND + '/visitor/delete_my_data?name=' + encodeURIComponent(trimmed), { method: 'POST' });
      setDeleted(true);
      setTimeout(() => { setDeleteMode(false); setDeleted(false); setDeleteName(''); }, 3500);
    } catch(e) { console.error(e); }
  };

  return (
    <div className="welcome-screen">
      <div className="welcome-bg" />
      <div className="grid-overlay" />
      <header className="welcome-header">
        <div className="header-logo-row">
          <svg className="header-rns" viewBox="0 0 200 60" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="hGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#00e5ff" />
                <stop offset="100%" stopColor="#2979ff" />
              </linearGradient>
            </defs>
            <text x="2" y="55" fontFamily="Arial Black,sans-serif"
              fontSize="58" fontWeight="900" fill="url(#hGrad)" letterSpacing="-1">RNS</text>
          </svg>
          <div className="header-titles">
            <div className="header-main">Digital Receptionist</div>
            <div className="header-sub">RNS Institute of Technology</div>
          </div>
        </div>
        {!askingName && (
          <div className="greeting-banner">
            <span className="greeting-text">{greeting}</span>
          </div>
        )}
        <div className="header-bottom">
          <div className="session-pill">
            <span className="session-dot" />
            <span>Session Active</span>
            <span className="session-id">{session?.session_id || 'pending...'}</span>
          </div>
          <button className="privacy-btn" onClick={() => setDeleteMode(d => !d)}>Delete My Data</button>
        </div>
      </header>

      {deleteMode && (
        <div className="modal-overlay" onClick={e => e.target === e.currentTarget && setDeleteMode(false)}>
          <div className="modal-card">
            {deleted ? (
              <div className="modal-success">
                <div className="modal-title">Data Deleted</div>
                <p className="modal-sub">Your face data has been permanently removed.</p>
              </div>
            ) : (
              <>
                <div className="modal-title">Delete My Data</div>
                <p className="modal-sub">Enter your name to permanently remove your face data.</p>
                <input className="modal-input" placeholder="Enter your name" value={deleteName}
                  onChange={e => setDeleteName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleDeleteData()} autoFocus />
                <div className="modal-buttons">
                  <button className="btn-secondary" onClick={() => setDeleteMode(false)}>Cancel</button>
                  <button className="btn-danger" onClick={handleDeleteData}>Delete Permanently</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {askingName && !deleteMode && (
        <div className="modal-overlay">
          <div className="modal-card">
            {submitted ? (
              <div className="modal-success">
                <div className="modal-title">{saveData ? 'Nice to meet you, ' + (name || 'Guest') + '!' : 'Welcome, Guest!'}</div>
                <p className="modal-sub">{saveData ? 'Your face has been saved. I will recognize you next time!' : 'No data saved. Enjoy your visit!'}</p>
              </div>
            ) : (
              <>
                <div className="modal-title">Hello! I do not think we have met.</div>
                <p className="modal-sub">What is your name?</p>
                <input ref={inputRef} className="modal-input" placeholder="Type your name"
                  value={name} onChange={e => setName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSubmitName()} autoFocus />
                <label className="privacy-toggle">
                  <div className={'toggle-track ' + (saveData ? 'on' : 'off')} onClick={() => setSaveData(s => !s)}>
                    <div className="toggle-thumb" />
                  </div>
                  <span className="toggle-label">{saveData ? 'Remember me for next time' : 'Do not save my info'}</span>
                </label>
                {!saveData && <p className="privacy-note">You will be greeted as a Guest. No face data will be stored.</p>}
                <div className="modal-buttons">
                  <button className="btn-secondary" onClick={() => handleSubmitName('Guest', false)}>Skip</button>
                  <button className="btn-primary" onClick={() => handleSubmitName()}>{saveData ? 'Remember Me' : 'Continue as Guest'}</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      <div className="chat-area" ref={scrollRef}>
        {messages.length === 0 && !liveText ? (
          <div className="chat-empty">
            <div className="listen-bars">
              {[1,2,3,4,5].map(i => <div key={i} className={'bar bar' + i} />)}
            </div>
            <p>{listening ? 'Listening...' : 'Starting microphone...'}</p>
          </div>
        ) : (
          <>
            {messages.map((msg, i) => (
              <div key={i} className={'bubble ' + (msg.speaker === 'kiosk' ? 'bubble-kiosk' : 'bubble-user')}>
                <div className="bubble-speaker">{msg.speaker === 'kiosk' ? 'Kiosk' : visitorName}</div>
                <div className="bubble-text">{msg.text}</div>
                <div className="bubble-time">{msg.timestamp}</div>
              </div>
            ))}
            {liveText && (
              <div className="bubble bubble-user" style={{ opacity: 0.6, fontStyle: 'italic' }}>
                <div className="bubble-speaker">{visitorName} (speaking...)</div>
                <div className="bubble-text">{liveText}</div>
              </div>
            )}
          </>
        )}
      </div>

      <footer className="welcome-footer">
        <span className="footer-hint">{listening ? 'Listening...' : 'Mic ready...'}</span>
        <div className="footer-bars">
          {[1,2,3,4,5].map(i => <div key={i} className={'bar bar' + i} />)}
        </div>
      </footer>
    </div>
  );
}