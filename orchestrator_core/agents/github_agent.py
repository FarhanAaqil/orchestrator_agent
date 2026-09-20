"""
orchestrator_core/agents/github_agent.py

GitHub Agent — Repository analyzer, README generator, and portfolio sync manager.

READ / WRITE SPLIT CONTRACT:
  - Free (un-gated): read repos, user profile, commits, issues, PR descriptions, commit messages, repo analysis.
  - Gated (approval required): creating issues, commenting, pushing code. Returns action_type for approval queue.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from groq import Groq
import requests

from orchestrator_core.config import get_settings
from orchestrator_core.models import AgentResult

logger = logging.getLogger(__name__)

GITHUB_USERNAME = "FarhanAaqil"

_SYSTEM_PROMPT = f"""You are Aaqil's GitHub Agent — his technical repository manager and documentation specialist.
User Profile: Farhan Aaqil ({GITHUB_USERNAME}) — Final-year AI/ML student at JPNCE Mahbubnagar.
Key Projects:
- orchestrator-agent: Production multi-agent orchestration service with approval gate.
- DiaPredict-AI: ML diabetes risk prediction (Published 2025).
- Self-Improving Code Agent: Vector-memory driven LLM refinement loop.
- SheetSense AI: Natural language spreadsheet analytics.
- IntelliGlove: Smart gesture recognition system.
- InterviewPro: AI interview preparation platform.

Always provide technically precise, well-formatted markdown output adhering to standard software engineering best practices."""


def _call_llm(prompt: str) -> str:
    """Make an LLM completion call via Groq with fallback."""
    settings = get_settings()
    try:
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.router_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
            max_tokens=2500,
        )
        return response.choices[0].message.content
    except Exception as exc:
        logger.warning("[github_agent] Groq call failed (%s) — providing fallback response.", exc)
        return (
            "### GitHub Recommendations & Documentation\n\n"
            "- **Target Repository**: `orchestrater_agent`\n"
            "- **Status**: Active (FastAPI core with audited human-in-the-loop gates)\n"
            "- **Key Action**: Document new multi-chat conversation memory and widened agent roster."
        )


def _api_get(endpoint: str) -> Any:
    """Call GitHub REST API with authorization headers if present."""
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.get(
            f"https://api.github.com{endpoint}",
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning("[github_agent] GitHub API %s returned status %d", endpoint, resp.status_code)
        return None
    except Exception as exc:
        logger.warning("[github_agent] GitHub API request error: %s", exc)
        return None


def _get_user_repos() -> list[dict]:
    """Fetch user repositories."""
    data = _api_get(f"/users/{GITHUB_USERNAME}/repos?per_page=10&sort=updated")
    if isinstance(data, list):
        return data
    return []


def handle(command: str, metadata: Optional[dict[str, Any]] = None) -> AgentResult:
    """
    Entry point for the GitHub Agent.
    Implements the Read/Write split:
      - Reads: listing repos, summaries, commit messages, READMEs, PR reviews (free)
      - Writes: creating issues, commenting, pushing (gated behind approval)
    """
    logger.info("[github_agent] Processing command: %.80s", command)
    lower = command.lower().strip()
    meta = dict(metadata or {})

    # 1. Gated Write Check: creating issues or commenting
    if any(k in lower for k in ("create issue", "open issue", "file issue", "new issue")):
        action_type = "github_create_issue"
        # Generate issue title and body via LLM
        issue_prompt = f"Extract or draft a GitHub issue title and body from this command: {command}. Format as:\nTitle: <title>\n\n<body>"
        issue_text = _call_llm(issue_prompt)
        payload = {"command": command, "draft": issue_text}
        meta["approval_payload"] = payload
        meta["action_type"] = action_type
        return AgentResult(
            agent="github_agent",
            output=(
                f"🔒 **GitHub Issue Creation Requires Approval**\n\n"
                f"{issue_text}\n\n"
                f"---\n*Action queued for review in the Approval Gate.*"
            ),
            action_type=action_type,
            metadata=meta,
        )

    if any(k in lower for k in ("post comment", "add comment", "comment on issue", "comment on pr")):
        action_type = "github_comment"
        comment_text = _call_llm(f"Draft a technical PR/Issue comment for: {command}")
        payload = {"command": command, "comment": comment_text}
        meta["approval_payload"] = payload
        meta["action_type"] = action_type
        return AgentResult(
            agent="github_agent",
            output=(
                f"🔒 **GitHub Comment Requires Approval**\n\n"
                f"{comment_text}\n\n"
                f"---\n*Action queued for review in the Approval Gate.*"
            ),
            action_type=action_type,
            metadata=meta,
        )

    # 2. Free Reads: Live repository list / profile inspection
    if any(k in lower for k in ("list repos", "show repos", "my repos", "github profile", "github stats")):
        repos = _get_user_repos()
        if repos:
            lines = [f"### 🐙 GitHub Repositories for [{GITHUB_USERNAME}](https://github.com/{GITHUB_USERNAME})\n"]
            for r in repos[:8]:
                star_str = f"⭐ {r.get('stargazers_count', 0)}" if r.get("stargazers_count") else ""
                desc = r.get("description") or "No description provided."
                lines.append(f"- **[{r.get('name')}]({r.get('html_url')})** {star_str}\n  {desc}")
            return AgentResult(
                agent="github_agent",
                output="\n".join(lines),
                action_type=None,
                metadata=meta,
            )

    # 3. Free Reads: Commit message generation, README authoring, PR description, code critique
    llm_output = _call_llm(command)
    return AgentResult(
        agent="github_agent",
        output=llm_output,
        action_type=None,
        metadata=meta,
    )
