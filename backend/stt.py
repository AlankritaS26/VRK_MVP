"""
STT Pipeline — RealtimeSTT with feed_audio()
Browser sends audio chunks via WebSocket → backend feeds to RealtimeSTT
RealtimeSTT handles VAD, silence detection, real-time text, final transcript
No mic needed on backend — works with Scenario B
"""

import threading
import time
from typing import Optional, Callable

class STTPipeline:
    """
    One instance per WebSocket connection.
    Browser feeds audio chunks, we stream partial + final text back.
    """

    def __init__(
        self,
        on_partial: Callable[[str], None],
        on_final: Callable[[str], None]
    ):
        self.on_partial = on_partial
        self.on_final = on_final
        self.recorder = None
        self._ready = False
        self._thread = None

    def start(self):
        """Initialize RealtimeSTT in a background thread."""
        self._thread = threading.Thread(target=self._init_and_run, daemon=True)
        self._thread.start()

    def _init_and_run(self):
        try:
            from RealtimeSTT import AudioToTextRecorder
            print("[STT] Initializing RealtimeSTT pipeline...")

            self.recorder = AudioToTextRecorder(
                # Main model — best accuracy on CPU without GPU
                model="small",
                transcription_engine="faster_whisper",

                # Real-time preview — tiny model is fast enough for live text
                enable_realtime_transcription=True,
                realtime_model_type="tiny",
                realtime_processing_pause=0.1,

                # No mic — we feed audio manually
                use_microphone=False,

                # Language
                language="en",

                # VAD — detects when you stop speaking
                silero_sensitivity=0.4,
                webrtc_sensitivity=2,
                post_speech_silence_duration=0.6,
                min_length_of_recording=0.4,
                min_gap_between_recordings=0.1,

                # Accuracy settings
                beam_size=5,
                beam_size_realtime=1,
                temperature=0.0,
                no_speech_threshold=0.5,
                condition_on_previous_text=False,

                # Callbacks
                on_realtime_transcription_update=self._on_partial,

                # No logging clutter
                no_log_file=True,
                spinner=False,
            )

            self._ready = True
            print("[STT] Pipeline ready. Waiting for audio...")

            # Keep running — process utterances continuously
            while self._ready:
                text = self.recorder.text()
                text = (text or "").strip()
                if text:
                    print(f"[STT] Final: '{text}'")
                    self.on_final(text)

        except Exception as e:
            print(f"[STT] Pipeline error: {e}")
            self._ready = False

    def _on_partial(self, text: str):
        """Called by RealtimeSTT with live text while speaking."""
        if text and text.strip():
            self.on_partial(text.strip())

    def feed(self, audio_bytes: bytes):
        """Feed audio chunk from browser into RealtimeSTT."""
        if self.recorder and self._ready:
            try:
                # RealtimeSTT expects 16kHz mono PCM
                # Browser sends WebM — we convert first
                pcm = self._convert_to_pcm(audio_bytes)
                if pcm:
                    self.recorder.feed_audio(pcm, original_sample_rate=16000)
            except Exception as e:
                print(f"[STT] Feed error: {e}")

    def _convert_to_pcm(self, audio_bytes: bytes) -> Optional[bytes]:
        """Convert WebM audio bytes to 16kHz mono PCM."""
        import subprocess
        import tempfile
        import os

        webm_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as f:
                f.write(audio_bytes)
                webm_path = f.name

            result = subprocess.run([
                'ffmpeg', '-y',
                '-i', webm_path,
                '-ar', '16000',
                '-ac', '1',
                '-f', 's16le',  # raw PCM format RealtimeSTT expects
                'pipe:1'        # output to stdout
            ], capture_output=True, timeout=3)

            if result.returncode == 0 and result.stdout:
                return result.stdout
            return None

        except Exception as e:
            print(f"[STT] Conversion error: {e}")
            return None
        finally:
            if webm_path:
                try:
                    os.remove(webm_path)
                except:
                    pass

    def is_ready(self) -> bool:
        return self._ready

    def stop(self):
        """Stop the pipeline."""
        self._ready = False
        if self.recorder:
            try:
                self.recorder.stop()
                self.recorder.shutdown()
            except:
                pass
        print("[STT] Pipeline stopped.")


# ─── FALLBACK for /stt POST endpoint ─────────────────────────────────────────

_fallback_model = None

def transcribe_audio(audio_bytes: bytes) -> dict:
    """Fallback using faster-whisper directly for POST /stt endpoint."""
    global _fallback_model

    if _fallback_model is None:
        from faster_whisper import WhisperModel
        print("[STT] Loading fallback small model...")
        _fallback_model = WhisperModel("small", device="cpu", compute_type="int8")
        print("[STT] Fallback ready.")

    import subprocess
    import tempfile
    import os
    import numpy as np
    import wave

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

        segments, info = _fallback_model.transcribe(
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
            except:
                pass