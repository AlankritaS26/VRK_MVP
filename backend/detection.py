"""
detection.py — EP-07 Presence Detection & Face Recognition Pipeline
VRK/RNS Digital Receptionist
"""

import os
import cv2
import numpy as np
import base64
import logging
import urllib.request
import time
import uuid
import threading
import httpx
from dataclasses import dataclass
from typing import Optional

import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision as mp_vision
from deepface import DeepFace

logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

# ─── Model auto-download ──────────────────────────────────────────────────────
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "face_landmarker.task")
_MODEL_URL  = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)

def _ensure_model():
    if not os.path.exists(_MODEL_PATH):
        logger.info("Downloading face_landmarker.task (~5 MB)...")
        urllib.request.urlretrieve(_MODEL_URL, _MODEL_PATH)
        logger.info("Model downloaded.")

_ensure_model()

# ─── MediaPipe FaceLandmarker ─────────────────────────────────────────────────
_base_opts = mp_tasks.BaseOptions(model_asset_path=_MODEL_PATH)
_lm_opts   = mp_vision.FaceLandmarkerOptions(
    base_options=_base_opts,
    running_mode=mp_vision.RunningMode.IMAGE,
    num_faces=1,
    min_face_detection_confidence=0.6,
    min_face_presence_confidence=0.6,
    min_tracking_confidence=0.5,
)
FACE_LANDMARKER = mp_vision.FaceLandmarker.create_from_options(_lm_opts)

# ─── DeepFace config ──────────────────────────────────────────────────────────
DEEPFACE_MODEL    = "Facenet512"
DEEPFACE_DETECTOR = "opencv"
COSINE_THRESHOLD  = 0.30

# ─── Global state ─────────────────────────────────────────────────────────────
_asking_name:        bool  = False
_last_trigger_ts:    float = 0.0
_COOLDOWN:           float = 120.0
_last_known_identity: str  = ""   # keeps name visible during cooldown
_known_faces_cache:  list  = []   # refreshed after every registration


# ─── Data classes ─────────────────────────────────────────────────────────────
@dataclass
class BoundingBox:
    x: int
    y: int
    w: int
    h: int

@dataclass
class DetectionResult:
    present:       bool
    bbox:          Optional[BoundingBox]
    face_crop:     Optional[np.ndarray]
    identity:      Optional[str]        = None
    verified:      bool                 = False
    confidence:    float                = 0.0
    landmarks_img: Optional[np.ndarray] = None
    error:         Optional[str]        = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _decode_frame(data) -> np.ndarray:
    if isinstance(data, np.ndarray):
        return data
    arr   = np.frombuffer(data, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Could not decode image bytes.")
    return frame

def _get_bbox(landmarks, img_w, img_h, pad=20) -> BoundingBox:
    xs = [lm.x * img_w for lm in landmarks]
    ys = [lm.y * img_h for lm in landmarks]
    x1 = max(0,     int(min(xs)) - pad)
    y1 = max(0,     int(min(ys)) - pad)
    x2 = min(img_w, int(max(xs)) + pad)
    y2 = min(img_h, int(max(ys)) + pad)
    return BoundingBox(x=x1, y=y1, w=x2 - x1, h=y2 - y1)

def _draw_landmarks(frame, landmarks, img_w, img_h) -> np.ndarray:
    out = frame.copy()
    for lm in landmarks:
        cv2.circle(out, (int(lm.x * img_w), int(lm.y * img_h)), 1, (0, 255, 0), -1)
    return out

def _cosine_similarity(a, b) -> float:
    a, b  = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


# ─── Backend HTTP helpers ─────────────────────────────────────────────────────

def _post(path, **kwargs):
    try:
        return httpx.post(f"{BACKEND_URL}{path}", timeout=5, **kwargs)
    except Exception as e:
        logger.warning(f"POST {path} failed: {e}")
        return None

def _get(path):
    try:
        return httpx.get(f"{BACKEND_URL}{path}", timeout=5)
    except Exception as e:
        logger.warning(f"GET {path} failed: {e}")
        return None

def _load_known_faces() -> list:
    try:
        r = httpx.get(f"{BACKEND_URL}/faces/all", timeout=5)
        if r and r.status_code == 200:
            faces = r.json().get("faces", [])
            logger.info(f"[DETECTION] Loaded {len(faces)} known faces from DB")
            return faces
        else:
            logger.warning(f"[DETECTION] /faces/all returned {r.status_code if r else 'no response'}")
    except Exception as e:
        logger.warning(f"Could not load known faces: {e}")
    return []


# ─── Step 1: Presence ─────────────────────────────────────────────────────────

def detect_presence(frame: np.ndarray, draw_mesh: bool = False) -> DetectionResult:
    rgb       = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    detection = FACE_LANDMARKER.detect(mp_image)

    if not detection.face_landmarks:
        return DetectionResult(present=False, bbox=None, face_crop=None)

    h, w      = frame.shape[:2]
    landmarks = detection.face_landmarks[0]
    bbox      = _get_bbox(landmarks, w, h)
    face_crop = frame[bbox.y : bbox.y + bbox.h, bbox.x : bbox.x + bbox.w].copy()
    mesh_img  = _draw_landmarks(frame, landmarks, w, h) if draw_mesh else None

    return DetectionResult(present=True, bbox=bbox, face_crop=face_crop, landmarks_img=mesh_img)


# ─── Step 2: Extract embedding ────────────────────────────────────────────────

def extract_embedding(face_crop: np.ndarray) -> Optional[list]:
    try:
        _, enc  = cv2.imencode(".jpg", face_crop)
        img_arr = cv2.imdecode(enc, cv2.IMREAD_COLOR)
        res = DeepFace.represent(
            img_path          = img_arr,
            model_name        = DEEPFACE_MODEL,
            detector_backend  = DEEPFACE_DETECTOR,
            enforce_detection = False,
        )
        return res[0]["embedding"]
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return None


# ─── Step 3: Recognise ────────────────────────────────────────────────────────

def recognize_face(face_crop: np.ndarray, known_faces: list) -> tuple:
    if not known_faces:
        return False, None, None, 0.0

    probe_emb = extract_embedding(face_crop)
    if probe_emb is None:
        return False, None, None, 0.0

    best_sim     = -1.0
    best_name    = None
    best_face_id = None

    for entry in known_faces:
        stored_enc = entry.get("encoding")
        if not stored_enc:
            continue
        sim = _cosine_similarity(probe_emb, stored_enc)
        if sim > best_sim:
            best_sim     = sim
            best_name    = entry["name"]
            best_face_id = entry["face_id"]

    verified   = best_sim >= (1.0 - COSINE_THRESHOLD)
    confidence = round(max(0.0, best_sim), 4)
    logger.info(f"[DETECTION] Best match: '{best_name}' sim={confidence:.4f} verified={verified}")

    if verified:
        return True, best_name, best_face_id, confidence
    return False, None, None, confidence


# ─── Background: unknown visitor flow ─────────────────────────────────────────

def _handle_unknown_visitor(face_crop: np.ndarray):
    """
    Runs in daemon thread.
    Order:
      1. Poll for name (frontend already showing input via /visitor/unknown)
      2. Save face to DB first (/face/register)
      3. Then start session (/session/start) — face_id now exists in DB
      4. Refresh cache
    """
    global _asking_name, _known_faces_cache, _last_known_identity, _last_trigger_ts
    try:
        r = _post("/visitor/unknown")
        if not r or r.status_code != 200:
            logger.warning("[DETECTION] /visitor/unknown call failed")
            return

        logger.info("[DETECTION] Waiting for visitor name...")

        deadline  = time.time() + 30.0
        name_data = None

        while time.time() < deadline:
            r = _get("/visitor/name_response")
            if r and r.status_code == 200:
                data = r.json()
                if data.get("ready"):
                    name_data = data
                    _post("/visitor/clear_response")
                    break
            time.sleep(0.5)

        visitor_name = (name_data.get("name") or "Guest").strip() if name_data else "Guest"
        save_face    = name_data.get("save", True)                 if name_data else False
        new_face_id  = str(uuid.uuid4())

        logger.info(f"[DETECTION] Name received: '{visitor_name}' save={save_face}")

        # ★ STEP 1: Save face to DB FIRST so face_id exists before session references it
        if save_face and visitor_name not in ("Guest", ""):
            embedding = extract_embedding(face_crop)
            if embedding:
                resp = _post("/faces/register", json={
                    "face_id":  new_face_id,
                    "name":     visitor_name,
                    "encoding": embedding,
                })
                if resp and resp.status_code == 200:
                    logger.info(f"[DETECTION] Face registered: {visitor_name}")
                    _known_faces_cache   = _load_known_faces()
                    _last_known_identity = visitor_name
                else:
                    logger.warning(f"[DETECTION] /faces/register failed: {resp}")
            else:
                logger.warning("[DETECTION] Embedding failed — face not saved")

        # ★ STEP 2: Start session AFTER face is saved
        _post("/session/start", params={
            "user_name":    visitor_name,
            "face_id":      new_face_id if (save_face and visitor_name not in ("Guest", "")) else "",
            "is_returning": False,
            "visit_count":  1,
            "trigger":      "camera",
        })

    except Exception as e:
        logger.error(f"[DETECTION] _handle_unknown_visitor error: {e}")
    finally:
        _last_trigger_ts = time.time() + 60.0  # 60s grace — won't retrigger immediately
        _asking_name     = False


# ─── Main pipeline ────────────────────────────────────────────────────────────

def run_pipeline(frame_data, known_faces: list = None, draw_mesh: bool = False) -> DetectionResult:
    global _asking_name, _last_trigger_ts, _known_faces_cache, _last_known_identity

    try:
        frame = _decode_frame(frame_data)
    except Exception as e:
        return DetectionResult(present=False, bbox=None, face_crop=None, error=str(e))

    result = detect_presence(frame, draw_mesh=draw_mesh)
    if not result.present:
        return result

    if _asking_name:
        result.identity = "Identifying..."
        return result

    now = time.time()
    if now - _last_trigger_ts < _COOLDOWN:
        # In cooldown — show last known name so screen doesn't blank out
        if _last_known_identity:
            result.identity = _last_known_identity
            result.verified = True
        return result

    # Always use global cache
    verified, name, face_id, confidence = recognize_face(result.face_crop, _known_faces_cache)
    result.verified   = verified
    result.confidence = confidence

    if verified and name:
        result.identity      = name
        _last_known_identity = name
        _last_trigger_ts     = now
        _post("/session/start", params={
            "user_name":    name,
            "face_id":      face_id,
            "is_returning": True,
            "visit_count":  1,
            "trigger":      "camera",
        })
        logger.info(f"[DETECTION] Returning visitor: {name} (sim={confidence})")
    else:
        _last_known_identity = ""
        _last_trigger_ts     = now
        _asking_name         = True
        threading.Thread(
            target=_handle_unknown_visitor,
            args=(result.face_crop.copy(),),
            daemon=True,
        ).start()

    return result


# ─── Utility ──────────────────────────────────────────────────────────────────

def face_crop_to_b64(face_crop: np.ndarray) -> str:
    _, buf = cv2.imencode(".jpg", face_crop)
    return base64.b64encode(buf.tobytes()).decode("utf-8")


# ─── Local webcam test ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    src = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else \
          sys.argv[1]       if len(sys.argv) > 1 else 0

    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        print(f"Cannot open source: {src}")
        sys.exit(1)

    print("Running — press Q to quit.")
    _known_faces_cache = _load_known_faces()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        result  = run_pipeline(frame, draw_mesh=True)
        display = result.landmarks_img if result.landmarks_img is not None else frame.copy()

        if result.present and result.bbox:
            b     = result.bbox
            color = (0, 255, 0) if result.verified else (0, 165, 255)
            cv2.rectangle(display, (b.x, b.y), (b.x + b.w, b.y + b.h), color, 2)
            label = result.identity or "Unknown"
            cv2.putText(display, label, (b.x, b.y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        else:
            cv2.putText(display, "NO FACE", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 2)

        cv2.imshow("VRK Digital Receptionist", display)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()