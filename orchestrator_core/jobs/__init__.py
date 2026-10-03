"""
orchestrator_core/jobs/__init__.py

Jobs domain: state machine, persistent queue service, worker, and zombie reaper.
"""

from orchestrator_core.jobs.events import JobEventHub, event_hub
from orchestrator_core.jobs.reaper import reap_zombies
from orchestrator_core.jobs.service import JobService
from orchestrator_core.jobs.state_machine import ALLOWED_TRANSITIONS, validate_transition
from orchestrator_core.jobs.worker import Worker

__all__ = [
    "validate_transition",
    "ALLOWED_TRANSITIONS",
    "JobService",
    "reap_zombies",
    "Worker",
    "JobEventHub",
    "event_hub",
]
