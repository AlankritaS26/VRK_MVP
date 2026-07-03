"""
STT Pipeline — faster-whisper directly
Browser sends audio → ffmpeg converts → Whisper transcribes
Simple, reliable, no WebSocket complexity
"""

import subprocess
import tempfile
import os
import time
import numpy as np
import wave
from faster_whisper import WhisperModel

print("[STT] Loading Whisper turbo model...")
# "turbo" is the correct shorthand for large-v3-turbo in faster-whisper.
# If your package version is older and doesn't recognize "turbo", use:
# model = WhisperModel("deepdml/faster-whisper-large-v3-turbo-ct2", device="cpu", compute_type="int8")
model = WhisperModel("turbo", device="cpu", compute_type="int8")
print("[STT] Whisper turbo model ready.")

# Keep STTPipeline class so main.py import doesn't break
class STTPipeline:
    def __init__(self, on_partial=None, on_final=None):
        pass
    def start(self): pass
    def is_ready(self): return True
    def feed(self, audio_bytes): pass
    def stop(self): pass


def transcribe_audio(audio_bytes: bytes) -> dict:
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

        with wave.open(wav_path, 'r') as wf:
            frames = wf.readframes(wf.getnframes())
            audio_np = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

        rms = np.sqrt(np.mean(audio_np ** 2))
        if rms < 0.005:
            return {"text": "", "confidence": 0.0, "language": "en", "error": "too_quiet"}

        segments, info = model.transcribe(
            wav_path,
            beam_size=5,
            language="en",
            vad_filter=True,
            temperature=0.0,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
        )

        full_text = ""
        scores = []
        for segment in segments:
            full_text += segment.text + " "
            scores.append(segment.avg_logprob)

        full_text = full_text.strip()
        confidence = max(0.0, min(1.0, sum(scores)/len(scores) + 1.0)) if scores else 0.0
        latency_ms = int((time.time() - start) * 1000)

        print(f"[STT] '{full_text}' | conf:{confidence:.2f} | {latency_ms}ms")
        return {
            "text": full_text,
            "confidence": round(confidence, 2),
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
            except: pass