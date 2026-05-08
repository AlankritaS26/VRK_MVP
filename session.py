"""
session.py  —  RNS Digital Receptionist  (Session Manager)

Your job (Slice 2):
  - Create a UUID the moment camera detects someone
  - Create a session folder to store the conversation
  - Receive text from Slice 1 (they handle mic + speech-to-text)
  - Save transcript to sessions/<uuid>/meta.json
  - NO audio libraries needed here

Run this in Terminal 4:
  python session.py
"""

import os, time, json, requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BACKEND      = os.getenv('BACKEND_URL', 'http://127.0.0.1:8000')
SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# BACKEND HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def get_current_session() -> dict | None:
    """Poll backend for the currently active session."""
    try:
        r = requests.get(f'{BACKEND}/session/current', timeout=2)
        data = r.json()
        return data if data.get('active') else None
    except Exception:
        return None

def get_new_messages(session_id: str, after_index: int) -> list:
    """Fetch any new messages posted to this session since last check."""
    try:
        r = requests.get(
            f'{BACKEND}/session/messages/{session_id}',
            params={'after': after_index},
            timeout=2
        )
        return r.json().get('messages', [])
    except Exception:
        return []

# ─────────────────────────────────────────────────────────────────────────────
# SESSION FOLDER MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────
def create_session_folder(session_id: str, user_name: str) -> Path:
    folder = SESSIONS_DIR / session_id
    folder.mkdir(parents=True, exist_ok=True)
    meta = {
        "session_id":  session_id,
        "user_name":   user_name,
        "started_at":  datetime.now().isoformat(),
        "ended_at":    None,
        "transcript":  []
    }
    with open(folder / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(f"[SESSION] Folder created → sessions/{session_id}/")
    return folder

def save_message(folder: Path, speaker: str, text: str):
    """Append a message line to the session transcript."""
    meta_path = folder / "meta.json"
    with open(meta_path, "r") as f:
        meta = json.load(f)
    meta["transcript"].append({
        "speaker":   speaker,
        "text":      text,
        "timestamp": datetime.now().isoformat()
    })
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

def close_session(folder: Path):
    meta_path = folder / "meta.json"
    with open(meta_path, "r") as f:
        meta = json.load(f)
    meta["ended_at"] = datetime.now().isoformat()
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n[SESSION] Closed — transcript summary:")
    for line in meta["transcript"]:
        print(f"  [{line['speaker'].upper()}] {line['text']}")
    print(f"  Saved to: {folder / 'meta.json'}\n")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────────────────────
def run():
    print("[SESSION MANAGER] Running. No audio needed — Slice 1 sends text.")
    print(f"[SESSION MANAGER] Sessions will be saved to: {SESSIONS_DIR.resolve()}\n")

    current_session_id = None
    session_folder     = None
    message_index      = 0

    while True:
        session = get_current_session()

        # ── New session started ───────────────────────────────────────────────
        if session and session.get('session_id') != current_session_id:
            current_session_id = session['session_id']
            user_name          = session.get('user_name', 'Guest')
            is_returning       = session.get('is_returning', False)

            print(f"[SESSION] Started → ID: {current_session_id}")
            print(f"[SESSION] Visitor: {user_name} ({'returning' if is_returning else 'new'})")

            session_folder = create_session_folder(current_session_id, user_name)
            message_index  = 0

        # ── Active session — save any new messages Slice 1 sent ──────────────
        elif session and current_session_id:
            new_msgs = get_new_messages(current_session_id, message_index)
            for msg in new_msgs:
                speaker = msg.get('speaker', 'user')
                text    = msg.get('text', '')
                print(f"  [{speaker.upper()}] {text}")
                save_message(session_folder, speaker, text)
                message_index += 1

        # ── Session ended ─────────────────────────────────────────────────────
        elif not session and current_session_id:
            print(f"[SESSION] Ended → {current_session_id}")
            if session_folder:
                close_session(session_folder)
            current_session_id = None
            session_folder     = None
            message_index      = 0
            print("[SESSION MANAGER] Waiting for next visitor…\n")

        time.sleep(1)

if __name__ == '__main__':
    try:
        run()
    except KeyboardInterrupt:
        print("\n[SESSION MANAGER] Stopped.")