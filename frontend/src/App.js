import React, { useEffect, useState, useRef } from 'react';
import IdleScreen from './IdleScreen';
import WelcomeScreen from './WelcomeScreen';
import GoodbyeScreen from './GoodbyeScreen';
import './index.css';

const BACKEND = process.env.REACT_APP_BACKEND_URL || 'http://127.0.0.1:8000';

export default function App() {
  const [screen,      setScreen]      = useState('idle');
  const [session,     setSession]     = useState(null);
  const [lastSession, setLastSession] = useState(null);
  const [messages,    setMessages]    = useState([]);
  const pollRef      = useRef(null);
  const goodbyeTimer = useRef(null);
  const prevActiveRef = useRef(false);

  useEffect(() => {
    async function poll() {
      try {
        const res  = await fetch(BACKEND + '/session/current');
        const data = await res.json();

        if (data && data.active) {
          if (!prevActiveRef.current) {
            setMessages([]);
            clearTimeout(goodbyeTimer.current);
          }
          prevActiveRef.current = true;
          setSession(data);
          setScreen('welcome');
        } else {
          if (prevActiveRef.current) {
            setSession(current => { setLastSession(current); return null; });
            setScreen('goodbye');
            goodbyeTimer.current = setTimeout(() => {
              setScreen('idle');
              setLastSession(null);
            }, 4000);
          }
          prevActiveRef.current = false;
        }
      } catch(e) {
        console.error('[poll error]', e);
      }
    }

    poll();
    pollRef.current = setInterval(poll, 1500);

    return () => {
      clearInterval(pollRef.current);
      clearTimeout(goodbyeTimer.current);
    };
  }, []);

  const askingName = session?.asking_name === true;

  if (screen === 'welcome')
    return <WelcomeScreen session={session} messages={messages} setMessages={setMessages} askingName={askingName} />;
  if (screen === 'goodbye')
    return <GoodbyeScreen session={lastSession} />;
  return <IdleScreen />;
}