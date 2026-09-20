"""
tests/test_unquarantined_agents.py

Comprehensive tests for un-quarantined and new agents:
- email_agent: free reads (inbox, draft) vs gated write (send_email)
- github_agent: free reads (repos, profile) vs gated write (github_create_issue)
- linkedin_agent: free reads (recruiter search, connection note) vs gated write (linkedin_post)
- general_chat_agent: conversational responses
"""

from unittest.mock import patch, MagicMock
import pytest

from orchestrator_core.agents import email_agent, github_agent, linkedin_agent, general_chat_agent


# ── email_agent tests ──────────────────────────────────────────────────────────

def test_email_agent_inbox_check_free_read():
    """Checking inbox should return an AgentResult with no action_type (free read)."""
    with patch("orchestrator_core.agents.email_agent.check_inbox", return_value="📬 Demo inbox"):
        result = email_agent.handle("check my inbox for unread messages")
        assert result.agent == "email_agent"
        assert result.action_type is None
        assert "Demo inbox" in result.output


def test_email_agent_draft_free_read():
    """Drafting an email without send intent should be a free read."""
    with patch("orchestrator_core.agents.email_agent._call_llm", return_value="Subject: Hello\n\nDraft content"):
        result = email_agent.handle("draft an email to recruiter about AI position")
        assert result.agent == "email_agent"
        assert result.action_type is None
        assert "Draft content" in result.output


def test_email_agent_send_email_gated_write():
    """Sending an email must return action_type='send_email' with approval payload."""
    with patch("orchestrator_core.agents.email_agent._call_llm", return_value="Subject: Interview\n\nReady to interview"):
        result = email_agent.handle("send email to recruiter@techcorp.com regarding interview")
        assert result.agent == "email_agent"
        assert result.action_type == "send_email"
        assert "recruiter@techcorp.com" in result.metadata["approval_payload"]["to_email"]
        assert "Interview" in result.metadata["approval_payload"]["subject"]
        assert "Requires Human Approval" in result.output


# ── github_agent tests ─────────────────────────────────────────────────────────

def test_github_agent_list_repos_free_read():
    """Listing repos should be an un-gated read action."""
    mock_repos = [
        {"name": "orchestrater_agent", "html_url": "https://github.com/test/repo", "description": "Core repo", "stargazers_count": 5}
    ]
    with patch("orchestrator_core.agents.github_agent._get_user_repos", return_value=mock_repos):
        result = github_agent.handle("list repos for my profile")
        assert result.agent == "github_agent"
        assert result.action_type is None
        assert "orchestrater_agent" in result.output


def test_github_agent_create_issue_gated_write():
    """Creating a GitHub issue must be gated behind approval."""
    with patch("orchestrator_core.agents.github_agent._call_llm", return_value="Title: Fix bug\n\nBug details"):
        result = github_agent.handle("create issue on repo about memory leak")
        assert result.agent == "github_agent"
        assert result.action_type == "github_create_issue"
        assert "Requires Approval" in result.output
        assert "approval_payload" in result.metadata


# ── linkedin_agent tests ───────────────────────────────────────────────────────

def test_linkedin_agent_recruiter_search_free_read():
    """Searching recruiters via web search should be a free read."""
    mock_search = [
        {"title": "Jane Doe - Technical Recruiter at Google", "url": "https://linkedin.com/in/janedoe", "snippet": "Hiring ML engineers"}
    ]
    with patch("orchestrator_core.agents.linkedin_agent.search_web", return_value=mock_search):
        result = linkedin_agent.handle("search recruiter for AI engineering at Google")
        assert result.agent == "linkedin_agent"
        assert result.action_type is None
        assert "Jane Doe" in result.output


def test_linkedin_agent_connection_note_free_read():
    """Generating a 300-char connection note should be a free read."""
    note = "Hi Jane, loved your post on distributed agent systems. Would love to connect!"
    with patch("orchestrator_core.agents.linkedin_agent._call_llm", return_value=note):
        result = linkedin_agent.handle("draft a connection note for VP of Engineering")
        assert result.agent == "linkedin_agent"
        assert result.action_type is None
        assert note in result.output
        assert "Connection Note" in result.output


def test_linkedin_agent_post_gated_write():
    """Publishing/sharing to LinkedIn must return action_type='linkedin_post'."""
    with patch("orchestrator_core.agents.linkedin_agent._call_llm", return_value="Excited to announce our multi-agent framework!"):
        result = linkedin_agent.handle("post on linkedin about our multi-agent framework")
        assert result.agent == "linkedin_agent"
        assert result.action_type == "linkedin_post"
        assert "Requires Approval" in result.output
        assert "approval_payload" in result.metadata


# ── general_chat_agent tests ──────────────────────────────────────────────────

def test_general_chat_agent():
    """General chat agent responds to conversational inputs as Toji."""
    with patch("orchestrator_core.agents.general_chat_agent._call_llm", return_value="Greetings. I am Toji."):
        result = general_chat_agent.handle("Hello Toji!")
        assert result.agent == "general_chat_agent"
        assert result.action_type is None
        assert "Toji" in result.output
