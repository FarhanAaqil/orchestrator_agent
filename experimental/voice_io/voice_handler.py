"""
NOT SUPPORTED in orchestrator_core v2.

This module is an experimental voice I/O helper. It is:
  - Not imported by orchestrator_core/
  - Not covered by any test in the CI suite
  - Not deployed in the production Docker image
  - Kept as a reference implementation only

Voice handler with graceful degradation.

Both pyttsx3 (TTS) and SpeechRecognition can fail to initialise on some
systems (Linux, Docker, missing audio drivers). Rather than crashing the
whole app at import time, we catch failures here and expose stub functions
that log a warning and do nothing.
"""
import logging

logger = logging.getLogger(__name__)

# ─── TTS Engine ───────────────────────────────────────────────────

_tts_engine = None
_tts_available = False

try:
    import pyttsx3
    import threading

    _tts_engine = pyttsx3.init()
    _tts_engine.setProperty('rate', 175)
    _tts_engine.setProperty('volume', 1.0)
    _tts_available = True
except Exception as e:
    logger.warning("pyttsx3 TTS unavailable: %s. Voice output disabled.", e)


def speak(text: str) -> None:
    """Speak text aloud. No-op if TTS is not available."""
    if not _tts_available or _tts_engine is None:
        return

    def _speak():
        try:
            _tts_engine.say(text)
            _tts_engine.runAndWait()
        except Exception as err:
            logger.warning("TTS speak() failed: %s", err)

    import threading
    thread = threading.Thread(target=_speak, daemon=True)
    thread.start()


# ─── Speech Recognition ───────────────────────────────────────────

_sr_available = False
_recognizer = None

try:
    import speech_recognition as sr
    _recognizer = sr.Recognizer()
    _sr_available = True
except Exception as e:
    logger.warning("SpeechRecognition unavailable: %s. Voice input disabled.", e)


def listen() -> str:
    """Listen for voice input. Returns empty string if SR is not available."""
    if not _sr_available or _recognizer is None:
        logger.warning("listen() called but SpeechRecognition is not available.")
        return ""

    try:
        import speech_recognition as sr
        with sr.Microphone() as source:
            _recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = _recognizer.listen(source, timeout=5, phrase_time_limit=10)
            return _recognizer.recognize_google(audio)
    except Exception:
        return ""