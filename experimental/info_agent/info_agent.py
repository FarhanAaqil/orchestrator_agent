"""
NOT SUPPORTED in orchestrator_core v2.

Info agent is experimental. It:
  - Is not imported by orchestrator_core/
  - Is not covered by any test in the CI suite
  - Will be moved to experimental/info_agent/ in Phase 4
  - Kept as a reference implementation only

InfoAgent — System Documentation & Interactive Help Agent

Provides:
  - Per-agent detailed profiles (tools, purpose, example commands)
  - System-wide health & stats dashboard
  - Searchable command reference
  - How-to guidance for pipelines, approvals, and scheduled jobs
  - Quick-start examples for new users
"""

from agents.base_agent import BaseAgent
import json


# ─── Static knowledge base ────────────────────────────────────────
# Hard-coded example commands and tips per agent so InfoAgent can
# answer even before an agent has been used (no DB entries needed).

AGENT_EXAMPLES: dict = {
    "github": [
        "show github",
        "github profile",
        "generate readme for <project>",
        "commit message for <changes>",
        "analyse my repos",
    ],
    "linkedin": [
        "search linkedin for ML engineers",
        "draft linkedin connection message for <name>",
        "find linkedin profiles for AI startups",
    ],
    "job": [
        "find machine learning internships",
        "find LLM agent jobs remote",
        "show jobs",
        "job dashboard",
        "write cover letter for AI Engineer at OpenAI",
        "mark applied <url>",
        "search remoteok for python intern",
    ],
    "project_manager": [
        "show tasks",
        "add task: <title> for project <name>",
        "show all projects",
        "show goals",
        "weekly report",
    ],
    "career": [
        "show skills",
        "my skills",
        "career dashboard",
        "career stats",
        "tailor resume for <job description>",
        "show certificates",
        "interview prep for Google SDE",
    ],
    "growth": [
        "linkedin post about <topic>",
        "twitter thread on <topic>",
        "blog post about <project>",
        "content dashboard",
        "my content",
        "content calendar",
    ],
    "research": [
        "write paper about <topic>",
        "show papers",
        "my papers",
        "research dashboard",
        "find journals for <topic>",
        "recommend journals for <paper title>",
        "is <journal name> predatory?",
        "draft submission email for <paper title> to <journal>",
    ],
    "email": [
        "show emails",
        "draft email to <name> about <topic>",
        "follow up on emails",
    ],
    "briefing": [
        "morning briefing",
        "generate briefing",
        "daily briefing",
        "good morning",
    ],
    "pipeline": [
        "apply pipeline <company>, <role>, <job description>, <email>",
        "publish pipeline <project>, <details>",
        "research pipeline <topic>, <description>, <target journal>",
        "show approvals",
        "approve <id>",
        "reject <id>",
    ],
}

PIPELINE_DOCS = """
## ⚙️ Pipelines

Pipelines are multi-agent workflows that chain several agents together automatically.
All pipeline outputs are **queued for your approval** before any action is taken.

### 📋 Apply Pipeline
```
apply pipeline Google, AI/ML Intern, <paste job description>, recruiter@google.com
```
Steps: CareerAgent tailors resume → JobAgent writes cover letter → CriticAgent reviews → queued for approval.

### 📢 Publish Pipeline
```
publish pipeline Orchestrator Agent, 9-agent LLM system
```
Steps: GrowthAgent generates LinkedIn post + blog → CriticAgent reviews → queued for approval.

### 📚 Research Pipeline
```
research pipeline LLM Agents, multi-agent orchestration systems, IEEE
```
Steps: ResearchAgent writes full paper with real ArXiv citations → finds target journals → queued for approval.

### ✅ Approvals
- `show approvals` — list all pending approvals
- `approve <id>` — approve an item
- `reject <id>` — reject an item
"""

SCHEDULER_DOCS = """
## ⏰ Background Scheduler

The system runs automatic tasks in the background:

| Time | Task |
|------|------|
| 8:00 AM | 🌅 Morning briefing generated |
| 10:00 AM | 🔍 Daily job search (ML/AI internships) |
| Every 4 hours | 📰 AI/ML news update |
| 6:00 PM | 🐙 GitHub activity snapshot |
| Sunday 9:00 PM | 📊 Weekly reflection report |
| 9:00 AM & 3:00 PM | 🔴 High-priority task reminder |
| Sunday 2:00 AM | 🧹 Memory consolidation |

All results appear as **notifications** (🔔 bell icon in the header).
"""

MEMORY_DOCS = """
## 🧠 Memory System

The system uses two memory layers:

### Short-Term (per session)
- Each agent keeps the last **10 conversation turns** in memory
- When that fills up, a summary is compressed into long-term memory
- This means agents remember context within a conversation

### Long-Term (ChromaDB vector store)
- All agent outputs are stored as semantic embeddings
- Agents automatically recall relevant past context before responding
- Semantic deduplication prevents storing the same info twice

### Memory Consolidation
- Runs weekly (Sunday 2 AM)
- Summarises old agent memories into core principles
"""


class InfoAgent(BaseAgent):

    TOOLS = [
        {
            "name": "get_agent_details",
            "description": "Get full profile for a specific agent: purpose, tools, example commands. Use for 'how does X agent work', 'what can X do', 'tell me about X agent'.",
            "args": {"agent_name": "str"}
        },
        {
            "name": "list_all_agents",
            "description": "List all agents with tool counts and one-line descriptions. Use for 'list agents', 'what agents are there', 'what can you do'.",
            "args": {}
        },
        {
            "name": "show_command_reference",
            "description": "Show a full categorised command reference for all agents. Use for 'show commands', 'command reference', 'how do I use this system', 'what commands can I run'.",
            "args": {}
        },
        {
            "name": "explain_pipelines",
            "description": "Explain the multi-agent pipeline system and approval flow. Use for 'how do pipelines work', 'explain apply pipeline', 'what is a pipeline'.",
            "args": {}
        },
        {
            "name": "explain_memory",
            "description": "Explain how the memory system works (ChromaDB + short-term context). Use for 'how does memory work', 'does it remember me', 'what is chroma'.",
            "args": {}
        },
        {
            "name": "explain_scheduler",
            "description": "Explain the background scheduler and what runs automatically. Use for 'what runs automatically', 'scheduled tasks', 'what does the scheduler do'.",
            "args": {}
        },
        {
            "name": "get_system_stats",
            "description": "Show live agent health statistics from the health monitor. Use for 'system status', 'agent health', 'which agents are active'.",
            "args": {}
        },
        {
            "name": "search_commands",
            "description": "Search the command reference for a specific keyword or topic. Use for 'how do I do X', 'find command for X', 'search commands for X'.",
            "args": {"query": "str"}
        },
    ]

    def __init__(self):
        super().__init__(
            name="info",
            system_prompt="""You are the System Documentation & Help Agent for the Aaqil AI orchestrator.

Your role is to:
- Explain how agents, pipelines, memory, and the scheduler work
- Show example commands a user can run
- Answer 'how do I...' questions about the system
- Surface health and usage statistics

Always use your tools to retrieve accurate, live information.
Format all responses with clear Markdown — use headers, code blocks, and tables.
Be concise but complete. Always end with 1-2 actionable suggestions."""
        )

    # ─── Tool Implementations ──────────────────────────────────────

    def get_agent_details(self, agent_name: str) -> str:
        agent_name = agent_name.lower().strip().replace(" ", "_")

        # Handle aliases
        aliases = {"pm": "project_manager", "project manager": "project_manager",
                   "proj": "project_manager", "jobs": "job", "papers": "research",
                   "emails": "email", "brief": "briefing", "git": "github"}
        agent_name = aliases.get(agent_name, agent_name)

        if agent_name not in self.AGENT_MAP:
            available = ", ".join(f"`{n}`" for n in self.AGENT_MAP)
            return (
                f"❌ Agent `{agent_name}` not found.\n\n"
                f"**Available agents:** {available}\n\n"
                "Try: `how does research agent work` or `list all agents`"
            )

        target = self.AGENT_MAP[agent_name]
        tools_str = json.dumps(target.TOOLS, indent=2) if target.TOOLS else "None (pure LLM agent)"

        examples = AGENT_EXAMPLES.get(agent_name, [])
        examples_str = "\n".join(f"- `{ex}`" for ex in examples) if examples else "_No examples recorded._"

        # Extract first two sentences of system prompt as a summary
        sp = target.system_prompt.strip().replace("\n", " ")
        summary = ". ".join(sp.split(".")[:2]).strip() + "."

        result = f"## 🤖 Agent: `{agent_name.replace('_', ' ').title()}`\n\n"
        result += f"**Purpose:** {summary}\n\n"
        result += f"**Tools ({len(target.TOOLS)}):**\n```json\n{tools_str}\n```\n\n"
        result += f"**Example Commands:**\n{examples_str}\n\n"
        result += f"> 💡 Ask me `explain pipelines` to see multi-agent workflows, or `show command reference` for a full list."

        return result

    def list_all_agents(self) -> str:
        if not self.AGENT_MAP:
            return "❌ No agents registered in the system."

        # Agent descriptions (supplement what the system prompt says)
        descriptions = {
            "github":          "Analyses repos, generates READMEs, drafts commit messages",
            "linkedin":        "Searches LinkedIn profiles and drafts connection messages",
            "job":             "Multi-source job search (RemoteOK, Remotive, LinkedIn, WWR)",
            "project_manager": "Tracks tasks, projects, deadlines, and weekly goals",
            "career":          "Manages skills, certificates, resume tailoring, interview prep",
            "growth":          "Creates LinkedIn posts, Twitter threads, and blog content",
            "research":        "Writes full IEEE papers with live ArXiv citations, finds journals",
            "email":           "Drafts and tracks professional outreach emails",
            "briefing":        "Generates a morning briefing with tasks, jobs, and news",
        }

        result = "## 📋 System Agents\n\n"
        result += "| Agent | Tools | Description |\n"
        result += "|-------|-------|-------------|\n"
        for name, agent in self.AGENT_MAP.items():
            desc = descriptions.get(name, agent.system_prompt.split(".")[0].strip())
            result += f"| `{name}` | {len(agent.TOOLS)} | {desc} |\n"

        result += "\n**Also available:**\n"
        result += "- ⚙️ **Pipelines** — `apply pipeline`, `publish pipeline`, `research pipeline`\n"
        result += "- ✅ **Approvals** — `show approvals`, `approve <id>`, `reject <id>`\n"
        result += "- ℹ️ **Info Mode** — toggle in sidebar to stay in help mode\n\n"
        result += "> 💡 Try `get agent details <name>` for tools and example commands."

        return result

    def show_command_reference(self) -> str:
        result = "## 📖 Full Command Reference\n\n"
        for agent_name, examples in AGENT_EXAMPLES.items():
            icon = {
                "github": "🐙", "linkedin": "💼", "job": "🔍",
                "project_manager": "📋", "career": "🎓", "growth": "📈",
                "research": "📚", "email": "📧", "briefing": "🌅",
                "pipeline": "⚙️",
            }.get(agent_name, "🤖")
            result += f"### {icon} {agent_name.replace('_', ' ').title()}\n"
            for ex in examples:
                result += f"- `{ex}`\n"
            result += "\n"

        result += "---\n"
        result += "> 💡 You can also use **natural language** — the router will match your intent to the right agent automatically."
        return result

    def search_commands(self, query: str) -> str:
        query_lower = query.lower()
        matches: list = []

        for agent_name, examples in AGENT_EXAMPLES.items():
            for ex in examples:
                if query_lower in ex.lower():
                    matches.append((agent_name, ex))

        if not matches:
            # Fall back to LLM to answer the how-to question
            task = (
                f"The user is asking: '{query}'\n\n"
                "Based on this Aaqil AI multi-agent system (agents: github, linkedin, job, "
                "project_manager, career, growth, research, email, briefing), "
                "suggest the best command or approach to accomplish this. "
                "Be specific and provide an exact example command."
            )
            return self.run(task)

        result = f"## 🔍 Commands matching `{query}`:\n\n"
        for agent_name, ex in matches:
            result += f"- **[{agent_name}]** `{ex}`\n"
        result += f"\n> Found {len(matches)} match(es). Use `get agent details <name>` for more."
        return result

    def explain_pipelines(self) -> str:
        return PIPELINE_DOCS

    def explain_memory(self) -> str:
        return MEMORY_DOCS

    def explain_scheduler(self) -> str:
        return SCHEDULER_DOCS

    def get_system_stats(self) -> str:
        try:
            from orchestrator.health_monitor import health_monitor
            stats = health_monitor.get_all_stats()
        except Exception:
            stats = {}

        result = "## ⚡ Live System Status\n\n"
        result += "| Agent | Status | Last Active | Tasks | Success Rate |\n"
        result += "|-------|--------|-------------|-------|--------------|\n"

        status_icon = {"idle": "🟢", "processing": "🟡", "error": "🔴"}

        for name, data in stats.items():
            icon  = status_icon.get(data.get("status", "idle"), "⚪")
            last  = data.get("last_active_str", "Never")
            total = data.get("total_tasks", 0)
            rate  = f"{data['success_rate']}%" if data.get("success_rate") is not None else "—"
            result += f"| `{name}` | {icon} {data.get('status','idle')} | {last} | {total} | {rate} |\n"

        if not stats:
            result += "| — | No activity recorded yet | — | — | — |\n"

        result += "\n> 🟢 idle = ready  🟡 processing = working  🔴 error = failed last task"
        return result

    # ─── Handle ───────────────────────────────────────────────────

    def handle(self, task: str) -> str:
        return self.think_and_act(task)
