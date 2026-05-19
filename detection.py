import cv2, requests, time, os, collections, sys, hashlib
import numpy as np
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from database import get_all_faces, save_face, update_face_seen, delete_face_by_name, get_next_label_int, init_db, save_face_image, load_face_images, save_face_image, load_face_images

load_dotenv()

BACKEND       = os.getenv('BACKEND_URL',           'http://127.0.0.1:8000')
THRESHOLD     = int(os.getenv('PASSERBY_THRESHOLD', 80))
FRAME_WINDOW  = int(os.getenv('FRAME_WINDOW',       10))
WALK_AWAY_SEC = int(os.getenv('WALK_AWAY_SECONDS',   5))
CAM_INDEX     = int(os.getenv('CAMERA_INDEX',        0))
CONFIDENCE_MAX = 55.0

MODEL_PATH = Path("face_model.yml")

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
)
recognizer = cv2.face.LBPHFaceRecognizer_create()

def train_model(label_map):
    faces, labels = [], []
    for lid, info in label_map.items():
        images = load_face_images(info["face_id"])
        for img_bytes in images:
            import numpy as np
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                faces.append(img); labels.append(lid)
    if faces:
        recognizer.train(faces, np.array(labels))
        recognizer.save(str(MODEL_PATH))
        print(f"[MODEL] Trained on {len(faces)} images, {len(label_map)} person(s).")

def load_model(label_map):
    if MODEL_PATH.exists() and label_map:
        try:
            recognizer.read(str(MODEL_PATH))
            print(f"[MODEL] Loaded. Known: {[v['name'] for v in label_map.values()]}")
        except:
            train_model(label_map)
    elif label_map:
        train_model(label_map)

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

def start_session(name, is_returning, visit_count, face_id=''):
    r = post('/session/start', params={
        'trigger': 'camera', 'user_name': name,
        'is_returning': str(is_returning).lower(),
        'visit_count': visit_count,
        'face_id': face_id
    })
    return r.get('session_id') if r else None

def ask_name_on_screen():
    post('/visitor/unknown')

def poll_name_response(timeout=60):
    print("[WAITING] Waiting for visitor to enter name on screen...")
    start = time.time()
    while time.time() - start < timeout:
        result = get('/visitor/name_response')
        if result and result.get('ready'):
            name = result.get('name', 'Guest').strip() or 'Guest'
            save = result.get('save', True)
            post('/visitor/clear_response')
            return name, save
        time.sleep(1)
    print("[TIMEOUT] No name entered - using Guest.")
    return "Guest", False

def capture_samples(cam, face_id):
    print("[CAPTURE] Capturing 30 face samples - please look at camera...")
    count = 0
    while count < 30:
        ok, frame = cam.read()
        if not ok: continue
        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        for (x, y, w, h) in faces:
            roi = cv2.resize(gray[y:y+h, x:x+w], (200, 200))
            _, buffer = cv2.imencode(".jpg", roi)
            save_face_image(face_id, count, buffer.tobytes())
            count += 1
            cv2.rectangle(frame, (x,y), (x+w,y+h), (0,255,0), 2)
            cv2.putText(frame, f"Saving sample {count}/30", (x, y-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        cv2.imshow("RNS Digital Receptionist", frame)
        cv2.waitKey(80)
    print("[CAPTURE] Done - 30 samples saved to PostgreSQL.")
#OLD_CAPTURE_REPLACED

def run():
    init_db()
    label_map = get_all_faces()
    load_model(label_map)

    cam = cv2.VideoCapture(CAM_INDEX, cv2.CAP_DSHOW)
    if not cam.isOpened():
        print("[ERROR] Cannot open camera.")
        sys.exit(1)

    cx_history     = collections.deque(maxlen=FRAME_WINDOW)
    session_active = False
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

            if label_map and MODEL_PATH.exists():
                try:
                    roi = cv2.resize(gray[y:y+h, x:x+w], (200,200))
                    pid, conf = recognizer.predict(roi)
                    label = label_map[pid]["name"] if conf < CONFIDENCE_MAX and pid in label_map else "Unknown"
                    cv2.putText(frame, label, (x, y-10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                except: pass

            if len(cx_history) == FRAME_WINDOW and not session_active:
                movement = max(cx_history) - min(cx_history)
                if movement > THRESHOLD:
                    cx_history.clear()
                else:
                    print('[VISITOR] Stopped in front of kiosk!')
                    cx_history.clear()

                    name         = "Guest"
                    is_returning = False
                    visit_count  = 1
                    recognized   = False

                    if label_map and MODEL_PATH.exists():
                        try:
                            roi = cv2.resize(gray[y:y+h, x:x+w], (200,200))
                            pid, conf = recognizer.predict(roi)
                            if conf < CONFIDENCE_MAX and pid in label_map:
                                info = label_map[pid]
                                name             = info["name"]
                                visit_count      = info.get("visit_count", 1) + 1
                                is_returning     = True
                                recognized       = True
                                recognized_face_id = info["face_id"]
                                update_face_seen(info["face_id"])
                                label_map[pid]["visit_count"] = visit_count
                                label_map[pid]["last_seen"]   = datetime.now().isoformat()
                                print(f"[RECOGNIZED] {name} - visit #{visit_count} (conf:{conf:.1f})")
                        except Exception as e:
                            print(f"[WARN] {e}")

                    if not recognized:
                        ask_name_on_screen()
                        name, save_to_db = poll_name_response(timeout=60)

                        if save_to_db and name != "Guest":
                            face_id  = hashlib.sha256(
                                f"{name}_{datetime.now().isoformat()}".encode()
                            ).hexdigest()[:12]
                            label_id = get_next_label_int()
                            # Save face to DB FIRST before capturing images
                            # so foreign key constraint is satisfied
                            save_face(label_id, face_id, name)
                            capture_samples(cam, face_id)
                            label_map[label_id] = {
                                "face_id":     face_id,
                                "name":        name,
                                "registered":  datetime.now().isoformat(),
                                "last_seen":   datetime.now().isoformat(),
                                "visit_count": 1
                            }
                            train_model(label_map)
                            print(f"[REGISTERED] '{name}' saved to PostgreSQL.")
                        else:
                            print(f"[GUEST] '{name}' chose not to save.")

                    if recognized:
                        current_face_id = recognized_face_id
                    elif save_to_db and name != "Guest":
                        current_face_id = face_id
                    else:
                        current_face_id = ""
                    sid = start_session(name, is_returning, visit_count, current_face_id)
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
                label_map = get_all_faces()

        cv2.imshow('RNS Digital Receptionist', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cam.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    run()