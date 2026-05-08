"""
detection.py  —  RNS Digital Receptionist
- Detects face with Haar Cascade
- Recognizes with OpenCV LBPH
- Unknown face → sends event to frontend → user types name on screen
- User can choose NOT to save → guest session only
- Known face → greets by name automatically
"""

import cv2, requests, time, os, collections, sys, hashlib, json
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

BACKEND        = os.getenv('BACKEND_URL',            'http://127.0.0.1:8000')
THRESHOLD      = int(os.getenv('PASSERBY_THRESHOLD',  80))
FRAME_WINDOW   = int(os.getenv('FRAME_WINDOW',        10))
WALK_AWAY_SEC  = int(os.getenv('WALK_AWAY_SECONDS',    5))
CAM_INDEX      = int(os.getenv('CAMERA_INDEX',         0))
CONFIDENCE_MAX = float(os.getenv('FACE_CONFIDENCE',   70))

FACES_DIR   = Path("faces");   FACES_DIR.mkdir(exist_ok=True)
MODEL_PATH  = Path("face_model.yml")
LABELS_PATH = Path("face_labels.json")

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
)
recognizer = cv2.face.LBPHFaceRecognizer_create()
label_map: dict[int, dict] = {}

# ─────────────────────────────────────────────────────────────────────────────
# LABEL MAP
# ─────────────────────────────────────────────────────────────────────────────
def load_labels():
    if not LABELS_PATH.exists():
        return {}

    raw = json.loads(LABELS_PATH.read_text())
    label_map: dict[int, dict] = {}
    pending: list[dict] = []

    for key, value in raw.items():
        try:
            lid = int(key)
            label_map[lid] = value
        except ValueError:
            # Some old files store face IDs as top-level keys.
            if isinstance(value, dict) and "label_int" in value:
                try:
                    lid = int(value["label_int"])
                    label_map[lid] = value
                    continue
                except ValueError:
                    pass
            pending.append(value)

    for info in pending:
        lid = next_id(label_map)
        label_map[lid] = info

    return label_map

def save_labels(lmap):
    LABELS_PATH.write_text(json.dumps({str(k): v for k, v in lmap.items()}, indent=2))

def purge_old(lmap):
    cutoff = datetime.now() - timedelta(days=30)
    return {k: v for k, v in lmap.items()
            if datetime.fromisoformat(v["last_seen"]) > cutoff}

def next_id(lmap): return max(lmap.keys(), default=-1) + 1

# ─────────────────────────────────────────────────────────────────────────────
# MODEL
# ─────────────────────────────────────────────────────────────────────────────
def train_model(lmap):
    faces, labels = [], []
    for lid, info in lmap.items():
        d = FACES_DIR / info["face_id"]
        if not d.exists(): continue
        for p in d.glob("*.jpg"):
            img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                faces.append(img); labels.append(lid)
    if faces:
        recognizer.train(faces, np.array(labels))
        recognizer.save(str(MODEL_PATH))
        print(f"[MODEL] Trained on {len(faces)} images, {len(lmap)} person(s).")

def load_model(lmap):
    if MODEL_PATH.exists() and lmap:
        try:
            recognizer.read(str(MODEL_PATH))
            print(f"[MODEL] Loaded. Known: {[v['name'] for v in lmap.values()]}")
        except: pass

# ─────────────────────────────────────────────────────────────────────────────
# BACKEND CALLS
# ─────────────────────────────────────────────────────────────────────────────
def post(endpoint, params=None, body=None):
    try:
        r = requests.post(f'{BACKEND}{endpoint}', params=params, json=body, timeout=3)
        return r.json()
    except Exception as e:
        print(f"[BACKEND] {endpoint} error: {e}")
        return None

def get(endpoint):
    try:
        return requests.get(f'{BACKEND}{endpoint}', timeout=3).json()
    except: return None

def start_session(name, is_returning, visit_count):
    r = post('/session/start', params={
        'trigger': 'camera', 'user_name': name,
        'is_returning': str(is_returning).lower(),
        'visit_count': visit_count
    })
    return r.get('session_id') if r else None

def ask_name_on_screen():
    """Tell frontend to show the name input form."""
    post('/visitor/unknown')

def poll_name_response(timeout=30) -> tuple[str, bool]:
    """
    Poll backend for the name the visitor typed on screen.
    Returns (name, save_to_db).
    Waits up to `timeout` seconds.
    """
    print("[WAITING] Waiting for visitor to enter name on screen...")
    start = time.time()
    while time.time() - start < timeout:
        result = get('/visitor/name_response')
        if result and result.get('ready'):
            name      = result.get('name', 'Guest').strip() or 'Guest'
            save      = result.get('save', True)
            post('/visitor/clear_response')   # reset for next visitor
            return name, save
        time.sleep(1)
    print("[TIMEOUT] No name entered — using Guest.")
    return "Guest", False

# ─────────────────────────────────────────────────────────────────────────────
# CAPTURE SAMPLES
# ─────────────────────────────────────────────────────────────────────────────
def capture_samples(cam, face_id):
    person_dir = FACES_DIR / face_id
    person_dir.mkdir(exist_ok=True)
    print("[CAPTURE] Capturing 30 face samples — please look at camera...")
    count = 0
    while count < 30:
        ok, frame = cam.read()
        if not ok: continue
        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        for (x, y, w, h) in faces:
            roi = cv2.resize(gray[y:y+h, x:x+w], (200, 200))
            cv2.imwrite(str(person_dir / f"{count:03d}.jpg"), roi)
            count += 1
            cv2.rectangle(frame, (x,y), (x+w,y+h), (0,255,0), 2)
            cv2.putText(frame, f"Saving sample {count}/30", (x, y-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        cv2.imshow('RNS Digital Receptionist', frame)
        cv2.waitKey(80)
    print(f"[CAPTURE] Done — 30 samples saved.")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────────────────────
def run():
    global label_map
    label_map = purge_old(load_labels())
    save_labels(label_map)
    load_model(label_map)

    cam = cv2.VideoCapture(CAM_INDEX, cv2.CAP_DSHOW)
    if not cam.isOpened():
        print("[ERROR] Cannot open camera.")
        sys.exit(1)

    cx_history      = collections.deque(maxlen=FRAME_WINDOW)
    session_active  = False
    current_session = None
    last_face_time  = 0

    print("[INFO] Camera active. Press Q to quit.")

    while True:
        ok, frame = cam.read()
        if not ok: continue

        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)

        if len(faces) > 0:
            (x, y, w, h) = faces[0]
            cx = x + w // 2
            last_face_time = time.time()
            cx_history.append(cx)

            color = (0,255,0) if session_active else (0,255,255)
            cv2.rectangle(frame, (x,y), (x+w,y+h), color, 2)

            # Show live name label
            if label_map and MODEL_PATH.exists():
                try:
                    roi = cv2.resize(gray[y:y+h, x:x+w], (200,200))
                    pid, conf = recognizer.predict(roi)
                    label = label_map[pid]["name"] if conf < CONFIDENCE_MAX and pid in label_map else "Unknown"
                    cv2.putText(frame, label, (x, y-10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                except: pass

            # ── Anti-passerby ─────────────────────────────────────────────────
            if len(cx_history) == FRAME_WINDOW and not session_active:
                movement = max(cx_history) - min(cx_history)
                if movement > THRESHOLD:
                    cx_history.clear()
                else:
                    print('[VISITOR] Stopped in front of kiosk!')
                    cx_history.clear()

                    name        = "Guest"
                    is_returning = False
                    visit_count  = 1

                    # ── Try to recognize ──────────────────────────────────────
                    recognized = False
                    if label_map and MODEL_PATH.exists():
                        try:
                            roi = cv2.resize(gray[y:y+h, x:x+w], (200,200))
                            pid, conf = recognizer.predict(roi)
                            if conf < CONFIDENCE_MAX and pid in label_map:
                                info = label_map[pid]
                                name = info["name"]
                                info["last_seen"]   = datetime.now().isoformat()
                                info["visit_count"] = info.get("visit_count",0) + 1
                                visit_count  = info["visit_count"]
                                is_returning = True
                                recognized   = True
                                label_map[pid] = info
                                save_labels(label_map)
                                print(f"[RECOGNIZED] {name} — visit #{visit_count} (conf:{conf:.1f})")
                        except Exception as e:
                            print(f"[WARN] {e}")

                    # ── Unknown — ask name on screen ──────────────────────────
                    if not recognized:
                        ask_name_on_screen()          # shows form on React
                        name, save_to_db = poll_name_response(timeout=30)

                        if save_to_db and name != "Guest":
                            face_id  = hashlib.sha256(
                                f"{name}_{datetime.now().isoformat()}".encode()
                            ).hexdigest()[:12]
                            label_id = next_id(label_map)
                            capture_samples(cam, face_id)
                            label_map[label_id] = {
                                "name":        name,
                                "face_id":     face_id,
                                "registered":  datetime.now().isoformat(),
                                "last_seen":   datetime.now().isoformat(),
                                "visit_count": 1
                            }
                            save_labels(label_map)
                            train_model(label_map)
                            post('/face/register', body={
                                "face_id": face_id, "name": name, "encoding": [float(label_id)]
                            })
                            print(f"[REGISTERED] '{name}' saved to database.")
                        else:
                            print(f"[GUEST] '{name}' chose not to save data — guest session only.")

                    sid = start_session(name, is_returning, visit_count)
                    if sid:
                        current_session = sid
                        session_active  = True

        else:
            cx_history.clear()
            if session_active and (time.time() - last_face_time > WALK_AWAY_SEC):
                print('[WALK-AWAY] Visitor left.')
                post('/session/end', params={'session_id': current_session})
                session_active  = False
                current_session = None

        cv2.imshow('RNS Digital Receptionist', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cam.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    run()