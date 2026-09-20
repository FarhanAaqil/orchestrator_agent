"""
orchestrator_core/agents/email_agent.py

Email Agent — Precision email writer, inbox reader, and outreach assistant.

READ / WRITE SPLIT CONTRACT:
  - Free (un-gated): check inbox, summarize unread emails, draft recruiter/application/follow-up/general emails.
  - Gated (approval required): sending emails. Returns action_type="send_email" with payload in metadata.
  - SDK isolation: NEVER imports smtplib. Execution is isolated strictly to approval_gate.py.
"""

from __future__ import annotations

import email
from email.header import decode_header
import imaplib
import logging
import os
import re
from typing import Any, Optional

from groq import Groq

from orchestrator_core.config import get_settings
from orchestrator_core.models import AgentResult

logger = logging.getLogger(__name__)

AAQIL_SIGNATURE = """--
Farhan Aaqil
B.Tech AI/ML | JPNCE Mahbubnagar
GitHub: github.com/FarhanAaqil
LinkedIn: linkedin.com/in/farhan-aaqil-4730432bb
Phone: +91-6300825009"""

_SYSTEM_PROMPT = f"""You are Aaqil's Email Agent — precision email communicator.
You help check inbox activity, summarize correspondence, and draft professional emails
for recruiter outreach, job applications, follow-ups, paper submissions, and general queries.

Tone: Professional, genuine, clear, and concise. Never generic.
Aaqil's Signature:
{AAQIL_SIGNATURE}
"""


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
            temperature=0.7,
            max_tokens=2000,
        )
        return response.choices[0].message.content
    except Exception as exc:
        logger.warning("[email_agent] Groq call failed (%s) — providing template fallback.", exc)
        return (
            f"Subject: Inquiring Regarding Opportunities\n\n"
            f"Dear Recipient,\n\n"
            f"I hope this message finds you well. I am reaching out regarding technical opportunities in AI/ML engineering.\n\n"
            f"Best regards,\n{AAQIL_SIGNATURE}"
        )


def _decode_mime_words(s: str) -> str:
    """Safely decode RFC 2047 MIME headers."""
    decoded_fragments = decode_header(s)
    result = []
    for fragment, encoding in decoded_fragments:
        if isinstance(fragment, bytes):
            result.append(fragment.decode(encoding or "utf-8", errors="replace"))
        else:
            result.append(str(fragment))
    return "".join(result)


def check_inbox(max_messages: int = 5) -> str:
    """
    Check unread messages in the user's Gmail inbox via IMAP.
    Free action: read-only, safe without approval gate.
    """
    email_addr = os.getenv("EMAIL_ADDRESS")
    email_pass = os.getenv("EMAIL_APP_PASSWORD")

    if not email_addr or not email_pass or "your_email" in email_addr:
        return (
            "📬 **Inbox Overview (Demo Mode)**\n\n"
            "- *No active Gmail credentials configured in .env (EMAIL_ADDRESS / EMAIL_APP_PASSWORD).*\n"
            "- Simulating recent inbox activity:\n"
            "  1. `[Google Cloud]` Alert: Monthly resource quota review scheduled\n"
            "  2. `[GitHub]` Repository notification: Star received on `orchestrater_agent`\n"
            "  3. `[ArXiv]` Daily digest: 3 new papers matched 'multi-agent consensus'"
        )

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(email_addr, email_pass)
        mail.select("inbox")

        status, response = mail.search(None, "UNSEEN")
        if status != "OK" or not response[0]:
            mail.logout()
            return "📬 **Inbox Clean**: No new unread messages in your inbox."

        msg_ids = response[0].split()[-max_messages:]
        summaries = []

        for mid in reversed(msg_ids):
            _, data = mail.fetch(mid, "(RFC822.HEADER)")
            for response_part in data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject = _decode_mime_words(msg.get("Subject", "No Subject"))
                    from_ = _decode_mime_words(msg.get("From", "Unknown Sender"))
                    date_ = msg.get("Date", "")[:16]
                    summaries.append(f"- **{from_}**: *{subject}* ({date_})")

        mail.logout()
        return f"📬 **Recent Unread Messages ({len(summaries)} found):**\n\n" + "\n".join(summaries)
    except Exception as exc:
        logger.warning("[email_agent] IMAP read failed: %s", exc)
        return f"⚠️ Could not check live inbox: {exc}. Verify EMAIL_ADDRESS and EMAIL_APP_PASSWORD in .env."


def handle(command: str, metadata: Optional[dict[str, Any]] = None) -> AgentResult:
    """
    Entry point for the Email Agent.
    Implements the Read/Write split:
      - Reads: inbox check, summarization, draft generation (free)
      - Writes: send requests return action_type="send_email" (gated)
    """
    logger.info("[email_agent] Processing command: %.80s", command)
    lower = command.lower().strip()
    meta = dict(metadata or {})

    # 1. Read: Inbox checking
    if any(k in lower for k in ("check inbox", "read emails", "show emails", "my emails", "unread", "inbox")):
        inbox_result = check_inbox()
        return AgentResult(
            agent="email_agent",
            output=inbox_result,
            action_type=None,
            metadata=meta,
        )

    # 2. Write: Sending email (Approval Gate Required)
    is_send_intent = any(k in lower for k in ("send email", "send an email", "shoot an email", "send mail"))

    # Extract recipient email if present in text
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", command)
    target_email = email_match.group(0) if email_match else meta.get("to_email", "recipient@example.com")

    # Generate draft content via LLM
    draft_prompt = f"""Based on this user command, produce a high-quality email draft:
User Request: {command}

Ensure the output includes:
1. A clear Subject line (prefixed with 'Subject: ')
2. The professional body
3. Aaqil's signature
"""
    draft_output = _call_llm(draft_prompt)

    # Parse subject line from generated output
    subject = "Message from Farhan Aaqil"
    for line in draft_output.split("\n"):
        if line.lower().startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
            break

    if is_send_intent:
        # GATED WRITE: wrap in approval action
        action_type = "send_email"
        payload = {
            "to_email": target_email,
            "subject": subject,
            "body": draft_output,
        }
        meta["approval_payload"] = payload
        meta["action_type"] = action_type

        output = (
            f"🔒 **Email Sending Requires Human Approval**\n\n"
            f"**To**: `{target_email}`\n"
            f"**Subject**: {subject}\n\n"
            f"### Generated Draft\n\n"
            f"{draft_output}\n\n"
            f"---\n"
            f"*Action queued for review in the Approval Gate with Zero Payload Substitution.*"
        )
        return AgentResult(
            agent="email_agent",
            output=output,
            action_type=action_type,
            metadata=meta,
        )

    # FREE READ: just drafting
    return AgentResult(
        agent="email_agent",
        output=f"📧 **Email Draft Ready**\n\n{draft_output}\n\n*To send this, say: 'Send email to {target_email} with this content' to queue approval.*",
        action_type=None,
        metadata=meta,
    )
