import React, { useEffect, useState, useRef } from 'react';
import IdleScreen from './IdleScreen';
import WelcomeScreen from './WelcomeScreen';
import GoodbyeScreen from './GoodbyeScreen';
import './index.css';

const WS_URL = (process.env.REACT_APP_BACKEND_URL || 'http://127.0.0.1:8000')
                .replace(/^http/, 'ws') + '/ws';

export default function App() {
  const [screen,      setScreen]      = useState('idle');
  const [session,     setSession]     = useState(null);
  const [lastSession, setLastSession] = useState(null);
  const [messages,    setMessages]    = useState([]);
  const wsRef        = useRef(null);
  const goodbyeTimer = useRef(null);

  useEffect(() => {
    function connect() {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onmessage = (e) => {
        const data = JSON.parse(e.data);

        if (data.type === 'session_start' || data.type === 'session_update') {
          clearTimeout(goodbyeTimer.current);
          setSession(data.session);
          setScreen('welcome');
        }

        if (data.type === 'ask_name') {
          clearTimeout(goodbyeTimer.current);
          setSession(prev => ({ ...(prev || {}), asking_name: true }));
          setScreen('welcome');
        }

        if (data.type === 'session_end') {
          setSession(current => { setLastSession(current); return null; });
          setScreen('goodbye');
          goodbyeTimer.current = setTimeout(() => {
            setScreen('idle');
            setMessages([]);
            setLastSession(null);
          }, 4000);
        }

        if (data.type === 'message') {
          setMessages(prev => [...prev, data.message]);
        }
      };

      ws.onclose = () => setTimeout(connect, 2000);
    }
    connect();
    return () => { wsRef.current?.close(); clearTimeout(goodbyeTimer.current); };
  }, []);

  const askingName = session?.asking_name === true;

  if (screen === 'welcome')
    return <WelcomeScreen session={session} messages={messages} askingName={askingName} />;
  if (screen === 'goodbye')
    return <GoodbyeScreen session={lastSession} />;
  return <IdleScreen />;
}