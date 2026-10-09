"""
orchestrator_core/tools/read/email_read.py

Email read-only IMAP inspection tool (Capability.READ).
Reads inbox headers and unread mail summaries.
Writing or sending email is strictly forbidden here — all outbound communications
MUST be staged through propose_action for human authorization.
"""

from __future__ import annotations

import email
from email.header import decode_header
import imaplib
import logging
import os
from typing import Optional
from pydantic import BaseModel, Field

from orchestrator_core.runner.sanitize import sanitize_observation

logger = logging.getLogger(__name__)


class EmailReadArgs(BaseModel):
    """Arguments for email_read tool."""
    action: str = Field(
        default="check_inbox",
        description="Action to perform: 'check_inbox' or 'summarize_unread'."
    )
    max_messages: int = Field(
        default=5, ge=1, le=20, description="Max messages to inspect."
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


def email_read(action: str = "check_inbox", max_messages: int = 5) -> str:
    """
    Check unread correspondence via IMAP read-only connection.
    """
    email_addr = os.getenv("EMAIL_ADDRESS")
    email_pass = os.getenv("EMAIL_APP_PASSWORD")

    if not email_addr or not email_pass or "your_email" in email_addr:
        demo_summary = (
            "Inbox Status (Demo Mode — No credentials configured in .env):\n"
            "1. [Google Cloud] Alert: Monthly resource quota review scheduled\n"
            "2. [GitHub] Star notification: FarhanAaqil/orchestrater_agent\n"
            "3. [ArXiv] Research alert: 3 papers matched 'multi-agent consensus'"
        )
        return sanitize_observation(demo_summary, source="email_imap")

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_addr, email_pass)
        mail.select("inbox", readonly=True)

        status, messages = mail.search(None, "UNSEEN")
        if status != "OK":
            return sanitize_observation("Failed to search inbox.", source="email_imap")

        email_ids = messages[0].split()
        if not email_ids:
            return sanitize_observation("Inbox has 0 unread messages.", source="email_imap")

        recent_ids = email_ids[-max_messages:]
        summaries = [f"Found {len(email_ids)} unread messages. Recent {len(recent_ids)}:"]

        for eid in reversed(recent_ids):
            res, msg_data = mail.fetch(eid, "(RFC822.HEADER)")
            if res != "OK":
                continue
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject = _decode_mime_words(msg.get("Subject", "(No Subject)"))
                    sender = _decode_mime_words(msg.get("From", "(Unknown Sender)"))
                    date = msg.get("Date", "")
                    summaries.append(f"- From: {sender} | Subject: {subject} | Date: {date}")

        mail.logout()
        return sanitize_observation("\n".join(summaries), source="email_imap")

    except Exception as exc:
        logger.warning("[email_read] IMAP error: %s", exc)
        return sanitize_observation(f"Unable to access inbox via IMAP: {exc}", source="email_imap")
