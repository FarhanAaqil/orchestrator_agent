"""
orchestrator_core/tools/read/fetch_page.py

Safe webpage text extraction tool (Capability.READ).
Uses the SSRF-guarded shared HTTP client, extracts human-readable text from HTML,
and wraps all extracted content inside <untrusted_data> isolation boundary tags.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from pydantic import BaseModel, Field

from orchestrator_core.runner.sanitize import sanitize_observation
from orchestrator_core.tools.read.shared_client import safe_get

logger = logging.getLogger(__name__)


class FetchPageArgs(BaseModel):
    """Arguments for fetch_page tool."""
    url: str = Field(description="The full HTTP/HTTPS URL of the web page to read.")


def _extract_readable_text(html: str) -> str:
    """Extract clean readable text from HTML by stripping boilerplate and script tags."""
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")

        # Remove non-content elements
        for element in soup(["script", "style", "noscript", "header", "footer", "nav", "svg", "form"]):
            element.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else "Untitled"

        # Get body or full document text
        body = soup.body or soup
        text = body.get_text(separator="\n", strip=True)

        # Clean consecutive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return f"Title: {title}\n\n{text}".strip()

    # Fallback when BeautifulSoup is not installed
    clean = re.sub(r"<(script|style|noscript|header|footer|nav|svg|form)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else "Untitled"
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return f"Title: {title}\n\n{clean}".strip()


def fetch_page(url: str, max_chars: int = 8000) -> str:
    """
    Fetch a web page using SSRF-hardened GET client, extract text, and wrap in XML boundaries.
    """
    try:
        response = safe_get(url)
        content_type = response.headers.get("Content-Type", "").lower()

        if "text/html" in content_type or not content_type:
            raw_text = _extract_readable_text(response.text)
        else:
            raw_text = response.text

        hostname = urlparse(url).hostname or "web_page"
        return sanitize_observation(raw_text, source=hostname, max_chars=max_chars)
    except Exception as exc:
        logger.warning("fetch_page failed for %s: %s", url, exc)
        return sanitize_observation(f"Error fetching page {url}: {exc}", source="fetch_page")
