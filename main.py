from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from faster_whisper import WhisperModel
import shutil
import os
import subprocess

app = FastAPI(title="Digital Receptionist Engine")

# ---------------------------------------------------------------------------
# LOAD THE MODEL ONCE at startup (not on every request — that would be slow)
# ---------------------------------------------------------------------------
print("Loading Whisper model... please wait.")
model = WhisperModel("base", device="cpu", compute_type="int8")
print("Model loaded. Engine is ready.")

# Path to your Piper model file — must be in the SAME folder as main.py
PIPER_MODEL = "en_US-amy-low.onnx"

# The fixed greeting the receptionist always speaks back
RECEPTIONIST_GREETING = (
    "Hello! I'm your digital receptionist. "
    "I can tell you our office hours or take a message for the team. "
    "How can I help?"
)


# ---------------------------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------------------------
@app.get("/")
def home():
    return {"status": "Digital Receptionist Engine is Online"}


# ---------------------------------------------------------------------------
# FEATURE 1: THE EARS — POST /transcribe
# Upload a .wav or .mp3, get back the spoken words as text.
# ---------------------------------------------------------------------------
@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    temp_path = "temp_upload.wav"

    try:
        # Save the uploaded file to disk
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Run Whisper on it
        segments, info = model.transcribe(temp_path, beam_size=5)
        full_text = " ".join(seg.text for seg in segments).strip()

        return {
            "transcription": full_text,
            "language": info.language,
            "language_probability": round(info.language_probability, 2),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

    finally:
        # FEATURE 3: CLEANUP CREW — always delete temp file, even on error
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ---------------------------------------------------------------------------
# FEATURE 2: THE MOUTH — POST /speak
# Send a text string, get back a .wav audio file of it spoken.
# ---------------------------------------------------------------------------
@app.post("/speak")
async def text_to_speech(text: str):
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    output_path = "receptionist_voice.wav"

    try:
        _run_piper(text, output_path)
        return FileResponse(
            output_path,
            media_type="audio/wav",
            filename="response.wav",
        )
    except Exception as e:
        if os.path.exists(output_path):
            os.remove(output_path)
        raise HTTPException(status_code=500, detail=f"Speech synthesis failed: {e}")


# ---------------------------------------------------------------------------
# FEATURE 4: THE BRIDGE — POST /chat
# Full pipeline: audio in -> transcribe -> greeting -> audio out
# This is what your frontend button will call.
# ---------------------------------------------------------------------------
@app.post("/chat")
async def chat(session_id: str, file: UploadFile = File(...)):
    temp_input  = "temp_input.wav"
    temp_output = "temp_output.wav"

    try:
        # Step 1: Save uploaded audio
        with open(temp_input, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Step 2: Transcribe (printed to terminal for debugging)
        segments, info = model.transcribe(temp_input, beam_size=5)
        user_said = " ".join(seg.text for seg in segments).strip()
        print(f"[Session {session_id}] User said: {user_said}")

        # Step 3: Generate the receptionist's spoken greeting
        _run_piper(RECEPTIONIST_GREETING, temp_output)

        # Step 4: Return the audio file
        return FileResponse(
            temp_output,
            media_type="audio/wav",
            filename="receptionist.wav",
            headers={"X-User-Said": user_said},
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat pipeline failed: {e}")

    finally:
        # Always clean up the input file
        if os.path.exists(temp_input):
            os.remove(temp_input)


# ---------------------------------------------------------------------------
# INTEGRATION: POST /new-user
# Slice 1 (Host) calls this when a person walks up to the receptionist.
# Receives the session_id and confirms the engine is ready to listen.
# ---------------------------------------------------------------------------
@app.post("/new-user")
async def new_user(session_id: str):
    print(f"[New User] Session started: {session_id}")
    return {"message": f"Listening for session {session_id}"}


# ---------------------------------------------------------------------------
# INTEGRATION: POST /speak-answer
# Slice 3 (Brain) calls this after looking up the answer in the database.
# Receives the answer text, converts it to voice, returns the audio.
# ---------------------------------------------------------------------------
@app.post("/speak-answer")
async def speak_answer(session_id: str, answer: str):
    if not answer.strip():
        raise HTTPException(status_code=400, detail="Answer cannot be empty.")

    output_path = "answer_voice.wav"
    print(f"[Session {session_id}] Speaking answer: {answer}")

    try:
        _run_piper(answer, output_path)
        return FileResponse(
            output_path,
            media_type="audio/wav",
            filename="answer.wav",
        )
    except Exception as e:
        if os.path.exists(output_path):
            os.remove(output_path)
        raise HTTPException(status_code=500, detail=f"Speech synthesis failed: {e}")


# ---------------------------------------------------------------------------
# HELPER: runs Piper as a subprocess (Windows-safe)
# ---------------------------------------------------------------------------
def _run_piper(text: str, output_path: str):
    command = [
        "python", "-m", "piper",
        "--model", PIPER_MODEL,
        "--output_file", output_path,
    ]

    result = subprocess.run(
        command,
        input=text.encode("utf-8"),
        capture_output=True,
    )

    if result.returncode != 0:
        error_msg = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Piper error (code {result.returncode}): {error_msg}")