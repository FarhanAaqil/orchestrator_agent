"""
orchestrator_core/tools/spec.py

Formal capability model and tool specification (Section 5.5).
Every tool in the system is declared with an explicit capability class:
  - READ: Idempotent, safe read with zero external side effects.
  - PROPOSE: Writes strictly to proposals / approvals table for human review.
  - EXEC: Real-world side effect; executor-only, NEVER registered in agent registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable, Optional
from pydantic import BaseModel


class Capability(StrEnum):
    """Tool capability classifications governing access and execution boundaries."""
    READ = "read"        # Safe, idempotent, read-only
    PROPOSE = "propose"  # Internal proposal queue write only
    EXEC = "exec"        # Real-world side effect (isolated strictly to approval executor)


@dataclass(frozen=True)
class ToolSpec:
    """
    Immutable specification of an agent tool.

    Attributes:
      name: Unique identifier for the tool.
      capability: Security capability classification.
      description: Human/LLM-readable summary of functionality.
      func: Callable execution function.
      schema: Pydantic model defining argument validation schema.
      timeout_s: Maximum execution duration before timing out.
      cacheable: Whether outputs can be cached.
      egress_allowlist: Allowed network domains (empty means no external network egress or unrestricted if tool is local).
    """
    name: str
    capability: Capability
    description: str
    func: Callable[..., Any]
    schema: type[BaseModel]
    timeout_s: float = 30.0
    cacheable: bool = False
    egress_allowlist: tuple[str, ...] = ()
