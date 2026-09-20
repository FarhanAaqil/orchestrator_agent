"""
toji-shell/voice/voice_runner.py

Voice pipeline coordinator for Toji:
Integrates Wake Word -> STT -> /api/dispatch -> TTS in an end-to-end loop.
"""

import argparse
import json
import logging
import os
import sys
import urllib.request
from pathlib import Path

from whisper_stt import WhisperSTT
from piper_tts import PiperTTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("toji.voice.runner")

DEFAULT_API_BASE = os.environ.get("TOJI_API_BASE", "http://127.0.0.1:8000")


def dispatch_command(command: str, api_base: str = DEFAULT_API_BASE) -> str:
    """Send command to the FastAPI sidecar /api/dispatch endpoint."""
    url = f"{api_base}/api/dispatch"
    payload = json.dumps({"command": command}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "TojiVoice/1.0"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("output", "")
    except Exception as e:
        logger.error("Failed to dispatch to %s: %s", url, e)
        return f"I encountered an error executing your command: {e}"


def run_voice_loop(api_base: str = DEFAULT_API_BASE) -> None:
    """Continuous voice interaction loop."""
    stt = WhisperSTT()
    tts = PiperTTS()

    logger.info("Toji Voice Pipeline started. Connected to %s", api_base)
    print("\n" + "=" * 50)
    print("  TOJI AUTONOMOUS VOICE INTERFACE")
    print(f"  Backend: {api_base}")
    print("=" * 50 + "\n")

    tts.speak("Toji voice system online and ready.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Toji Voice Pipeline Runner")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="FastAPI sidecar URL")
    args = parser.parse_args()

    run_voice_loop(api_base=args.api_base)


if __name__ == "__main__":
    main()
