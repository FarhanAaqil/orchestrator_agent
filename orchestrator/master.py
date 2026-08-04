import sys
import os
import re
import logging
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


from orchestrator.router import route_task
from orchestrator.pipeline import Pipeline
from memory.chroma_store import store_memory
from agents.github_agent import GitHubAgent
from agents.linkedin_agent import LinkedInAgent
from agents.job_agent import JobAgent
from agents.project_manager_agent import ProjectManagerAgent
from agents.career_agent import CareerAgent
from agents.growth_agent import GrowthAgent
from agents.research_agent import ResearchAgent
from agents.email_agent import EmailAgent
from agents.briefing_agent import BriefingAgent
from agents.critic_agent import CriticAgent
from agents.info_agent import InfoAgent
from scheduler.background import start_scheduler, scheduler
from orchestrator.health_monitor import health_monitor

logger = logging.getLogger(__name__)

# ─── Agent Lazy Init ──────────────────────────────────────────────
# Agents are constructed on first use to keep cold-start fast.

_agent_instances: dict = {}


def _get_agent(name: str):
    if name not in _agent_instances:
        factory = {
            "github":          GitHubAgent,
            "linkedin":        LinkedInAgent,
            "job":             JobAgent,
            "project_manager": ProjectManagerAgent,
            "career":          CareerAgent,
            "growth":          GrowthAgent,
            "research":        ResearchAgent,
            "email":           EmailAgent,
            "briefing":        BriefingAgent,
        }
        if name in factory:
            _agent_instances[name] = factory[name]()
    return _agent_instances.get(name)


def _build_agent_map() -> dict:
    """Return the live agent map, constructing any not yet initialised."""
    names = ["github", "linkedin", "job", "project_manager",
             "career", "growth", "research", "email", "briefing"]
    return {n: _get_agent(n) for n in names if _get_agent(n) is not None}


# Critic and Info are always needed
critic_agent = CriticAgent()
info_agent   = InfoAgent()

AGENT_MAP = _build_agent_map()

# Inject AGENT_MAP into BaseAgent for cross-agent consultation
from agents.base_agent import BaseAgent
BaseAgent.AGENT_MAP = AGENT_MAP

# Pipeline engine
pipeline = Pipeline(AGENT_MAP, critic_agent)

# Start background scheduler
if not scheduler.running:
    start_scheduler(AGENT_MAP, pipeline)

# ─── Short-term Memory (session-keyed) ────────────────────────────
# Keyed by session_id so concurrent sessions don't corrupt each other.
# { session_id: { agent_name: [messages] } }
_session_memory: dict = {}

def _get_agent_mem(session_id: str, agent_name: str) -> list:
    if session_id not in _session_memory:
        _session_memory[session_id] = {a: [] for a in AGENT_MAP}
    if agent_name not in _session_memory[session_id]:
        _session_memory[session_id][agent_name] = []
    return _session_memory[session_id][agent_name]

# Orchestrator-level context, also session-keyed
_orchestrator_context: dict = {}

def _get_orch_ctx(session_id: str) -> list:
    if session_id not in _orchestrator_context:
        _orchestrator_context[session_id] = []
    return _orchestrator_context[session_id]

# ─── Fast Pre-Router (module-level constant — never rebuilt per call) ─
FAST_ROUTES: dict = {
    # briefing
    "morning briefing": "briefing", "generate briefing": "briefing",
    "good morning": "briefing", "daily briefing": "briefing",
    # job
    "job dashboard": "job", "show jobs": "job", "all jobs": "job",
    "find internship": "job", "search internshala": "job",
    # career
    "show skills": "career", "my skills": "career",
    "show cert": "career", "career dashboard": "career",
    "career stats": "career",
    # project manager
    "show all tasks": "project_manager", "show tasks": "project_manager",
    "add task": "project_manager", "show all projects": "project_manager",
    "show goals": "project_manager",
    # github
    "show github": "github", "github profile": "github",
    "generate readme": "github", "commit message": "github",
    # growth
    "content dashboard": "growth", "my content": "growth",
    "content calendar": "growth", "linkedin post": "growth",
    "twitter thread": "growth", "blog post": "growth",
    # research
    "research dashboard": "research", "show papers": "research",
    "my papers": "research", "write paper": "research",
    # email
    "show emails": "email", "draft email": "email",
}

# ─── Helpers ──────────────────────────────────────────────────────

def summarize_and_store_context(agent_name: str, context: list, session_id: str = "default"):
    """Summarize long context and store in ChromaDB."""
    text_to_summarize = "\n".join([f"{m['role']}: {m['content']}" for m in context])
    summary_prompt = f"Summarize the key points of this conversation thread concisely:\n\n{text_to_summarize}"
    try:
        from config import get_model, GROQ_API_KEY
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        resp = client.chat.completions.create(
            model=get_model("fast"),
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.1
        )
        summary = resp.choices[0].message.content
        store_memory(agent_name, f"summary_{hash(summary)}", summary, {"type": "conversation_summary"})
    except Exception as e:
        logger.warning("Summarization failed for %s: %s", agent_name, e)


def _dispatch_to_agent(agent_name: str, task: str, user_input: str, session_id: str) -> dict:
    """Shared logic for routing to a known agent with memory management."""
    try:
        health_monitor.set_status(agent_name, "processing")

        mem = _get_agent_mem(session_id, agent_name)
        mem.append({"role": "user", "content": task})

        AGENT_MAP[agent_name].current_context = mem
        response = AGENT_MAP[agent_name].handle(task)

        mem.append({"role": "assistant", "content": response})
        if len(mem) > 10:
            summarize_and_store_context(agent_name, mem, session_id)
            # Keep last 4 turns for continuity
            _session_memory[session_id][agent_name] = mem[-4:]

        health_monitor.record_success(agent_name)
        return {"agent": agent_name, "task": task,
                "response": response, "routed_to": agent_name}

    except Exception as e:
        health_monitor.record_failure(agent_name)
        logger.error("Agent %s failed: %s", agent_name, e, exc_info=True)
        return {"agent": agent_name, "task": task,
                "response": f"Error executing task: {e}", "routed_to": agent_name}


# ─── Main Handle ──────────────────────────────────────────────────

def handle(user_input: str, force_agent: str = None, session_id: str = "default") -> dict:
    u = user_input.lower()

    # Direct routing bypass
    if force_agent == "info":
        response = info_agent.handle(user_input)
        return {"agent": "info", "task": user_input, "response": response, "routed_to": "info"}

    store_memory(
        "orchestrator",
        f"task_{hash(user_input)}",
        user_input,
        {"timestamp": datetime.now().isoformat()}
    )

    orch_ctx = _get_orch_ctx(session_id)
    orch_ctx.append({"role": "user", "content": user_input})
    if len(orch_ctx) > 10:
        _orchestrator_context[session_id] = orch_ctx[-10:]
        orch_ctx = _orchestrator_context[session_id]

    # ── Pipeline triggers ──────────────────────────────────────
    if ("apply pipeline" in u) or ("apply to" in u and "pipeline" in u):
        parts = user_input.split(",")
        company = parts[0].replace("apply pipeline", "").replace("apply to", "").strip()
        role    = parts[1].strip() if len(parts) > 1 else "AI/ML Intern"
        jd      = parts[2].strip() if len(parts) > 2 else ""
        email   = parts[3].strip() if len(parts) > 3 else ""
        result  = pipeline.run_apply_pipeline(company, role, jd, email)
        return {"agent": "pipeline", "task": user_input, "response": result}

    if "publish pipeline" in u or "content pipeline" in u:
        parts   = user_input.split(",")
        project = parts[0].replace("publish pipeline", "").replace("content pipeline", "").strip()
        details = parts[1].strip() if len(parts) > 1 else ""
        result  = pipeline.run_publish_pipeline(project, details)
        return {"agent": "pipeline", "task": user_input, "response": result}

    if "research pipeline" in u:
        parts       = user_input.split(",")
        project     = parts[0].replace("research pipeline", "").strip()
        description = parts[1].strip() if len(parts) > 1 else ""
        journal     = parts[2].strip() if len(parts) > 2 else ""
        result      = pipeline.run_research_pipeline(project, description, journal)
        return {"agent": "pipeline", "task": user_input, "response": result}

    # ── Approval system ───────────────────────────────────────
    if "show approvals" in u or "pending approvals" in u:
        approvals = pipeline.get_pending_approvals()
        if not approvals:
            return {"agent": "orchestrator", "task": user_input,
                    "response": "✅ No pending approvals."}
        result = f"📋 **{len(approvals)} Pending Approvals:**\n\n"
        for a in approvals:
            result += f"**[{a['id']}] {a['title']}**\n"
            result += f"Type: {a['type']} | {a['created_at'][:10]}\n"
            result += f"Preview: {a['content'][:200]}...\n"
            result += f"→ Type 'approve {a['id']}' or 'reject {a['id']}'\n\n"
        return {"agent": "orchestrator", "task": user_input, "response": result}

    if u.startswith("approve "):
        match = re.search(r'\d+', user_input)
        if not match:
            return {"agent": "orchestrator", "task": user_input,
                    "response": "❌ Please provide a valid approval ID (e.g. 'approve 3')."}
        approval_id = int(match.group())
        result = pipeline.approve(approval_id)
        return {"agent": "orchestrator", "task": user_input, "response": result}

    if u.startswith("reject "):
        match = re.search(r'\d+', user_input)
        if not match:
            return {"agent": "orchestrator", "task": user_input,
                    "response": "❌ Please provide a valid rejection ID (e.g. 'reject 3')."}
        approval_id = int(match.group())
        result = pipeline.reject(approval_id)
        return {"agent": "orchestrator", "task": user_input, "response": result}

    # ── Fast pre-router ───────────────────────────────────────
    for keyword, agent_name in FAST_ROUTES.items():
        if keyword in u and agent_name in AGENT_MAP:
            return _dispatch_to_agent(agent_name, user_input, user_input, session_id)

    # ── Normal LLM routing ────────────────────────────────────
    routed     = route_task(user_input, context=orch_ctx)
    agent_name = routed.get("agent", "unknown")
    task       = routed.get("task", user_input)

    if agent_name in AGENT_MAP:
        return _dispatch_to_agent(agent_name, task, user_input, session_id)

    # ── Fallback: orchestrator direct response ────────────────
    try:
        from config import get_model, GROQ_API_KEY
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)

        system_prompt = (
            "You are Aaqil AI, a highly capable Multi-Agent Orchestrator. "
            "You manage a team of specialized agents: github, linkedin, job, project manager, "
            "career, growth, research, email, and briefing. "
            "Respond to casual conversation, greetings, or questions about what you can do politely and conversationally."
        )
        messages = [{"role": "system", "content": system_prompt}] + orch_ctx

        resp = client.chat.completions.create(
            model=get_model("fast"),
            messages=messages,
            temperature=0.7
        )
        reply = resp.choices[0].message.content

        orch_ctx.append({"role": "assistant", "content": reply})

        return {
            "agent": "orchestrator",
            "task": user_input,
            "response": reply,
            "routed_to": "orchestrator"
        }
    except Exception as e:
        logger.error("Orchestrator fallback failed: %s", e)
        return {
            "agent": "orchestrator",
            "response": "Aaqil here. I'm having trouble connecting to my brain right now. Can you try again?",
            "routed_to": "none"
        }


def get_health_monitor():
    return health_monitor


def get_pipeline():
    return pipeline