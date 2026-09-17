"""
tests/test_router.py

Unit tests for orchestrator_core/core/router.py.
All tests use mock LLM responses so no Groq API key or network access is required.
"""

from unittest.mock import patch
import pytest

from orchestrator_core.core.router import (
    classify,
    prompt_hash,
    _groq_breaker,
    SUPPORTED_AGENTS,
)
from orchestrator_core.models import RouterResult, ClarificationNeeded


@pytest.fixture(autouse=True)
def reset_router_circuit_breaker():
    """Ensure circuit breaker is in clean CLOSED state before and after each test."""
    _groq_breaker.reset()
    yield
    _groq_breaker.reset()


def test_classify_high_confidence_returns_router_result():
    """When the LLM returns a valid agent with confidence >= threshold, return RouterResult."""
    mock_response = {
        "agent": "career_agent",
        "confidence": 0.95,
        "reasoning": "Explicit request for resume tailoring and review.",
    }
    with patch("orchestrator_core.core.router._call_groq", return_value=mock_response):
        result = classify("Tailor my resume for a Senior Machine Learning Engineer position")
        assert isinstance(result, RouterResult)
        assert result.agent == "career_agent"
        assert result.confidence == 0.95
        assert "resume" in result.reasoning.lower()


def test_classify_low_confidence_returns_clarification_needed():
    """When confidence is below the threshold, return ClarificationNeeded."""
    mock_response = {
        "agent": "career_agent",
        "confidence": 0.45,
        "reasoning": "Could be career advice or content writing.",
    }
    with patch("orchestrator_core.core.router._call_groq", return_value=mock_response):
        result = classify("What should I do next with my project?")
        assert isinstance(result, ClarificationNeeded)
        assert len(result.candidates) >= 2
        assert "career_agent" in result.candidates
        assert "Confidence" in result.reasoning or "Could be" in result.reasoning


def test_classify_unknown_agent_returns_clarification_needed():
    """When LLM returns an unsupported agent name, return ClarificationNeeded."""
    mock_response = {
        "agent": "crypto_trader_agent",
        "confidence": 0.99,
        "reasoning": "Sounds like finance.",
    }
    with patch("orchestrator_core.core.router._call_groq", return_value=mock_response):
        result = classify("Buy 50 bitcoins")
        assert isinstance(result, ClarificationNeeded)
        assert set(result.candidates).issubset(set(SUPPORTED_AGENTS.keys()))


def test_prompt_hash_deterministic():
    """prompt_hash() should produce a deterministic 16-character hex hash."""
    h1 = prompt_hash("Tailor resume")
    h2 = prompt_hash("Tailor resume")
    h3 = prompt_hash("Write paper")

    assert len(h1) == 16
    assert h1 == h2
    assert h1 != h3
