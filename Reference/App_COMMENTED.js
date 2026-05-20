/**
 * RNSIT DIGITAL RECEPTIONIST - FRONTEND
 * =====================================
 *
 * This is the display/user interface that visitors interact with.
 * It's a React application that runs on the kiosk screen.
 *
 * What it does:
 * 1. Shows different screens (Idle, Welcome, Goodbye)
 * 2. Listens to visitor speech (voice input)
 * 3. Sends questions to the backend
 * 4. Displays answers from the backend
 * 5. Speaks answers out loud (text-to-speech)
 * 6. Manages the flow of a visitor session
 * 7. Shows real-time updates from other kiosks (WebSocket)
 */

import React, { useEffect, useState, useRef } from 'react';

// Import the different screen components
// Each component is a different visual state
import IdleScreen from './src/IdleScreen';      // Screen when no one is at the kiosk
import WelcomeScreen from './src/WelcomeScreen'; // Screen when visitor is interacting
import GoodbyeScreen from './src/GoodbyeScreen'; // Screen after visitor leaves
import './index.css';                        // CSS styling for the app

/**
 * ═════════════════════════════════════════════════════════════
 * BACKEND CONNECTION
 * ═════════════════════════════════════════════════════════════
 * 
 * This tells the frontend where the backend server is running.
 * In development: http://127.0.0.1:8000 (localhost)
 * In production: Read from environment variable REACT_APP_BACKEND_URL
 * 
 * Environment variables are set in .env file:
 *   REACT_APP_BACKEND_URL=http://192.168.1.100:8000
 */
const BACKEND = process.env.REACT_APP_BACKEND_URL || 'http://127.0.0.1:8000';

/**
 * ═════════════════════════════════════════════════════════════
 * MAIN APP COMPONENT
 * ═════════════════════════════════════════════════════════════
 * 
 * This is the root component that manages the entire application flow.
 * It handles:
 * - Which screen to show (idle/welcome/goodbye)
 * - Session data (who's visiting)
 * - Message history
 * - Polling backend for session changes
 */
export default function App() {
  // ─────────────────────────────────────────────────────
  // STATE VARIABLES - Data that changes and re-renders UI
  // ─────────────────────────────────────────────────────
  
  // screen: which screen to display
  // Values: 'idle', 'welcome', 'goodbye'
  // 'idle' = waiting for visitor
  // 'welcome' = visitor is here, chatting
  // 'goodbye' = visitor just left, showing goodbye message
  const [screen, setScreen] = useState('idle');
  
  // session: current visitor's info
  // Structure: { session_id, user_name, is_returning, visit_count, ... }
  // null = no active visitor
  const [session, setSession] = useState(null);
  
  // lastSession: the previous visitor's info (for goodbye screen)
  // We keep this so we can say goodbye to the person by name
  const [lastSession, setLastSession] = useState(null);
  
  // messages: array of all messages in current session
  // Each message: { text, speaker, timestamp }
  // speaker = 'user' (visitor) or 'kiosk' (us)
  const [messages, setMessages] = useState([]);

  // ─────────────────────────────────────────────────────
  // REF VARIABLES - Data that doesn't trigger re-render
  // ─────────────────────────────────────────────────────
  
  // pollRef: Reference to the setInterval timer that checks for sessions
  // We keep this so we can clear it when component unmounts (cleanup)
  const pollRef = useRef(null);
  
  // goodbyeTimer: Reference to timeout for goodbye screen
  // We keep this so we can clear it if another visitor arrives
  const goodbyeTimer = useRef(null);
  
  // prevActiveRef: Track if session was active in previous poll
  // This helps us detect when a session starts or ends
  // (Without this, we'd re-trigger stuff on every poll)
  const prevActiveRef = useRef(false);

  /**
   * ═════════════════════════════════════════════════════════════
   * MAIN EFFECT - Poll Backend for Session Changes
   * ═════════════════════════════════════════════════════════════
   * 
   * This effect runs when component mounts and sets up continuous polling.
   * Every 1.5 seconds, we check: "Is there an active session?"
   * 
   * Why? The backend doesn't push updates to us. We have to ask.
   * (This is simpler than WebSocket for session detection)
   */
  useEffect(() => {
    /**
     * poll() - Fetch current session from backend
     */
    async function poll() {
      try {
        // Make HTTP request to backend
        // GET /session/current returns current active visitor info
        const res = await fetch(BACKEND + '/session/current');
        const data = await res.json();

        /**
         * CASE 1: Backend says there's an active session
         * (Someone is at the kiosk right now)
         */
        if (data && data.active) {
          // If this is the FIRST time we're detecting the session
          // (wasn't active before), clear old data and show welcome
          if (!prevActiveRef.current) {
            // Clear old messages from previous visitor
            setMessages([]);
            // Cancel any goodbye timer that was running
            clearTimeout(goodbyeTimer.current);
          }
          
          // Update our tracking
          prevActiveRef.current = true;
          
          // Save the session data and show welcome screen
          setSession(data);        // Store who's visiting
          setScreen('welcome');    // Show welcome screen
        }
        /**
         * CASE 2: Backend says there's NO active session
         * (The visitor just left or session ended)
         */
        else {
          // Only act if we had an active session before
          // (This prevents triggering goodbye on every idle poll)
          if (prevActiveRef.current) {
            // Save the session info before clearing it
            // (We need the name for the goodbye message)
            setSession(current => {
              setLastSession(current);  // Save current session
              return null;              // Clear current session
            });
            
            // Show goodbye screen for 4 seconds
            setScreen('goodbye');
            
            // After 4 seconds, go back to idle waiting screen
            goodbyeTimer.current = setTimeout(() => {
              setScreen('idle');           // Show idle screen
              setLastSession(null);        // Clear last session data
            }, 4000);
          }
          
          // Update our tracking - no active session now
          prevActiveRef.current = false;
        }
      } catch (e) {
        // Network error or backend not responding
        console.error('[poll error]', e);
        // The app continues - we'll retry on next poll
      }
    }

    // Call poll() immediately (don't wait for interval)
    poll();
    
    // Then call poll() every 1.5 seconds
    // This keeps us in sync with backend
    // 1.5s = fast enough to feel responsive, slow enough to not overload
    pollRef.current = setInterval(poll, 1500);

    // ─────────────────────────────────────────────────────
    // CLEANUP - Run when component unmounts (app closes)
    // ─────────────────────────────────────────────────────
    return () => {
      // Stop polling to avoid memory leaks
      clearInterval(pollRef.current);
      // Cancel any pending goodbye timer
      clearTimeout(goodbyeTimer.current);
    };
  }, []); // Empty dependency array = run only once on mount

  /**
   * ═════════════════════════════════════════════════════════════
   * CHECK IF WE'RE WAITING FOR VISITOR TO ENTER THEIR NAME
   * ═════════════════════════════════════════════════════════════
   * 
   * When we don't recognize someone's face, we ask them to type their name.
   * This flag tells the WelcomeScreen to show the name input box.
   */
  const askingName = session?.asking_name === true;

  /**
   * ═════════════════════════════════════════════════════════════
   * RENDER - Choose which screen to show
   * ═════════════════════════════════════════════════════════════
   */
  
  // If we're welcoming a visitor, show WelcomeScreen
  if (screen === 'welcome')
    return (
      <WelcomeScreen
        session={session}              // Visitor info
        messages={messages}            // Chat history
        setMessages={setMessages}      // Function to add messages
        askingName={askingName}        // Should we ask for name?
      />
    );
  
  // If visitor just left, show GoodbyeScreen
  if (screen === 'goodbye')
    return <GoodbyeScreen session={lastSession} />;
  
  // Default: Show idle screen (waiting for visitor)
  return <IdleScreen />;
}
