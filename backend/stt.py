import io
import subprocess
import tempfile
import os
import numpy as np
from faster_whisper import WhisperModel

print("[STT] Loading Whisper model...")
model = WhisperModel("base", device="cpu", compute_type="int8")
print("[STT] Whisper model ready.")


def transcribe_audio(audio_bytes: bytes) -> dict:
    try:
        # Save incoming WebM bytes to a temp file
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as f:
            f.write(audio_bytes)
            webm_path = f.name

        wav_path = webm_path.replace('.webm', '.wav')

        # Convert WebM to WAV using ffmpeg
        result = subprocess.run([
            'ffmpeg', '-y',
            '-i', webm_path,
            '-ar', '16000',
            '-ac', '1',
            '-f', 'wav',
            wav_path
        ], capture_output=True, timeout=10)

        if result.returncode != 0:
            print(f"[STT] ffmpeg error: {result.stderr.decode()}")
            return {"text": "", "confidence": 0.0, "language": "en", "error": "conversion_failed"}

        # Transcribe the WAV file directly
        segments, info = model.transcribe(
            wav_path,
            beam_size=5,
            language="en",
            initial_prompt=None
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

        print(f"[STT] Heard: '{full_text}' | confidence: {avg_confidence:.2f}")

        return {
            "text": full_text,
            "confidence": round(avg_confidence, 2),
            "language": info.language
        }

    except Exception as e:
        print(f"[STT] Error: {e}")
        return {"text": "", "confidence": 0.0, "language": "en"}

    finally:
        # Clean up temp files
        for path in [webm_path, wav_path]:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass