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
    get_admission_fee_by_branch, get_admission_requirements
)

# Import your local RAG service components
from backend.llm import initialize_rag_knowledge_base, generate_rag_kiosk_response

load_dotenv()

# basic logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("RNSIT_Receptionist")

ALLOWED_ORIGINS: List[str] = os.getenv("ALLOWED_ORIGINS", "*").split(",")
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

# Set up SQL database tables on startup execution
init_db()

# --- ASYNCHRONOUS ENGINE STARTUP HOOK ---
@app.on_event("startup")
async def startup_event():
    logger.info("[SYSTEM] Booting server core infrastructure...")
    try:
        # Pre-process the JSON files and generate structural vector dimensions instantly
        await initialize_rag_knowledge_base()
        logger.info("[SYSTEM] Local RAG Vector Cache matrix fully established.")
    except Exception as e:
        logger.error(f"[SYSTEM] Startup RAG caching vector routine failed: {e}")

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
        for ws in self.active[:]:
            try:
                await ws.send_json(data)
            except Exception:
                self.active.remove(ws)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)

# --- health check ---
@app.get("/")
def root():
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

    save_session(final_session_id, face_id or None, user_name, is_returning, visit_count)
    await manager.broadcast({"type": "session_start", "session": active_session})
    return {"status": "success", "session_id": final_session_id, "session": active_session}


@app.post("/session/end")
async def end_session_endpoint(session_id: str = None):
    global active_session
    sid = session_id or (active_session["session_id"] if active_session else None)
    if sid:
        end_session(sid)
    active_session = None

    await manager.broadcast({"type": "session_end", "session_id": sid})
    return {"status": "success"}


@app.get("/session/current")
def get_current_session():
    if active_session:
        return {"active": True, **active_session}
    return {"active": False}


@app.get("/session/messages/{session_id}")
def get_session_messages(session_id: str, after: int = 0):
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
        return v[:MAX_QUERY_LENGTH] if len(v) > MAX_QUERY_LENGTH else v


@app.post("/message")
async def post_message(payload: MessagePayload):
    entry = {
        "index":     len(message_log),
        "text":      payload.text,
        "speaker":   payload.speaker,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    message_log.append(entry)
    await manager.broadcast({"type": "message", **entry})
    return {"status": "ok"}


# --- Smart Core Ask / FAQ Router Endpoint ---

@app.get("/ask")
async def ask_kiosk(question: str = Query(..., description="Visitor question")):
    """
    Tiered Production Routing Engine:
    Tier 1: Deterministic SQL Lookups (Fees, Admission Verification paperwork)
    Tier 2: High-Speed Text Intercept Fallbacks (Short conversational phrases)
    Tier 3: Contextual Local RAG Pipeline (Ollama + Llama 3.1 Neural Search Engine)
    """
    q = question.lower().strip()
    sid = active_session["session_id"] if active_session else "unknown"

    # -------------------------------------------------------------------------
    # TIER 1: DETERMINISTIC SQL CHECKS (Fees & Certificate Requirements)
    # -------------------------------------------------------------------------
    if any(kw in q for kw in ["fee", "fees", "cost", "price", "instalment", "payment"]):
        branch_keyword = None
        for b in ["cse", "ai", "data", "cyber", "ece", "vlsi", "eee", "mech", "civil"]:
            if b in q:
                branch_keyword = b
                break
        
        if branch_keyword:
            fee_data = get_admission_fee_by_branch(branch_keyword)
            if fee_data:
                name, annual, inst1, inst2 = fee_data
                if inst2 == 0:
                    answer = f"The annual management quota fee for {name} is ₹{annual:,.2f}. Note that for this branch, it must be paid as a single installment at the time of admission."
                else:
                    answer = f"The annual management fee for {name} is ₹{annual:,.2f}. Parents can split this payment into two parts: ₹{inst1:,.2f} due at admission, and ₹{inst2:,.2f} paid via post-dated cheques over 3 months."
            else:
                answer = "I couldn't find the exact fee mapping for that stream. Management fees at RNSIT range from ₹1,10,000 up to ₹7,50,000 per year depending on the branch. Which specific branch are you looking for?"
        else:
            answer = "Management quota fees range from ₹1,10,000 (Civil) up to ₹7,50,000 per year (Core CSE). If you name a specific engineering branch, I can give you its exact annual cost and installment structure!"
        
        try:
            save_interaction(sid, question, answer)  # Fixed parameter bug
        except Exception as exc:
            logger.exception("Admissions fee DB log failed: %s", exc)
        return {"question": question, "answer": answer}

    if any(kw in q for kw in ["document", "documents", "certificate", "paperwork", "bring", "marks card"]):
        quota = "KCET" if any(k in q for k in ["cet", "kea", "govt"]) else "Management"
        docs = get_admission_requirements(quota)
        
        if docs:
            # Unpacking table positional tuples (document_name, copy_count) securely
            doc_list = "\n".join([f"- {doc} ({doc} copies)" for doc in docs])
            answer = f"For {quota} Quota admissions, you must bring the following original files along with photocopies:\n{doc_list}"
        else:
            answer = "Please bring your 10th and 12th Marks Cards, Transfer Certificate, Entrance Exam Rank Card, and ID card copies to the Admin Block window."
        
        try:
            save_interaction(sid, question, answer)  # Fixed parameter bug
        except Exception as exc:
            logger.exception("Requirements documentation DB log failed: %s", exc)
        return {"question": question, "answer": answer}

    # -------------------------------------------------------------------------
    # TIER 2: STATIC HIGH-SPEED TEXT INTERCEPTS
    # -------------------------------------------------------------------------
    short_greetings = {
        "hi":  "Hi there! Welcome to RNSIT. How can I help you today?",
        "ok":  "Alright! Let me know if you need any further assistance.",
        "hey": "Hey! Welcome to RNS Institute of Technology. What can I help with?",
    }
    if q in short_greetings:
        answer = short_greetings[q]
        try:
            save_interaction(sid, question, answer)
        except Exception as exc:
            logger.exception("Greeting intercept DB log failed: %s", exc)
        return {"question": question, "answer": answer}

    # -------------------------------------------------------------------------
    # TIER 3: CONTEXT-INJECTED LOCAL SEMANTIC RAG INFERENCE (Llama 3.1)
    # -------------------------------------------------------------------------
    try:
        # Pass the current question and the last 6 messages (3 full conversational turns)
        recent_history = message_log[-6:] if message_log else []
        answer = await generate_rag_kiosk_response(question, history=recent_history)
        
    except Exception as exc:
        logger.error(f"Semantic Local AI matching operation failed: {exc}")
        answer = "I am sorry, I am currently having trouble processing that query. Please visit the Admin Block for assistance."
    # save this question+answer interaction to the database
    try:
        save_interaction(sid, question, answer)
    except Exception as exc:
        logger.exception("DB interaction log failed: %s", exc)

    return {"question": question, "answer": answer}


# --- visitor name flow ---

@app.post("/visitor/unknown")
async def visitor_unknown():
    global visitor_name_response, active_session
    visitor_name_response = {"ready": False, "name": "", "save": True}

    if active_session is None:
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
    global visitor_name_response, active_session
    visitor_name_response = {"ready": True, "name": name, "save": save}
    if active_session:
        active_session["asking_name"] = False

    return {"status": "ok"}


@app.get("/visitor/name_response")
def get_name_response():
    return visitor_name_response


@app.post("/visitor/clear_response")
def clear_response():
    global visitor_name_response
    visitor_name_response = {"ready": False, "name": "", "save": True}
    return {"status": "cleared"}


@app.post("/visitor/delete_my_data")
async def delete_my_data(name: str):
    try:
        face_ids = delete_face_by_name(name)
        if not face_ids:
            return {"success": False, "message": f"No data found for {name}."}

        for face_id in face_ids:
            face_dir = PROJECT_ROOT / "faces" / face_id
            if face_dir.exists():
                shutil.rmtree(face_dir)

        model_path = PROJECT_ROOT / "face_model.yml"
        if model_path.exists():
            model_path.unlink()

        return {"success": True, "message": f"Data for {name} deleted successfully."}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


# --- face registration ---

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
    return {"status": "ok", "face_id": payload.face_id}