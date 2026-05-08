import os
import json
import uuid
import base64
from datetime import datetime, timedelta

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import redis

# Slice 3 custom imports
from database import get_db_connection, init_db
from memory import set_context, get_context

# 1. Load environment variables & Initialize DB
load_dotenv()
init_db()

app = FastAPI(title='RNSIT Proactive Digital Receptionist')

# Allow React to talk to FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Setup DB Connections (Memurai + PostgreSQL)
try:
    r = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)
    conn = get_db_connection()
    if conn and r:
       print("✅ Both databases connected successfully!")
except Exception as e:
    print(f"⚠️ Connection Error: {e}")

# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────
def load_college_data():
    try:
        with open("data/college_info.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

FACE_DB_PATH = "face_db.json"

def load_face_db() -> dict:
    if os.path.exists(FACE_DB_PATH):
        with open(FACE_DB_PATH, "r") as f:
            return json.load(f)
    return {}

def save_face_db(db: dict):
    with open(FACE_DB_PATH, "w") as f:
        json.dump(db, f, indent=2)

def purge_old_entries(db: dict) -> dict:
    cutoff = datetime.now() - timedelta(days=30)
    return {
        k: v for k, v in db.items()
        if datetime.fromisoformat(v["last_seen"]) > cutoff
    }

# ─────────────────────────────────────────────
# WEBSOCKET MANAGER
# ─────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                dead.append(conn)
        for d in dead:
            self.active_connections.remove(d)

manager = ConnectionManager()
active_session: dict | None = None
message_log: list[dict] = []

# ─────────────────────────────────────────────
# ROUTES (COMBINED)
# ─────────────────────────────────────────────

@app.get("/")
def home():
    return {
        "status": "RNSIT Kiosk Backend is Live ✅",
        "database": "Connected"
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/test-memory/{name}")
def test_memory(name: str):
    set_context("guest", "name", name, expiry=60)
    return {"message": f"I will remember you for 60 seconds, {name}!"}

@app.get("/ask")
def ask_kiosk(question: str = Query(..., description="The student's question")):
    user_name = get_context("guest", "name")
    greeting = f"Hello {user_name}! " if user_name else ""

    data = load_college_data()
    question_lower = question.lower()
    
    stop_words = ["is", "the", "where", "can", "you", "tell", "me", "who", "what", "how", "of", "in", "at", "a", "an"]
    query_words = [w for w in question_lower.split() if w not in stop_words]
    
    answer = None
    best_match_score = 0
    
    for faq in data.get("faqs", []):
        faq_q_lower = faq["q"].lower()
        score = sum(1 for word in query_words if word in faq_q_lower)
        if score > best_match_score:
            best_match_score = score
            answer = faq["a"]

    if best_match_score < 1:
        for block_key, desc in data.get("blocks", {}).items():
            clean_block = block_key.replace("_", " ")
            if any(word in clean_block for word in query_words):
                answer = desc
                break
        
        if not answer:
            for dept_key, details in data.get("departments", {}).items():
                dept_name_clean = dept_key.replace("_", " ")
                if dept_name_clean in question_lower or dept_key in question_lower:
                    if any(word in question_lower for word in ["intake", "seats", "capacity", "how many"]):
                        answer = f"The {dept_name_clean.upper()} department has an annual intake of {details.get('intake', '180')} students."
                    elif any(word in question_lower for word in ["hod", "head", "boss", "chairman"]):
                        answer = f"The HOD of {dept_name_clean.upper()} is {details.get('hod', 'not listed')}."
                    else:
                        answer = f"The {dept_name_clean.upper()} department is located on the {details.get('floor', 'ground floor')}."
                    break

    if not answer:
        answer = "I'm sorry, I don't have that information yet. Please visit the Admin Block."

    try:
        db_conn = get_db_connection()
        cur = db_conn.cursor()
        cur.execute(
            "INSERT INTO interactions (input_text, response_text) VALUES (%s, %s)",
            (str(question), str(answer))
        )
        db_conn.commit()
        cur.close()
        db_conn.close()
    except Exception as e:
        print(f"⚠️ Database logging failed: {e}")

    return {"question": question, "answer": f"{greeting}{answer}"}

# --- Slice 1/2 Session & Face Endpoints ---
@app.get("/session/current")
async def get_current_session():
    if active_session:
        return {"active": True, **active_session}
    return {"active": False}

class RegisterFacePayload(BaseModel):
    face_id: str
    name: str
    encoding: list[float]

@app.post("/face/register")
async def register_face(payload: RegisterFacePayload):
    db = load_face_db()
    db = purge_old_entries(db)
    db[payload.face_id] = {
        "name": payload.name,
        "encoding": payload.encoding,
        "registered_at": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat(),
        "visit_count": db.get(payload.face_id, {}).get("visit_count", 0) + 1
    }
    save_face_db(db)
    return {"status": "registered", "name": payload.name}

@app.get("/face/lookup/{face_id}")
async def lookup_face(face_id: str):
    db = load_face_db()
    db = purge_old_entries(db)
    if face_id in db:
        db[face_id]["last_seen"] = datetime.now().isoformat()
        db[face_id]["visit_count"] = db[face_id].get("visit_count", 0) + 1
        save_face_db(db)
        return {"found": True, **db[face_id]}
    return {"found": False}

@app.get("/face/all")
async def get_all_faces():
    db = load_face_db()
    db = purge_old_entries(db)
    save_face_db(db)
    return db

@app.post("/session/start")
async def start_session(trigger: str = "camera", user_name: str = "Guest", is_returning: bool = False, visit_count: int = 1):
    global active_session, message_log
    session_id = str(uuid.uuid4())
    active_session = {
        "session_id":  session_id,
        "user_name":   user_name,
        "is_returning": is_returning,
        "visit_count": visit_count
    }
    message_log = []
    await manager.broadcast({"type": "session_start", "session": active_session})
    return {"status": "success", "session_id": session_id, "session": active_session}

@app.post("/session/end")
async def end_session(session_id: str = None):
    global active_session
    active_session = None
    await manager.broadcast({"type": "session_end", "session_id": session_id})
    return {"status": "success"}

class MessagePayload(BaseModel):
    session_id: str
    text: str
    speaker: str = "user"

@app.post("/message")
async def send_message(payload: MessagePayload):
    entry = {"session_id": payload.session_id, "text": payload.text, "speaker": payload.speaker}
    message_log.append(entry)
    await manager.broadcast({"type": "message", "text": payload.text, "speaker": payload.speaker})
    return {"status": "success"}

@app.get("/session/messages/{session_id}")
async def get_messages(session_id: str, after: int = 0):
    relevant = [m for m in message_log if m["session_id"] == session_id]
    return {"messages": relevant[after:]}

visitor_name_response: dict = {"ready": False, "name": "", "save": True}

@app.post("/visitor/unknown")
async def visitor_unknown():
    global visitor_name_response
    visitor_name_response = {"ready": False, "name": "", "save": True}
    await manager.broadcast({"type": "ask_name"})
    return {"status": "asking"}

@app.post("/visitor/submit_name")
async def submit_name(name: str = "", save: bool = True):
    global visitor_name_response
    visitor_name_response = {"ready": True, "name": name, "save": save}
    await manager.broadcast({"type": "name_received", "name": name, "save": save})
    return {"status": "received"}

@app.get("/visitor/name_response")
async def get_name_response():
    return visitor_name_response

@app.post("/visitor/clear_response")
async def clear_response():
    global visitor_name_response
    visitor_name_response = {"ready": False, "name": "", "save": True}
    return {"status": "cleared"}