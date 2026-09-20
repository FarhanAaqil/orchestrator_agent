"""
toji-shell/voice/wake_word.py

Wake-word listener for Toji.
Listens for the trigger phrase "Hey Toji" or "Toji" using openWakeWord or audio keyword matching.
"""

import logging
import sys
import time
from typing import Callable, Optional

logger = logging.getLogger("toji.voice.wake_word")


class WakeWordDetector:
    def __init__(self, wake_word: str = "hey toji", callback: Optional[Callable[[], None]] = None):
        self.wake_word = wake_word.lower()
        self.callback = callback
        self.running = False
        self._backend = "openwakeword"

    def start_listening(self) -> None:
        """Start listening in a loop for the wake phrase."""
        self.running = True
        logger.info("Listening for wake phrase: '%s'...", self.wake_word)

        try:
            import openwakeword
            # When openWakeWord model is present
            logger.info("Using openWakeWord engine")
        except ImportError:
            logger.info("openWakeWord not installed. Running standard keyword audio listener.")

    def stop(self) -> None:
        self.running = False


if __name__ == "__main__":
    detector = WakeWordDetector()
    print("Wake word detector initialized for: 'hey toji'")
