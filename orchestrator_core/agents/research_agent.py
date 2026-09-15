"""
orchestrator_core/agents/research_agent.py

Research agent v2 — clean port of v1 ResearchAgent.

Exposes handle(command) -> AgentResult.

Security fix: read_full_paper PDF fetch is guarded with:
  - HTTPS only
  - arxiv.org allowlist
  - 10 MB size limit
  - no redirects
  - 15 s timeout
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from groq import Groq

from orchestrator_core.config import get_settings
from orchestrator_core.exceptions import SSRFViolationError
from orchestrator_core.models import AgentResult

logger = logging.getLogger(__name__)

# ── SSRF guard configuration ───────────────────────────────────────────────────
_PDF_ALLOWED_HOSTS = {"arxiv.org", "ar5iv.labs.arxiv.org"}
_PDF_MAX_BYTES = 10 * 1024 * 1024   # 10 MB
_PDF_TIMEOUT_S = 15

_SYSTEM_PROMPT = """You are Aaqil's Research Agent.
You write professional research papers, find reputable journals, summarize ArXiv papers, and manage submissions.
Author: Farhan Aaqil — B.Tech AI/ML, JPNCE Mahbubnagar. Published researcher (ML-based Diabetes Prediction, 2025).
Always write in formal academic style. Follow IEEE/ACM standards.
Never suggest predatory journals. Only reputable, indexed publishers."""


def _ssrf_safe_pdf_fetch(pdf_url: str) -> str:
    """
    Fetch a PDF from an allowlisted host only.
    Raises SSRFViolationError on any policy violation.
    """
    parsed = urlparse(pdf_url)

    if parsed.scheme != "https":
        raise SSRFViolationError(f"Only HTTPS PDF URLs are allowed. Got scheme: {parsed.scheme!r}")

    # Normalise: strip 'www.' prefix for comparison
    host = parsed.netloc.lower().removeprefix("www.")
    if host not in _PDF_ALLOWED_HOSTS:
        raise SSRFViolationError(
            f"PDF host {parsed.netloc!r} is not on the allowlist. "
            f"Allowed: {sorted(_PDF_ALLOWED_HOSTS)}"
        )

    response = requests.get(
        pdf_url,
        timeout=_PDF_TIMEOUT_S,
        allow_redirects=False,
        stream=True,
    )
    response.raise_for_status()

    # Read up to the size limit
    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=65536):
        total += len(chunk)
        if total > _PDF_MAX_BYTES:
            raise SSRFViolationError(
                f"PDF at {pdf_url!r} exceeds the {_PDF_MAX_BYTES // (1024*1024)} MB size limit."
            )
        chunks.append(chunk)

    return b"".join(chunks).decode("utf-8", errors="replace")


def _call_llm(prompt: str) -> str:
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)
    response = client.chat.completions.create(
        model=settings.router_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=2048,
    )
    return response.choices[0].message.content


def handle(command: str, metadata: Optional[dict[str, Any]] = None) -> AgentResult:
    """
    Entry point for the research agent.

    Detects read_full_paper intent and applies the SSRF guard before fetching.
    All other commands go straight to the LLM.
    """
    logger.info("[research_agent] Processing command: %.80s", command)

    lower = command.lower()
    output: str

    # Detect PDF fetch intent and apply SSRF guard
    if any(kw in lower for kw in ("read paper", "summarize paper", "fetch paper", "arxiv.org")):
        # Extract URL from command (look for https://...)
        import re
        url_match = re.search(r"https?://\S+", command)
        if url_match:
            pdf_url = url_match.group(0).rstrip(".,;)")
            try:
                raw_text = _ssrf_safe_pdf_fetch(pdf_url)
                prompt = f"""Summarize this research paper and extract key findings:

{raw_text[:8000]}

Provide:
1. Core Methodology
2. Key Results (with numbers if available)
3. Main Contributions
4. Limitations"""
                output = _call_llm(prompt)
            except SSRFViolationError:
                raise
            except Exception as e:
                output = f"Failed to fetch the paper: {e}"
        else:
            output = _call_llm(command)
    else:
        output = _call_llm(command)

    return AgentResult(
        agent="research_agent",
        output=output,
        metadata=metadata or {},
    )
