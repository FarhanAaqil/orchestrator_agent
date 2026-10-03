"""
tests/test_job_state_machine.py

Unit tests for the autonomous job state machine.
Verifies all valid transitions, terminal state immutability, and illegal transition exceptions.
"""

import pytest

from orchestrator_core.exceptions import InvalidJobStateTransitionError
from orchestrator_core.jobs.state_machine import ALLOWED_TRANSITIONS, validate_transition
from orchestrator_core.models import JobStatus


def test_allowed_transitions_coverage():
    """Verify all defined statuses have explicit transition mappings."""
    expected_statuses = {
        "queued",
        "running",
        "awaiting_approval",
        "awaiting_input",
        "succeeded",
        "failed",
        "cancelled",
        "expired",
    }
    assert set(ALLOWED_TRANSITIONS.keys()) == expected_statuses


@pytest.mark.parametrize(
    "from_state,to_state",
    [
        ("queued", "running"),
        ("queued", "cancelled"),
        ("running", "awaiting_approval"),
        ("running", "awaiting_input"),
        ("running", "succeeded"),
        ("running", "failed"),
        ("running", "cancelled"),
        ("running", "queued"),
        ("awaiting_approval", "queued"),
        ("awaiting_approval", "running"),
        ("awaiting_approval", "cancelled"),
        ("awaiting_input", "queued"),
        ("awaiting_input", "running"),
        ("awaiting_input", "cancelled"),
        ("failed", "queued"),
    ],
)
def test_valid_transitions_pass(from_state: JobStatus, to_state: JobStatus):
    """All valid transitions should execute without raising exceptions."""
    validate_transition("test-job-123", from_state, to_state)


@pytest.mark.parametrize(
    "from_state,to_state",
    [
        # Terminal states cannot transition to anything
        ("succeeded", "queued"),
        ("succeeded", "running"),
        ("succeeded", "failed"),
        ("succeeded", "cancelled"),
        ("cancelled", "running"),
        ("cancelled", "queued"),
        ("expired", "running"),
        ("expired", "queued"),
        # Queued cannot jump directly to terminal success or awaiting states without running
        ("queued", "succeeded"),
        ("queued", "awaiting_approval"),
        ("queued", "awaiting_input"),
        ("queued", "failed"),
        # Failed cannot jump directly to succeeded
        ("failed", "succeeded"),
        ("failed", "running"),
    ],
)
def test_invalid_transitions_raise(from_state: JobStatus, to_state: JobStatus):
    """Illegal transitions must raise InvalidJobStateTransitionError."""
    with pytest.raises(InvalidJobStateTransitionError) as exc_info:
        validate_transition("test-job-456", from_state, to_state)
    assert exc_info.value.job_id == "test-job-456"
    assert exc_info.value.current_state == from_state
    assert exc_info.value.target_state == to_state
