# RNSIT Digital Receptionist Frontend
## Complete Guide & Documentation

---

## TABLE OF CONTENTS
1. [System Overview](#system-overview)
2. [Architecture Diagrams](#architecture-diagrams)
3. [File Structure](#file-structure)
4. [How It Works](#how-it-works)
5. [Installation & Setup](#installation--setup)
6. [Component Reference](#component-reference)
7. [State Management](#state-management)
8. [Communication with Backend](#communication-with-backend)
9. [Troubleshooting](#troubleshooting)

---

## SYSTEM OVERVIEW

### What is This?
This is the **frontend** (display/interface) of the digital receptionist kiosk.

It's what visitors see and interact with on the screen. It:
- ✅ Shows different screens based on state (idle/welcome/goodbye)
- ✅ Listens to visitor speech (voice input)
- ✅ Sends questions to backend
- ✅ Receives and displays answers
- ✅ Speaks answers out loud
- ✅ Manages the conversation flow
- ✅ Real-time sync with backend

### Technology Stack

```
React           → JavaScript library for building UIs
JavaScript      → Programming language
CSS             → Styling
Web Speech API  → Voice input/output
Fetch API       → HTTP requests to backend
```

---

## ARCHITECTURE DIAGRAMS

### Frontend System Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   KIOSK SCREEN (Display)                 │
│                   (Visitor sees this)                    │
└────────────┬─────────────────────────────────────────────┘
             │
    ┌────────▼─────────────────────────────┐
    │   React Application (App.js)         │
    │   ┌──────────────────────────────┐   │
    │   │ useState() - State Variables  │   │
    │   │ • screen (idle/welcome/bye)  │   │
    │   │ • session (visitor info)     │   │
    │   │ • messages (chat history)    │   │
    │   │ • useRef() - Timers & Refs   │   │
    │   └──────────────────────────────┘   │
    └────────┬───────────────┬──────────────┘
             │               │
        ┌────▼───┐      ┌───▼──────┐
        │ Screens │      │ Services │
        │         │      │          │
        │ Idle    │      │ Voice    │
        │Welcome  │      │ Backend  │
        │ Goodbye │      │ WebSocket│
        └─────────┘      └──────────┘
             │                │
        ┌────▼────────────────▼────┐
        │   User Interactions      │
        │ • Touch / Keyboard       │
        │ • Microphone (Speech)    │
        │ • Speaker (Audio)        │
        └──────────────────────────┘
```

---

### Data Flow: Question to Answer

```
VISITOR SPEAKS          FRONTEND              BACKEND
     │                     │                     │
     │ "Where is..."       │                     │
     │─────────────────────>                     │
     │ (Voice captured)    │                     │
     │                  [STT Engine]             │
     │                 Converts speech          │
     │                 to text: "Where..."      │
     │                     │                     │
     │                     │ GET /ask?question=...
     │                     │────────────────────>
     │                     │                     │
     │                     │                  [Search]
     │                     │                  [Answer]
     │                     │                     │
     │                     │<────────────────────
     │                     │ {"answer": "..."}   │
     │                     │                     │
     │              Display answer               │
     │              Show on screen               │
     │                  │                        │
     │              [TTS Engine]                 │
     │              Convert to speech            │
     │                  │                        │
     │<─────────────────┘                        │
     │ Hears the answer                          │
     │                                            │
```

---

### Screen State Flow Diagram

```
                    ┌────────────┐
                    │ IDLE SCREEN│
                    │ (Waiting)  │
                    └──────┬─────┘
                           │
                    Poll every 1.5s
                    /session/current
                           │
        ┌──────────────────┴──────────────────┐
        │                                     │
        ▼                                     ▼
   Session Active                        No Session
        │                                     │
        └────────────┬────────────────────────┘
                     │
            Set screen = 'welcome'
                     │
        ┌────────────▼──────────────────┐
        │   WELCOME SCREEN              │
        │   (Visitor interacting)       │
        │   • Chat history              │
        │   • Voice input               │
        │   • Visitor name display      │
        └────────────┬──────────────────┘
                     │
            Visitor leaves
            Session ends
            /session/end called
                     │
        Poll detects:
        Session = null
                     │
        Clear messages
        Save last session
                     │
        Set screen = 'goodbye'
                     │
        ┌────────────▼──────────────────┐
        │   GOODBYE SCREEN              │
        │   Shows for 4 seconds         │
        │   Displays goodbye message    │
        │   with visitor's name         │
        └────────────┬──────────────────┘
                     │
            After 4 seconds
            setTimeout completes
                     │
        Clear last session data
        Set screen = 'idle'
                     │
                [Back to IDLE]
```

---

### Component Hierarchy

```
┌─ App.js (Main)
│  ├─ Manages all state
│  ├─ Polling backend every 1.5s
│  ├─ Screen routing
│  │
│  ├─ IdleScreen.js
│  │  └─ Shows RNSIT logo
│  │     Shows "Please wait..." or "Hi there, welcome!"
│  │     Just informational, no interaction
│  │
│  ├─ WelcomeScreen.js
│  │  ├─ Shows session info
│  │  ├─ Voice input (speech-to-text)
│  │  ├─ Chat history
│  │  ├─ Name input (if asking)
│  │  ├─ Data deletion flow
│  │  └─ Voice output (text-to-speech)
│  │
│  └─ GoodbyeScreen.js
│     └─ Shows goodbye message
│        Displays visitor's name
│        Shows for 4 seconds then returns to idle

CSS Files:
└─ index.css
   └─ Styling for all components
```

---

### Voice Processing Pipeline

```
SPEECH INPUT → STT → TEXT → BACKEND → ANSWER → TTS → SPEECH OUTPUT
    │           │      │       │        │       │      │
    │           │      │       │        │       │      └─ Speaker
    │           │      │       │        │       └─ Text to Speech
    │           │      │       │        └─ Backend /ask endpoint
    │           │      │       └─ HTTP Fetch
    │           │      └─ "Where is library?"
    │           └─ Web Speech API
    └─ Microphone (navigator.mediaDevices)

Detailed Flow:

1. startListening()
   └─ Create new SpeechRecognition object
   └─ Set language: 'en-US'
   └─ Set continuous: false
   └─ Set interimResults: true (show partial results)
   
2. recog.onstart
   └─ Show "Listening..." indicator
   └─ Clear previous text
   
3. recog.onresult (fires multiple times as user speaks)
   └─ Capture interim results: "Wher..." "Where is..." "Where is lib..."
   └─ Capture final results: "Where is the library?"
   └─ Display live text on screen
   
4. recog.onend
   └─ Get final transcript
   └─ Remove trailing punctuation
   └─ Send to backend: /ask?question=Where%20is%20the%20library?
   
5. Backend responds with answer
   └─ Add message to chat
   └─ Call speak(answer)
   
6. speak() - Text to Speech
   └─ Create SpeechSynthesisUtterance
   └─ Set lang, rate, volume
   └─ window.speechSynthesis.speak()
   └─ Wait for speech to finish
   
7. onend of speech
   └─ Resume listening
   └─ Loop back to step 1
```

---

## FILE STRUCTURE

```
frontend/
├── package.json              # Project metadata, dependencies
├── .env.example              # Example environment variables
├── public/
│  ├── index.html             # HTML entry point
│  ├── favicon.ico            # Browser tab icon
│  └── rnslogo.webp           # RNSIT college logo
│
└── src/
   ├── App.js                 # Main component, session management
   ├── App_COMMENTED.js       # Heavily commented version
   ├── IdleScreen.js          # Waiting screen
   ├── WelcomeScreen.js       # Conversation screen
   ├── GoodbyeScreen.js       # Exit screen
   ├── index.js               # React entry point
   └── index.css              # All styling
```

---

## HOW IT WORKS

### The Complete Flow - Step by Step

```
STEP 1: STARTUP
┌─────────────────┐
│  App.js mounts  │
└────────┬────────┘
         │
    Initialization:
    • screen = 'idle'
    • session = null
    • messages = []
         │
    Set up polling:
    • Call poll() immediately
    • Then poll() every 1.5 seconds
         │
    useEffect return() cleanup:
    • When app closes, clear intervals
         │
    ┌────▼─────────────────────┐
    │ IDLE SCREEN DISPLAYED    │
    │ Shows RNSIT logo         │
    │ Waiting for visitor      │
    └──────────────────────────┘


STEP 2: VISITOR ARRIVES
┌─────────────────────────┐
│  Poll checks session    │
│  /session/current       │
└────────┬────────────────┘
         │
    Backend created new session
    (by camera or detection.py)
    Session: {
      session_id: "abc123",
      user_name: "John",
      is_returning: true
    }
         │
    ┌────▼────────────────────────────┐
    │ UPDATE STATE                    │
    │ • session = {backend response}  │
    │ • screen = 'welcome'            │
    │ • messages = []                 │
    │ • clearTimeout(goodbyeTimer)    │
    └────┬─────────────────────────────┘
         │
    ┌────▼──────────────────────┐
    │ WELCOME SCREEN DISPLAYED  │
    │ Shows visitor greeting    │
    │ Ready for questions       │
    └───────────────────────────┘


STEP 3: VISITOR ASKS A QUESTION (Voice)
┌──────────────────┐
│ Visitor speaks   │
│ "Hello there"    │
└────────┬─────────┘
         │
    ┌────▼────────────────────────┐
    │ Speech Recognition Active   │
    │ (Web Speech API)            │
    │ • Listens to microphone     │
    │ • Transcribes to text       │
    │ • Shows live text           │
    └────┬──────────────────────  ┘
         │
    User finishes speaking
    (silence detected)
         │
    ┌────▼────────────────────────┐
    │ recog.onend fires           │
    │ Final text: "Hello there"   │
    │ Call: sendToBackend()       │
    └────┬──────────────────────  ┘
         │
         ├─ addMessage("Hello there", "user")
         │  └─ Update state: messages = [..., new message]
         │
         ├─ POST /message
         │  └─ Send to backend for logging
         │
         ├─ GET /ask?question=Hello%20there
         │  └─ Backend searches knowledge base
         │  └─ Response: {"answer": "Hello! Welcome to RNSIT..."}
         │
         ├─ addMessage(answer, "kiosk")
         │  └─ Update state with answer
         │
         ├─ speak(answer)
         │  └─ Convert text to speech
         │  └─ Play through speaker
         │  └─ Wait for audio to finish
         │
         └─ startListening()
            └─ Loop back to listening
                for next question


STEP 4: VISITOR SAYS GOODBYE
┌──────────────────────────┐
│ Visitor speaks           │
│ "Thank you, goodbye"     │
└────────┬─────────────────┘
         │
    ┌────▼──────────────────────────┐
    │ sendToBackend() detects       │
    │ goodbye words in text:        │
    │ • thank you, thanks           │
    │ • bye, goodbye                │
    │ • see you, ok bye             │
    └────┬──────────────────────────┘
         │
    ├─ addMessage("Thank you, goodbye", "user")
    │
    ├─ addMessage("Goodbye! Have a great day!", "kiosk")
    │
    ├─ speak("Goodbye! Have a great day!")
    │
    └─ POST /session/end?session_id=abc123
       └─ Backend marks session as ended
       └─ Saves to database


STEP 5: SESSION ENDS
┌──────────────────────┐
│ Poll checks again    │
│ /session/current     │
└────────┬─────────────┘
         │
    Backend returns:
    {"active": false}
         │
    ┌────▼──────────────────────────┐
    │ prevActiveRef was true        │
    │ Now it's false                │
    │ Transition triggered!         │
    └────┬──────────────────────────┘
         │
    ├─ setLastSession(currentSession)
    │  └─ Save "John" for goodbye message
    │
    ├─ setSession(null)
    │  └─ Clear active session
    │
    ├─ setScreen('goodbye')
    │  └─ Show goodbye screen
    │
    └─ setTimeout(4000, () => {
        └─ setScreen('idle')
        └─ setLastSession(null)
       })
          └─ After 4 seconds, go back to idle


STEP 6: BACK TO IDLE
┌───────────────────────────┐
│ screen = 'idle'           │
│ Waiting for next visitor  │
│ (Loop back to STEP 2)     │
└───────────────────────────┘
```

---

## INSTALLATION & SETUP

### Prerequisites

```
✓ Node.js 14+ (includes npm)
✓ Git installed
✓ Modern web browser (Chrome, Firefox, Edge, Safari)
```

### Step 1: Install Dependencies

```bash
# Navigate to frontend directory
cd frontend

# Install all dependencies (React, etc.)
npm install

# This creates node_modules/ folder with all packages
```

### Step 2: Create Environment File

Create `.env` file in `frontend/` directory:

```env
# Backend server URL
REACT_APP_BACKEND_URL=http://localhost:8000

# For production:
# REACT_APP_BACKEND_URL=http://192.168.1.100:8000
```

### Step 3: Start Development Server

```bash
# From frontend/ directory
npm start

# This:
# 1. Starts React development server
# 2. Opens browser to http://localhost:3000
# 3. Hot-reloads on file changes (great for development)
```

### Step 4: Build for Production

```bash
# Create optimized production build
npm run build

# This creates 'build/' folder with:
# • Minified JavaScript
# • Optimized CSS
# • Ready to deploy to web server
```

### Step 5: Deploy to Kiosk

**Option A: USB/Local File**
```bash
# Copy build/ folder to USB
# Transfer to kiosk machine
# Open build/index.html in browser
```

**Option B: Web Server**
```bash
# Deploy build/ folder to Nginx or Apache
# Kiosk accesses via: http://kiosk-server/
```

---

## COMPONENT REFERENCE

### App.js (Main Component)

**Purpose:** Root component that manages entire application

**State Variables:**
```javascript
screen          // Current screen: 'idle', 'welcome', 'goodbye'
session         // Current visitor info
lastSession     // Previous visitor (for goodbye)
messages        // Chat history
```

**Key Functions:**
```javascript
poll()          // Check backend every 1.5s for session changes
useEffect()     // Set up polling, cleanup on unmount
```

**Logic Flow:**
```
Poll backend → Session exists? 
→ Yes: Show welcome screen
→ No: Show idle or goodbye screen
```

---

### IdleScreen.js

**Purpose:** Display when kiosk is waiting for visitors

**Features:**
- RNSIT logo with animation
- "Welcome" text
- Idle state message
- Nice styling with gradient background

**What it shows:**
```
┌────────────────────────────┐
│     RNSIT COLLEGE LOGO     │
│                            │
│   RNS Institute of Tech    │
│                            │
│   "Welcome to our kiosk"   │
│                            │
│  Please wait for           │
│  assistance...             │
└────────────────────────────┘
```

**Props:** None

---

### WelcomeScreen.js

**Purpose:** Main interaction screen - this is where everything happens!

**Features:**
- Visitor greeting ("Welcome back, John!")
- Chat history display
- Speech-to-text input
- Text-to-speech output
- Name entry form (if unknown visitor)
- Data deletion form (GDPR)

**State Variables:**
```javascript
name            // Name they're entering
saveData        // Checkbox: save my data?
submitted       // Have they submitted name?
deleteMode      // Showing delete form?
deleteName      // Name to delete
deleted         // Was deletion successful?
liveText        // Live speech recognition text
listening       // Currently listening?
```

**Key Functions:**
```javascript
startListening()     // Start speech recognition
speak(text)          // Convert text to speech
sendToBackend(text)  // Send question to backend
addMessage()         // Add to chat
handleNameSubmit()   // Process name entry
handleDelete()       // Process GDPR deletion
```

**What it shows:**
```
┌─────────────────────────────────────┐
│ Welcome back, John!                 │
│ (This is your 3rd visit)            │
│                                     │
│ ┌───────────────────────────────┐  │
│ │ Chat History                  │  │
│ │ • How can I help?             │  │
│ │ • Where is the library?       │  │
│ │ • It's in Block A             │  │
│ │ • Thank you                   │  │
│ └───────────────────────────────┘  │
│                                     │
│ [Listening...] 🎤                   │
│ "Where is"                          │
│                                     │
│ [ Delete My Data ] [ Settings ]     │
└─────────────────────────────────────┘
```

**Props:**
```javascript
session       // Visitor info
messages      // Chat history
setMessages   // Function to update messages
askingName    // Should we show name input?
```

---

### GoodbyeScreen.js

**Purpose:** Show goodbye message when visitor leaves

**Features:**
- Personal goodbye message using visitor's name
- Animated display
- Shows for 4 seconds then auto-dismisses

**What it shows:**
```
┌────────────────────────────┐
│   Thank you, John!         │
│                            │
│   Have a wonderful day!    │
│                            │
│   [Fades out after 4 sec]  │
└────────────────────────────┘
```

**Props:**
```javascript
session  // Last visitor's info (for name)
```

---

## STATE MANAGEMENT

### How State Works

**State = Data that changes and updates the UI**

```javascript
// Create a state variable
const [variableName, setVariableName] = useState(initialValue);

// Example:
const [screen, setScreen] = useState('idle');

// To update state:
setScreen('welcome');  // Automatically re-renders UI

// Inside functions:
function handleClick() {
  setScreen('goodbye');  // Triggers re-render with new value
}
```

### State Flow Diagram

```
User Action (e.g., visitor arrives)
         │
         ▼
Backend updates (session created)
         │
         ▼
App.js polls and detects change
         │
         ▼
useState setter called (e.g., setScreen('welcome'))
         │
         ▼
Component re-renders with new state
         │
         ▼
Display updates on screen
         │
         ▼
[Now waiting for next state change]
```

### Key State Variables

```javascript
// Main flow state
screen              // Which screen to show
session             // Current visitor (null or object)
lastSession         // Previous visitor (for goodbye)

// Message history
messages            // Array of message objects

// Refs (don't trigger re-render)
pollRef             // Polling interval ID
goodbyeTimer        // Goodbye timeout ID
prevActiveRef       // Was session active before?
```

---

## COMMUNICATION WITH BACKEND

### HTTP Requests (Polling & Data)

**GET /session/current**
```javascript
// Check if there's an active session
const res = await fetch(BACKEND + '/session/current');
const data = await res.json();

if (data.active) {
  // Someone is at the kiosk
  setSession(data);
  setScreen('welcome');
} else {
  // No one is visiting
  setScreen('idle');
}
```

**GET /ask**
```javascript
// Ask a question
const text = "Where is the library?";
const res = await fetch(
  BACKEND + '/ask?question=' + encodeURIComponent(text)
);
const data = await res.json();
const answer = data.answer;

// Display and speak the answer
addMessage(answer, 'kiosk');
speak(answer);
```

**POST /message**
```javascript
// Log a message
await fetch(BACKEND + '/message', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    session_id: sid,
    text: messageText,
    speaker: 'user' // or 'kiosk'
  })
});
```

**POST /session/end**
```javascript
// End the session (visitor said goodbye)
await fetch(BACKEND + '/session/end?session_id=' + sid, {
  method: 'POST'
});
```

**POST /visitor/submit_name**
```javascript
// Submit visitor's name
await fetch(BACKEND + '/visitor/submit_name', {
  method: 'POST',
  body: new URLSearchParams({
    name: visitorName,
    save: true
  })
});
```

**POST /visitor/delete_my_data**
```javascript
// Delete visitor's data (GDPR)
await fetch(
  BACKEND + '/visitor/delete_my_data?name=' + encodeURIComponent(name),
  { method: 'POST' }
);
```

### Polling Strategy

```
App.js continuously polls backend every 1.5 seconds:

Time 0.0s: poll() → /session/current → null (idle)
Time 1.5s: poll() → /session/current → null (idle)
Time 3.0s: poll() → /session/current → {session_id: "abc"} ← DETECTED!
          │
          └─ Screen changes from idle to welcome
          └─ Visitor now interacting
          
Time 4.5s: poll() → /session/current → {session_id: "abc"} (still there)
Time 6.0s: poll() → /session/current → {session_id: "abc"} (still there)
Time 7.5s: poll() → /session/current → null ← SESSION ENDED!
          │
          └─ Screen changes to goodbye
          └─ After 4 seconds, back to idle
```

---

## TROUBLESHOOTING

### Problem: Blank white screen / App not loading

**Solution:**
```bash
# Check frontend is running
npm start

# Check browser console for errors (F12)
# Check that REACT_APP_BACKEND_URL is correct in .env
```

---

### Problem: Can't connect to backend (Error in console)

**Error:** "Failed to fetch from http://localhost:8000"

**Causes & Solutions:**
```bash
# 1. Backend not running
# Start backend:
cd ..  # Go back to project root
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 2. Wrong backend URL
# Check .env file:
REACT_APP_BACKEND_URL=http://localhost:8000

# 3. CORS issue (frontend can't talk to backend)
# Backend must have CORS enabled
# Check main.py has CORSMiddleware configured

# 4. Firewall blocking
# Make sure port 8000 is accessible
# Windows Firewall: Allow Python through firewall
```

---

### Problem: Microphone not working

**Solution:**
```bash
# 1. Check browser permissions
# Click the lock icon in address bar
# Allow "Microphone" access

# 2. Test browser support
# Only works on HTTPS or localhost
# Not supported: HTTP on public URLs

# 3. Check microphone works
# Test in another app first (Discord, Skype, etc.)

# 4. Check browser support
# Chrome ✓, Firefox ✓, Edge ✓, Safari ✓
```

---

### Problem: Speaker/Audio not working

**Solution:**
```bash
# 1. Check system volume is not muted
# 2. Check browser isn't muted
#    Look for speaker icon with X in tab
# 3. Test speakers work
#    YouTube video test
# 4. Check browser permissions
#    May need to allow audio playback
```

---

### Problem: Speech recognition doesn't understand

**Possible Causes:**
- Accent not recognized (language setting)
- Background noise too loud
- Speaking too fast/slow
- Microphone quality poor

**Solutions:**
```javascript
// Adjust language (in WelcomeScreen.js)
recog.lang = 'en-IN';  // For Indian English
// or
recog.lang = 'en-GB';  // For British English
// or
recog.lang = 'en-US';  // For American English

// Reduce noise
// Move away from fans, speakers, traffic

// Try again with clearer pronunciation
```

---

### Problem: Chat history not showing

**Causes:**
- messages state not updating
- Backend not responding
- Browser cache issue

**Solution:**
```bash
# 1. Check browser console (F12)
# Look for error messages

# 2. Clear cache
# Ctrl+Shift+Del (or Cmd+Shift+Del on Mac)
# Clear "Cached images and files"
# Reload page

# 3. Check backend is logging messages
# POST /message requests reaching backend?
# Check backend logs
```

---

### Problem: Polling seems slow / Session detection delayed

**Expected Behavior:**
- Poll happens every 1.5 seconds
- Session detection takes up to 1.5 seconds

**To speed up:**
```javascript
// In App.js, change polling interval
pollRef.current = setInterval(poll, 1000);  // Every 1 second instead of 1.5

// Or for instant (not recommended - uses more CPU):
pollRef.current = setInterval(poll, 500);   // Every 500ms
```

---

### Problem: Name input not appearing when unknown visitor

**Cause:** Backend not sending `asking_name: true`

**Debug:**
```javascript
// In WelcomeScreen.js, add console log
console.log('Asking for name?', askingName);
console.log('Full session:', session);

// Check if /visitor/unknown was called
// Check backend logs
```

---

### Problem: Goodbye screen doesn't appear

**Cause:** Session not ending properly

**Debug:**
```javascript
// In App.js, add logs
console.log('Previous active:', prevActiveRef.current);
console.log('Current session:', session);
console.log('Screen:', screen);

// Check backend /session/end is being called
// Check database - is session marked as ended?
```

---

## RUNNING & MONITORING

### Development Mode

```bash
# Start dev server with hot reload
npm start

# Features:
# • Auto-reload on code changes
# • Better error messages
# • Slower performance
# • Use for development only
```

### Production Mode

```bash
# Build optimized production files
npm run build

# Copy build/ folder to kiosk/server
# Serve with: serve -s build -l 3000
# Or deploy to web server

# Features:
# • Minified & optimized
# • Faster performance
# • No error messages (security)
# • Use for live kiosk
```

### Monitor Live

```bash
# 1. Browser DevTools
# Press F12 to open
# Check Console tab for errors
# Check Network tab for API calls

# 2. Check requests
# Open Console tab
# Look for fetch calls
# See response data

# 3. Check session state
# Add console.log() to see state changes
```

---

## QUICK REFERENCE

| Task | File | How |
|------|------|-----|
| Change welcome message | WelcomeScreen.js | Modify greeting variable |
| Change colors/styling | index.css | Edit CSS classes |
| Change polling interval | App.js | Modify setInterval(poll, X) |
| Add new screen | New JS file | Create component, import in App.js |
| Change backend URL | .env | Set REACT_APP_BACKEND_URL |
| Add feature | WelcomeScreen.js | Extend with new state & handlers |
| Debug state | App.js | Add console.log(state) |
| Fix voice input | WelcomeScreen.js | Check STT language settings |

---

## SUMMARY

```
┌──────────────────────────────────────────────────────┐
│         HOW THE FRONTEND WORKS                       │
├──────────────────────────────────────────────────────┤
│                                                      │
│  1. App.js mounts                                   │
│     • Initialize state                              │
│     • Start polling backend every 1.5s              │
│                                                      │
│  2. Display IdleScreen                              │
│     • Show RNSIT logo                               │
│     • Wait for visitor                              │
│                                                      │
│  3. Poll detects session started                    │
│     • Show WelcomeScreen                            │
│     • Display greeting with visitor name            │
│                                                      │
│  4. Visitor speaks question                         │
│     • Microphone listens                            │
│     • Speech-to-text converts to text               │
│     • Send to backend /ask endpoint                 │
│                                                      │
│  5. Backend returns answer                          │
│     • Add to chat history                           │
│     • Display on screen                             │
│     • Text-to-speech speaks answer                  │
│     • Resume listening                              │
│                                                      │
│  6. Repeat steps 4-5 until goodbye                  │
│                                                      │
│  7. Visitor says goodbye                            │
│     • Detect "thank you", "bye", etc                │
│     • Call /session/end                             │
│     • Stop listening                                │
│                                                      │
│  8. Poll detects session ended                      │
│     • Show GoodbyeScreen for 4 sec                  │
│     • Back to IdleScreen                            │
│                                                      │
│  [Wait for next visitor → back to step 2]           │
│                                                      │
└──────────────────────────────────────────────────────┘
```

---

**End of Guide**

For more information, see:
- `App_COMMENTED.js` - Heavily commented main component
- Backend guide: `BACKEND_GUIDE.md`
- React docs: https://react.dev
