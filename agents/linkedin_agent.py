"""
NOT SUPPORTED in orchestrator_core v2.

LinkedIn-related features are experimental. This agent:
  - Is not imported by orchestrator_core/
  - Is not covered by any test in the CI suite
  - Is not deployed in the production Docker image
  - Will be moved to experimental/linkedin_agent/ in Phase 4
  - Kept as a reference implementation only

LinkedIn Agent — No Playwright, no login required.
Uses DuckDuckGo to search LinkedIn profiles and jobs.
Generates all outreach content via LLM.
"""

from agents.base_agent import BaseAgent
import os

AAQIL_BIO = """
Farhan Aaqil | B.Tech AI/ML (Final Year) | JPNCE Mahbubnagar
Skills: Python, LangChain, LLM Agents, ML, ChromaDB, FastAPI, Streamlit
Experience: Python Full Stack + AIML Intern (Jala Academy)
Research: ML-based Diabetes Prediction (2025, published)
Projects: 9-Agent AI Orchestrator, SheetSense AI, IntelliGlove, InterviewPro
GitHub: github.com/FarhanAaqil | LinkedIn: linkedin.com/in/farhan-aaqil-4730432bb
Target: Remote paid internships in Python/AI/ML/LLM Agents
"""


class LinkedInAgent(BaseAgent):

    TOOLS = [
        {
            "name": "draft_connection_request",
            "description": "Draft a LinkedIn connection request message. Use when user says 'connect with [name]' or 'connection request for [name]'.",
            "args": {"name": "str", "role": "str (their job title)", "company": "str"}
        },
        {
            "name": "draft_outreach",
            "description": "Draft a LinkedIn cold outreach or DM to a recruiter/hiring manager. Use when user says 'message recruiter' or 'outreach to [name]'.",
            "args": {"name": "str", "role": "str", "company": "str", "job_title": "str (optional)"}
        },
        {
            "name": "draft_follow_up",
            "description": "Draft a follow-up message to someone you already messaged. Use when user says 'follow up with [name]'.",
            "args": {"name": "str", "company": "str", "context": "str", "days_ago": "int (default 7)"}
        },
        {
            "name": "analyze_job",
            "description": "Analyze a job description for fit with Aaqil's profile. Use when user pastes a JD or says 'analyze this job'.",
            "args": {"job_description": "str"}
        },
        {
            "name": "search_recruiters",
            "description": "Search for recruiters at a specific company on LinkedIn via DuckDuckGo. Use when user says 'find recruiter at [company]'.",
            "args": {"company": "str", "role_type": "str (e.g. 'Technical Recruiter')"}
        },
        {
            "name": "optimize_headline",
            "description": "Generate an optimized LinkedIn headline for Aaqil's profile. Use when user says 'optimize my headline' or 'improve my linkedin'.",
            "args": {"target_role": "str (optional)"}
        },
        {
            "name": "write_about_section",
            "description": "Write an optimized LinkedIn About section for Aaqil. Use when user says 'write about section' or 'improve my profile'.",
            "args": {"focus": "str (optional, e.g. 'AI agents', 'ML research')"}
        }
    ]

    def __init__(self):
        super().__init__(
            name="linkedin",
            system_prompt=f"""You are Aaqil's LinkedIn strategist — like a personal career coach.
You help craft professional outreach, optimize profile, and strategize job applications.

Aaqil's profile:
{AAQIL_BIO}

Be direct, sharp, and authentic. No corporate fluff. Messages should sound like a real person, not a template."""
        )

    def draft_connection_request(self, name: str, role: str = "professional",
                                  company: str = "your company") -> str:
        task = f"""Write a LinkedIn connection request for Aaqil to send to:
Name: {name}
Their Role: {role} at {company}

Rules:
- STRICT 300 character limit (LinkedIn's max)
- Reference something specific about their company or role
- Show genuine interest in their work or AI/ML field
- Don't mention job seeking in the first message
- End with a question or reason they'd want to connect
- Sound like a smart, curious student, not a template

Just write the message, nothing else."""
        result = self.run(task, temperature=0.8)
        if len(result) > 300:
            result = result[:297] + "..."
        return f"💬 **Connection Request for {name}:**\n\n_{result}_\n\n📏 Length: {len(result)}/300"

    def draft_outreach(self, name: str, role: str = "Recruiter",
                       company: str = "your company", job_title: str = "") -> str:
        target = job_title or "AI/ML Intern or Python Developer Intern"
        
        # Auto-detect role type to adjust tone
        role_lower = role.lower()
        if any(r in role_lower for r in ["recruiter", "talent", "hr", "sourcer"]):
            persona_focus = "Focus on culture fit, fast learning, and matching their required keywords."
        else:
            persona_focus = "Focus on technical depth, architecture, and solving hard engineering problems."

        task = f"""Write a LinkedIn InMail/DM to a {role}:

To: {name}, {role} at {company}
Target Role: {target}

From: Farhan Aaqil — Final-year AI/ML student

{persona_focus}

Structure (3 short paragraphs):
1. Opening: ONE specific thing about {company} that genuinely interests Aaqil
2. Value: Most relevant proof point (LLM agent system with 9 agents, published ML research, or Jala Academy internship)
3. Ask: Simple, low-friction CTA (quick call? share resume? referral?)

Tone: Confident, direct, no fluff. Max 150 words total."""
        result = self.run(task, temperature=0.8)
        return f"📨 **Outreach to {name} at {company}:**\n\n{result}"

    def draft_follow_up(self, name: str = "them", company: str = "the company",
                         context: str = "my application", days_ago: int = 7) -> str:
        task = f"""Write a brief LinkedIn follow-up:

Context: Aaqil messaged {name} at {company} about {context}, {days_ago} days ago, no reply.

Rules:
- Max 80 words
- Reference the original context
- Add ONE new value-add (mention a recent achievement like completing a new agent feature)
- Don't be needy or desperate
- End with a clear question"""
        result = self.run(task, temperature=0.7)
        return f"🔄 **Follow-up to {name}:**\n\n{result}"

    def analyze_job(self, job_description: str) -> str:
        task = f"""Analyze this job description specifically for Farhan Aaqil:

JD:
{job_description}

Aaqil's profile: {AAQIL_BIO}

Your analysis (be brutally honest):
1. **Match Score** (X/10) with clear reasoning
2. **✅ Skills Aaqil Has** (from the required skills)
3. **❌ Skills Aaqil Lacks** (be specific)
4. **Verdict** — Should he apply? Strong/Maybe/Skip, with one sentence of reasoning
5. **Customization Tips** — What to emphasize in resume/cover letter for THIS specific job"""
        return self.run(task)

    def search_recruiters(self, company: str, role_type: str = "Technical Recruiter") -> str:
        from utils.web_search import search_web
        query = f'site:linkedin.com/in "{role_type}" "{company}" recruiting'
        results = search_web(query, max_results=8)

        if not results or (len(results) > 0 and "error" in results[0]):
            return f"❌ Could not find recruiters at {company}. Try searching manually on LinkedIn."

        output = f"👥 **Recruiters at {company}:**\n\n"
        for i, r in enumerate(results[:5], 1):
            title = r.get("title", "").replace(" | LinkedIn", "").strip()
            url = r.get("url", "")
            snippet = r.get("snippet", "")
            if "linkedin.com/in/" not in url:
                continue
            output += f"{i}. **{title}**\n"
            output += f"   _{snippet[:100]}_\n"
            output += f"   🔗 {url}\n\n"

        output += "\n💡 Say **'draft outreach to [name] at [company]'** to message them."
        return output

    def optimize_headline(self, target_role: str = "AI/ML Intern") -> str:
        task = f"""Write 5 optimized LinkedIn headline options for Aaqil targeting '{target_role}':

Profile: {AAQIL_BIO}

Rules per headline:
- Max 220 characters
- Include strong keywords (LLM, AI Agent, Python, Machine Learning)
- Show unique value (published research, live agent system)
- Avoid generic phrases like "Aspiring" or "Passionate"

Format as:
1. [Headline] — Why it works
2. [Headline] — Why it works
(etc)

Star your top recommendation."""
        return f"✨ **LinkedIn Headline Options:**\n\n{self.run(task)}"

    def write_about_section(self, focus: str = "AI/ML agents and research") -> str:
        task = f"""Write Aaqil's LinkedIn About section focused on '{focus}':

Profile: {AAQIL_BIO}

Structure (800-1200 chars total):
1. Opening hook — surprising or impressive stat/fact about his work
2. What he builds — specific projects with concrete outcomes
3. Research background — published paper mention
4. What he's looking for — remote internships, be direct
5. CTA — GitHub/email links

Tone: First person, conversational, confident. Not a resume. Not corporate."""
        return f"📝 **LinkedIn About Section:**\n\n{self.run(task)}"

    def handle(self, task: str) -> str:
        return self.think_and_act(task)