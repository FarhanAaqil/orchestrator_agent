"""
toji-shell/voice/piper_tts.py

Text-to-Speech synthesizer for Toji voice responses.
Supports local Piper TTS executable, with fallback to Windows SAPI / pyttsx3.
"""

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("toji.voice.tts")


class PiperTTS:
    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path
        self.piper_exe = shutil.which("piper")
        self._backend = "piper" if self.piper_exe else "sapi"
        logger.info("Toji TTS initialized with backend: %s", self._backend)

    def speak(self, text: str, output_path: Optional[str] = None) -> bool:
        """Speak or synthesize text to audio."""
        if not text.strip():
            return False

        # If Piper is available and model path provided
        if self._backend == "piper" and self.model_path and os.path.exists(self.model_path):
            out_file = output_path or "toji_speech.wav"
            cmd = [
                self.piper_exe,
                "--model", self.model_path,
                "--output_file", out_file,
            ]
            try:
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                proc.communicate(input=text.encode("utf-8"))
                return proc.returncode == 0
            except Exception as e:
                logger.error("Piper TTS execution failed: %s", e)

        # Fallback 1: pyttsx3
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 175)
            engine.setProperty("volume", 0.95)
            if output_path:
                engine.save_to_file(text, output_path)
            else:
                engine.say(text)
            engine.runAndWait()
            return True
        except Exception as e:
            logger.debug("pyttsx3 fallback unavailable: %s", e)

        # Fallback 2: PowerShell SAPI on Windows
        if sys.platform == "win32" and not output_path:
            try:
                escaped = text.replace('"', '`"').replace("'", "''")
                ps_cmd = f'Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak("{escaped}")'
                subprocess.run(["powershell", "-Command", ps_cmd], check=True)
                return True
            except Exception as e:
                logger.error("PowerShell SAPI speech failed: %s", e)

        return False


if __name__ == "__main__":
    tts = PiperTTS()
    print(f"Toji TTS backend: {tts._backend}")
    if len(sys.argv) > 1:
        tts.speak(" ".join(sys.argv[1:]))
