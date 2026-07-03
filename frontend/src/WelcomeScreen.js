import React, { useEffect, useRef, useState, useCallback } from 'react';

const BACKEND = process.env.REACT_APP_BACKEND_URL || 'http://127.0.0.1:8000';

export default function WelcomeScreen({ session, messages, setMessages, askingName }) {
  const scrollRef      = useRef(null);
  const inputRef       = useRef(null);
  const isMounted      = useRef(true);
  const isSpeaking     = useRef(false);
  const isListening    = useRef(false);
  const analyserRef    = useRef(null);
  const animFrameRef   = useRef(null);
  const canvasRef      = useRef(null);
  const audioCtxRef    = useRef(null);

  const [name,       setName]       = useState('');
  const [saveData,   setSaveData]   = useState(true);
  const [submitted,  setSubmitted]  = useState(false);
  const [deleteMode, setDeleteMode] = useState(false);
  const [deleteName, setDeleteName] = useState('');
  const [deleted,    setDeleted]    = useState(false);
  const [liveText,   setLiveText]   = useState('');
  const [listening,  setListening]  = useState(false);
  const [status,     setStatus]     = useState('ready');

  const visitorName = session?.user_name    || 'Guest';
  const isReturning = session?.is_returning || false;
  const visitCount  = session?.visit_count  || 1;

  const greeting = isReturning
    ? visitCount > 2
      ? 'Welcome back, ' + visitorName + '! Great to see you again.'
      : 'Welcome back, ' + visitorName + '!'
    : 'Welcome, ' + visitorName + '! How may I assist you today?';

  useEffect(() => {
    if (scrollRef.current)
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, liveText]);

  useEffect(() => {
    isMounted.current = true;
    return () => { isMounted.current = false; stopWaveform(); };
  }, []);

  useEffect(() => {
    if (askingName) {
      setSubmitted(false); setName(''); setSaveData(true);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [askingName]);

  const addMessage = useCallback((text, speaker) => {
    setMessages(prev => [...prev, {
      text, speaker,
      timestamp: new Date().toLocaleTimeString()
    }]);
  }, [setMessages]);

  // ── WAVEFORM ─────────────────────────────────────────────────────────────
  const stopWaveform = useCallback(() => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (audioCtxRef.current) {
      try { audioCtxRef.current.close(); } catch(e) {}
      audioCtxRef.current = null;
    }
    analyserRef.current = null;
    const canvas = canvasRef.current;
    if (canvas) {
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
  }, []);

  const startWaveform = useCallback((stream) => {
    const audioCtx = new AudioContext();
    audioCtxRef.current = audioCtx;
    const source = audioCtx.createMediaStreamSource(stream);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    analyserRef.current = analyser;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    const draw = () => {
      animFrameRef.current = requestAnimationFrame(draw);
      analyser.getByteFrequencyData(dataArray);
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const barWidth = 3;
      const gap = 2;
      const bars = Math.floor(canvas.width / (barWidth + gap));
      const step = Math.floor(dataArray.length / bars);

      for (let i = 0; i < bars; i++) {
        const value = dataArray[i * step] / 255;
        const barHeight = Math.max(4, value * canvas.height * 0.9);
        const x = i * (barWidth + gap);
        const y = (canvas.height - barHeight) / 2;
        const gradient = ctx.createLinearGradient(0, y, 0, y + barHeight);
        gradient.addColorStop(0, `rgba(100, 200, 255, ${0.4 + value * 0.6})`);
        gradient.addColorStop(1, `rgba(26, 35, 126, ${0.4 + value * 0.6})`);
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.roundRect(x, y, barWidth, barHeight, 2);
        ctx.fill();
      }
    };
    draw();
  }, []);

  // ── STT via POST /stt ─────────────────────────────────────────────────────
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const startListening = useCallback(() => {
    if (!isMounted.current) return;
    if (isListening.current) return;
    if (isSpeaking.current) return;
    if (askingName) return;

    isListening.current = true;
    setListening(true);
    setLiveText('');
    setStatus('listening');

    navigator.mediaDevices.getUserMedia({
      audio: {
        noiseSuppression: true,
        echoCancellation: true,
        autoGainControl: true,
        sampleRate: 16000
      }
    }).then(stream => {
      startWaveform(stream);

      const audioChunks = [];
      const mediaRecorder = new MediaRecorder(stream);

      // Silence detection
      const silenceCtx = new AudioContext();
      const silenceSource = silenceCtx.createMediaStreamSource(stream);
      const silenceAnalyser = silenceCtx.createAnalyser();
      silenceAnalyser.fftSize = 512;
      silenceSource.connect(silenceAnalyser);
      const silenceData = new Uint8Array(silenceAnalyser.frequencyBinCount);

      let silenceStart = null;
      let hasSpeech = false;
      let stopped = false;
      const SILENCE_THRESHOLD = 20;
      const SILENCE_DURATION = 1200;
      const MAX_DURATION = 8000;
      const speechStart = Date.now();

      const stopRecording = () => {
        if (stopped) return;
        stopped = true;
        clearInterval(silenceChecker);
        try { silenceCtx.close(); } catch(e) {}
        if (mediaRecorder.state !== 'inactive') mediaRecorder.stop();
      };

      const silenceChecker = setInterval(() => {
        silenceAnalyser.getByteFrequencyData(silenceData);
        const avg = silenceData.reduce((a, b) => a + b, 0) / silenceData.length;

        if (avg > SILENCE_THRESHOLD) {
          hasSpeech = true;
          silenceStart = null;
        } else if (hasSpeech) {
          if (!silenceStart) silenceStart = Date.now();
          if (Date.now() - silenceStart > SILENCE_DURATION) stopRecording();
        }

        if (Date.now() - speechStart > MAX_DURATION) stopRecording();
      }, 100);

      mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) audioChunks.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        stopWaveform();
        isListening.current = false;
        if (isMounted.current) setListening(false);

        if (!hasSpeech || audioChunks.length === 0) {
          setStatus('ready');
          if (!isSpeaking.current && isMounted.current) setTimeout(startListening, 400);
          return;
        }

        setStatus('processing');
        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        const arrayBuffer = await audioBlob.arrayBuffer();

        try {
          const response = await fetch(BACKEND + '/stt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/octet-stream' },
            body: new Uint8Array(arrayBuffer)
          });

          const result = await response.json();
          console.log('[STT WHISPER]', result);
          const heard = (result.text || '').trim();

          if (heard && heard.length > 1 && !isSpeaking.current) {
            if (isMounted.current) setLiveText(heard);
            sendToBackend(heard);
          } else {
            setStatus('ready');
            if (!isSpeaking.current && isMounted.current) setTimeout(startListening, 400);
          }
        } catch (err) {
          console.error('[STT] Error:', err);
          setStatus('ready');
          if (!isSpeaking.current && isMounted.current) setTimeout(startListening, 400);
        }
      };

      mediaRecorder.start(100);

    }).catch(err => {
      console.error('[MIC] Error:', err);
      isListening.current = false;
      setListening(false);
      setStatus('ready');
    });
  }, [askingName, startWaveform, stopWaveform]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const sendToBackend = useCallback(async (text) => {
    if (!text) return;
    setLiveText('');
    const sid = session?.session_id || 'guest';
    addMessage(text, 'user');

    const goodbyeWords = ['thank you', 'thanks', 'bye', 'goodbye', 'see you', 'ok bye', 'thank you so much'];
    if (goodbyeWords.some(w => text.toLowerCase().includes(w))) {
      addMessage('You are most welcome! Have a wonderful day. Goodbye!', 'kiosk');
      speak('You are most welcome! Have a wonderful day. Goodbye!');
      try { await fetch(BACKEND + '/session/end?session_id=' + sid, { method: 'POST' }); } catch(e) {}
      return;
    }

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
      const answer = data.answer || 'Sorry, I do not have that information. Please visit the Admin Block.';
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
      setStatus('ready');
      if (isMounted.current) startListening();
    }
  }, [session, addMessage]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const speak = useCallback((text) => {
    window.speechSynthesis.cancel();
    isSpeaking.current = true;
    setStatus('speaking');
    const utter  = new SpeechSynthesisUtterance(text);
    utter.lang   = 'en-US';
    utter.rate   = 1.0;
    utter.volume = 1;
    utter.onend = () => {
      isSpeaking.current = false;
      setStatus('ready');
      if (isMounted.current) startListening();
    };
    utter.onerror = () => {
      isSpeaking.current = false;
      setStatus('ready');
      if (isMounted.current) startListening();
    };
    window.speechSynthesis.speak(utter);
  }, [startListening]);

  useEffect(() => {
    if (askingName) return;
    const t = setTimeout(startListening, 500);
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

  const statusLabel = {
    ready:      'Microphone ready',
    listening:  'Listening — speak your question',
    processing: 'Processing...',
    speaking:   'Speaking...'
  }[status] || 'Ready';

  const statusColor = {
    ready:      '#ffb300',
    listening:  '#43a047',
    processing: '#7e57c2',
    speaking:   '#ef5350'
  }[status] || '#ffb300';

  const inputStyle = {
    width: '100%', padding: '12px 16px', border: '1.5px solid #c5cae9',
    borderRadius: '8px', fontSize: '15px', boxSizing: 'border-box',
    outline: 'none', color: '#1a237e', background: '#f8f9ff', transition: 'border 0.2s'
  };
  const btnPrimary = {
    padding: '11px 24px', border: 'none', borderRadius: '8px',
    background: '#1a237e', color: '#fff', cursor: 'pointer',
    fontSize: '14px', fontWeight: '600', letterSpacing: '0.3px'
  };
  const btnSecondary = {
    padding: '11px 24px', border: '1.5px solid #c5cae9', borderRadius: '8px',
    background: '#fff', color: '#555', cursor: 'pointer', fontSize: '14px'
  };

  return (
    <div style={{ minHeight: '100vh', background: '#f5f6fa', fontFamily: "'Segoe UI', Arial, sans-serif", display: 'flex', flexDirection: 'column' }}>

      <header style={{ background: '#ffffff', borderBottom: '2px solid #e8eaf6', padding: '14px 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxShadow: '0 2px 10px rgba(26,35,126,0.07)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <img src="/rnslogo.webp" alt="RNSIT" style={{ height: '56px', objectFit: 'contain' }} />
          <div>
            <div style={{ fontSize: '18px', fontWeight: '800', color: '#1a237e', letterSpacing: '0.3px' }}>RNS Institute of Technology</div>
            <div style={{ fontSize: '12px', color: '#888', marginTop: '2px', letterSpacing: '0.5px' }}>DIGITAL RECEPTIONIST — INTERACTIVE KIOSK</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', justifyContent: 'flex-end' }}>
              <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#43a047' }} />
              <span style={{ fontSize: '12px', color: '#43a047', fontWeight: '600' }}>Session Active</span>
            </div>
            <div style={{ fontSize: '11px', color: '#bbb', fontFamily: 'monospace', marginTop: '2px' }}>{(session?.session_id || '').slice(0,20)}...</div>
          </div>
          <button onClick={() => setDeleteMode(d => !d)} style={{ background: '#fff5f5', border: '1.5px solid #ef9a9a', color: '#c62828', borderRadius: '8px', padding: '9px 18px', fontSize: '13px', cursor: 'pointer', fontWeight: '600' }}>
            Delete My Data
          </button>
        </div>
      </header>

      {!askingName && (
        <div style={{ background: 'linear-gradient(90deg, #1a237e, #283593)', color: '#fff', padding: '11px 32px', fontSize: '14px', fontWeight: '500', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#90caf9" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/></svg>
          {greeting}
        </div>
      )}

      {deleteMode && (
        <div onClick={e => e.target === e.currentTarget && setDeleteMode(false)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ background: '#fff', borderRadius: '16px', padding: '40px', width: '420px', boxShadow: '0 12px 48px rgba(0,0,0,0.18)' }}>
            {deleted ? (
              <div style={{ textAlign: 'center' }}>
                <div style={{ width: '64px', height: '64px', borderRadius: '50%', background: '#e8f5e9', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#43a047" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                </div>
                <div style={{ fontSize: '20px', fontWeight: '700', color: '#1a237e' }}>Data Deleted Successfully</div>
                <p style={{ color: '#666', marginTop: '8px', fontSize: '14px' }}>Your face data has been permanently removed from the system.</p>
              </div>
            ) : (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                  <div style={{ width: '44px', height: '44px', borderRadius: '50%', background: '#ffebee', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#c62828" strokeWidth="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
                  </div>
                  <div>
                    <div style={{ fontSize: '17px', fontWeight: '700', color: '#c62828' }}>Delete My Data</div>
                    <div style={{ fontSize: '12px', color: '#999' }}>This action cannot be undone</div>
                  </div>
                </div>
                <p style={{ color: '#666', marginBottom: '16px', fontSize: '14px', lineHeight: '1.6' }}>Enter your registered name to permanently remove your face data from the system.</p>
                <input style={inputStyle} placeholder="Enter your registered name"
                  value={deleteName} onChange={e => setDeleteName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleDeleteData()} autoFocus />
                <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '20px' }}>
                  <button onClick={() => setDeleteMode(false)} style={btnSecondary}>Cancel</button>
                  <button onClick={handleDeleteData} style={{ ...btnPrimary, background: '#c62828' }}>Delete Permanently</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {askingName && !deleteMode && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ background: '#fff', borderRadius: '16px', padding: '40px', width: '440px', boxShadow: '0 12px 48px rgba(0,0,0,0.18)' }}>
            {submitted ? (
              <div style={{ textAlign: 'center' }}>
                <div style={{ width: '64px', height: '64px', borderRadius: '50%', background: '#e8eaf6', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#1a237e" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                </div>
                <div style={{ fontSize: '20px', fontWeight: '700', color: '#1a237e' }}>
                  {saveData ? 'Welcome, ' + (name || 'Guest') + '!' : 'Welcome, Guest!'}
                </div>
                <p style={{ color: '#666', marginTop: '10px', fontSize: '14px', lineHeight: '1.6' }}>
                  {saveData ? 'Your face has been registered. We will recognize you on your next visit.' : 'You are visiting as a guest. No data has been saved.'}
                </p>
              </div>
            ) : (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
                  <div style={{ width: '44px', height: '44px', borderRadius: '50%', background: '#e8eaf6', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#1a237e" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                  </div>
                  <div>
                    <div style={{ fontSize: '18px', fontWeight: '700', color: '#1a237e' }}>Hello! Welcome to RNSIT</div>
                    <div style={{ fontSize: '13px', color: '#888' }}>We do not recognize you yet</div>
                  </div>
                </div>
                <div style={{ marginBottom: '16px' }}>
                  <label style={{ fontSize: '13px', fontWeight: '600', color: '#444', display: 'block', marginBottom: '6px' }}>Your Full Name</label>
                  <input ref={inputRef} style={inputStyle} placeholder="e.g. Akshatha A"
                    value={name} onChange={e => setName(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleSubmitName()} autoFocus />
                </div>
                <div style={{ background: '#f8f9ff', border: '1.5px solid #e8eaf6', borderRadius: '10px', padding: '14px 16px', marginBottom: '20px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: '600', color: '#333' }}>Remember me for next visit</div>
                      <div style={{ fontSize: '12px', color: '#999', marginTop: '2px' }}>{saveData ? 'Your face will be saved securely' : 'No data will be stored'}</div>
                    </div>
                    <div onClick={() => setSaveData(s => !s)} style={{ width: '48px', height: '26px', borderRadius: '13px', background: saveData ? '#1a237e' : '#ddd', cursor: 'pointer', position: 'relative', transition: 'background 0.25s', flexShrink: 0 }}>
                      <div style={{ position: 'absolute', top: '3px', left: saveData ? '25px' : '3px', width: '20px', height: '20px', borderRadius: '50%', background: '#fff', transition: 'left 0.25s', boxShadow: '0 1px 4px rgba(0,0,0,0.2)' }} />
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <button onClick={() => handleSubmitName('Guest', false)} style={{ ...btnSecondary, flex: 1 }}>Continue as Guest</button>
                  <button onClick={() => handleSubmitName()} style={{ ...btnPrimary, flex: 1 }}>{saveData ? 'Register & Continue' : 'Continue'}</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      <div ref={scrollRef} style={{ flex: '1 1 0', overflowY: 'auto', minHeight: 0, padding: '28px 32px', display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '900px', width: '100%', margin: '0 auto', alignSelf: 'stretch' }}>
        {messages.length === 0 && !liveText ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px', paddingTop: '40px' }}>
            <div style={{ width: '220px', height: '80px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {listening ? (
                <canvas ref={canvasRef} width={220} height={80}
                  style={{ borderRadius: '12px', background: 'rgba(26,35,126,0.04)' }} />
              ) : (
                <div style={{ width: '72px', height: '72px', borderRadius: '50%', background: '#e8eaf6', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#1a237e" strokeWidth="1.5">
                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                    <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                    <line x1="12" y1="19" x2="12" y2="23"/>
                    <line x1="8" y1="23" x2="16" y2="23"/>
                  </svg>
                </div>
              )}
            </div>
            <div style={{ fontSize: '17px', fontWeight: '700', color: '#1a237e' }}>
              {status === 'listening'   && 'Listening...'}
              {status === 'processing'  && 'Processing...'}
              {status === 'speaking'    && 'Speaking...'}
              {status === 'ready'       && 'Ready to assist you'}
            </div>
            <div style={{ fontSize: '14px', color: '#aaa', textAlign: 'center', maxWidth: '300px', lineHeight: '1.6' }}>
              {status === 'listening' ? 'Please speak your question clearly' : 'Ask me anything about RNSIT'}
            </div>
          </div>
        ) : (
          <>
            {listening && (
              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '4px' }}>
                <canvas ref={canvasRef} width={300} height={48}
                  style={{ borderRadius: '8px', background: 'rgba(26,35,126,0.04)' }} />
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: msg.speaker === 'kiosk' ? 'flex-start' : 'flex-end' }}>
                <div style={{ fontSize: '11px', color: '#bbb', marginBottom: '4px', paddingLeft: msg.speaker === 'kiosk' ? '4px' : 0, paddingRight: msg.speaker !== 'kiosk' ? '4px' : 0, fontWeight: '500' }}>
                  {msg.speaker === 'kiosk' ? 'RNSIT Kiosk' : visitorName} &nbsp;·&nbsp; {msg.timestamp}
                </div>
                <div style={{
                  maxWidth: '60%', padding: '14px 18px',
                  borderRadius: msg.speaker === 'kiosk' ? '4px 18px 18px 18px' : '18px 4px 18px 18px',
                  background: msg.speaker === 'kiosk' ? '#ffffff' : '#1a237e',
                  color: msg.speaker === 'kiosk' ? '#222' : '#ffffff',
                  border: msg.speaker === 'kiosk' ? '1.5px solid #e8eaf6' : 'none',
                  fontSize: '14px', lineHeight: '1.65',
                  boxShadow: msg.speaker === 'kiosk' ? '0 2px 8px rgba(0,0,0,0.06)' : '0 2px 8px rgba(26,35,126,0.18)'
                }}>
                  {msg.text}
                </div>
              </div>
            ))}
            {liveText && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                <div style={{ fontSize: '11px', color: '#bbb', marginBottom: '4px', paddingRight: '4px' }}>{visitorName} (speaking...)</div>
                <div style={{ maxWidth: '60%', padding: '14px 18px', borderRadius: '18px 4px 18px 18px', background: '#e8eaf6', color: '#1a237e', fontSize: '14px', fontStyle: 'italic', lineHeight: '1.65', border: '1.5px solid #c5cae9' }}>
                  {liveText}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      <footer style={{ background: '#ffffff', borderTop: '1.5px solid #e8eaf6', padding: '12px 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxShadow: '0 -2px 8px rgba(26,35,126,0.05)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: statusColor, transition: 'background 0.3s', animation: listening ? 'pulse 1.5s infinite' : 'none' }} />
          <span style={{ fontSize: '13px', color: '#555', fontWeight: '500' }}>{statusLabel}</span>
        </div>
        <div style={{ fontSize: '12px', color: '#bbb' }}>RNSIT Digital Receptionist &nbsp;·&nbsp; Bengaluru — 560098</div>
      </footer>

      <style>{`
        @keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.5;transform:scale(1.4)} }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        input:focus { border-color: #1a237e !important; box-shadow: 0 0 0 3px rgba(26,35,126,0.1); }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: #f5f6fa; }
        ::-webkit-scrollbar-thumb { background: #c5cae9; border-radius: 3px; }
      `}</style>
    </div>
  );
}