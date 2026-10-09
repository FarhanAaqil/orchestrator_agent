"""
orchestrator_core/runner package

Autonomous agent runner engine enforcing ReAct loop, safety guards,
untrusted data isolation, and crash resumption.
"""

from orchestrator_core.runner.caps import check_guards
from orchestrator_core.runner.context import build_messages, build_system_prompt
from orchestrator_core.runner.repeat_detector import RepeatDetector
from orchestrator_core.runner.sanitize import sanitize_observation, strip_control_chars


def __getattr__(name: str):
    if name == "run_job":
        from orchestrator_core.runner.loop import run_job
        return run_job
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "check_guards",
    "build_messages",
    "build_system_prompt",
    "run_job",
    "RepeatDetector",
    "sanitize_observation",
    "strip_control_chars",
]
