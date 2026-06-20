"""
STT Pipeline using RealtimeSTT
- Uses faster-whisper as the transcription engine
- Small model for accuracy, tiny for real-time preview
- Built-in VAD so it stops when you stop talking
- Streams partial text while you speak
"""

import asyncio
import threading
from typing import Callable, Optional
from RealtimeSTT import AudioToTextRecorder

# ─── RECORDER INSTANCE ───────────────────────────────────────────────────────
# We create one global recorder and reuse it
# This avoids reloading the model on every request

recorder: Optional[AudioToTextRecorder] = None
recorder_lock = threading.Lock()

def get_recorder() -> AudioToTextRecorder:
    global recorder
    if recorder is None:
        print("[STT] Initializing RealtimeSTT recorder...")
        recorder = AudioToTextRecorder(
            # Main transcription model — better accuracy
            model="small",
            transcription_engine="faster_whisper",

            # Real-time preview model — fast live text
            enable_realtime_transcription=True,
            realtime_model_type="tiny",

            # Language
            language="en",

            # VAD settings — stops recording when you stop talking
            silero_sensitivity=0.4,
            webrtc_sensitivity=2,
            post_speech_silence_duration=0.6,  # 0.6s silence = end of speech
            min_length_of_recording=0.3,       # ignore sounds under 0.3s
            min_gap_between_recordings=0.1,

            # Campus vocabulary bias
            initial_prompt=(
                "RNSIT, RNS Institute of Technology, Channasandra, Bengaluru, "
                "USN, SGPA, CGPA, CIE, SEE, CSE, ECE, EEE, ISE, AI, ML, "
                "fees, hostel, canteen, library, admin block, principal, HOD"
            ),

            # Performance
            beam_size=5,
            beam_size_realtime=1,   # tiny model uses beam 1 for speed
            no_log_file=True,
            spinner=False,
        )
        print("[STT] RealtimeSTT ready.")
    return recorder


def transcribe_once(
    on_realtime_text: Optional[Callable[[str], None]] = None
) -> dict:
    """
    Records one utterance and returns the final transcript.
    Calls on_realtime_text callback with partial text while speaking.
    """
    import time
    start = time.time()

    rec = get_recorder()

    # Set real-time callback if provided
    if on_realtime_text:
        rec.on_realtime_transcription_update = on_realtime_text

    # This blocks until the user stops speaking and returns final text
    text = rec.text()
    text = text.strip()

    latency_ms = int((time.time() - start) * 1000)
    print(f"[STT] '{text}' | {latency_ms}ms")

    return {
        "text": text,
        "confidence": 1.0,  # RealtimeSTT doesn't expose logprob directly
        "language": "en",
        "latency_ms": latency_ms
    }


# ─── SIMPLE FUNCTION FOR FASTAPI ENDPOINT ────────────────────────────────────
# This is what main.py calls

def transcribe_audio(audio_bytes: bytes) -> dict:
    """
    NOTE: RealtimeSTT reads directly from the microphone.
    This function is kept for API compatibility but RealtimeSTT
    is better used via the WebSocket streaming endpoint.
    For the /stt POST endpoint, we still use faster-whisper directly
    as a fallback for browser audio bytes.
    """
    import io
    import subprocess
    import tempfile
    import os
    import time
    import numpy as np
    from faster_whisper import WhisperModel

    # Lazy load fallback model
    if not hasattr(transcribe_audio, '_model'):
        print("[STT] Loading fallback Whisper small model...")
        transcribe_audio._model = WhisperModel("small", device="cpu", compute_type="int8")
        print("[STT] Fallback model ready.")

    start = time.time()
    webm_path = None
    wav_path = None

    try:
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as f:
            f.write(audio_bytes)
            webm_path = f.name

        wav_path = webm_path.replace('.webm', '.wav')

        result = subprocess.run([
            'ffmpeg', '-y', '-i', webm_path,
            '-ar', '16000', '-ac', '1', '-f', 'wav', wav_path
        ], capture_output=True, timeout=5)

        if result.returncode != 0:
            return {"text": "", "confidence": 0.0, "language": "en", "error": "conversion_failed"}

        import wave
        with wave.open(wav_path, 'r') as wf:
            frames = wf.readframes(wf.getnframes())
            audio_np = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

        rms = np.sqrt(np.mean(audio_np ** 2))
        if rms < 0.005:
            return {"text": "", "confidence": 0.0, "language": "en", "error": "too_quiet"}

        segments, info = transcribe_audio._model.transcribe(
            wav_path,
            beam_size=5,
            language="en",
            initial_prompt=(
                "RNSIT, RNS Institute of Technology, USN, SGPA, CIE, "
                "fees, hostel, canteen, library, admin block, principal"
            ),
            vad_filter=True,
            temperature=0.0,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
        )

        full_text = ""
        confidence_scores = []
        for segment in segments:
            full_text += segment.text + " "
            confidence_scores.append(segment.avg_logprob)

        full_text = full_text.strip()
        avg_confidence = 0.0
        if confidence_scores:
            avg_logprob = sum(confidence_scores) / len(confidence_scores)
            avg_confidence = max(0.0, min(1.0, avg_logprob + 1.0))

        latency_ms = int((time.time() - start) * 1000)
        print(f"[STT] '{full_text}' | conf: {avg_confidence:.2f} | {latency_ms}ms")

        return {
            "text": full_text,
            "confidence": round(avg_confidence, 2),
            "language": info.language,
            "latency_ms": latency_ms
        }

    except Exception as e:
        print(f"[STT] Error: {e}")
        return {"text": "", "confidence": 0.0, "language": "en", "error": str(e)}

    finally:
        for path in [webm_path, wav_path]:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except:
                pass