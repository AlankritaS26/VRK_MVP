# RNSIT Digital Receptionist Backend
## Complete Guide & Documentation

---

## TABLE OF CONTENTS
1. [System Overview](#system-overview)
2. [Architecture Diagrams](#architecture-diagrams)
3. [How It Works](#how-it-works)
4. [Installation & Setup](#installation--setup)
5. [API Endpoints Reference](#api-endpoints-reference)
6. [Data Flow Examples](#data-flow-examples)
7. [Troubleshooting](#troubleshooting)

---

## SYSTEM OVERVIEW

### What is This?
This is the **backend server** (brain) of a digital receptionist kiosk for RNSIT college.

Think of it like a real receptionist that:
- ✅ Listens to visitor questions
- ✅ Answers from a knowledge base (FAQs, facilities, departments)
- ✅ Remembers who's visiting (sessions)
- ✅ Recognizes returning visitors (face matching)
- ✅ Keeps a record of all interactions (database)
- ✅ Talks to multiple kiosk screens in real-time (WebSocket)

### Key Technologies Used
```
FastAPI          → Web framework (handles HTTP & WebSocket)
PostgreSQL       → Database (stores everything)
Pydantic         → Data validation (checks incoming data is correct)
Python           → Programming language
WebSocket        → Real-time communication with clients
```

---

## ARCHITECTURE DIAGRAMS

### System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        KIOSK SCREENS (Frontend)                 │
│                  (React, displays questions/answers)            │
└────────┬────────────────────────────────────────┬───────────────┘
         │                                        │
         │ HTTP Requests                          │ WebSocket
         │ (Questions, Sessions)                  │ (Real-time Updates)
         │                                        │
┌────────▼────────────────────────────────────────▼───────────────┐
│                  BACKEND SERVER (This Code)                      │
│                  ┌──────────────────────────────┐                │
│                  │   FastAPI Application        │                │
│                  │  ┌────────────────────────┐  │                │
│                  │  │ /ask (FAQ Search)      │  │                │
│                  │  │ /session/* (Sessions)  │  │                │
│                  │  │ /message (Logging)     │  │                │
│                  │  │ /face/* (Recognition)  │  │                │
│                  │  │ /visitor/* (Names)     │  │                │
│                  │  └────────────────────────┘  │                │
│                  └──────────────────────────────┘                │
│                                 │                                │
│                  ┌──────────────▼──────────────┐                │
│                  │ In-Memory State             │                │
│                  │ • Active Session            │                │
│                  │ • Message Log               │                │
│                  │ • Visitor Name Response     │                │
│                  └─────────────────────────────┘                │
└────────┬───────────────────────────────────────────┬────────────┘
         │                                           │
         │ SQL Queries                              │ JSON
         │ (Read/Write Data)                        │ (College Info)
         │                                           │
┌────────▼────────────────────┐  ┌────────────────▼──────────────┐
│    PostgreSQL Database       │  │   college_info.json File      │
│  ┌──────────────────────┐    │  │  (FAQs, Facilities, Depts)    │
│  │ interactions table   │    │  │  (Cached in Memory at Start)  │
│  │ faces table          │    │  └───────────────────────────────┘
│  │ sessions table       │    │
│  └──────────────────────┘    │
└─────────────────────────────┘
```

---

### Request Flow: When Visitor Asks a Question

```
KIOSK SCREEN                          BACKEND SERVER
     │                                      │
     │ "Where is the library?"              │
     │─────────────────────────────────────>│ GET /ask?question=...
     │                                      │
     │                                  ┌───▼─────────────────┐
     │                                  │ Search Knowledge    │
     │                                  │ Base:               │
     │                                  │ 1. FAQs            │
     │                                  │ 2. Facilities      │
     │                                  │ 3. Departments     │
     │                                  │ 4. Admin           │
     │                                  │ 5. College Info    │
     │                                  └───┬────────────────┘
     │                                      │
     │                                  ┌───▼─────────────────┐
     │                                  │ Match found!        │
     │                                  │ "Library is in      │
     │                                  │  Block A, 2nd floor"│
     │                                  └───┬────────────────┘
     │                                      │
     │<─────────────────────────────────────│ Return Answer
     │ {"question": "...", "answer": "..."} │
     │                                      │
     └──────────────────────────────────────┘
```

---

### Session Lifecycle Diagram

```
VISITOR ARRIVES
     │
     ▼
Camera detects face
     │
     ├─ Is face recognized?
     │  ├─ YES → GET /face/lookup/{face_id}
     │  │        (Returning visitor, known name)
     │  │
     │  └─ NO → POST /visitor/unknown
     │          (New visitor, ask for name)
     │
     ▼
POST /session/start
(Create session, initialize state)
     │
     ▼
[Active Session Running]
     │
     ├─ Visitor asks questions → GET /ask
     ├─ Messages logged → POST /message
     ├─ Real-time updates → WebSocket broadcast
     │
     ▼
Visitor Leaves
     │
     ▼
POST /session/end
(Save to database, clean up)
     │
     ▼
SESSION COMPLETE
```

---

### Data Model Diagram

```
┌─────────────────────┐
│   ACTIVE_SESSION    │
│  (In Memory)        │
├─────────────────────┤
│ session_id: "abc"   │
│ user_name: "John"   │
│ is_returning: true  │
│ visit_count: 5      │
│ face_id: "xyz"      │
│ asking_name: false  │
└─────────────────────┘

         │
         │ Persisted to
         ▼
┌──────────────────────────────────────┐
│   DATABASE - sessions table          │
├──────────────────────────────────────┤
│ session_id (PRIMARY KEY)             │
│ face_id (FOREIGN KEY to faces)       │
│ user_name                            │
│ is_returning                         │
│ visit_count                          │
│ started_at (timestamp)               │
│ ended_at (timestamp)                 │
└──────────────────────────────────────┘


┌─────────────────────┐
│   MESSAGE_LOG       │
│  (In Memory List)   │
├─────────────────────┤
│ {                   │
│   index: 0,         │
│   text: "hi",       │
│   speaker: "user",  │
│   timestamp: "14:30"│
│ },                  │
│ {                   │
│   index: 1,         │
│   text: "hello!",   │
│   speaker: "asst"   │
│ }                   │
└─────────────────────┘

         │
         │ Persisted to
         ▼
┌──────────────────────────────────────┐
│   DATABASE - interactions table      │
├──────────────────────────────────────┤
│ id (PRIMARY KEY)                     │
│ session_id                           │
│ input_text (the question)            │
│ response_text (the answer)           │
│ created_at (timestamp)               │
└──────────────────────────────────────┘


┌─────────────────────┐
│   COLLEGE_DATA      │
│  (Cached in Memory) │
├─────────────────────┤
│ {                   │
│   "faqs": [...],    │
│   "facilities": {..}│
│   "departments": {..│
│   "admin": {...}    │
│   "college": {...}  │
│ }                   │
└─────────────────────┘
     Loaded from
       ▼
   college_info.json
   (Read at startup)
```

---

### WebSocket Broadcasting Flow

```
CLIENT 1 (Kiosk Screen A)      CLIENT 2 (Kiosk Screen B)      CLIENT 3 (Kiosk Screen C)
        │                              │                              │
        │ Connects                     │ Connects                     │ Connects
        └──────────────┬───────────────┴──────────────┬───────────────┘
                       │                              │
                       ▼ /ws endpoint                ▼
                  ┌─────────────────────────┐
                  │  ConnectionManager      │
                  │ ┌─────────────────────┐ │
                  │ │ active_connections: │ │
                  │ │ [client1, client2,  │ │
                  │ │  client3]           │ │
                  │ └─────────────────────┘ │
                  └─────────────────────────┘
                           │
        [Something happens - session starts, message sent, etc.]
                           │
                           ▼
               await manager.broadcast({
                 "type": "message",
                 "text": "Hello!"
               })
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    SEND to client1   SEND to client2   SEND to client3
         │                 │                 │
         ▼                 ▼                 ▼
      Screen A         Screen B         Screen C
   Updates in real   Updates in real   Updates in real
   time (no reload)  time (no reload)  time (no reload)
```

---

## HOW IT WORKS

### The /ask Endpoint - Step by Step

When a visitor asks "Who is the Principal?", here's what happens:

```
1. Frontend sends:
   GET /ask?question=Who%20is%20the%20Principal?

2. Backend receives the question and cleans it:
   question = "who is the principal?"
   → Remove stop words → ["principal"]
   
3. Search knowledge base in order of priority:
   
   a) Check FAQs:
      FAQs = [
        {question: "Who is the principal?", answer: "Dr. Smith"},
        {question: "How to apply?", answer: "..."},
        ...
      ]
      → MATCH FOUND! "Dr. Smith" (score: 2 points)
   
   b) [Search would continue but we found a match, so we stop]
   
4. Return response:
   {
     "question": "Who is the principal?",
     "answer": "Dr. Smith"
   }

5. Save to database (fire and forget, async):
   INSERT INTO interactions (input_text, response_text)
   VALUES ('Who is the principal?', 'Dr. Smith')

6. Broadcast to all connected WebSocket clients:
   {
     "type": "message",
     "text": "Dr. Smith",
     "speaker": "assistant"
   }
```

---

### Search Priority & Scoring System

```
FAQs                    → Score 2 (exact question match)
  ↓
Facilities              → Score 3 (library, lab, cafeteria)
  ↓
Departments             → Score 2 (CSE, ECE, Mechanical)
  ↓
Administration          → Score 2 (principal, dean, director)
  ↓
College Info            → Score 2 (address, phone, website)
  ↓
Fallback Message        → No score
  "I'm sorry, I don't have that info..."
```

**How scoring works:**
- Each word match in the question = 1 or 2 points
- Higher score = better match
- We keep the highest scoring answer

---

## INSTALLATION & SETUP

### Prerequisites

```
✓ Python 3.8+
✓ PostgreSQL installed and running
✓ Git installed
✓ Virtual environment (venv)
```

### Step 1: Clone & Setup

```bash
# Clone the repository
git clone <repo-url>
cd VRK_MVP

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment

Create `.env` file in the project root:

```env
# Database connection
DATABASE_URL=postgresql://user:password@localhost:5432/rnsit_kiosk

# Frontend allowed origins
ALLOWED_ORIGINS=http://localhost:3000,http://192.168.1.100:3000

# Optional admin API key
ADMIN_API_KEY=your-secret-key-here
```

### Step 3: Prepare Data

Ensure `data/college_info.json` exists with structure:

```json
{
  "faqs": [
    {
      "question": "Who is the principal?",
      "answer": "Dr. John Smith"
    }
  ],
  "facilities": {
    "library": {
      "name": "Central Library",
      "location": "Block A, Ground Floor",
      "timings": "8 AM - 8 PM",
      "details": "3000+ books"
    }
  },
  "departments": {
    "CSE": {
      "hod": "Dr. Jane Doe",
      "floor": "3rd Floor",
      "intake": "180"
    }
  },
  "administration": {
    "principal": {
      "name": "Dr. John Smith",
      "qualification": "PhD"
    }
  },
  "college": {
    "name": "RNSIT",
    "address": "Location...",
    "phone": "+91-xxx-xxx-xxxx"
  }
}
```

### Step 4: Run the Server

```bash
# Activate environment first
venv\Scripts\activate  # or source venv/bin/activate

# Start the server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Server will be available at:
# http://localhost:8000
# WebSocket at: ws://localhost:8000/ws
```

---

## API ENDPOINTS REFERENCE

### 1. HEALTH CHECK
```
GET /
├─ Purpose: Check if server is running
├─ Auth: None
├─ Parameters: None
└─ Response: {"status": "RNSIT Kiosk Backend is Live"}
```

---

### 2. ASK / FAQ SEARCH (Most Important)
```
GET /ask?question=<query>
├─ Purpose: Search knowledge base for answers
├─ Auth: None
├─ Parameters:
│  └─ question (string, max 500 chars): "Where is the library?"
└─ Response:
   {
     "question": "Where is the library?",
     "answer": "The library is in Block A, Ground Floor..."
   }

Example:
  GET /ask?question=Who%20is%20the%20principal?
  Response: {"question": "Who is the principal?", "answer": "Dr. Smith"}
```

---

### 3. SESSION MANAGEMENT

#### 3a. Start Session
```
POST /session/start
├─ Purpose: Create a new visitor session
├─ Auth: None
├─ Body Parameters (all optional):
│  ├─ trigger: "camera" or "manual" (what triggered this)
│  ├─ user_name: "John" (visitor's name)
│  ├─ is_returning: true/false (recognized visitor?)
│  ├─ visit_count: 5 (how many times visited)
│  ├─ face_id: "abc123" (face recognition ID)
│  └─ session_id: "xyz789" (specific session ID)
└─ Response:
   {
     "status": "success",
     "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
     "session": {
       "session_id": "f47ac10b...",
       "user_name": "John",
       "is_returning": true,
       "visit_count": 5,
       "face_id": "abc123",
       "asking_name": false
     }
   }
```

#### 3b. End Session
```
POST /session/end
├─ Purpose: End active session and save to database
├─ Auth: None
├─ Parameters:
│  └─ session_id: optional (if not provided, ends current session)
└─ Response: {"status": "success"}
```

#### 3c. Get Current Session
```
GET /session/current
├─ Purpose: Check which visitor is currently active
├─ Auth: None
├─ Parameters: None
└─ Response (if active):
   {
     "active": true,
     "session_id": "f47ac10b...",
     "user_name": "John",
     "is_returning": true,
     "visit_count": 5
   }
   Or if no active session:
   {"active": false}
```

#### 3d. Get Session Messages
```
GET /session/messages/{session_id}?after=<index>
├─ Purpose: Get conversation history
├─ Auth: None
├─ Parameters:
│  ├─ session_id: "f47ac10b..." (which session)
│  └─ after: 0 (only get messages after index N - for efficiency)
└─ Response:
   {
     "messages": [
       {
         "index": 0,
         "text": "Hello",
         "speaker": "user",
         "timestamp": "14:30:45"
       },
       {
         "index": 1,
         "text": "Hi, how can I help?",
         "speaker": "assistant",
         "timestamp": "14:30:46"
       }
     ]
   }
```

---

### 4. MESSAGING

#### 4a. Post Message
```
POST /message
├─ Purpose: Log a message in the session
├─ Auth: None
├─ Body (JSON):
│  {
│    "session_id": "f47ac10b...",
│    "text": "Where is the cafeteria?",
│    "speaker": "user"
│  }
└─ Response: {"status": "ok"}

Effect: Message is added to message_log and broadcast to all WebSocket clients
```

---

### 5. VISITOR NAME FLOW

#### 5a. Mark Visitor as Unknown
```
POST /visitor/unknown
├─ Purpose: Trigger name entry prompt
├─ Auth: None
└─ Response: {"status": "asking"}
```

#### 5b. Submit Visitor Name
```
POST /visitor/submit_name
├─ Purpose: Save the name visitor entered
├─ Body Parameters:
│  ├─ name: "John" (visitor's name)
│  └─ save: true (whether to save their data)
└─ Response: {"status": "ok"}
```

#### 5c. Get Name Response
```
GET /visitor/name_response
├─ Purpose: Poll to check if visitor submitted name
├─ Auth: None
└─ Response:
   {
     "ready": true,  # Has visitor entered their name?
     "name": "John", # What name did they enter?
     "save": true    # Do they want to save data?
   }
```

#### 5d. Clear Name Response
```
POST /visitor/clear_response
├─ Purpose: Reset name state (for next visitor)
├─ Auth: None
└─ Response: {"status": "cleared"}
```

---

### 6. FACE RECOGNITION & DATA

#### 6a. Register Face
```
POST /face/register
├─ Purpose: Register a face (called from detection.py)
├─ Auth: None
├─ Body (JSON):
│  {
│    "face_id": "abc123def456",
│    "name": "John Smith",
│    "encoding": [0.1, -0.2, 0.3, ... 128-512 numbers]
│  }
└─ Response: {"status": "ok", "face_id": "abc123def456"}

Note: encoding is the mathematical fingerprint of the face
      generated by face recognition AI (usually 128-512 floats)
```

#### 6b. Delete My Data
```
POST /visitor/delete_my_data?name=<name>
├─ Purpose: GDPR - Delete all data for a visitor
├─ Auth: None
├─ Parameters:
│  └─ name: "John" (visitor's name)
└─ Response (success):
   {
     "success": true,
     "message": "Data for John deleted successfully."
   }
   Or (failure):
   {
     "success": false,
     "message": "No data found."
   }

Effect: Deletes face folder, face database record, and model file
```

---

### 7. WEBSOCKET

#### WebSocket Connection
```
WS /ws
├─ Purpose: Real-time bidirectional communication
├─ Auth: None
├─ How it works:
│  ├─ Client connects: ws://localhost:8000/ws
│  ├─ Client stays connected
│  ├─ Receives broadcasts whenever anything happens
│  └─ Server detects disconnect and cleans up
└─ Broadcast messages received by client:
   {
     "type": "session_start",
     "session": {...}
   }
   or
   {
     "type": "message",
     "text": "...",
     "speaker": "user/assistant"
   }
   or
   {
     "type": "session_end",
     "session_id": "..."
   }
```

---

## DATA FLOW EXAMPLES

### Example 1: New Visitor Session

```
Timeline:
─────────

T=0s: Camera detects unknown face
      ↓
      POST /session/start
      {
        "trigger": "camera",
        "user_name": "Unknown",
        "is_returning": false,
        "face_id": ""
      }
      ↓
      Backend creates session:
      active_session = {
        "session_id": "sess-001",
        "user_name": "Unknown",
        "is_returning": false,
        "visit_count": 1,
        "face_id": "",
        "asking_name": false
      }
      ↓
      Broadcast to all WebSocket clients:
      {"type": "session_start", "session": {...}}
      ↓
      Kiosk screens show: "Welcome! Please enter your name"

T=5s: Visitor types "John Smith" and clicks OK
      ↓
      POST /visitor/submit_name?name=John%20Smith&save=true
      ↓
      Backend stores:
      visitor_name_response = {
        "ready": true,
        "name": "John Smith",
        "save": true
      }
      ↓
      active_session["user_name"] = "John Smith"

T=8s: Visitor asks "Where is the library?"
      ↓
      GET /ask?question=Where%20is%20the%20library?
      ↓
      Backend searches:
      1. Check FAQs → "facility" in FAQs? No exact match
      2. Check Facilities → MATCH! "library" found
         library → {
           "location": "Block A, Ground Floor",
           "timings": "8 AM - 8 PM"
         }
      ↓
      Response: {
        "question": "Where is the library?",
        "answer": "Library is in Block A, Ground Floor. Timings: 8 AM - 8 PM"
      }
      ↓
      Save to database + Broadcast
```

---

### Example 2: Returning Visitor (Face Recognition)

```
Timeline:
─────────

T=0s: Camera detects face
      Face recognition AI analyzes the face
      Sends face encoding to /face/register
      ↓
      Backend looks up in database:
      SELECT * FROM faces WHERE face_id = 'abc123'
      → FOUND! "John Smith" (visit_count: 5, last_seen: 3 days ago)
      ↓
      POST /session/start
      {
        "trigger": "camera",
        "user_name": "John Smith",
        "is_returning": true,
        "visit_count": 6,
        "face_id": "abc123"
      }
      ↓
      Kiosk screens show:
      "Welcome back, John Smith! 
       This is your 6th visit.
       How can I help you today?"

T=5s: Visitor asks "What are the lab timings?"
      ↓
      GET /ask?question=What%20are%20the%20lab%20timings?
      ↓
      Search → Facilities → "lab" found
      ↓
      Response with lab details
      ↓
      Database logs: session_id=xyz, question="...", answer="..."
```

---

### Example 3: Real-time Broadcasting

```
SCENARIO: Multiple screens in different locations

Location A: Kiosk Screen 1          Location B: Kiosk Screen 2
──────────────────────────────      ──────────────────────────────
   [Visitor 1 is here]                 [Visitor 2 is here]
       │                                   │
       └─ WebSocket /ws ─────────┬─────────┘
                                  │
                          ┌───────▼────────┐
                          │ ConnectionMgr  │
                          │ [conn1, conn2] │
                          └───────┬────────┘
                                  │
       ┌─ POST /message ──────────┴─────── POST /message
       │                                      │
   Entry:                                Entry:
   {                                     {
     "session_id": "sess-001",             "session_id": "sess-002",
     "text": "Library location?",          "text": "Fee structure?",
     "speaker": "user"                    "speaker": "user"
   }                                     }
       │                                  │
       └─────────┬──────────────────────┬─┘
                 │                      │
         manager.broadcast()            │
                 │                      │
    Send to all connections:            │
    {                                   │
      "type": "message",                │
      "text": "Library location?",      │
      "speaker": "user"                 │
    }                                   │
         │                          │
         ▼ (Kiosk 1 updates)        ▼ (Kiosk 2 updates)
         │                          │
    Screen 1 shows:             Screen 2 shows:
    "Message received"          "Message received"
    (Real-time, no reload)      (Real-time, no reload)
```

---

## TROUBLESHOOTING

### Problem: "ModuleNotFoundError: No module named 'fastapi'"

**Solution:**
```bash
# Activate your virtual environment
venv\Scripts\activate

# Install requirements
pip install -r requirements.txt

# Specifically install missing module
pip install fastapi uvicorn
```

---

### Problem: "psycopg2.OperationalError: Connection refused"

**Cause:** PostgreSQL not running or DATABASE_URL is wrong

**Solution:**
```bash
# Check PostgreSQL is running
psql --version

# Verify DATABASE_URL in .env file
# Should be like: postgresql://username:password@localhost:5432/database_name

# Test connection:
psql -U username -d database_name -h localhost
```

---

### Problem: "FileNotFoundError: data/college_info.json"

**Cause:** Missing college data file

**Solution:**
```bash
# Create the file with required structure
mkdir -p data

# Create college_info.json with:
{
  "faqs": [],
  "facilities": {},
  "departments": {},
  "administration": {},
  "college": {}
}
```

---

### Problem: Frontend can't connect (CORS error)

**Cause:** Frontend domain not in ALLOWED_ORIGINS

**Solution:**
```bash
# Check .env file has correct origins:
ALLOWED_ORIGINS=http://localhost:3000,http://192.168.1.1:3000

# Restart server after changing
```

---

### Problem: WebSocket messages not received

**Cause:** Client not properly connected to /ws endpoint

**Solution:**
```javascript
// Frontend code - ensure correct connection:
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onopen = () => {
  console.log('WebSocket connected');
  ws.send('Connected'); // Send something to keep alive
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);
  // Update UI here
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};
```

---

### Problem: Questions not returning good answers

**Debugging:**
```bash
# Check college_info.json has good data
cat data/college_info.json | python -m json.tool

# Test the /ask endpoint directly:
curl "http://localhost:8000/ask?question=Who%20is%20the%20principal?"

# Check logs for what's happening
# Look for debug info in console output
```

---

### Problem: Session not persisting to database

**Check:**
```bash
# Verify database connection
psql $DATABASE_URL

# Check if tables exist:
\dt  # List all tables

# Check if data is being saved:
SELECT * FROM sessions LIMIT 5;
SELECT * FROM interactions LIMIT 5;
```

---

## RUNNING & MONITORING

### Start the Server
```bash
# Development mode (with reload on file changes)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production mode (faster, no reload)
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Monitor Live
```bash
# API Documentation (auto-generated)
http://localhost:8000/docs

# Interactive testing:
http://localhost:8000/redoc
```

### View Logs
```bash
# Watch log file (if saved)
tail -f app.log

# Or check console output where you ran uvicorn
```

---

## SUMMARY

```
┌──────────────────────────────────────────────────────────┐
│              HOW THE SYSTEM WORKS                        │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  1. Visitor walks to kiosk                              │
│     ↓                                                   │
│  2. Camera detects face                                 │
│     ↓                                                   │
│  3. POST /session/start (creates session)               │
│     ↓                                                   │
│  4. If unknown: POST /visitor/unknown & ask for name   │
│     ↓                                                   │
│  5. Visitor asks question                               │
│     ↓                                                   │
│  6. GET /ask?question=...                               │
│     ↓                                                   │
│  7. Search knowledge base → Return answer               │
│     ↓                                                   │
│  8. POST /message (log the Q&A)                         │
│     ↓                                                   │
│  9. WebSocket broadcast to all screens                  │
│     ↓                                                   │
│  10. Save to database                                   │
│     ↓                                                   │
│  11. Repeat steps 5-10 until visitor leaves             │
│     ↓                                                   │
│  12. POST /session/end (close session, save)            │
│     ↓                                                   │
│  NEXT VISITOR ARRIVES → START OVER                      │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## QUICK REFERENCE SHEET

| Operation | Endpoint | Method | Purpose |
|-----------|----------|--------|---------|
| Health Check | `/` | GET | Server running? |
| Search FAQ | `/ask?question=...` | GET | Get answer |
| Start Session | `/session/start` | POST | New visitor |
| End Session | `/session/end` | POST | Visitor leaves |
| Current Session | `/session/current` | GET | Who's here? |
| Session History | `/session/messages/{id}` | GET | Chat history |
| Log Message | `/message` | POST | Record message |
| Unknown Visitor | `/visitor/unknown` | POST | Ask name |
| Submit Name | `/visitor/submit_name` | POST | Save name |
| Check Name | `/visitor/name_response` | GET | Poll for name |
| Clear Name | `/visitor/clear_response` | POST | Reset |
| Register Face | `/face/register` | POST | Save face data |
| Delete Data | `/visitor/delete_my_data` | POST | GDPR delete |
| WebSocket | `/ws` | WS | Real-time |

---

**End of Guide**

For more information, see:
- `main_fully_commented.py` - Heavily commented source code
- `database.py` - Database helper functions
- Project README.md - Installation & setup
