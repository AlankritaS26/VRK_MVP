"""
RNSIT Digital Receptionist - Backend Server

HOW TO RUN (always from VRK_MVP/ folder, not from inside backend/):
    python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
"""

import os
import json
import uuid
import shutil
import logging
from pathlib import Path
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

# add project root to path so "from backend.xxx import" works
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import (
    get_db_connection, init_db,
    save_session, end_session, save_interaction,
    delete_face_by_name,
)

load_dotenv()

# basic logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("RNSIT_Receptionist")

# --- config (change these in .env file) ---
# ALLOWED_ORIGINS: which websites can talk to this server (comma separated)
# COLLEGE_DATA_PATH: the JSON file with all college info
# MAX_QUERY_LENGTH: max characters allowed in a question
ALLOWED_ORIGINS: List[str] = os.getenv("ALLOWED_ORIGINS", "*").split(",")
COLLEGE_DATA_PATH: Path = PROJECT_ROOT / "data" / "college_info.json"
MAX_QUERY_LENGTH: int = 500

# create the app
app = FastAPI(title="RNSIT Digital Receptionist")

# allow frontend to talk to this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True if ALLOWED_ORIGINS != ["*"] else False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# set up database tables on startup
init_db()

# college data lives here after loading from disk
COLLEGE_DATA_CACHE: Dict[str, Any] = {}


def load_college_data() -> Dict[str, Any]:
    """Load college_info.json into memory so we don't read the file on every request."""
    global COLLEGE_DATA_CACHE
    try:
        if COLLEGE_DATA_PATH.exists():
            with open(COLLEGE_DATA_PATH, encoding="utf-8") as fh:
                COLLEGE_DATA_CACHE = json.load(fh)
                logger.info("Loaded college data with %d top-level keys", len(COLLEGE_DATA_CACHE))
        else:
            COLLEGE_DATA_CACHE = {}
            logger.warning("College data file not found: %s", COLLEGE_DATA_PATH)
    except Exception as exc:
        logger.exception("Failed to load college data: %s", exc)
        COLLEGE_DATA_CACHE = {}
    return COLLEGE_DATA_CACHE


# load college data when server starts
load_college_data()

# --- in-memory state for the current visitor ---
active_session: dict | None = None
message_log: list[dict] = []
visitor_name_response: dict = {"ready": False, "name": "", "save": True}


# --- websocket manager ---
class ConnectionManager:
    """Keeps track of all open websocket connections and sends them messages."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, data: dict):
        # send to all connected clients, remove any that have disconnected
        for ws in self.active[:]:
            try:
                await ws.send_json(data)
            except Exception:
                self.active.remove(ws)


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # keep the connection open until the client disconnects
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


# --- health check ---
@app.get("/")
def root():
    # just confirms the server is running
    return {"status": "RNSIT Kiosk Backend is Live"}


# --- session endpoints ---

@app.post("/session/start")
async def start_session(
    trigger: str = "camera",
    user_name: str = "Guest",
    is_returning: bool = False,
    visit_count: int = 1,
    face_id: str = "",
    session_id: str = "",
):
    # start a new visitor session (or resume if we know their face)
    # session id priority: face_id > provided session_id > random new id
    global active_session, message_log

    final_session_id = face_id or session_id or str(uuid.uuid4())

    active_session = {
        "session_id":   final_session_id,
        "user_name":    user_name,
        "is_returning": is_returning,
        "visit_count":  visit_count,
        "face_id":      face_id,
        "asking_name":  False,
    }
    message_log = []

    # save to database
    save_session(final_session_id, face_id or None, user_name, is_returning, visit_count)

    # tell the frontend a session started
    await manager.broadcast({"type": "session_start", "session": active_session})
    return {"status": "success", "session_id": final_session_id, "session": active_session}


@app.post("/session/end")
async def end_session_endpoint(session_id: str = None):
    # end the current session in memory and in the database
    global active_session

    sid = session_id or (active_session["session_id"] if active_session else None)
    if sid:
        end_session(sid)
    active_session = None

    await manager.broadcast({"type": "session_end", "session_id": sid})
    return {"status": "success"}


@app.get("/session/current")
def get_current_session():
    # returns the active session, or {active: False} if nobody is at the kiosk
    if active_session:
        return {"active": True, **active_session}
    return {"active": False}


@app.get("/session/messages/{session_id}")
def get_session_messages(session_id: str, after: int = 0):
    # return messages newer than the given index (used for polling)
    msgs = [m for m in message_log if m.get("index", 0) > after]
    return {"messages": msgs}


# --- message endpoint ---

class MessagePayload(BaseModel):
    session_id: str = Field(..., description="Session identifier")
    text: str = Field(..., description="Message text from visitor or system")
    speaker: str = Field(..., description="Speaker id/name")

    @field_validator("text")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        return v.strip()

    @field_validator("text")
    @classmethod
    def _limit_length(cls, v: str) -> str:
        # cut off if too long
        return v[:MAX_QUERY_LENGTH] if len(v) > MAX_QUERY_LENGTH else v


@app.post("/message")
async def post_message(payload: MessagePayload):
    # save message to log and push it to the frontend
    entry = {
        "index":     len(message_log),
        "text":      payload.text,
        "speaker":   payload.speaker,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    message_log.append(entry)
    await manager.broadcast({"type": "message", **entry})
    return {"status": "ok"}


# --- ask / FAQ endpoint ---

@app.get("/ask")
def ask_kiosk(question: str = Query(..., description="Visitor question")):
    """
    Tries to answer the visitor's question using college_info.json.
    Checks in this order: FAQs → Facilities → Departments → Administration → College info → Fallback
    """
    global COLLEGE_DATA_CACHE
    if not COLLEGE_DATA_CACHE:
        load_college_data()
    data = COLLEGE_DATA_CACHE or {}

    q = question.lower().strip()

    # ignore these common words when matching
    stop_words = {
        "is","the","where","can","you","tell","me","who","what","how","of","in",
        "at","a","an","are","was","i","do","does","please","to","find","get",
        "go","about","any","have","which","when","there","its","your",
    }

    # handle short greetings before filtering strips everything out
    short_greetings = {
        "hi":  "Hi there! Welcome to RNSIT. How can I help you today?",
        "ok":  "Alright! Let me know if you need any further assistance.",
        "hey": "Hey! Welcome to RNS Institute of Technology. What can I help you with?",
    }
    if q in short_greetings:
        return {"question": question, "answer": short_greetings[q]}

    # keywords = question words minus stopwords, longer than 2 chars
    words = [w for w in q.split() if w not in stop_words and len(w) > 2]

    answer = None
    best = 0  # best match score so far

    # 1. check FAQs — score by how many keywords match the stored question
    for faq in data.get("faqs", []):
        score = sum(2 for w in words if w in faq["question"].lower())
        if score > best:
            best = score
            answer = faq["answer"]

    # 2. check facilities — match by facility name
    for fname, fval in data.get("facilities", {}).items():
        if fname in q or any(w in fname for w in words):
            if isinstance(fval, dict):
                parts = []
                if fval.get("name"):      parts.append(fval["name"])
                if fval.get("location"):  parts.append("Location: " + fval["location"])
                if fval.get("timings"):   parts.append("Timings: "  + fval["timings"])
                if fval.get("details"):   parts.append(fval["details"])
                if fval.get("usage"):     parts.append(fval["usage"])
                candidate = ". ".join(parts)
            else:
                candidate = str(fval)
            if best < 3:
                answer = candidate
                best = 3
            break

    # 3. check departments — give specific info based on what they asked
    if best < 2:
        for dept, details in data.get("departments", {}).items():
            dc = dept.replace("_", " ").lower()
            if any(w in dc for w in words) or dc in q:
                if isinstance(details, dict):
                    if any(w in q for w in ["hod", "head", "who"]):
                        answer = f"HOD of {dept.upper()} is {details.get('hod', 'not listed')}."
                    elif any(w in q for w in ["intake", "seats", "students"]):
                        answer = f"{dept.upper()} has intake of {details.get('intake', '180')} students."
                    elif any(w in q for w in ["floor", "location", "where", "block"]):
                        answer = f"{dept.upper()} is on {details.get('floor', 'ground floor')}."
                    else:
                        answer = f"{dept.upper()} - Floor: {details.get('floor', '')}, HOD: {details.get('hod', '')}."
                best = 2
                break

    # 4. check administration — match by role name
    if best < 2:
        for key, val in data.get("administration", {}).items():
            kc = key.replace("_", " ").lower()
            if any(w in kc for w in words):
                if isinstance(val, dict):
                    name = val.get("name", "")
                    qual = val.get("qualification", "")
                    answer = kc.title() + ": " + name + (", " + qual if qual else "")
                else:
                    answer = str(val)
                best = 2
                break

    # 5. check general college info
    if best < 2:
        for key, val in data.get("college", {}).items():
            if any(w in key.lower() for w in words):
                answer = str(val)
                best = 2
                break

    # 6. nothing matched — send them to admin
    if not answer:
        answer = "I am sorry, I do not have that information. Please visit the Admin Block for assistance."

    # save this question+answer to the database (ignore errors)
    try:
        sid = active_session["session_id"] if active_session else "unknown"
        save_interaction(sid, question, answer)
    except Exception as exc:
        logger.exception("DB interaction log failed: %s", exc)

    return {"question": question, "answer": answer}


# --- visitor name flow ---

@app.post("/visitor/unknown")
async def visitor_unknown():
    # called when the camera doesn't recognise someone — start asking for their name
    global visitor_name_response, active_session

    visitor_name_response = {"ready": False, "name": "", "save": True}

    if active_session is None:
        # create a basic session so other endpoints don't break
        active_session = {
            "session_id":   str(uuid.uuid4()),
            "user_name":    "Unknown",
            "is_returning": False,
            "visit_count":  1,
            "face_id":      "",
            "asking_name":  True,
        }
    else:
        active_session["asking_name"] = True

    return {"status": "asking"}


@app.post("/visitor/submit_name")
async def submit_name(name: str = "Guest", save: bool = True):
    # visitor typed their name on the kiosk
    # save=True means store their face for next time, save=False means keep visit anonymous
    global visitor_name_response, active_session

    visitor_name_response = {"ready": True, "name": name, "save": save}
    if active_session:
        active_session["asking_name"] = False

    return {"status": "ok"}


@app.get("/visitor/name_response")
def get_name_response():
    # detection.py polls this to check if the visitor has typed their name yet
    return visitor_name_response


@app.post("/visitor/clear_response")
def clear_response():
    # reset after detection.py has read the name
    global visitor_name_response
    visitor_name_response = {"ready": False, "name": "", "save": True}
    return {"status": "cleared"}


@app.post("/visitor/delete_my_data")
async def delete_my_data(name: str):
    # delete everything we have stored for a visitor (face images + database records)
    try:
        face_ids = delete_face_by_name(name)
        if not face_ids:
            return {"success": False, "message": f"No data found for {name}."}

        # delete face image folders from disk
        for face_id in face_ids:
            face_dir = PROJECT_ROOT / "faces" / face_id
            if face_dir.exists():
                shutil.rmtree(face_dir)

        # delete the trained model so it gets rebuilt without this person
        model_path = PROJECT_ROOT / "face_model.yml"
        if model_path.exists():
            model_path.unlink()

        return {"success": True, "message": f"Data for {name} deleted successfully."}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


# --- face registration (called by detection.py) ---

class RegisterFacePayload(BaseModel):
    face_id: str = Field(..., description="Unique face id")
    name: str = Field(..., description="Person's name")
    encoding: List[float] = Field(..., description="Face encoding vector")

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("encoding")
    @classmethod
    def _validate_encoding(cls, v: List[float]) -> List[float]:
        if not v:
            raise ValueError("encoding must be a non-empty list of floats")
        return v


@app.post("/face/register")
async def register_face(payload: RegisterFacePayload):
    # detection.py sends new face data here after capturing it
    return {"status": "ok", "face_id": payload.face_id}