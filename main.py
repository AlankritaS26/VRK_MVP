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
async def ask_kiosk(question: str = Query(..., description="question")):
    global active_session  # ← required so we can set active_session = None

    with open("data/college_info.json", encoding="utf-8") as f:
        data = json.load(f)

    q = question.lower().strip()

    # ── 1. Greetings (early return, no DB log needed) ──────────────────────
    if any(greet in q for greet in ["hello", "hi", "hey", "good morning"]):
        return {"question": question, "answer": "Hello! Welcome to RNSIT. How can I help you today?"}

    # ── 2. Session end (thank you / goodbye) ───────────────────────────────
    if any(thanks in q for thanks in ["thank you", "thanks", "tysm", "that's all"]):
        session_id = active_session["session_id"] if active_session else None
        active_session = None
        await manager.broadcast({"type": "session_end", "session_id": session_id})
        return {
            "question": question,
            "answer": "You're very welcome! Have a great day at RNSIT. Session closed.",
            "session_ended": True
        }

    # ── 3. Keyword scoring ─────────────────────────────────────────────────
    stop_words = {
        "is", "the", "where", "can", "you", "tell", "me", "who", "what",
        "how", "of", "in", "at", "a", "an", "are", "was", "i", "do",
        "does", "please", "to", "find", "get", "go", "about", "any",
        "have", "which", "when"
    }
    words = [w for w in q.split() if w not in stop_words and len(w) > 2]

    answer = None
    best = 0

    # FAQs
    for faq in data.get("faqs", []):
        fq = faq["question"].lower()
        score = sum(2 for w in words if w in fq)
        if score > best:
            best = score
            answer = faq["answer"]

    # Facilities
    for fname, fval in data.get("facilities", {}).items():
        if fname in q or any(w in fname for w in words):
            if isinstance(fval, dict):
                parts = []
                if fval.get("name"):     parts.append(fval["name"])
                if fval.get("location"): parts.append("Location: " + fval["location"])
                if fval.get("timings"):  parts.append("Timings: " + fval["timings"])
                if fval.get("details"):  parts.append(fval["details"])
                if fval.get("usage"):    parts.append(fval["usage"])
                candidate = ". ".join(parts)
            else:
                candidate = str(fval)
            if best < 3:
                answer = candidate
                best = 3
            break

    # Departments
    if best < 2:
        for dept, details in data.get("departments", {}).items():
            dc = dept.replace("_", " ").lower()
            if any(w in dc for w in words) or dc in q:
                if isinstance(details, dict):
                    if any(w in q for w in ["hod", "head", "who"]):
                        answer = "HOD of " + dept.upper() + " is " + str(details.get("hod", "not listed")) + "."
                    elif any(w in q for w in ["intake", "seats", "students"]):
                        answer = dept.upper() + " has intake of " + str(details.get("intake", "180")) + " students."
                    elif any(w in q for w in ["floor", "location", "where", "block"]):
                        answer = dept.upper() + " is on " + str(details.get("floor", "ground floor")) + "."
                    else:
                        answer = dept.upper() + " - Floor: " + str(details.get("floor", "")) + ", HOD: " + str(details.get("hod", "")) + "."
                best = 2
                break

    # College info
    if best < 2:
        college = data.get("college", {})
        for key, val in college.items():
            if any(w in key.lower() for w in words):
                answer = str(val)
                best = 2
                break

    # Administration
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

    # Fallback
    if not answer:
        answer = "I am sorry, I do not have that information. Please visit the Admin Block."

    # ── 4. Log to DB ───────────────────────────────────────────────────────
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
        print(f"DB log failed: {e}")

    return {"question": question, "answer": answer}
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


@app.post("/visitor/delete_my_data")
async def delete_my_data(name: str):
    import shutil
    from pathlib import Path
    BASE = Path(__file__).parent
    deleted = False
    try:
        labels_path = BASE / "face_labels.json"
        if labels_path.exists():
            with open(labels_path) as f:
                label_map = json.load(f)
            to_delete = [k for k, v in label_map.items() if v.get("name","").lower() == name.lower()]
            for key in to_delete:
                face_id = label_map[key].get("face_id","")
                face_dir = BASE / "faces" / face_id
                if face_dir.exists():
                    shutil.rmtree(face_dir)
                del label_map[key]
                deleted = True
            with open(labels_path, "w") as f:
                json.dump(label_map, f, indent=2)
            model_path = BASE / "trainer.yml"
            if not label_map and model_path.exists():
                model_path.unlink()
        if deleted:
            return {"success": True, "message": f"Data for {name} deleted."}
        else:
            return {"success": False, "message": f"No data found for {name}."}
    except Exception as e:
        return {"success": False, "message": str(e)}
@app.post("/visitor/unknown")
async def visitor_unknown():
    global visitor_name_response, active_session
    visitor_name_response = {"ready": False, "name": "", "save": True}
    if active_session is None:
        active_session = {
            "session_id": str(uuid.uuid4()),
            "user_name": "Unknown",
            "is_returning": False,
            "visit_count": 1,
            "asking_name": True
        }
    else:
        active_session["asking_name"] = True
    await manager.broadcast({"type": "ask_name"})
    return {"status": "asking"}

@app.post("/visitor/submit_name")
async def submit_name(name: str = "", save: bool = True):
    global visitor_name_response
    visitor_name_response = {"ready": True, "name": name, "save": save}
    if active_session:
        active_session["asking_name"] = False
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


