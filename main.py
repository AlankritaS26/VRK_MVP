from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid, json, os, base64
from datetime import datetime, timedelta

app = FastAPI(title='Slice 2 - Proactive Digital Receptionist')

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# FACE DATABASE  (stored as JSON on disk)
# ─────────────────────────────────────────────
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
    """Remove faces not seen in 30 days."""
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

# ─────────────────────────────────────────────
# IN-MEMORY ACTIVE SESSION (session.py polls this)
# ─────────────────────────────────────────────
active_session: dict | None = None

# ─────────────────────────────────────────────
# CURRENT SESSION ENDPOINT (for session.py)
# ─────────────────────────────────────────────
@app.get("/session/current")
async def get_current_session():
    if active_session:
        return {"active": True, **active_session}
    return {"active": False}

# ─────────────────────────────────────────────
# WEBSOCKET ENDPOINT
# ─────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ─────────────────────────────────────────────
# FACE REGISTRATION  (called from detection.py)
# ─────────────────────────────────────────────
class RegisterFacePayload(BaseModel):
    face_id: str          # unique key from face_recognition (encoding hash)
    name: str             # e.g. "Akshatha"
    encoding: list[float] # 128-float face encoding

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

# ─────────────────────────────────────────────
# FACE LOOKUP  (called from detection.py on match)
# ─────────────────────────────────────────────
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

# ─────────────────────────────────────────────
# GET ALL KNOWN FACES  (so detection.py can load encodings on startup)
# ─────────────────────────────────────────────
@app.get("/face/all")
async def get_all_faces():
    db = load_face_db()
    db = purge_old_entries(db)
    save_face_db(db)
    return db

# ─────────────────────────────────────────────
# SESSION START  (camera triggers this)
# ─────────────────────────────────────────────
@app.post("/session/start")
async def start_session(
    trigger: str = "camera",
    user_name: str = "Guest",
    is_returning: bool = False,
    visit_count: int = 1
):
    global active_session, message_log
    session_id = str(uuid.uuid4())
    active_session = {
        "session_id":  session_id,
        "user_name":   user_name,
        "is_returning": is_returning,
        "visit_count": visit_count
    }
    message_log = []   # clear log for new session
    await manager.broadcast({
        "type": "session_start",
        "session": active_session
    })
    print(f"[SESSION] STARTED {session_id} user={user_name} returning={is_returning} visit={visit_count}")
    return {"status": "success", "session_id": session_id, "session": active_session}

# ─────────────────────────────────────────────
# SESSION END  (camera triggers when visitor leaves)
# ─────────────────────────────────────────────
@app.post("/session/end")
async def end_session(session_id: str = None):
    global active_session
    active_session = None
    await manager.broadcast({"type": "session_end", "session_id": session_id})
    return {"status": "success"}

# ─────────────────────────────────────────────
# MESSAGE STORE (in-memory log per session)
# ─────────────────────────────────────────────
message_log: list[dict] = []   # cleared on each new session

# ─────────────────────────────────────────────
# MESSAGE  (Slice 1 posts here, we broadcast to React + store)
# ─────────────────────────────────────────────
class MessagePayload(BaseModel):
    session_id: str
    text: str
    speaker: str = "user"   # "user" or "kiosk"

@app.post("/message")
async def send_message(payload: MessagePayload):
    entry = {
        "session_id": payload.session_id,
        "text":       payload.text,
        "speaker":    payload.speaker
    }
    message_log.append(entry)
    await manager.broadcast({
        "type":    "message",
        "text":    payload.text,
        "speaker": payload.speaker
    })
    return {"status": "success"}

# ─────────────────────────────────────────────
# GET MESSAGES  (session.py polls this to save transcript)
# ─────────────────────────────────────────────
@app.get("/session/messages/{session_id}")
async def get_messages(session_id: str, after: int = 0):
    relevant = [m for m in message_log if m["session_id"] == session_id]
    return {"messages": relevant[after:]}

# ─────────────────────────────────────────────
# ROOT HEALTH CHECK
# ─────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "RNS Digital Receptionist Backend Running ✅"}

# ─────────────────────────────────────────────
# VISITOR NAME COLLECTION
# ─────────────────────────────────────────────
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

@app.post("/visitor/delete_my_data")
async def delete_my_data(name: str = ""):
    import shutil, json as _json
    from pathlib import Path as _Path
    lp = _Path("face_labels.json"); fd = _Path("faces"); mp = _Path("face_model.yml")
    deleted = False
    if lp.exists():
        lmap = _json.loads(lp.read_text())
        new_lmap = {}
        for k, v in lmap.items():
            if v.get("name","").lower() == name.lower():
                face_dir = fd / v.get("face_id","")
                if face_dir.exists(): shutil.rmtree(face_dir)
                deleted = True
                print(f"[PRIVACY] Deleted data for {name}")
            else:
                new_lmap[k] = v
        lp.write_text(_json.dumps(new_lmap, indent=2))
        if mp.exists(): mp.unlink()
    await manager.broadcast({"type": "data_deleted", "name": name})
    return {"deleted": deleted, "name": name}