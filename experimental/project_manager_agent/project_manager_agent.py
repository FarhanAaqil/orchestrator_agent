"""
NOT SUPPORTED in orchestrator_core v2.

Project Manager agent is experimental. It:
  - Is not imported by orchestrator_core/
  - Is not covered by any test in the CI suite
  - Will be moved to experimental/project_manager_agent/ in Phase 4
  - Kept as a reference implementation only

Project Manager Agent — Tracks projects, tasks, deadlines, and goals.
Fully LLM-dispatched via think_and_act().
"""

from agents.base_agent import BaseAgent
from database.tracker import (
    add_project, get_projects, update_project_progress,
    add_task, get_tasks, complete_task,
    add_goal, update_goal, get_goals
)
from datetime import datetime


class ProjectManagerAgent(BaseAgent):

    TOOLS = [
        {
            "name": "format_projects",
            "description": "Show all projects with progress bars. Use for 'show projects', 'all projects', 'project status'.",
            "args": {}
        },
        {
            "name": "format_tasks",
            "description": "Show tasks, optionally filtered by project. Use for 'show tasks', 'tasks for [project]'.",
            "args": {"project": "str (optional)"}
        },
        {
            "name": "format_goals",
            "description": "Show all goals with progress bars. Use for 'show goals', 'my goals', 'goal progress'.",
            "args": {}
        },
        {
            "name": "add_project_db",
            "description": "Add a new project to the tracker. Use for 'add project [name]', 'create project'.",
            "args": {"name": "str", "desc": "str (optional)", "deadline": "str (optional, YYYY-MM-DD)",
                     "github_url": "str (optional)", "deployed_url": "str (optional)"}
        },
        {
            "name": "add_task_db",
            "description": "Add a task to a project. Use for 'add task [title] to [project]', 'create task'.",
            "args": {"project": "str", "title": "str", "priority": "str (high/medium/low)", "deadline": "str (optional)"}
        },
        {
            "name": "complete_task_db",
            "description": "Mark a task as done by ID. Use for 'done task [ID]', 'complete task [ID]'.",
            "args": {"task_id": "int"}
        },
        {
            "name": "add_goal_db",
            "description": "Add a new goal. Use for 'add goal [title], [N] per week'.",
            "args": {"title": "str", "target": "int", "period": "str (weekly/monthly/daily)"}
        },
        {
            "name": "update_project_db",
            "description": "Update a project's progress %. Use for 'update [project] to [N]%', 'set progress'.",
            "args": {"name": "str", "progress": "int", "status": "str (optional: active/completed/paused)"}
        },
        {
            "name": "weekly_report",
            "description": "Generate a full weekly progress report. Use for 'weekly report', 'how was my week'.",
            "args": {}
        },
        {
            "name": "plan_sprint",
            "description": "Plan a N-day sprint with priorities. Use for 'plan sprint', 'plan my week'.",
            "args": {"duration_days": "int (default 7)"}
        },
        {
            "name": "suggest_next",
            "description": "Suggest what to work on RIGHT NOW. Use for 'what should I do', 'next task', 'prioritize'.",
            "args": {}
        }
    ]

    def __init__(self):
        super().__init__(
            name="project_manager",
            system_prompt="""You are Aaqil's Project Manager — a smart technical lead who always knows what matters most.
You track projects, tasks, deadlines, and goals. Give clear, direct, prioritized guidance.
Current projects: Aaqil (9-agent AI), Self-Improving Code Agent, SheetSense AI,
IntelliGlove, InterviewPro, DiaPredict AI.
Numbers and specifics beat generalities. Always prioritize ruthlessly."""
        )

    def add_project_db(self, name: str, desc: str = "", deadline: str = "",
                       github_url: str = "", deployed_url: str = "") -> str:
        add_project(name, desc, deadline, github_url, deployed_url)
        return f"✅ Project **{name}** added!"

    def add_task_db(self, project: str, title: str, priority: str = "medium",
                    deadline: str = "") -> str:
        add_task(project, title, priority, deadline)
        return f"✅ Task added to **{project}**: {title}"

    def complete_task_db(self, task_id: int) -> str:
        complete_task(int(task_id))
        return f"✅ Task {task_id} marked as done!"

    def add_goal_db(self, title: str, target: int = 10, period: str = "weekly") -> str:
        add_goal(title, target, period)
        return f"🎯 Goal added: **{title}** — {target} ({period})"

    def update_project_db(self, name: str, progress: int, status: str = None) -> str:
        update_project_progress(name, int(progress), status)
        return f"✅ **{name}** updated to {progress}%"

    def weekly_report(self) -> str:
        projects = get_projects()
        tasks = get_tasks()
        goals = get_goals()
        done_tasks = [t for t in tasks if t["status"] == "done"]
        todo_tasks = [t for t in tasks if t["status"] == "todo"]
        high_priority = [t for t in todo_tasks if t["priority"] == "high"]

        data = f"""
Projects: {len(projects)} total | Active: {len([p for p in projects if p['status'] == 'active'])}
Tasks done: {len(done_tasks)} | Pending: {len(todo_tasks)} | High priority: {len(high_priority)}

Projects: {chr(10).join([f"- {p['name']}: {p['progress']}% | Deadline: {p['deadline'] or 'None'}" for p in projects])}
Goals: {chr(10).join([f"- {g['title']}: {g['current']}/{g['target']} ({g['period']})" for g in goals])}
High Priority Tasks: {chr(10).join([f"- [{t['project_name']}] {t['title']}" for t in high_priority[:5]])}
"""
        return self.run(f"Generate a weekly progress report:\n{data}")

    def plan_sprint(self, duration_days: int = 7) -> str:
        tasks = get_tasks(status="todo")
        projects = get_projects(status="active")
        task_str = chr(10).join([
            f"- [{t['priority'].upper()}] [{t['project_name']}] {t['title']}"
            for t in tasks[:15]
        ])
        proj_str = chr(10).join([f"- {p['name']}: {p['progress']}% done" for p in projects])
        return self.run(
            f"Plan a {duration_days}-day sprint for Aaqil.\n"
            f"Active Projects:\n{proj_str}\n\nPending Tasks:\n{task_str}\n\n"
            f"Day-by-day plan. Be realistic. High-priority items first."
        )

    def suggest_next(self) -> str:
        tasks = get_tasks(status="todo")
        high = [t for t in tasks if t["priority"] == "high"]
        top = (high + [t for t in tasks if t["priority"] == "medium"])[:5]
        if not top:
            return "No pending tasks. Add some with: 'add task [title] to [project]'"
        task_str = chr(10).join([
            f"- [{t['priority'].upper()}] [{t['project_name']}] {t['title']}"
            for t in top
        ])
        return self.run(
            f"What should Aaqil work on RIGHT NOW?\n{task_str}\n\n"
            f"Give ONE clear recommendation with 2-sentence reasoning."
        )

    def format_projects(self) -> str:
        projects = get_projects()
        if not projects:
            return "No projects yet. Say: 'add project [name]'"
        result = "📁 **All Projects:**\n\n"
        for p in projects:
            bar = "█" * (p["progress"] // 10) + "░" * (10 - p["progress"] // 10)
            result += f"**{p['name']}**\n  [{bar}] {p['progress']}%\n"
            result += f"  Status: {p['status']} | Deadline: {p['deadline'] or 'None'}\n"
            if p["github_url"]: result += f"  GitHub: {p['github_url']}\n"
            if p["deployed_url"]: result += f"  Live: {p['deployed_url']}\n"
            result += "\n"
        return result

    def format_tasks(self, project: str = None) -> str:
        tasks = get_tasks(project_name=project)
        if not tasks:
            return "No tasks found."
        todo = [t for t in tasks if t["status"] == "todo"]
        done = [t for t in tasks if t["status"] == "done"]
        result = f"📋 **Tasks** {'for ' + project if project else '(All)'}:\n\n"
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        if todo:
            result += "**Pending:**\n"
            for t in todo:
                emoji = priority_emoji.get(t["priority"], "⚪")
                result += f"{emoji} [{t['id']}] {t['title']}"
                if not project: result += f" | [{t['project_name']}]"
                if t["deadline"]: result += f" | Due: {t['deadline']}"
                result += "\n"
        if done:
            result += f"\n✅ **Done ({len(done)}):**\n"
            for t in done[:5]:
                result += f"  ✓ {t['title']}\n"
        return result

    def format_goals(self) -> str:
        goals = get_goals()
        if not goals:
            return "No goals set. Say: 'add goal [title], target [N]'"
        result = "🎯 **Goals:**\n\n"
        for g in goals:
            pct = int((g["current"] / g["target"]) * 100) if g["target"] > 0 else 0
            bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
            result += f"**{g['title']}**\n  [{bar}] {g['current']}/{g['target']} ({pct}%) — {g['period']}\n\n"
        return result

    def handle(self, task: str) -> str:
        return self.think_and_act(task)