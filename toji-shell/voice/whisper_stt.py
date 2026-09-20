"""
toji-shell/voice/whisper_stt.py

Speech-to-Text module for Toji.
Supports local faster-whisper/whisper when installed, with graceful fallback
to speech_recognition or audio input streaming.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("toji.voice.stt")


class WhisperSTT:
    def __init__(self, model_size: str = "tiny.en"):
        self.model_size = model_size
        self._model = None
        self._backend = None
        self._initialize_backend()

    def _initialize_backend(self) -> None:
        """Attempt to load faster-whisper or openai-whisper."""
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
            self._backend = "faster-whisper"
            logger.info("Loaded faster-whisper (%s)", self.model_size)
            return
        except ImportError:
            pass

        try:
            import whisper
            self._model = whisper.load_model(self.model_size)
            self._backend = "openai-whisper"
            logger.info("Loaded openai-whisper (%s)", self.model_size)
            return
        except ImportError:
            pass

        self._backend = "fallback"
        logger.info("Local Whisper libraries not installed; falling back to speech_recognition / Web Speech API")

    def transcribe(self, audio_path: str) -> Optional[str]:
        """Transcribe an audio file to text."""
        if not os.path.exists(audio_path):
            logger.error("Audio file does not exist: %s", audio_path)
            return None

        if self._backend == "faster-whisper":
            segments, _ = self._model.transcribe(audio_path)
            text = " ".join([s.text for s in segments]).strip()
            return text
        elif self._backend == "openai-whisper":
            res = self._model.transcribe(audio_path)
            return res.get("text", "").strip()
        else:
            try:
                import speech_recognition as sr
                r = sr.Recognizer()
                with sr.AudioFile(audio_path) as source:
                    audio_data = r.record(source)
                    return r.recognize_google(audio_data)
            except Exception as e:
                logger.warning("Transcription fallback error: %s", e)
                return None


if __name__ == "__main__":
    stt = WhisperSTT()
    print(f"Toji STT initialized with backend: {stt._backend}")
