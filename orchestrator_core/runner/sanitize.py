"""
orchestrator_core/runner/sanitize.py

Untrusted data sanitization for agent observations (Section 5.5 & SEC-08).
All external inputs (web scraping, API outputs, command outputs, file content)
are wrapped in explicit XML boundary tags, sanitized of dangerous terminal escape
sequences and control characters, escaped against tag breakout injections,
and capped to safe length thresholds.
"""

from __future__ import annotations

import re

# ANSI escape sequence regex (colors, cursor movements, terminal controls)
_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

# Dangerous non-printable ASCII control characters (preserving \t, \n, \r)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def strip_control_chars(text: str) -> str:
    """Strip ANSI escape sequences and non-printable control characters."""
    if not text:
        return ""
    # Strip terminal escape codes
    text = _ANSI_ESCAPE_RE.sub("", text)
    # Strip non-whitespace control characters
    text = _CONTROL_CHAR_RE.sub("", text)
    return text


def sanitize_observation(
    raw_content: str,
    source: str = "tool",
    max_chars: int = 8000,
) -> str:
    """
    Sanitize and wrap an observation from an untrusted tool or environment.

    Guarantees:
      1. Dangerous terminal sequences & control characters are stripped.
      2. Tag breakout sequences like </untrusted_data> are escaped.
      3. Content exceeding max_chars is safely truncated with a disclosure notice.
      4. Wrapped in boundary tags: <untrusted_data source="...">...</untrusted_data>
    """
    if raw_content is None:
        raw_content = ""
    elif not isinstance(raw_content, str):
        raw_content = str(raw_content)

    cleaned = strip_control_chars(raw_content)

    # Neutralize closing boundary tags to prevent prompt injection breakouts
    cleaned = cleaned.replace("</untrusted_data>", "&lt;/untrusted_data&gt;")
    cleaned = cleaned.replace("<untrusted_data", "&lt;untrusted_data")

    # Safe truncation
    if len(cleaned) > max_chars:
        truncated_count = len(cleaned) - max_chars
        cleaned = f"{cleaned[:max_chars]}\n... [truncated {truncated_count} characters]"

    safe_source = strip_control_chars(source).replace('"', "&quot;").strip() or "tool"
    return f'<untrusted_data source="{safe_source}">\n{cleaned}\n</untrusted_data>'
