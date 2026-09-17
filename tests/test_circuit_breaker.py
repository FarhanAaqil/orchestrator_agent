"""
tests/test_circuit_breaker.py

Unit tests for orchestrator_core/core/circuit_breaker.py.
Verifies failure threshold counting, OPEN state fail-fast, cooldown transitions,
and HALF_OPEN trial recovery.
"""

import time
import pytest

from orchestrator_core.core.circuit_breaker import CircuitBreaker
from orchestrator_core.exceptions import CircuitOpenError


def test_circuit_breaker_stays_closed_on_success():
    cb = CircuitBreaker(service="test_svc", failure_threshold=3, cooldown_seconds=1.0)

    res = cb.call(lambda: "ok")
    assert res == "ok"
    assert cb.state == "CLOSED"


def test_circuit_breaker_opens_after_threshold_failures():
    cb = CircuitBreaker(service="test_svc", failure_threshold=3, cooldown_seconds=2.0)

    def failing():
        raise RuntimeError("boom")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            cb.call(failing)

    assert cb.state == "OPEN"

    # 4th call must fail fast with CircuitOpenError without calling func
    with pytest.raises(CircuitOpenError) as exc_info:
        cb.call(lambda: "should not run")

    assert "test_svc" in str(exc_info.value)
    assert exc_info.value.cooldown_remaining_s > 0


def test_circuit_breaker_half_open_trial_and_recovery():
    # Set short cooldown for fast testing
    cb = CircuitBreaker(service="test_svc", failure_threshold=2, cooldown_seconds=0.1, reset_on_success=1)

    def failing():
        raise RuntimeError("service unavailable")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(failing)

    assert cb.state == "OPEN"

    # Wait for cooldown to expire
    time.sleep(0.15)

    # Next call executes trial in HALF_OPEN and succeeds -> closes circuit
    res = cb.call(lambda: "recovered")
    assert res == "recovered"
    assert cb.state == "CLOSED"


def test_circuit_breaker_half_open_failure_reopens():
    cb = CircuitBreaker(service="test_svc", failure_threshold=2, cooldown_seconds=0.1)

    def failing():
        raise RuntimeError("still down")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(failing)

    assert cb.state == "OPEN"
    time.sleep(0.15)

    # Trial call fails -> re-opens circuit
    with pytest.raises(RuntimeError):
        cb.call(failing)

    assert cb.state == "OPEN"
