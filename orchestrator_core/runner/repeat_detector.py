"""
orchestrator_core/runner/repeat_detector.py

Repeat Action Detector (Section 5.5).
Tracks consecutive actions with identical arguments.
Injects a warning into the agent's observation stream at 3 consecutive identical actions.
Raises LoopDetectedError at 5 consecutive identical actions to abort infinite loops.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

from orchestrator_core.exceptions import LoopDetectedError

logger = logging.getLogger(__name__)


def compute_action_hash(action_name: str, args: Any) -> str:
    """Compute a deterministic hash for an action and its arguments."""
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
            canonical_json = json.dumps(parsed, separators=(",", ":"), sort_keys=True)
        except Exception:
            canonical_json = args.strip()
    elif isinstance(args, (dict, list)):
        canonical_json = json.dumps(args, separators=(",", ":"), sort_keys=True)
    elif args is None:
        canonical_json = ""
    else:
        canonical_json = str(args).strip()

    combined = f"{action_name.strip()}:{canonical_json}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


class RepeatDetector:
    """
    Monitors agent action sequences for stuck loops or repetitive actions.
    """

    def __init__(
        self,
        job_id: str,
        warning_threshold: int = 3,
        abort_threshold: int = 5,
    ) -> None:
        self.job_id = job_id
        self.warning_threshold = warning_threshold
        self.abort_threshold = abort_threshold
        self._last_action_hash: Optional[str] = None
        self._last_action_name: Optional[str] = None
        self._consecutive_count: int = 0

    def record_action(self, action_name: str, args: Any = None) -> Optional[str]:
        """
        Record an action and its arguments.
        Returns a warning message if warning_threshold is reached.
        Raises LoopDetectedError if abort_threshold is reached.
        """
        action_hash = compute_action_hash(action_name, args)

        if action_hash == self._last_action_hash:
            self._consecutive_count += 1
        else:
            self._last_action_hash = action_hash
            self._last_action_name = action_name
            self._consecutive_count = 1

        if self._consecutive_count >= self.abort_threshold:
            logger.critical(
                "Job %s reached repeat abort threshold: '%s' called %d times with identical arguments",
                self.job_id,
                action_name,
                self._consecutive_count,
            )
            raise LoopDetectedError(self.job_id, action_name, self._consecutive_count)

        if self._consecutive_count >= self.warning_threshold:
            logger.warning(
                "Job %s repeated action warning: '%s' called %d times with identical arguments",
                self.job_id,
                action_name,
                self._consecutive_count,
            )
            return (
                f"Warning: You have executed action '{action_name}' {self._consecutive_count} times "
                "consecutively with identical arguments without making progress. "
                "You MUST alter your approach, examine prior errors, or ask the user for guidance."
            )

        return None

    def reset(self) -> None:
        """Reset consecutive counter."""
        self._last_action_hash = None
        self._last_action_name = None
        self._consecutive_count = 0
