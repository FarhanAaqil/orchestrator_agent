"""
orchestrator_core/jobs/state_machine.py

Formal Job state machine enforcing allowed state transitions (Section 5.4).

Allowed transitions:
  queued             -> running, cancelled
  running            -> awaiting_approval, awaiting_input, succeeded, failed, cancelled, queued (backoff/re-queue)
  awaiting_approval  -> queued, running, cancelled
  awaiting_input     -> queued, running, cancelled
  succeeded          -> (terminal)
  failed             -> queued (manual retry / retry loop)
  cancelled          -> (terminal)
  expired            -> (terminal)
"""

from __future__ import annotations

from orchestrator_core.exceptions import InvalidJobStateTransitionError

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancelled"}),
    "running": frozenset({
        "awaiting_approval",
        "awaiting_input",
        "succeeded",
        "failed",
        "cancelled",
        "queued",
    }),
    "awaiting_approval": frozenset({"queued", "running", "cancelled"}),
    "awaiting_input": frozenset({"queued", "running", "cancelled"}),
    "succeeded": frozenset(),
    "failed": frozenset({"queued"}),
    "cancelled": frozenset(),
    "expired": frozenset(),
}

TERMINAL_STATES = frozenset({"succeeded", "cancelled", "expired"})


def can_transition(current_status: str, target_status: str) -> bool:
    """Return True if transition from current_status to target_status is valid."""
    if current_status == target_status:
        return True
    allowed = ALLOWED_TRANSITIONS.get(current_status, frozenset())
    return target_status in allowed


def validate_transition(job_id: str, current_status: str, target_status: str) -> None:
    """
    Enforce state machine transition.
    Raises InvalidJobStateTransitionError if transition is illegal.
    """
    if not can_transition(current_status, target_status):
        raise InvalidJobStateTransitionError(job_id, current_status, target_status)
