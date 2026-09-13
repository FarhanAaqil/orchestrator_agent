"""
Email Agent — Drafts and sends professional emails via Gmail.
Fully LLM-dispatched via think_and_act().
"""

from agents.base_agent import BaseAgent
from database.tracker import add_email, mark_email_sent, get_emails
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

AAQIL_SIGNATURE = """
--
Farhan Aaqil
B.Tech AI/ML | JPNCE Mahbubnagar
GitHub: github.com/FarhanAaqil
LinkedIn: linkedin.com/in/farhan-aaqil-4730432bb
Phone: +91-6300825009
"""


class EmailAgent(BaseAgent):

    TOOLS = [
        {
            "name": "draft_recruiter_email",
            "description": "Draft a cold outreach email to a recruiter. Use for 'email recruiter', 'outreach email to [name]', 'cold email to [company]'.",
            "args": {"name": "str", "company": "str", "role": "str", "email": "str (optional)"}
        },
        {
            "name": "draft_application_email",
            "description": "Draft a job application email. Use for 'application email for [role] at [company]', 'apply email'.",
            "args": {"company": "str", "role": "str", "jd_summary": "str (optional)", "email": "str (optional)"}
        },
        {
            "name": "draft_follow_up",
            "description": "Draft a follow-up email. Use for 'follow up with [name]', 'follow up email to [company]'.",
            "args": {"name": "str", "company": "str", "context": "str", "days_ago": "int (default 7)"}
        },
        {
            "name": "draft_publisher_email",
            "description": "Draft a research paper submission email to a journal. Use for 'submit paper', 'journal email', 'publisher email'.",
            "args": {"paper_title": "str", "journal": "str", "editor_email": "str (optional)"}
        },
        {
            "name": "email_dashboard",
            "description": "Show all drafted emails and stats. Use for 'show emails', 'email dashboard', 'my emails'.",
            "args": {}
        },
        # NOTE: send_email removed from TOOLS — direct send without approval gate
        # is a live safety hole. Email sending is gated behind the approval queue
        # in orchestrator_core/core/approval_gate.py.
        # The send_email() method remains below for reference but must NOT be
        # an LLM-selectable tool in any supported agent path.
        {
            "name": "draft_general_email",
            "description": "Draft a general, non-specific email. Use for 'send an email to [email] saying [context]', 'greetings email', etc.",
            "args": {"context": "str", "to_name": "str (optional)", "to_email": "str (optional)"}
        }
    ]

    def __init__(self):
        super().__init__(
            name="email",
            system_prompt=f"""You are Aaqil's Email Agent — precision email writer.
You draft and send professional emails for job applications, recruiter outreach,
research paper submissions, and follow-ups.
Always be professional, concise, and genuine. Never generic.
Aaqil's signature: {AAQIL_SIGNATURE}"""
        )
        self.from_email = os.getenv("EMAIL_ADDRESS")
        self.password = os.getenv("EMAIL_APP_PASSWORD")

    def _send_email(self, to_email: str, subject: str, body: str) -> dict:
        if not self.from_email or not self.password:
            return {"success": False, "error": "Gmail credentials missing in .env (EMAIL_ADDRESS + EMAIL_APP_PASSWORD)"}
        try:
            msg = MIMEMultipart()
            msg["From"] = self.from_email
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(self.from_email, self.password)
                server.send_message(msg)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def draft_recruiter_email(self, name: str, company: str,
                               role: str = "AI/ML Intern", email: str = "") -> str:
        task = f"""Draft a cold outreach email from Farhan Aaqil to a recruiter:
Recruiter: {name} at {company}
Target Role: {role}

Write a compelling email (150-200 words):
- Subject line first (on its own line, prefix with "Subject: ")
- Personal hook: reference something specific about {company}'s AI/ML work
- 2 sentences on Aaqil's strongest relevant experience (LLM agent system, published ML paper)
- Specific, low-friction ask (30-min call? resume review?)
{AAQIL_SIGNATURE}"""
        result = self.run(task)
        subject = f"AI/ML Internship Opportunity — Farhan Aaqil"
        for line in result.split('\n'):
            if line.lower().startswith("subject:"):
                subject = line.replace("Subject:", "").replace("subject:", "").strip()
                break
        email_id = add_email(email, name, subject, result, "recruiter_outreach")
        return f"📧 **Recruiter Email Drafted** (ID: {email_id})\n\n{result}"

    def draft_application_email(self, company: str, role: str,
                                  jd_summary: str = "", email: str = "") -> str:
        task = f"""Draft a job application email from Farhan Aaqil:
Company: {company}
Role: {role}
JD: {jd_summary if jd_summary else 'AI/ML internship'}

Include:
- Strong subject line (prefix with "Subject: ")
- Opening that references {company} specifically
- 3 bullet points: most relevant project/skill for this role
- Link to GitHub and LinkedIn
{AAQIL_SIGNATURE}"""
        result = self.run(task)
        subject = f"Application for {role} — Farhan Aaqil"
        for line in result.split('\n'):
            if line.lower().startswith("subject:"):
                subject = line.replace("Subject:", "").replace("subject:", "").strip()
                break
        email_id = add_email(email, company, subject, result, "job_application")
        return f"📧 **Application Email Drafted** (ID: {email_id})\n\n{result}"

    def draft_follow_up(self, name: str, company: str = "the company",
                         context: str = "my application", days_ago: int = 7) -> str:
        task = f"""Draft a follow-up email from Farhan Aaqil:
To: {name} at {company}
Context: {context}
Sent {days_ago} days ago, no reply.

Write a short, polite follow-up (80-100 words):
- Reference the original context
- Add ONE new value-add (recent project milestone)
- Clear ask
{AAQIL_SIGNATURE}"""
        result = self.run(task)
        subject = f"Following up — {context[:40]}"
        email_id = add_email("", name, subject, result, "follow_up")
        return f"📧 **Follow-up Drafted** (ID: {email_id})\n\n{result}"

    def draft_publisher_email(self, paper_title: str, journal: str,
                               editor_email: str = "") -> str:
        task = f"""Draft a manuscript submission email from Farhan Aaqil:
Paper: {paper_title}
Journal: {journal}

Academic submission email:
- Subject: Manuscript Submission — {paper_title}
- State paper title and contribution
- Why it fits {journal}
- Originality declaration
{AAQIL_SIGNATURE}"""
        result = self.run(task)
        subject = f"Manuscript Submission — {paper_title}"
        email_id = add_email(editor_email, f"Editor, {journal}", subject, result, "paper_submission")
        return f"📧 **Submission Email Drafted** (ID: {email_id})\n\n{result}"

    def draft_general_email(self, context: str, to_name: str = "", to_email: str = "") -> str:
        task = f"""Draft a general email from Farhan Aaqil:
To: {to_name if to_name else 'the recipient'} ({to_email})
Context: {context}

Write a polite and appropriate email:
- Subject line first (on its own line, prefix with "Subject: ")
- Body of the email based on the context
{AAQIL_SIGNATURE}"""
        result = self.run(task)
        subject = f"Message from Farhan Aaqil"
        for line in result.split('\n'):
            if line.lower().startswith("subject:"):
                subject = line.replace("Subject:", "").replace("subject:", "").strip()
                break
        email_id = add_email(to_email, to_name, subject, result, "general")
        return f"📧 **General Email Drafted** (ID: {email_id})\n\n{result}\n\n*To send this, type: 'send email {email_id} to {to_email}'*"

    def send_email(self, email_id: int, to_email: str) -> str:
        emails = get_emails()
        email = next((e for e in emails if e["id"] == email_id), None)
        if not email:
            return f"❌ Email ID {email_id} not found. Use 'show emails' to see IDs."
        result = self._send_email(to_email, email["subject"], email["body"])
        if result["success"]:
            mark_email_sent(email_id)
            return f"✅ Email sent to {to_email}"
        return f"❌ Failed to send: {result['error']}"

    def email_dashboard(self) -> str:
        emails = get_emails()
        by_cat = {}
        for e in emails:
            by_cat.setdefault(e["category"], []).append(e)
        result = f"📬 **Email Dashboard ({len(emails)} total):**\n\n"
        cat_emoji = {
            "recruiter_outreach": "🤝", "job_application": "💼",
            "follow_up": "🔄", "paper_submission": "📚", "general": "📧"
        }
        for cat, cat_emails in by_cat.items():
            sent = len([e for e in cat_emails if e["status"] == "sent"])
            emoji = cat_emoji.get(cat, "📧")
            result += f"{emoji} {cat.replace('_', ' ').title()}: {len(cat_emails)} | {sent} sent\n"
        result += "\n**Recent Emails:**\n"
        for e in emails[:5]:
            result += f"\n• [{e['id']}] [{e['status'].upper()}] {e['subject'][:50]}\n"
            result += f"  To: {e['to_name']} | {e['created_at'][:10]}\n"
        return result

    def handle(self, task: str) -> str:
        return self.think_and_act(task)