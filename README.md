# RNS Digital Receptionist — Complete Setup Guide

## What this system does
- Detects faces via webcam
- Recognizes returning visitors within **30 days** and greets them by name
- Shows live speech transcript on screen (both user and kiosk speech)
- Displays the **RNS logo** on idle screen with breathing animation
- Auto-resets when visitor walks away

---

## Folder Structure
```
Slice2/
├── backend/
│   ├── main.py          ← FastAPI server (WebSockets, face DB, sessions)
│   ├── detection.py     ← Camera engine (face detection + recognition)
│   ├── requirements.txt
│   ├── .env             ← Config (camera index, thresholds)
│   └── face_db.json     ← Auto-created on first face registration
└── frontend/
    └── src/
        ├── App.js
        ├── IdleScreen.js
        ├── WelcomeScreen.js
        └── index.css
```

---

## Step 1 — Install Backend Dependencies
Open Terminal in `Slice2/backend/` and run:
```powershell
pip install -r requirements.txt
```

### Optional: Enable Full Face Recognition (Python 3.9–3.12 only)
```powershell
pip install face_recognition dlib
```
If this fails, the system automatically falls back to OpenCV (detects faces but won't recognize names).

---

## Step 2 — Start the Backend (Terminal 1)
```powershell
cd Desktop\Slice2\backend
uvicorn main:app --reload
```
You should see: `Uvicorn running on http://127.0.0.1:8000`

Verify it works: Open http://127.0.0.1:8000/docs in your browser.

---

## Step 3 — Start the Frontend (Terminal 2)
```powershell
cd Desktop\Slice2\frontend
npm start
```
Open http://localhost:3000 — you'll see the **breathing RNS logo**.

---

## Step 4 — Start the Camera (Terminal 3)
```powershell
cd Desktop\Slice2\backend
python detection.py
```

---

## Step 5 — Register Yourself (First Time)
1. Step in front of the camera
2. Stand still for ~2 seconds
3. **Terminal 3 will print:** `[NEW VISITOR DETECTED] Face not recognized.`
4. **Type your name and press Enter** (e.g., `Akshatha`)
5. You're registered! The screen will show: `Hello, Akshatha! Welcome to RNS Institute of Technology! 🎓`

## Step 6 — Test Return Recognition
Next time you step in front of the camera, the screen will show:
`Hey Akshatha! Welcome back! 😊`
(No need to type your name again — works for 30 days!)

---

## Sending Speech Text to Screen
### Test as "User Speaking":
```powershell
curl -X POST http://127.0.0.1:8000/message ^
  -H "Content-Type: application/json" ^
  -d "{\"session_id\": \"test\", \"text\": \"Where is the library?\", \"speaker\": \"user\"}"
```

### Test as "Kiosk Replying":
```powershell
curl -X POST http://127.0.0.1:8000/message ^
  -H "Content-Type: application/json" ^
  -d "{\"session_id\": \"test\", \"text\": \"The library is on the 2nd floor of Block B.\", \"speaker\": \"kiosk\"}"
```

---

## How Face Recognition Works (30-Day Memory)
- On first visit: camera detects face → asks for name in terminal → saves encoding + name to `face_db.json`
- On return visit: camera matches face encoding → greets by name automatically
- Faces not seen in 30 days are automatically purged from the database

## Adjusting Sensitivity (in .env)
| Setting | Default | Effect |
|---|---|---|
| `PASSERBY_THRESHOLD` | 80 | Higher = less sensitive to stopping |
| `WALK_AWAY_SECONDS` | 5 | Seconds before session ends |
| `FACE_TOLERANCE` | 0.50 | Lower = stricter face matching |
| `CAMERA_INDEX` | 0 | Change if wrong camera used |
