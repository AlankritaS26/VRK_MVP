import io
import wave
import numpy as np

# We'll use piper for TTS
# If piper has issues on Windows, we fall back to a simple alternative
try:
    from piper.voice import PiperVoice
    PIPER_AVAILABLE = True
    print("[TTS] Piper imported successfully.")
except ImportError:
    PIPER_AVAILABLE = False
    print("[TTS] Piper not available, will use fallback.")


def text_to_speech(text: str, language: str = "en") -> bytes:
    """
    Converts text to audio bytes (WAV format).
    Returns raw WAV bytes that can be streamed to the browser.
    """
    if not text or not text.strip():
        return b""

    try:
        if PIPER_AVAILABLE:
            return _piper_tts(text)
        else:
            return _fallback_tts(text)

    except Exception as e:
        print(f"[TTS] Error: {e}")
        return b""


def _piper_tts(text: str) -> bytes:
    """
    Uses Piper TTS to generate audio.
    """
    import subprocess
    import tempfile
    import os

    # Write text to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(text)
        txt_path = f.name

    # Output WAV path
    wav_path = txt_path.replace('.txt', '.wav')

    try:
        # Run piper via command line
        subprocess.run([
            'piper',
            '--model', 'en_US-lessac-medium',
            '--output_file', wav_path
        ], input=text.encode(), capture_output=True, timeout=10)

        # Read the WAV file
        with open(wav_path, 'rb') as f:
            return f.read()

    finally:
        # Clean up temp files
        if os.path.exists(txt_path):
            os.remove(txt_path)
        if os.path.exists(wav_path):
            os.remove(wav_path)


def _fallback_tts(text: str) -> bytes:
    """
    Fallback: generates a silent WAV file.
    Frontend will use browser TTS instead.
    """
    # Return empty WAV — frontend detects this and uses browser TTS
    return b""
