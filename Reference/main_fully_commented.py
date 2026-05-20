"""
RNSIT DIGITAL RECEPTIONIST - BACKEND SERVER
============================================

This is the main backend server that:
1. Answers visitor questions about the college
2. Manages visitor sessions (who's visiting, what they asked)
3. Handles real-time communication via WebSocket
4. Stores visitor interactions in the database
5. Manages face recognition data

Think of it like a receptionist that:
- Listens to visitor questions (via /ask endpoint)
- Remembers who's visiting (sessions)
- Talks to everyone connected via WebSocket
- Records everything in a logbook (database)
"""

# ═══════════════════════════════════════════════════════════════════════════
# IMPORT STATEMENTS - Load external libraries we need
# ═══════════════════════════════════════════════════════════════════════════

import os
# Reason: To read environment variables (like database password) from .env file
# Example: os.getenv("DATABASE_URL") reads the DATABASE_URL from .env

import json
# Reason: To read and parse JSON files (like college_info.json with FAQ data)
# Example: json.load(f) converts text JSON into Python dictionaries we can search

import uuid
# Reason: To generate unique IDs for each visitor session
# Example: uuid.uuid4() creates something like "f47ac10b-58cc-4372-a567-0e02b2c3d479"

import shutil
# Reason: To delete folders (when visitor asks to delete their data)
# Example: shutil.rmtree(folder) completely removes a folder and everything in it

import logging
# Reason: To write error messages and info messages to a log file
# Example: logger.error("Something went wrong") writes to the application log

from pathlib import Path
# Reason: To work with file paths in a clean way (handles Windows/Mac/Linux differences)
# Example: Path("data") / "college_info.json" creates the correct path for any OS

from datetime import datetime
# Reason: To get the current time and add timestamps to messages
# Example: datetime.now().strftime("%H:%M:%S") gives "14:30:45" format

from typing import Dict, List, Optional, Any
# Reason: To specify what type of data functions accept/return (for code clarity)
# Example: def my_func(name: str) -> str: means "takes a string, returns a string"

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect, HTTPException, status
# Reason: FastAPI is the web framework that handles HTTP requests and WebSocket connections
# - FastAPI: the main web server
# - Query: to parse URL query parameters (like ?question=hello)
# - WebSocket: to handle real-time two-way communication with connected clients
# - WebSocketDisconnect: to detect when a client disconnects
# - HTTPException: to send error responses (404, 401, 500, etc.)
# - status: provides HTTP status codes (200 OK, 404 NOT FOUND, etc.)

from fastapi.middleware.cors import CORSMiddleware
# Reason: To allow frontend (running on different URL) to talk to this backend
# Without CORS, browsers block cross-origin requests for security

from pydantic import BaseModel, Field, field_validator
# Reason: To validate incoming data from clients
# - BaseModel: base class for data validation models
# - Field: to specify validation rules (min/max length, etc.)
# - field_validator: to run custom validation on fields

from dotenv import load_dotenv
# Reason: To read variables from .env file (passwords, API keys, etc.)
# It's safer than putting secrets in the code

# Import our database helper functions
from database import (
    get_db_connection,     # Get a connection to PostgreSQL
    init_db,               # Create tables if they don't exist
    save_session,          # Store session info in database
    end_session,           # Mark a session as ended in database
    save_interaction,      # Store Q&A in database
    delete_face_by_name    # Remove face data for a visitor
)

# ═══════════════════════════════════════════════════════════════════════════
# SETUP LOGGING - So we can track errors and important events
# ═══════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    # What level to log: INFO = important events, DEBUG = detailed info, ERROR = problems
    level=logging.INFO,
    # Format: show timestamp, logger name, severity level, and the message
    # Example output: "2026-05-20 14:30:45,123 - RNSIT_Receptionist - INFO - Server started"
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Create a logger object - we'll use "logger.info()" or "logger.error()" throughout the code
logger = logging.getLogger("RNSIT_Receptionist")

# ═══════════════════════════════════════════════════════════════════════════
# LOAD ENVIRONMENT VARIABLES from .env file
# ═══════════════════════════════════════════════════════════════════════════

# load_dotenv() reads the .env file and makes variables available via os.getenv()
load_dotenv()

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION - Important settings
# ═══════════════════════════════════════════════════════════════════════════

# Allowed origins for CORS - which websites can talk to this backend
# "*" means "allow everyone" (not secure for production)
ALLOWED_ORIGINS: List[str] = os.getenv("ALLOWED_ORIGINS", "*").split(",")
# If ALLOWED_ORIGINS not in .env, defaults to "*"
# The .split(",") converts "http://localhost:3000,http://192.168.1.1" into a list

# Path to the JSON file with all college FAQs and facility info
# Path(__file__).parent gets the directory this script is in
# Then we go to "data" folder and read "college_info.json"
COLLEGE_DATA_PATH: Path = Path(__file__).parent / "data" / "college_info.json"

# Maximum length of a question we accept (longer ones get rejected)
# This prevents someone from sending a 10MB question to crash the server
MAX_QUERY_LENGTH: int = 500

# ═══════════════════════════════════════════════════════════════════════════
# GLOBAL IN-MEMORY STATE - Data that lives while the server is running
# ═══════════════════════════════════════════════════════════════════════════

# Stores the currently active visitor's info (None if no one is visiting)
# Example: {"session_id": "abc123", "user_name": "John", "is_returning": True, ...}
active_session: Optional[Dict[str, Any]] = None

# Stores all messages from current session
# Each entry: {"index": 0, "text": "Hello", "speaker": "user", "timestamp": "14:30:45"}
# This lets the frontend show conversation history
message_log: List[Dict[str, Any]] = []

# Temporary storage for visitor name submission
# "ready": True when they've entered name, False when asking for it
# "name": the name they entered
# "save": whether to save their data
visitor_name_response: Dict[str, Any] = {"ready": False, "name": "", "save": True}

# Cache of college info (loaded once at startup, not reloaded each time)
# Stores FAQs, departments, facilities, administration, etc.
COLLEGE_DATA_CACHE: Dict[str, Any] = {}

# ═══════════════════════════════════════════════════════════════════════════
# LOAD AND CACHE COLLEGE INFO - Read once at startup for performance
# ═══════════════════════════════════════════════════════════════════════════

def load_cached_knowledge_base() -> None:
    """
    Read college_info.json file once and store in memory (COLLEGE_DATA_CACHE).
    This is faster than reading from disk every time someone asks a question.
    """
    global COLLEGE_DATA_CACHE
    # global means we're modifying the global variable, not creating a local one
    
    try:
        # Check if college_info.json file exists
        if COLLEGE_DATA_PATH.exists():
            # Open the file in read mode, using UTF-8 encoding (handles all languages)
            with open(COLLEGE_DATA_PATH, "r", encoding="utf-8") as f:
                # json.load() reads the file and converts JSON text to Python dict
                COLLEGE_DATA_CACHE = json.load(f)
            # Log a success message
            logger.info("Knowledge base JSON profile read and cached into RAM memory layout.")
        else:
            # File doesn't exist - log an error but don't crash
            logger.error(f"Critical asset dependency footprint missing at: {COLLEGE_DATA_PATH}")
    except Exception as exc:
        # If anything goes wrong (bad JSON, permissions, etc.), catch the error
        # but don't crash the server
        logger.error(f"Failed parsing local static semantic records into core application framework: {exc}")

# Call this function now to load the data when server starts
init_db()
load_cached_knowledge_base()

# ═══════════════════════════════════════════════════════════════════════════
# NLP (Natural Language Processing) - Help understand what visitors ask
# ═══════════════════════════════════════════════════════════════════════════

# Short greetings that we recognize
GREETINGS_MAP = {
    'hi': 'Hi there! Welcome to RNSIT. How can I help you today?',
    'ok': 'Alright! Let me know if you need any further assistance.',
    'hey': 'Hey! Welcome to RNS Institute of Technology. What can I help you with?'
}

# Words to ignore when searching (they don't add meaning)
# Example: "where is the library" - we ignore "is" and "the", search for "where" and "library"
STOP_WORDS = {
    "is", "the", "where", "can", "you", "tell", "me", "who", "what", "how", "of", "in",
    "at", "a", "an", "are", "was", "i", "do", "does", "please", "to", "find", "get",
    "go", "about", "any", "have", "which", "when", "there", "its", "your"
}

# ═══════════════════════════════════════════════════════════════════════════
# WEBSOCKET CONNECTION MANAGER - Handle real-time connections
# ═══════════════════════════════════════════════════════════════════════════

class ConnectionManager:
    """
    Manages all active WebSocket connections.
    
    Think of it like a group chat:
    - connect() = someone joins the chat
    - disconnect() = someone leaves the chat
    - broadcast() = send a message to everyone in the chat
    """
    
    def __init__(self) -> None:
        """
        Initialize the manager with an empty list of connections.
        When we create a ConnectionManager(), active_connections starts as []
        """
        # This will store all active WebSocket connections
        # Each WebSocket is a connection to one client
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """
        Accept a new WebSocket connection and add it to our list.
        
        Args:
            websocket: The new connection from a client
        """
        # Accept the connection (tell the client "yes, I'm ready to talk")
        await websocket.accept()
        # Add this connection to our list so we can send messages to it later
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove a disconnected WebSocket from our list.
        
        Args:
            websocket: The connection that's disconnecting
        """
        # Only remove if it's actually in the list (prevent errors)
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """
        Send a message to all connected clients.
        If a connection is dead, remove it.
        
        Args:
            message: Dictionary to send as JSON
                     Example: {"type": "message", "text": "Hello everyone"}
        """
        # Create a copy of the list so we can modify it while looping
        for conn in list(self.active_connections):
            try:
                # Send the message as JSON to this connection
                # await = wait for the sending to complete before moving to next connection
                await conn.send_json(message)
            except Exception:
                # If sending failed (connection is dead), remove it
                self.disconnect(conn)

# Create one global ConnectionManager instance that all endpoints will use
manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint - clients connect here for real-time updates.
    
    When a client connects to /ws, this function runs.
    It keeps the connection open until the client disconnects.
    """
    # Register this new connection
    await manager.connect(websocket)
    try:
        # Keep the connection alive by waiting for messages
        # This loop never breaks unless the client disconnects
        while True:
            # Wait for a message from the client
            # (We don't actually use the message, just checking if they're still connected)
            await websocket.receive_text()
    except WebSocketDisconnect:
        # Client disconnected - remove them from our list
        manager.disconnect(websocket)

# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC DATA VALIDATION MODELS - Validate incoming data from clients
# ═══════════════════════════════════════════════════════════════════════════

class MessagePayload(BaseModel):
    """
    Validates incoming messages from frontend.
    
    When frontend sends a POST request to /message, we check:
    1. Does it have a session_id? (required)
    2. Does it have text? (required, between 1-1000 chars)
    3. Does it have a speaker? (required)
    
    If any check fails, FastAPI automatically returns an error.
    """
    # session_id must be a string and not empty
    session_id: str = Field(..., min_length=1)
    # text must be 1-1000 characters
    text: str = Field(..., min_length=1, max_length=1000)
    # speaker must be a string and not empty (usually "user" or "assistant")
    speaker: str = Field(..., min_length=1)


class RegisterFacePayload(BaseModel):
    """
    Validates face registration data from detection.py.
    """
    # Unique ID for this face (usually a hash)
    face_id: str = Field(..., min_length=1, max_length=128)
    # Person's name
    name: str = Field(..., min_length=1, max_length=128)
    # Face encoding - 128-512 floating point numbers that describe the face
    # (This is the "fingerprint" of a face from face recognition AI)
    encoding: List[float] = Field(..., min_length=128, max_length=512)

    @field_validator("encoding")
    @classmethod
    def validate_vector_boundaries(cls, v: List[float]) -> List[float]:
        """
        Custom validation: ensure each encoding value is between -10.0 and 10.0.
        
        This catches bad data from the face detection algorithm.
        If any value is outside this range, reject the entire request.
        """
        if any(not (-10.0 <= x <= 10.0) for x in v):
            raise ValueError("Encoding structural vector values out of math boundaries (-10.0 to 10.0).")
        return v

# ═══════════════════════════════════════════════════════════════════════════
# CREATE THE FASTAPI APPLICATION - The main web server
# ═══════════════════════════════════════════════════════════════════════════

# This creates the actual web server. All endpoints will be attached to it.
app = FastAPI(title="RNSIT Digital Receptionist")

# Add CORS middleware - allows frontend to make requests
app.add_middleware(
    CORSMiddleware,
    # Which websites are allowed to make requests
    allow_origins=ALLOWED_ORIGINS,
    # Whether to allow cookies and authorization headers
    allow_credentials=True if ALLOWED_ORIGINS != ["*"] else False,
    # Allow all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_methods=["*"],
    # Allow any headers from the client
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS - The "doors" clients can knock on to get things done
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/")
def read_system_root_health():
    """
    Health check endpoint - just confirms the server is running.
    Clients can hit this to see if the server is alive.
    GET / returns: {"status": "RNSIT Kiosk Backend is Live"}
    """
    return {"status": "RNSIT Kiosk Backend is Live"}

# ─────────────────────────────────────────────────────────────────────────
# SESSION MANAGEMENT ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────

@app.post("/session/start")
async def start_session(
    trigger: str = "camera",           # What triggered the session start (camera, manual, etc.)
    user_name: str = "Guest",          # Visitor's name
    is_returning: bool = False,        # True if we recognize them (face match)
    visit_count: int = 1,              # How many times they've visited before
    face_id: str = "",                 # Their face ID (if recognized)
    session_id: str = ""               # Specific session ID (if provided)
):
    """
    Start a new visitor session.
    
    Called when:
    1. Camera recognizes a face
    2. Someone walks up as a new visitor
    3. Frontend explicitly starts a session
    
    This initializes everything we need to track their visit.
    """
    global active_session, message_log
    # global = we're modifying the global variables, not creating local ones
    
    # Determine the session ID to use
    # Priority: face_id > provided session_id > generate new UUID
    # This ensures the same person always gets the same session_id
    final_session_id = face_id if face_id else (session_id if session_id else str(uuid.uuid4()))
    
    # Create a dictionary with all session info
    active_session = {
        "session_id": final_session_id,       # Unique ID for this session
        "user_name": user_name,                # Visitor's name
        "is_returning": is_returning,          # Did we recognize them?
        "visit_count": visit_count,            # How many previous visits
        "face_id": face_id,                    # Their face ID (if recognized)
        "asking_name": False,                  # Are we waiting for their name?
    }
    
    # Start with an empty message log for this session
    message_log = []

    # Save to database so we have a record even if the server crashes
    try:
        save_session(
            final_session_id,
            face_id if face_id else None,  # Only save face_id if we have one
            user_name,
            is_returning,
            visit_count
        )
    except Exception as db_err:
        # If database save fails, log it but keep going
        logger.error(f"Operational intercept failure linking database context profiles: {db_err}")

    # Tell all connected WebSocket clients about this new session
    # Everyone's screen will update in real-time
    await manager.broadcast({"type": "session_start", "session": active_session})
    
    # Return the session info to the client
    return {
        "status": "success",
        "session_id": final_session_id,
        "session": active_session
    }


@app.post("/session/end")
async def end_session_endpoint(session_id: Optional[str] = None):
    """
    End the current visitor session.
    
    Called when:
    1. Visitor leaves
    2. Session times out
    3. Visitor clicks "Done"
    """
    global active_session
    
    # Get the session ID to end
    # Use provided ID, or the active one, or None if no session
    sid = session_id or (active_session["session_id"] if active_session else None)
    
    # Save the end time in database
    if sid:
        try:
            end_session(sid)
        except Exception as e:
            logger.error(f"Downstream tracking link termination fault: {e}")
            
    # Clear the active session (no one is visiting now)
    active_session = None
    
    # Notify all WebSocket clients that session ended
    await manager.broadcast({"type": "session_end", "session_id": sid})
    
    return {"status": "success"}


@app.get("/session/current")
def get_current_session():
    """
    Get info about the currently active session.
    
    Frontend uses this to:
    1. Show who's visiting
    2. Check if a session is active
    3. Know which session_id to use for messages
    
    Returns: {"active": True, "session_id": "...", "user_name": "..."} or {"active": False}
    """
    if active_session:
        # Return all session info, plus "active": True
        return {"active": True, **active_session}
    # No active session
    return {"active": False}


@app.get("/session/messages/{session_id}")
def get_session_messages(session_id: str, after: int = 0):
    """
    Get all messages from a session (for conversation history).
    
    Args:
        session_id: Which session to get messages from
        after: Only get messages with index > this number
               (This lets us get only NEW messages, not the whole history)
    
    Returns: {"messages": [...all messages...]}
    """
    # Filter to only messages after a certain index
    # This is efficient - frontend only downloads new messages
    msgs = [m for m in message_log if m.get("index", 0) > after]
    return {"messages": msgs}

# ─────────────────────────────────────────────────────────────────────────
# MESSAGE ENDPOINT - Log visitor messages
# ─────────────────────────────────────────────────────────────────────────

@app.post("/message")
async def post_message(payload: MessagePayload):
    """
    Log a message from the visitor (or assistant).
    
    Called when:
    1. Visitor types and sends a message
    2. Assistant/AI generates a response
    
    This stores the message and broadcasts to all connected clients.
    """
    # Create a message entry with all the info
    entry = {
        "index": len(message_log),              # Position in conversation
        "text": payload.text,                    # What they said
        "speaker": payload.speaker,              # Who said it (user or assistant)
        "timestamp": datetime.now().strftime("%H:%M:%S"),  # When (14:30:45 format)
    }
    
    # Add to the message log for this session
    message_log.append(entry)
    
    # Broadcast to all WebSocket clients so they see it in real-time
    await manager.broadcast({"type": "message", **entry})
    
    return {"status": "ok"}

# ─────────────────────────────────────────────────────────────────────────
# KNOWLEDGE BASE SEARCH ENDPOINT - Answer visitor questions
# ─────────────────────────────────────────────────────────────────────────

@app.get("/ask")
def ask_kiosk(question: str = Query(..., max_length=MAX_QUERY_LENGTH)):
    """
    Main endpoint - Search knowledge base for answers to questions.
    
    Called when visitor types a question like "Where is the library?"
    
    This searches:
    1. FAQs (frequently asked questions)
    2. Facilities (library, lab, cafeteria, etc.)
    3. Departments (CSE, ECE, Mechanical, etc.)
    4. Administration staff
    5. General college info
    
    Returns the best match found, or a default "sorry" message.
    """
    # Lowercase the question so matching is case-insensitive
    # Strip whitespace from start/end
    q_clean = question.lower().strip()
    
    # 1. CHECK FOR GREETINGS FIRST
    # If they just say "hi", respond friendly immediately
    if q_clean in GREETINGS_MAP:
        return {'question': question, 'answer': GREETINGS_MAP[q_clean]}
    
    # 2. FILTER QUESTION INTO MEANINGFUL WORDS
    # Remove stop words (is, the, where, etc.) and keep only significant words
    # Also only keep words longer than 2 characters (no "a" or "is")
    search_words = [w for w in q_clean.split() if w not in STOP_WORDS and len(w) > 2]
    
    # We'll keep track of the best answer found and its score
    matched_answer = None
    highest_score = 0

    # 3. SEARCH FAQs - Do any FAQ questions match?
    # Give points for each word from the visitor that appears in an FAQ question
    for faq in COLLEGE_DATA_CACHE.get("faqs", []):
        faq_q = faq["question"].lower()
        # Count matches: each matching word = 2 points
        score = sum(2 for w in search_words if w in faq_q)
        # Keep track of the best match
        if score > highest_score:
            highest_score = score
            matched_answer = faq["answer"]

    # 4. SEARCH FACILITIES - Is any facility mentioned?
    # Like "library", "cafeteria", "lab", etc.
    for facility_name, facility_val in COLLEGE_DATA_CACHE.get("facilities", {}).items():
        # Check if facility name is mentioned in the question
        if facility_name in q_clean or any(word in facility_name for word in search_words):
            # If facility has details (dict), format them nicely
            if isinstance(facility_val, dict):
                parts = []
                # Add each field if it exists
                for prop in ["name", "location", "timings", "details", "usage"]:
                    if facility_val.get(prop):
                        # Add a label for location and timings
                        prefix = f"{prop.title()}: " if prop in ["location", "timings"] else ""
                        parts.append(f"{prefix}{facility_val[prop]}")
                candidate_str = ". ".join(parts)
            else:
                # If it's just a simple string, use it directly
                candidate_str = str(facility_val)
            
            # Facility matches get score 3 (better than FAQ)
            if highest_score < 3:
                matched_answer = candidate_str
                highest_score = 3
            break  # Stop looking (first facility match wins)

    # 5. SEARCH DEPARTMENTS - Are they asking about a department?
    # Like "Computer Science", "Mechanical Engineering", etc.
    if highest_score < 2:  # Only search if we didn't find something better
        for dept, details in COLLEGE_DATA_CACHE.get("departments", {}).items():
            # Normalize department name (remove underscores, lowercase)
            normalized_dept = dept.replace("_", " ").lower()
            # Check if department name appears in question
            if any(word in normalized_dept for word in search_words) or normalized_dept in q_clean:
                if isinstance(details, dict):
                    dept_upper = dept.upper()
                    # Different answer depending on what they asked about
                    if any(word in q_clean for word in ["hod", "head", "who"]):
                        # They asked about the department head
                        matched_answer = f"HOD of {dept_upper} is {details.get('hod', 'not listed')}."
                    elif any(word in q_clean for word in ["intake", "seats", "students"]):
                        # They asked about admission capacity
                        matched_answer = f"{dept_upper} has intake of {details.get('intake', '180')} students."
                    elif any(word in q_clean for word in ["floor", "location", "where", "block"]):
                        # They asked where it is
                        matched_answer = f"{dept_upper} is on {details.get('floor', 'ground floor')}."
                    else:
                        # Generic department info
                        matched_answer = f"{dept_upper} - Floor: {details.get('floor', '')}, HOD: {details.get('hod', '')}."
                highest_score = 2
                break

    # 6. SEARCH ADMINISTRATION - Are they asking about admin staff?
    if highest_score < 2:
        for key, val in COLLEGE_DATA_CACHE.get("administration", {}).items():
            # Normalize key (remove underscores, lowercase)
            normalized_admin_key = key.replace("_", " ").lower()
            # Check if admin staff name appears in question
            if any(word in normalized_admin_key for word in search_words):
                if isinstance(val, dict):
                    name = val.get("name", "")
                    qual = val.get("qualification", "")
                    # Format like "Principal: Dr. John Smith, PhD"
                    matched_answer = f"{normalized_admin_key.title()}: {name}" + (f", {qual}" if qual else "")
                else:
                    matched_answer = str(val)
                highest_score = 2
                break

    # 7. SEARCH GENERAL COLLEGE INFO
    # Like "founded year", "address", "contact", etc.
    if highest_score < 2:
        for key, val in COLLEGE_DATA_CACHE.get("college", {}).items():
            # Check if any search word appears in the key
            if any(word in key.lower() for word in search_words):
                matched_answer = str(val)
                highest_score = 2
                break

    # 8. FALLBACK - No match found, send apology message
    final_reply = matched_answer or "I am sorry, I do not have that information. Please visit the Admin Block for assistance."

    # Save this interaction to database (so we can learn from it later)
    try:
        sid = active_session["session_id"] if active_session else "unknown"
        save_interaction(sid, question, final_reply)
    except Exception as db_log_err:
        logger.error(f"Telemetry pipeline failed capturing interaction to target data table: {db_log_err}")

    return {"question": question, "answer": final_reply}

# ─────────────────────────────────────────────────────────────────────────
# VISITOR NAME FLOW ENDPOINTS - Handle unknown visitors
# ─────────────────────────────────────────────────────────────────────────

@app.post("/visitor/unknown")
async def visitor_unknown():
    """
    Called when camera doesn't recognize the visitor's face.
    
    This asks the visitor to enter their name so we can add them to the system.
    """
    global visitor_name_response, active_session
    
    # Reset name response state
    visitor_name_response = {"ready": False, "name": "", "save": True}
    
    # If no session exists yet, create one
    if active_session is None:
        active_session = {
            "session_id": str(uuid.uuid4()),
            "user_name": "Unknown",
            "is_returning": False,
            "visit_count": 1,
            "face_id": "",
            "asking_name": True,  # Flag: we're waiting for their name
        }
    else:
        # Session exists, just mark that we're asking for the name
        active_session["asking_name"] = True
    
    return {"status": "asking"}


@app.post("/visitor/submit_name")
async def submit_name(name: str = "Guest", save: bool = True):
    """
    Called when visitor submits their name via the screen.
    
    Args:
        name: The name they entered
        save: Whether they want to save their data for next time
    """
    global visitor_name_response, active_session
    
    # Store the submitted name and save preference
    visitor_name_response = {"ready": True, "name": name, "save": save}
    
    # Update the active session to mark name collection complete
    if active_session:
        active_session["asking_name"] = False
    
    return {"status": "ok"}


@app.get("/visitor/name_response")
def get_name_response():
    """
    Frontend polls this to check if visitor has submitted their name.
    
    Returns: {"ready": True/False, "name": "...", "save": True/False}
    """
    return visitor_name_response


@app.post("/visitor/clear_response")
def clear_response():
    """
    Clear the name response state (when starting a new session).
    """
    global visitor_name_response
    visitor_name_response = {"ready": False, "name": "", "save": True}
    return {"status": "cleared"}


@app.post("/visitor/delete_my_data")
async def delete_my_data(name: str):
    """
    GDPR compliance - visitor can ask to delete all their data.
    
    This removes:
    1. Their face data (encodings)
    2. Their interaction history
    3. Trained face recognition model
    
    Called when: Visitor clicks "Delete my data" or "Forget me"
    """
    try:
        # Find all face records for this person
        face_ids = delete_face_by_name(name)
        
        # If no data found, return error
        if not face_ids:
            return {"success": False, "message": f"No data found for {name}."}
        
        # Delete face directories
        # Each face has a folder like "faces/abc123def456/"
        for face_id in face_ids:
            face_dir = Path("faces") / face_id
            # If folder exists, delete it and everything in it
            if face_dir.exists():
                shutil.rmtree(face_dir)  # rmtree = "remove tree" = delete folder recursively
        
        # Delete the trained face model file
        # This forces retraining next time we need face detection
        model_path = Path("face_model.yml")
        if model_path.exists():
            model_path.unlink()  # unlink = delete file
        
        return {"success": True, "message": f"Data for {name} deleted successfully."}
    except Exception as exc:
        # If something goes wrong, log and return error
        logger.critical(f"Filesystem unlinking task raised catastrophic runtime failures: {exc}")
        return {"success": False, "message": str(exc)}

# ─────────────────────────────────────────────────────────────────────────
# FACE REGISTRATION ENDPOINT - Called from detection.py
# ─────────────────────────────────────────────────────────────────────────

@app.post("/face/register")
async def register_face(payload: RegisterFacePayload):
    """
    Register a new face (or update existing one).
    
    Called from detection.py when:
    1. A new face is detected and captured
    2. Existing visitor is recognized again (update last_seen time)
    
    The face encoding is the mathematical "fingerprint" of the face.
    128-512 numbers that uniquely identify this person.
    """
    # For now, just return success
    # In the future, this should save to database
    return {"status": "ok", "face_id": payload.face_id}
