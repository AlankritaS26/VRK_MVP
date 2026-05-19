import os
import json
import uuid
import shutil
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from database import (
    get_db_connection, init_db,
    save_session, end_session, save_interaction,
    delete_face_by_name
)

load_dotenv()
init_db()

app = FastAPI(title="RNSIT Digital Receptionist")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# IN-MEMORY STATE  (session lives here while active)
# ─────────────────────────────────────────────
active_session: dict | None = None
message_log: list[dict] = []
visitor_name_response: dict = {"ready": False, "name": "", "save": True}

# ─────────────────────────────────────────────
# WEBSOCKET MANAGER
# ─────────────────────────────────────────────
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

# ─────────────────────────────────────────────
# HEALTH
# ─────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "RNSIT Kiosk Backend is Live"}

# ─────────────────────────────────────────────
# SESSION ENDPOINTS
# ─────────────────────────────────────────────
@app.post("/session/start")
async def start_session(
    trigger: str = "camera",
    user_name: str = "Guest",
    is_returning: bool = False,
    visit_count: int = 1,
    face_id: str = ""
):
    global active_session, message_log
    session_id = str(uuid.uuid4())
    active_session = {
        "session_id":   session_id,
        "user_name":    user_name,
        "is_returning": is_returning,
        "visit_count":  visit_count,
        "face_id":      face_id,
        "asking_name":  False,
    }
    message_log = []

    # Save to PostgreSQL
    save_session(
        session_id,
        face_id if face_id else None,
        user_name,
        is_returning,
        visit_count
    )

    await manager.broadcast({"type": "session_start", "session": active_session})
    return {"status": "success", "session_id": session_id, "session": active_session}


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

# ─────────────────────────────────────────────
# MESSAGE ENDPOINT
# ─────────────────────────────────────────────
class MessagePayload(BaseModel):
    session_id: str
    text: str
    speaker: str

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

# ─────────────────────────────────────────────
# ASK / FAQ ENDPOINT
# ─────────────────────────────────────────────
@app.get("/ask")
def ask_kiosk(question: str = Query(..., description="Visitor question")):
    BASE_DIR = Path(__file__).parent
    with open(BASE_DIR / "data" / "college_info.json", encoding="utf-8") as f:
        data = json.load(f)

    q = question.lower().strip()
    stop_words = {
        "is","the","where","can","you","tell","me","who","what","how","of","in",
        "at","a","an","are","was","i","do","does","please","to","find","get",
        "go","about","any","have","which","when","there","its","your"
    }
    # Check short greetings first before filtering
    short_greetings = {'hi': 'Hi there! Welcome to RNSIT. How can I help you today?', 'ok': 'Alright! Let me know if you need any further assistance.', 'hey': 'Hey! Welcome to RNS Institute of Technology. What can I help you with?'}
    if q.strip() in short_greetings:
        return {'question': question, 'answer': short_greetings[q.strip()]}
    words = [w for w in q.split() if w not in stop_words and len(w) > 2]

    answer = None
    best = 0

    # 1. FAQs — score by question match
    for faq in data.get("faqs", []):
        fq = faq["question"].lower()
        score = sum(2 for w in words if w in fq)
        if score > best:
            best = score
            answer = faq["answer"]

    # 2. Facilities — direct keyword match
    for fname, fval in data.get("facilities", {}).items():
        if fname in q or any(w in fname for w in words):
            if isinstance(fval, dict):
                parts = []
                if fval.get("name"):        parts.append(fval["name"])
                if fval.get("location"):    parts.append("Location: " + fval["location"])
                if fval.get("timings"):     parts.append("Timings: " + fval["timings"])
                if fval.get("details"):     parts.append(fval["details"])
                if fval.get("usage"):       parts.append(fval["usage"])
                candidate = ". ".join(parts)
            else:
                candidate = str(fval)
            if best < 3:
                answer = candidate
                best = 3
            break

    # 3. Departments
    if best < 2:
        for dept, details in data.get("departments", {}).items():
            dc = dept.replace("_", " ").lower()
            if any(w in dc for w in words) or dc in q:
                if isinstance(details, dict):
                    if any(w in q for w in ["hod","head","who"]):
                        answer = "HOD of " + dept.upper() + " is " + str(details.get("hod","not listed")) + "."
                    elif any(w in q for w in ["intake","seats","students"]):
                        answer = dept.upper() + " has intake of " + str(details.get("intake","180")) + " students."
                    elif any(w in q for w in ["floor","location","where","block"]):
                        answer = dept.upper() + " is on " + str(details.get("floor","ground floor")) + "."
                    else:
                        answer = dept.upper() + " - Floor: " + str(details.get("floor","")) + ", HOD: " + str(details.get("hod","")) + "."
                best = 2
                break

    # 4. Administration
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

    # 5. College info
    if best < 2:
        for key, val in data.get("college", {}).items():
            if any(w in key.lower() for w in words):
                answer = str(val)
                best = 2
                break

    if not answer:
        answer = "I am sorry, I do not have that information. Please visit the Admin Block for assistance."

    greeting = ""

    # Save interaction to PostgreSQL
    try:
        sid = active_session["session_id"] if active_session else "unknown"
        save_interaction(sid, question, greeting + answer)
    except Exception as e:
        print(f"DB log failed: {e}")

    return {"question": question, "answer": greeting + answer}

# ─────────────────────────────────────────────
# VISITOR NAME FLOW
# ─────────────────────────────────────────────
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
            face_dir = Path("faces") / face_id
            if face_dir.exists():
                shutil.rmtree(face_dir)
        model_path = Path("face_model.yml")
        if model_path.exists():
            model_path.unlink()
        return {"success": True, "message": f"Data for {name} deleted successfully."}
    except Exception as e:
        return {"success": False, "message": str(e)}

# ─────────────────────────────────────────────
# FACE REGISTRATION (called from detection.py)
# ─────────────────────────────────────────────
class RegisterFacePayload(BaseModel):
    face_id: str
    name: str
    encoding: list[float]

@app.post("/face/register")
async def register_face(payload: RegisterFacePayload):
    return {"status": "ok", "face_id": payload.face_id}