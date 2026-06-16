"""
RNSIT Digital Receptionist - Backend Server

HOW TO RUN (always from VRK_MVP/ folder):
    python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
"""

import os
import uuid
import shutil
import logging
import hashlib
import string
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List
import sys

import redis
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import (
    init_db,
    save_session, end_session, save_interaction,
    delete_face_by_name, update_face_seen,
    get_admission_fee_by_branch, get_admission_requirements,
)
from backend.llm import initialize_rag_knowledge_base, generate_rag_kiosk_response
from backend.stt import transcribe_audio
from backend.tts import text_to_speech

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("RNSIT_Kiosk")

ALLOWED_ORIGINS: List[str] = os.getenv("ALLOWED_ORIGINS", "*").split(",")
MAX_QUERY_LENGTH: int = 500
SESSION_TIMEOUT_SECONDS: int = 120   # auto-end session after 2 min no activity

DOMAINS_CORRECTIONS = {
    "pricipal":  "principal",
    "prinsipal": "principal",
    "libary":    "library",
    "placment":  "placement",
    "fees":      "fee",
}

app = FastAPI(title="RNSIT Digital Receptionist")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOWED_ORIGINS != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis / Memurai
try:
    redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
    redis_client.ping()
    logger.info("[REDIS] Connected to Memurai caching engine.")
except Exception as e:
    logger.warning("[REDIS] Memurai unreachable: %s", e)
    redis_client = None

# In-memory state
active_session: dict | None = None
message_log: list[dict] = []
visitor_name_response: dict = {"ready": False, "name": "", "save": True}
_last_activity_ts: float = 0.0   # updated on every /ask call

init_db()


# ==========================================
# STARTUP
# ==========================================

@app.on_event("startup")
async def startup_event():
    logger.info("[SYSTEM] Booting server...")
    try:
        await initialize_rag_knowledge_base()
        logger.info("[SYSTEM] RAG vector cache loaded.")
    except Exception as e:
        logger.error("[SYSTEM] RAG startup failed: %s", e)
    # Start background session timeout checker
    asyncio.create_task(_session_timeout_loop())


# ==========================================
# SESSION TIMEOUT BACKGROUND TASK
# ==========================================

async def _session_timeout_loop():
    """Every 30s, check if session has been idle for SESSION_TIMEOUT_SECONDS."""
    global active_session, _last_activity_ts
    while True:
        await asyncio.sleep(30)
        if active_session and _last_activity_ts > 0:
            idle = datetime.now().timestamp() - _last_activity_ts
            if idle >= SESSION_TIMEOUT_SECONDS:
                logger.info(f"[SESSION] Timeout after {idle:.0f}s idle — ending session")
                sid = active_session.get("session_id")
                if sid:
                    end_session(sid)
                active_session    = None
                _last_activity_ts = 0.0
                await manager.broadcast({"type": "session_end", "session_id": sid, "reason": "timeout"})


# ==========================================
# WEBSOCKET
# ==========================================

class ConnectionManager:
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


# ==========================================
# HELPERS
# ==========================================

def _log_message(text: str, speaker: str) -> dict:
    entry = {
        "index":     len(message_log),
        "text":      text,
        "speaker":   speaker,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    message_log.append(entry)
    return entry


# ==========================================
# HEALTH
# ==========================================

@app.get("/")
def root():
    return {"status": "RNSIT Kiosk Backend is Live"}


# ==========================================
# SESSION
# ==========================================

@app.post("/session/start")
async def start_session(
    trigger: str = "camera",
    user_name: str = "Guest",
    is_returning: bool = False,
    visit_count: int = 1,
    face_id: str = "",
    session_id: str = "",
):
    global active_session, message_log, _last_activity_ts
    final_session_id = face_id or session_id or str(uuid.uuid4())

    active_session = {
        "session_id":   final_session_id,
        "user_name":    user_name,
        "is_returning": is_returning,
        "visit_count":  visit_count,
        "face_id":      face_id,
        "trigger":      trigger,
        "asking_name":  False,
    }
    message_log       = []
    _last_activity_ts = datetime.now().timestamp()

    db_face_id = face_id.strip() if face_id and face_id.strip() else None
    save_session(final_session_id, db_face_id, user_name, is_returning, visit_count)
    await manager.broadcast({"type": "session_start", "session": active_session})
    return {"status": "success", "session_id": final_session_id, "session": active_session}


@app.post("/session/end")
async def end_session_endpoint(session_id: str = None):
    global active_session, _last_activity_ts
    sid = session_id or (active_session["session_id"] if active_session else None)
    if sid:
        end_session(sid)
    active_session    = None
    _last_activity_ts = 0.0
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


# ==========================================
# MESSAGE
# ==========================================

class MessagePayload(BaseModel):
    session_id: str = Field(..., description="Session identifier")
    text: str = Field(..., description="Message text")
    speaker: str = Field(..., description="Speaker id/name")

    @field_validator("text")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        v = v.strip()
        return v[:MAX_QUERY_LENGTH] if len(v) > MAX_QUERY_LENGTH else v


@app.post("/message")
async def post_message(payload: MessagePayload):
    entry = _log_message(payload.text, payload.speaker)
    await manager.broadcast({"type": "message", **entry})
    return {"status": "ok"}


# ==========================================
# STT
# ==========================================

@app.post("/stt")
async def speech_to_text(request: Request):
    try:
        audio_bytes = await request.body()
        if not audio_bytes or len(audio_bytes) < 1000:
            return {"text": "", "confidence": 0.0, "error": "No audio received"}
        result = transcribe_audio(audio_bytes)
        return result
    except Exception as e:
        logger.error(f"[STT] Endpoint error: {e}")
        return {"text": "", "confidence": 0.0, "error": str(e)}


# ==========================================
# TTS
# ==========================================

@app.post("/tts")
async def text_to_speech_endpoint(request: Request):
    try:
        body = await request.json()
        text = body.get("text", "").strip()
        if not text:
            return {"error": "No text provided"}
        audio_bytes = text_to_speech(text)
        if not audio_bytes:
            return {"fallback": True, "text": text}
        import base64
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        return {"audio": audio_b64, "fallback": False}
    except Exception as e:
        logger.error(f"[TTS] Endpoint error: {e}")
        return {"fallback": True, "text": ""}


# ==========================================
# ASK
# ==========================================

@app.get("/ask")
async def ask_kiosk(question: str = Query(..., description="Visitor question")):
    global _last_activity_ts
    _last_activity_ts = datetime.now().timestamp()   # reset timeout on every question

    q_clean = question.lower().strip()
    q_clean = q_clean.translate(str.maketrans('', '', string.punctuation)).strip()

    words          = q_clean.split()
    corrected_words = [DOMAINS_CORRECTIONS.get(w, w) for w in words]
    q_normalized   = " ".join(corrected_words)

    sid          = active_session["session_id"] if active_session else "unknown"
    visitor_name = (active_session.get("user_name") or "there") if active_session else "there"

    visitor_entry = _log_message(question, "visitor")
    await manager.broadcast({"type": "message", **visitor_entry})

    async def _respond(answer: str, source: str = "") -> dict:
        try:
            save_interaction(sid, question, answer)
        except Exception as exc:
            logger.error("[DATABASE ERROR] Failed to log interaction: %s", exc)
        kiosk_entry = _log_message(answer, "kiosk")
        await manager.broadcast({"type": "message", **kiosk_entry})
        result = {"question": question, "answer": answer}
        if source:
            result["source"] = source
        return result

    # --- TIER 1: Fees ---
    if any(kw in q_normalized for kw in ["fee", "cost", "price", "instalment", "payment"]):
        branch_keyword = next(
            (b for b in ["cse", "ai", "data", "cyber", "ece", "vlsi", "eee", "mech", "civil"] if b in q_normalized),
            None,
        )
        if branch_keyword:
            fee_data = get_admission_fee_by_branch(branch_keyword)
            if fee_data:
                name, annual, inst1, inst2 = fee_data
                if inst2 == 0:
                    answer = (
                        f"The annual management quota fee for {name} is ₹{annual:,.2f}. "
                        "It must be paid as a single installment at the time of admission."
                    )
                else:
                    answer = (
                        f"The annual management fee for {name} is ₹{annual:,.2f}. "
                        f"Split into ₹{inst1:,.2f} at admission and ₹{inst2:,.2f} via post-dated cheques over 3 months."
                    )
            else:
                answer = "I couldn't find the exact fee for that stream. Management fees range from ₹1,10,000 to ₹7,50,000/year. Which branch are you asking about?"
        else:
            answer = "Management fees range from ₹1,10,000 (Civil) to ₹7,50,000/year (Core CSE). Name a specific branch for exact figures!"
        return await _respond(answer)

    # --- TIER 1: Documents ---
    if any(kw in q_normalized for kw in ["document", "documents", "certificate", "paperwork", "bring", "marks card"]):
        quota = "KCET" if any(k in q_normalized for k in ["cet", "kea", "govt"]) else "Management"
        docs  = get_admission_requirements(quota)
        if docs:
            doc_list = "\n".join(f"- {doc}" for doc in docs)
            answer   = f"For {quota} Quota admissions, bring originals and photocopies of:\n{doc_list}"
        else:
            answer = "Please bring your 10th and 12th Marks Cards, Transfer Certificate, Entrance Exam Rank Card, and ID copies to the Admin Block."
        return await _respond(answer)

    # --- TIER 2: Greetings ---
    short_greetings = {
        "hi":  f"Hi {visitor_name}! Welcome to RNSIT. How can I help you today?",
        "hey": f"Hey {visitor_name}! Welcome to RNS Institute of Technology. What can I help with?",
        "ok":  "Alright! Let me know if you need any further assistance.",
    }
    if q_normalized in short_greetings:
        return await _respond(short_greetings[q_normalized])

    # --- Redis cache ---
    cache_key = f"kiosk:cache:{hashlib.md5(q_normalized.encode()).hexdigest()}"
    if redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                logger.info("[REDIS HIT] For normalized key: '%s'", q_normalized)
                return await _respond(cached, source="redis_cache")
        except Exception as e:
            logger.warning("Redis read error: %s", e)

    # --- TIER 3: RAG ---
    logger.info("[CACHE MISS] Running RAG for processed string: '%s'", q_normalized)
    try:
        answer = await generate_rag_kiosk_response(q_normalized, history=message_log[:-1][-6:])
        if redis_client and answer:
            try:
                redis_client.set(cache_key, answer, ex=3600)
            except Exception as e:
                logger.warning("Redis write error: %s", e)
    except Exception as exc:
        logger.error("RAG inference failed: %s", exc)
        answer = "I'm having trouble processing that. Please visit the Admin Block for assistance."

    return await _respond(answer, source="local_llm")


# ==========================================
# VISITOR
# ==========================================

@app.post("/visitor/unknown")
async def visitor_unknown():
    global visitor_name_response, active_session
    if not visitor_name_response.get("ready"):
        visitor_name_response = {"ready": False, "name": "", "save": True}

    if active_session is None:
        active_session = {
            "session_id":   str(uuid.uuid4()),
            "user_name":    "Unknown",
            "is_returning": False,
            "visit_count":  1,
            "face_id":      "",
            "trigger":      "camera",
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
        active_session["user_name"]   = name
    logger.info(f"[VISITOR] Name submitted: '{name}' save={save}")
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


# ==========================================
# FACE
# ==========================================

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
            raise ValueError("encoding must be non-empty")
        return v


@app.get("/faces/all")
def get_all_faces_endpoint():
    from backend.database import get_all_face_encodings
    faces = get_all_face_encodings()
    logger.info(f"[FACE] /faces/all returning {len(faces)} faces")
    return {"faces": faces}


@app.post("/faces/register")
async def register_face(payload: RegisterFacePayload):
    from backend.database import save_face_encoding
    save_face_encoding(payload.face_id, payload.name, payload.encoding)
    logger.info(f"[FACE] Registered: {payload.name} ({payload.face_id})")
    return {"status": "ok", "face_id": payload.face_id}


@app.post("/faces/visit")
def record_face_visit(face_id: str):
    """Increment visit count for a returning visitor."""
    update_face_seen(face_id)
    logger.info(f"[FACE] Visit count incremented for face_id={face_id}")
    return {"status": "ok"}


# Aliases so old routes still work
@app.get("/face/all")
def get_all_faces_old():
    return get_all_faces_endpoint()

@app.post("/face/register")
async def register_face_old(payload: RegisterFacePayload):
    return await register_face(payload)