"""
NOT SUPPORTED in orchestrator_core v2.

GitHub agent is experimental. It:
  - Is not imported by orchestrator_core/
  - Is not covered by any test in the CI suite
  - Will be moved to experimental/github_agent/ in Phase 4
  - Kept as a reference implementation only

GitHub Agent — Real GitHub API + LLM-driven dispatch.
Manages repos, generates READMEs, commit messages, and profile insights.
"""

import os
import requests
from agents.base_agent import BaseAgent
from dotenv import load_dotenv

load_dotenv()

GITHUB_USERNAME = "FarhanAaqil"


class GitHubAgent(BaseAgent):

    TOOLS = [
        {
            "name": "profile_summary",
            "description": "Get a summary of Aaqil's GitHub profile with repo list and insights. Use for 'show github', 'github profile', 'github stats'.",
            "args": {}
        },
        {
            "name": "generate_readme",
            "description": "Generate a professional README.md for a specific repo. Use for 'generate readme for [repo]', 'write readme'.",
            "args": {"repo_name": "str"}
        },
        {
            "name": "generate_commit_message",
            "description": "Generate a conventional commit message for code changes. Use for 'commit message for [changes]', 'write commit'.",
            "args": {"changes": "str (description of what changed)"}
        },
        {
            "name": "analyze_repo",
            "description": "Deep analysis of a specific repo with improvement suggestions. Use for 'analyze [repo]', 'how can I improve [repo]'.",
            "args": {"repo_name": "str"}
        },
        {
            "name": "list_repos",
            "description": "List all of Aaqil's repositories. Use for 'list repos', 'show my repos', 'what repos do I have'.",
            "args": {}
        },
        {
            "name": "suggest_improvements",
            "description": "Suggest concrete improvements for Aaqil's overall GitHub profile/portfolio. Use for 'improve my github', 'github tips'.",
            "args": {}
        },
        {
            "name": "write_pr_description",
            "description": "Write a professional Pull Request description. Use for 'PR description for [feature]', 'write pull request'.",
            "args": {"feature": "str", "changes": "str"}
        }
    ]

    def __init__(self):
        super().__init__(
            name="github",
            system_prompt="""You are Aaqil's GitHub Agent — his technical portfolio manager.
You analyze repos, generate excellent documentation, and help maintain a strong GitHub presence.
Farhan Aaqil: Final-year AI/ML student. Repos: orchestrator-agent (9-agent AI), SheetSense-AI,
IntelliGlove, InterviewPro, DiaPredict-AI. GitHub: github.com/FarhanAaqil
Be technically precise, use proper Markdown, follow GitHub conventions."""
        )
        self._token = os.getenv("GITHUB_TOKEN")
        self._headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def _api(self, endpoint: str) -> dict:
        """Call GitHub API with error handling."""
        if not self._token:
            return {"error": "GITHUB_TOKEN not set in .env"}
        try:
            resp = requests.get(
                f"https://api.github.com{endpoint}",
                headers=self._headers, timeout=10
            )
            if resp.status_code == 404:
                return {"error": f"Not found: {endpoint}"}
            if resp.status_code == 401:
                return {"error": "Invalid GITHUB_TOKEN — check your .env file"}
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    def _get_repos(self) -> list:
        data = self._api(f"/users/{GITHUB_USERNAME}/repos?per_page=100&sort=updated")
        if isinstance(data, list):
            return data
        return []

    def list_repos(self) -> str:
        repos = self._get_repos()
        if not repos:
            return "❌ Could not fetch repos. Check GITHUB_TOKEN in .env"
        result = f"📁 **Farhan Aaqil's Repositories ({len(repos)}):**\n\n"
        for r in repos:
            lang = r.get("language") or "N/A"
            stars = r.get("stargazers_count", 0)
            desc = r.get("description") or ""
            result += f"**{r['name']}** ({lang})"
            if stars: result += f" ⭐{stars}"
            result += f"\n"
            if desc: result += f"  _{desc}_\n"
            result += f"  🔗 {r['html_url']}\n\n"
        return result

    def profile_summary(self) -> str:
        user = self._api(f"/users/{GITHUB_USERNAME}")
        repos = self._get_repos()
        events = self._api(f"/users/{GITHUB_USERNAME}/events?per_page=10")

        if "error" in user:
            return f"❌ GitHub API error: {user['error']}"

        # Recent activity
        activity_lines = []
        if isinstance(events, list):
            for e in events[:5]:
                etype = e.get("type", "")
                repo = e.get("repo", {}).get("name", "").replace(f"{GITHUB_USERNAME}/", "")
                if etype == "PushEvent":
                    n = len(e.get("payload", {}).get("commits", []))
                    activity_lines.append(f"🔀 Pushed {n} commit(s) to **{repo}**")
                elif etype == "CreateEvent":
                    activity_lines.append(f"✨ Created {e['payload'].get('ref_type', '')} in **{repo}**")
                elif etype == "WatchEvent":
                    activity_lines.append(f"⭐ Starred **{repo}**")

        # Top repos
        top_repos = sorted(repos, key=lambda x: x.get("stargazers_count", 0), reverse=True)[:6]
        repo_lines = "\n".join([
            f"- {r['name']} ({r.get('language') or 'N/A'}) — {r.get('description') or ''}"
            for r in top_repos
        ])

        task = f"""Summarize Farhan Aaqil's GitHub profile:
Username: {user.get('login')}
Public Repos: {user.get('public_repos')}
Followers: {user.get('followers')} | Following: {user.get('following')}
Bio: {user.get('bio') or 'Not set'}
Profile: {user.get('html_url')}

Top Repos:
{repo_lines}

Recent Activity:
{chr(10).join(activity_lines) if activity_lines else 'No recent activity'}

Give:
1. A crisp profile summary (2 sentences)
2. Repo highlights — top 3 most impressive repos with WHY they're impressive
3. GitHub profile score (X/10) with specific reasons
4. Top 2 actionable improvements for his profile"""

        return self.run(task)

    def generate_readme(self, repo_name: str) -> str:
        # Fetch repo data from GitHub API
        repo = self._api(f"/repos/{GITHUB_USERNAME}/{repo_name}")
        if "error" in repo:
            # Try to generate from just the name
            task = f"""Generate a complete, professional README.md for a GitHub repo called '{repo_name}'.

Repo owner: Farhan Aaqil — AI/ML student. Assume it's an AI/ML or Python project.

Include:
# {repo_name}
Brief description, Features list, Tech Stack, Installation steps, Usage examples, Author section.
Use proper Markdown. Make it look professional."""
            return f"📝 **README.md for {repo_name}:**\n\n```markdown\n{self.run(task)}\n```"

        # Fetch file tree
        tree_data = self._api(f"/repos/{GITHUB_USERNAME}/{repo_name}/contents/")
        files = [f["name"] for f in tree_data if isinstance(tree_data, list)]

        task = f"""Generate a complete, professional README.md for this GitHub repo:

**{repo.get('name')}** by Farhan Aaqil
Description: {repo.get('description') or 'No description yet'}
Language: {repo.get('language') or 'Python'}
Stars: {repo.get('stargazers_count', 0)} | Forks: {repo.get('forks_count', 0)}
Topics: {', '.join(repo.get('topics', []))}
Files in root: {', '.join(files[:15])}
License: {repo.get('license', {}).get('name', 'Not specified') if repo.get('license') else 'Not specified'}

Generate a full README.md with:
1. Project title + badge line (if applicable)
2. Description (2-3 sentences, specific and compelling)
3. ✨ Features (5-7 bullet points)
4. 🛠️ Tech Stack
5. 🚀 Quick Start / Installation
6. 📖 Usage (with example)
7. 🤝 Contributing (brief)
8. 👤 Author — Farhan Aaqil | github.com/FarhanAaqil

Use proper Markdown formatting."""
        readme = self.run(task, temperature=0.6)
        return f"📝 **README.md for {repo_name}:**\n\n```markdown\n{readme}\n```"

    def generate_commit_message(self, changes: str) -> str:
        task = f"""Generate a conventional commit message for these changes:

{changes}

Format: <type>(<scope>): <subject>

Types: feat, fix, docs, style, refactor, test, chore
Rules:
- Subject line: max 72 chars, imperative mood ("add" not "added")
- If complex, add a body explaining WHY
- Keep it professional and specific

Output just the commit message, nothing else."""
        result = self.run(task, temperature=0.3)
        return f"💬 **Commit Message:**\n\n```\n{result}\n```"

    def analyze_repo(self, repo_name: str) -> str:
        repo = self._api(f"/repos/{GITHUB_USERNAME}/{repo_name}")
        if "error" in repo:
            return f"❌ Repo '{repo_name}' not found. Check the name."

        tree = self._api(f"/repos/{GITHUB_USERNAME}/{repo_name}/contents/")
        files = [f["name"] for f in tree if isinstance(tree, list)]

        task = f"""Analyze this GitHub repo for Farhan Aaqil and give improvement recommendations:

Repo: {repo.get('name')}
Description: {repo.get('description') or 'No description'}
Language: {repo.get('language') or 'Python'}
Stars: {repo.get('stargazers_count', 0)} | Forks: {repo.get('forks_count', 0)}
Open Issues: {repo.get('open_issues_count', 0)}
Has README: {'README.md' in files or 'README' in files}
Has License: {'.github' in files or any('license' in f.lower() for f in files)}
Files: {', '.join(files[:20])}

Analyze:
1. **What this repo does** (inferred from name/files)
2. **Strengths** (what's done well)
3. **Issues** (what's missing or could be better)
4. **Top 5 Improvements** (specific, actionable, ranked by impact)
5. **SEO/Discoverability score** (X/10) — topics, description, README quality"""
        return self.run(task)

    def suggest_improvements(self) -> str:
        user = self._api(f"/users/{GITHUB_USERNAME}")
        repos = self._get_repos()
        no_desc = [r["name"] for r in repos if not r.get("description")]
        no_topics = [r["name"] for r in repos if not r.get("topics")]

        task = f"""Give 8 specific GitHub profile improvements for Farhan Aaqil:

Profile stats:
- Public repos: {user.get('public_repos', 0)}
- Followers: {user.get('followers', 0)}
- Bio: {user.get('bio') or 'Not set'}
- Repos missing description: {no_desc[:5]}
- Repos missing topics: {no_topics[:5]}

Be specific. Prioritize by impact. Include:
- Profile-level changes (pinned repos, bio, profile README)
- Repo-level changes (descriptions, topics, READMEs)
- Activity-level changes (contribution patterns)"""
        return f"💡 **GitHub Improvement Plan:**\n\n{self.run(task)}"

    def write_pr_description(self, feature: str, changes: str = "") -> str:
        task = f"""Write a professional GitHub Pull Request description:

Feature/Change: {feature}
Details: {changes if changes else 'Implement the feature as described'}

Include:
## Summary
Brief description of what and why

## Changes Made
- Bullet list of specific changes

## Testing
How to test this change

## Related Issues
#TODO

Use proper GitHub markdown."""
        result = self.run(task, temperature=0.5)
        return f"📋 **PR Description:**\n\n{result}"

    def handle(self, task: str) -> str:
        if not self._token:
            return "❌ GitHub agent: GITHUB_TOKEN is not set in your .env file."
        return self.think_and_act(task)