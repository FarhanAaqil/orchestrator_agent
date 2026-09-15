"""
orchestrator_core/core/circuit_breaker.py

Simple counting circuit breaker for external LLM/API calls.
Tracks consecutive failures and moves to OPEN state to fail-fast when the
external service is clearly degraded. No external dependencies.

States:
    CLOSED  → normal operation, calls pass through.
    OPEN    → too many failures; raises CircuitOpenError immediately.
    HALF_OPEN → one trial call allowed after the cooldown period.
"""

import time
import threading
from typing import Any, Callable, TypeVar

from orchestrator_core.exceptions import CircuitOpenError

F = TypeVar("F")


class CircuitBreaker:
    """
    Thread-safe counting circuit breaker.

    Args:
        service:        Name of the guarded service (used in error messages).
        failure_threshold:  Number of consecutive failures before OPEN.
        cooldown_seconds:   Seconds to wait before trying HALF_OPEN.
        reset_on_success:   Number of successful half-open calls before CLOSED.
    """

    def __init__(
        self,
        service: str,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        reset_on_success: int = 1,
    ):
        self.service = service
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.reset_on_success = reset_on_success

        self._consecutive_failures = 0
        self._state = "CLOSED"       # "CLOSED" | "OPEN" | "HALF_OPEN"
        self._opened_at: float = 0.0
        self._half_open_successes = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        return self._state

    def _check_transition(self) -> None:
        """Check whether OPEN should transition to HALF_OPEN based on cooldown."""
        if self._state == "OPEN":
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.cooldown_seconds:
                self._state = "HALF_OPEN"
                self._half_open_successes = 0

    def call(self, func: Callable[..., F], *args: Any, **kwargs: Any) -> F:
        """
        Execute func through the circuit breaker.
        Raises CircuitOpenError if the breaker is OPEN.
        """
        with self._lock:
            self._check_transition()

            if self._state == "OPEN":
                remaining = self.cooldown_seconds - (time.monotonic() - self._opened_at)
                raise CircuitOpenError(self.service, max(0.0, remaining))

        try:
            result = func(*args, **kwargs)
        except Exception:
            self._on_failure()
            raise

        self._on_success()
        return result

    def _on_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.failure_threshold:
                self._state = "OPEN"
                self._opened_at = time.monotonic()

    def _on_success(self) -> None:
        with self._lock:
            if self._state == "HALF_OPEN":
                self._half_open_successes += 1
                if self._half_open_successes >= self.reset_on_success:
                    self._state = "CLOSED"
                    self._consecutive_failures = 0
            elif self._state == "CLOSED":
                self._consecutive_failures = 0

    def reset(self) -> None:
        """Manually reset the breaker to CLOSED state (useful in tests)."""
        with self._lock:
            self._state = "CLOSED"
            self._consecutive_failures = 0
            self._opened_at = 0.0
            self._half_open_successes = 0
