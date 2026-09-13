"""
NOT SUPPORTED in orchestrator_core v2.

Job search features are experimental. This agent:
  - Is not imported by orchestrator_core/
  - Is not covered by any test in the CI suite
  - Is not deployed in the production Docker image
  - Will be moved to experimental/job_search_agent/ in Phase 4
  - Kept as a reference implementation only

Job Agent — Real multi-source job search.

Sources (all free, no API key required):
  - RemoteOK API      → JSON API, AI/ML remote jobs globally
  - Remotive API      → JSON API, curated remote jobs
  - We Work Remotely  → RSS feed parser
  - DuckDuckGo        → web search for job listings
  - LinkedIn Jobs     → via DuckDuckGo site:linkedin.com/jobs
  - Google Careers    → via DuckDuckGo site search
"""

import requests
import feedparser
import json
import re
import time
import hashlib
import pathlib
from datetime import datetime, timedelta
from agents.base_agent import BaseAgent
from database.tracker import insert_job, update_status, get_all_jobs, get_stats

# File-based job cache so results persist across restarts
_CACHE_FILE = pathlib.Path("./job_cache.json")
CACHE_TTL_SECONDS = 3600  # 1 hour


def _load_cache() -> dict:
    if _CACHE_FILE.exists():
        try:
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict):
    try:
        _CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _cache_get(key: str):
    cache = _load_cache()
    entry = cache.get(key)
    if entry and (time.time() - entry["ts"]) < CACHE_TTL_SECONDS:
        return entry["data"]
    return None


def _cache_set(key: str, data):
    cache = _load_cache()
    cache[key] = {"ts": time.time(), "data": data}
    # Evict entries older than TTL to keep file small
    now = time.time()
    cache = {k: v for k, v in cache.items() if (now - v["ts"]) < CACHE_TTL_SECONDS}
    _save_cache(cache)


# ─── Profile & Keyword Config ─────────────────────────────────────

AAQIL_PROFILE = """
Name: Farhan Aaqil
Degree: B.Tech AI/ML (Final Year, 2027) — JPNCE Mahbubnagar
Skills: Python, LangChain, LLM Agents, Machine Learning, Data Science,
        ChromaDB, FastAPI, Streamlit, Deep Learning, NLP
Experience: Python Full Stack + AIML Intern at Jala Academy
Published Research: ML-based Diabetes Prediction (2025)
Projects: Orchestrator Agent (9-agent system), SheetSense AI,
          IntelliGlove, InterviewPro, DiaPredict AI
Certifications: 4x Anthropic, Apna College Full Stack, NPTEL DBMS, 2x SkillUp
Target: Remote paid internships — Python, AI/ML, LLM Agents. NO pure web-dev.
"""

RELEVANCE_KEYWORDS = {
    "high":   ["llm", "langchain", "ai agent", "nlp", "large language", "transformer", "rag"],
    "medium": ["python", "machine learning", "data science", "deep learning", "ml engineer", "ai/ml", "ai ml"],
    "low":    ["intern", "remote", "api", "backend", "fastapi", "pytorch", "tensorflow"]
}

EXCLUDE_KEYWORDS = [
    "react", "angular", "vue", "frontend only", "php", "ruby",
    "wordpress", "graphic design", "sales", "marketing only",
    "devops only", "java only", "c++", ".net only"
]



class JobAgent(BaseAgent):

    TOOLS = [
        {
            "name": "search_all",
            "description": "Search for jobs/internships across all sources (RemoteOK, Remotive, LinkedIn, DuckDuckGo). Use for 'find jobs', 'search internships', 'find me something'.",
            "args": {"keywords": "str (e.g. 'machine learning intern')", "limit": "int (default 15)"}
        },
        {
            "name": "search_linkedin_jobs",
            "description": "Search LinkedIn specifically for jobs. Use when user mentions LinkedIn.",
            "args": {"keywords": "str", "limit": "int"}
        },
        {
            "name": "search_remoteok",
            "description": "Search RemoteOK for remote jobs. Use for remote-specific searches.",
            "args": {"keywords": "str", "limit": "int"}
        },
        {
            "name": "generate_cover_letter",
            "description": "Generate a tailored cover letter for a specific job. Use when user says 'write cover letter' or 'apply to X at Y'.",
            "args": {"title": "str", "company": "str", "description": "str (optional)"}
        },
        {
            "name": "get_dashboard",
            "description": "Show the job application dashboard with stats. Use for 'show dashboard', 'job stats', 'how many applied'.",
            "args": {}
        },
        {
            "name": "mark_applied",
            "description": "Mark a job as applied. Use when user says 'I applied to X' or 'mark applied'.",
            "args": {"url": "str", "company": "str (optional)"}
        },
        {
            "name": "show_all_tracked",
            "description": "Show all tracked/saved jobs. Use for 'show jobs', 'list jobs', 'what jobs do I have'.",
            "args": {}
        }
    ]

    def __init__(self):
        super().__init__(
            name="job",
            system_prompt=f"""You are Aaqil's Job Search Agent — think J.A.R.V.I.S. for internships.
You search multiple real job platforms simultaneously, filter for relevance, score matches, and help apply.

Aaqil's profile:
{AAQIL_PROFILE}

Be direct, specific, and proactive. When you find jobs, rank them by match quality.
Always tell Aaqil WHY a job is a good or bad match for him."""
        )

    # ─── Scoring ──────────────────────────────────────────────────────

    def _score_job(self, title: str, description: str = "") -> int:
        text = (title + " " + description).lower()
        if any(kw in text for kw in EXCLUDE_KEYWORDS):
            return 0
        score = 0
        for kw in RELEVANCE_KEYWORDS["high"]:
            if kw in text: score += 3
        for kw in RELEVANCE_KEYWORDS["medium"]:
            if kw in text: score += 2
        for kw in RELEVANCE_KEYWORDS["low"]:
            if kw in text: score += 1
        return min(score, 10)

    def _score_job_llm_batch(self, jobs: list) -> list:
        """Score a list of jobs in a SINGLE LLM call. Returns list of scores (same order)."""
        if not jobs:
            return []
        from config import get_model
        job_list = "\n".join([
            f"{i+1}. {j['title']} at {j['company']}: {j.get('description', '')[:200]}"
            for i, j in enumerate(jobs)
        ])
        prompt = f"""Rate each job's match with this profile on a scale of 1-10.

Profile:
{AAQIL_PROFILE}

Jobs:
{job_list}

Return ONLY a JSON array of integers in the same order, e.g. [7, 4, 9, ...]"""
        try:
            resp = self.client.chat.completions.create(
                model=get_model("fast"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )
            raw = resp.choices[0].message.content.strip()
            # Extract the JSON array
            match = re.search(r'\[.*?\]', raw, re.DOTALL)
            if match:
                scores = json.loads(match.group())
                if isinstance(scores, list) and len(scores) == len(jobs):
                    return [min(max(int(s), 0), 10) for s in scores]
        except Exception:
            pass
        # Fallback: keyword scoring
        return [self._score_job(j["title"], j.get("description", "")) for j in jobs]

    def _is_relevant(self, title: str, description: str = "") -> bool:
        text = (title + " " + description).lower()
        has_include = any(
            kw in text for kws in RELEVANCE_KEYWORDS.values() for kw in kws
        )
        has_exclude = any(kw in text for kw in EXCLUDE_KEYWORDS)
        return has_include and not has_exclude

    def _dedup(self, jobs: list) -> list:
        seen = set()
        result = []
        for j in jobs:
            key = hashlib.md5((j.get("title", "") + j.get("company", "")).lower().encode()).hexdigest()
            if key not in seen:
                seen.add(key)
                result.append(j)
        return result

    # ─── Source: RemoteOK ─────────────────────────────────────────────

    def search_remoteok(self, keywords: str = "machine learning", limit: int = 15) -> str:
        limit = int(limit)  # Guard: LLM sometimes passes limit as a string
        cache_key = f"remoteok_{keywords}"
        cached = _cache_get(cache_key)
        if cached:
            jobs = cached
        else:
            try:
                tag = keywords.lower().replace(" ", "+")
                url = f"https://remoteok.com/api?tag={tag}"
                resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
                data = resp.json()
                jobs = []
                for item in data[1:]:  # first item is a notice
                    if not isinstance(item, dict):
                        continue
                    title = item.get("position", "")
                    company = item.get("company", "")
                    description = item.get("description", "")
                    apply_url = item.get("url", f"https://remoteok.com/l/{item.get('id', '')}")
                    if not self._is_relevant(title, description):
                        continue
                    score = self._score_job(title, description)
                    jobs.append({
                        "title": title,
                        "company": company,
                        "location": "Remote",
                        "url": apply_url,
                        "source": "RemoteOK",
                        "match_score": score,
                        "description": description[:300]
                    })
                _cache_set(cache_key, jobs)
            except Exception as e:
                return f"❌ RemoteOK search failed: {e}"

        # Save to DB
        for j in jobs[:limit]:
            insert_job(j)

        if not jobs:
            return "No relevant jobs found on RemoteOK for that search."

        jobs_sorted = sorted(jobs, key=lambda x: x["match_score"], reverse=True)[:limit]
        return self._format_jobs(jobs_sorted, "RemoteOK")

    # ─── Source: Remotive ─────────────────────────────────────────────

    def _search_remotive(self, keywords: str = "machine learning") -> list:
        cache_key = f"remotive_{keywords}"
        cached = _cache_get(cache_key)
        if cached:
            return cached
        try:
            url = f"https://remotive.com/api/remote-jobs?search={requests.utils.quote(keywords)}&limit=30"
            resp = requests.get(url, timeout=15)
            data = resp.json()
            jobs = []
            for item in data.get("jobs", []):
                title = item.get("title", "")
                company = item.get("company_name", "")
                description = item.get("description", "")[:300]
                apply_url = item.get("url", "")
                if not self._is_relevant(title, description):
                    continue
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": item.get("candidate_required_location", "Remote"),
                    "url": apply_url,
                    "source": "Remotive",
                    "match_score": self._score_job(title, description),
                    "description": description
                })
            _cache_set(cache_key, jobs)
            return jobs
        except Exception:
            return []

    # ─── Source: We Work Remotely RSS ─────────────────────────────────

    def _search_weworkremotely(self, category: str = "programming") -> list:
        cache_key = f"wwr_{category}"
        cached = _cache_get(cache_key)
        if cached:
            return cached
        try:
            url = f"https://weworkremotely.com/categories/remote-{category}-jobs.rss"
            feed = feedparser.parse(url)
            jobs = []
            for entry in feed.entries[:20]:
                title = entry.get("title", "")
                company = entry.get("author", "Unknown")
                link = entry.get("link", "")
                summary = re.sub(r'<[^>]+>', '', entry.get("summary", ""))[:300]
                if not self._is_relevant(title, summary):
                    continue
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": "Remote",
                    "url": link,
                    "source": "We Work Remotely",
                    "match_score": self._score_job(title, summary),
                    "description": summary
                })
            _cache_set(cache_key, jobs)
            return jobs
        except Exception:
            return []

    # ─── Source: LinkedIn via DuckDuckGo ──────────────────────────────

    def search_linkedin_jobs(self, keywords: str = "AI ML intern remote", limit: int = 10) -> str:
        limit = int(limit)  # Guard: LLM sometimes passes limit as a string
        from utils.web_search import search_web
        cache_key = f"linkedin_{keywords}"
        cached = _cache_get(cache_key)
        if not cached:
            query = f'site:linkedin.com/jobs "{keywords}" intern OR internship remote'
            results = search_web(query, max_results=limit)
            cached = results
            _cache_set(cache_key, results)

        if not cached or (len(cached) > 0 and "error" in cached[0]):
            return "❌ LinkedIn job search failed. Try again shortly."

        jobs = []
        for r in cached:
            title = r.get("title", "").replace(" | LinkedIn", "").strip()
            snippet = r.get("snippet", "")
            url = r.get("url", "")
            if not url or "linkedin.com" not in url:
                continue
            # Extract company from title/snippet heuristics
            company = "Unknown"
            if " at " in title:
                parts = title.split(" at ")
                title_clean = parts[0].strip()
                company = parts[-1].strip()
            else:
                title_clean = title

            score = self._score_job(title_clean, snippet)
            if score == 0:
                continue

            job = {
                "title": title_clean,
                "company": company,
                "location": "Remote" if "remote" in snippet.lower() else "See link",
                "url": url,
                "source": "LinkedIn",
                "match_score": score,
                "description": snippet[:200]
            }
            jobs.append(job)
            insert_job(job)

        if not jobs:
            return "No relevant LinkedIn jobs found. Try different keywords."

        jobs_sorted = sorted(jobs, key=lambda x: x["match_score"], reverse=True)
        return self._format_jobs(jobs_sorted, "LinkedIn")

    # ─── Source: DuckDuckGo general job search ────────────────────────

    def _search_duckduckgo_jobs(self, keywords: str) -> list:
        from utils.web_search import search_web
        cache_key = f"ddg_jobs_{keywords}"
        cached = _cache_get(cache_key)
        if cached:
            return cached

        queries = [
            f'"{keywords}" internship remote India 2025 apply',
            f'"{keywords}" intern "apply now" site:wellfound.com OR site:ycombinator.com/jobs',
        ]
        jobs = []
        for query in queries:
            results = search_web(query, max_results=8)
            for r in results:
                title = r.get("title", "")
                snippet = r.get("snippet", "")
                url = r.get("url", "")
                if not url or not self._is_relevant(title, snippet):
                    continue
                jobs.append({
                    "title": title[:80],
                    "company": "See link",
                    "location": "Remote",
                    "url": url,
                    "source": "Web",
                    "match_score": self._score_job(title, snippet),
                    "description": snippet[:200]
                })
        _cache_set(cache_key, jobs)
        return jobs

    # ─── Aggregate Search ─────────────────────────────────────────────

    def search_all(self, keywords: str = "machine learning intern", limit: int = 15) -> str:
        """Search all sources simultaneously and return ranked results."""
        limit = int(limit)  # Guard: LLM sometimes passes limit as a string
        all_jobs = []

        # 1. RemoteOK
        remoteok_raw = []
        try:
            tag = keywords.lower().replace(" ", "+")
            url = f"https://remoteok.com/api?tag={tag}"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
            for item in resp.json()[1:]:
                if not isinstance(item, dict): continue
                t = item.get("position", "")
                c = item.get("company", "")
                d = item.get("description", "")[:200]
                if self._is_relevant(t, d):
                    remoteok_raw.append({
                        "title": t, "company": c, "location": "Remote",
                        "url": item.get("url", ""), "source": "RemoteOK",
                        "match_score": self._score_job(t, d), "description": d
                    })
        except Exception:
            pass

        # 2. Remotive
        remotive_raw = self._search_remotive(keywords)

        # 3. We Work Remotely
        wwr_raw = self._search_weworkremotely("programming")

        # 4. DuckDuckGo
        ddg_raw = self._search_duckduckgo_jobs(keywords)

        # 5. LinkedIn via DuckDuckGo
        from utils.web_search import search_web
        linkedin_results = search_web(
            f'site:linkedin.com/jobs/view "{keywords}" remote intern', max_results=8
        )
        for r in linkedin_results:
            title = r.get("title", "").replace(" | LinkedIn", "").strip()
            snippet = r.get("snippet", "")
            url = r.get("url", "")
            if url and "linkedin.com" in url and self._is_relevant(title, snippet):
                company = title.split(" at ")[-1].strip() if " at " in title else "Unknown"
                title_clean = title.split(" at ")[0].strip() if " at " in title else title
                all_jobs.append({
                    "title": title_clean, "company": company,
                    "location": "Remote", "url": url, "source": "LinkedIn",
                    "match_score": self._score_job(title_clean, snippet),
                    "description": snippet[:200]
                })

        all_jobs += remoteok_raw + remotive_raw + wwr_raw + ddg_raw

        # Deduplicate + filter zero-score
        all_jobs = self._dedup(all_jobs)
        all_jobs = [j for j in all_jobs if j["match_score"] > 0]

        # Score the top 20 candidates using a SINGLE batched LLM call
        top_candidates = sorted(all_jobs, key=lambda x: x["match_score"], reverse=True)[:20]
        if top_candidates:
            batch_scores = self._score_job_llm_batch(top_candidates)
            for job, score in zip(top_candidates, batch_scores):
                job["match_score"] = score

        # Re-sort based on LLM scores
        all_jobs = sorted(top_candidates, key=lambda x: x["match_score"], reverse=True)

        # Save top results to DB
        for j in all_jobs[:limit]:
            insert_job(j)

        if not all_jobs:
            return (
                f"🔍 No relevant jobs found for **{keywords}** right now.\n\n"
                "Try: 'find python ml intern' or 'find LLM jobs remote'"
            )

        top = all_jobs[:limit]
        return self._format_jobs(top, f"All Sources ({len(all_jobs)} total found)")

    # ─── Formatting ───────────────────────────────────────────────────

    def _format_jobs(self, jobs: list, source_label: str) -> str:
        result = f"🔍 **{len(jobs)} Jobs Found — {source_label}:**\n\n"
        source_emoji = {"RemoteOK": "🟢", "LinkedIn": "💼", "Remotive": "🔵",
                        "We Work Remotely": "🏠", "Web": "🌐"}

        for i, job in enumerate(jobs, 1):
            emoji = source_emoji.get(job.get("source", ""), "📌")
            score = job.get("match_score", 0)
            stars = "⭐" * min(score // 2, 5)

            result += f"**{i}. {job['title']}**\n"
            result += f"   🏢 {job['company']} {emoji} {job['source']}\n"
            result += f"   📍 {job.get('location', 'Remote')} | {stars} Match: {score}/10\n"
            if job.get("description"):
                result += f"   _{job['description'][:120]}..._\n"
            result += f"   🔗 {job['url']}\n\n"

        result += "\n💡 Say **'write cover letter for [title] at [company]'** to apply to any of these!"
        return result

    # ─── Cover Letter ─────────────────────────────────────────────────

    def generate_cover_letter(self, title: str, company: str, description: str = "") -> str:
        task = f"""Write a highly tailored cover letter for Aaqil for this role:

Role: {title}
Company: {company}
Job Description: {description if description else 'AI/ML/Python internship'}

His Profile:
{AAQIL_PROFILE}

Write 3 focused paragraphs:
1. Hook — specific to {company}'s work, show you know them
2. Why Aaqil — most relevant project + achievement (published paper, LLM agent system)
3. Ask — enthusiasm + next step

Tone: confident, genuine, technical. NOT generic. NOT "I am writing to express interest"."""

        draft = self.run(task)

        # Use the shared critic agent via consultation (no new instance per call)
        try:
            improved = self.consult("critic", f"improve cover_letter: {draft}")
            if improved and len(improved) > 100 and "not found" not in improved.lower():
                draft = improved
        except Exception:
            pass

        return f"📝 **Cover Letter — {title} at {company}**\n\n{draft}"

    # ─── Dashboard ────────────────────────────────────────────────────

    def get_dashboard(self) -> str:
        stats = get_stats()
        jobs = get_all_jobs()

        result = "📊 **Job Application Dashboard**\n\n"
        result += f"📋 Total tracked: {len(jobs)}\n"

        emoji_map = {"found": "🔍", "applied": "✅", "rejected": "❌",
                     "interview": "🎯", "offer": "🏆"}
        for status, count in stats.items():
            result += f"{emoji_map.get(status, '📌')} {status.capitalize()}: {count}\n"

        top_matches = [j for j in jobs if j["status"] == "found"]
        top_matches = sorted(top_matches, key=lambda x: x.get("match_score", 0), reverse=True)[:5]

        if top_matches:
            result += "\n🔥 **Top Matches (Not Applied Yet):**\n"
            for j in top_matches:
                result += f"\n• **{j['title']}** at {j['company']}\n"
                result += f"  ⭐ {j['match_score']}/10 | {j['source']} | 🔗 {j['url']}\n"

        result += "\n💡 Say 'apply [URL]' to mark as applied, or 'write cover letter for [role] at [company]'"
        return result

    # ─── Tracking ─────────────────────────────────────────────────────

    def mark_applied(self, url: str = "", company: str = "") -> str:
        if url:
            update_status(url, "applied")
            return f"✅ Marked as applied: {url}"
        return "❌ Please provide the job URL to mark as applied."

    def show_all_tracked(self) -> str:
        jobs = get_all_jobs()
        if not jobs:
            return "No jobs tracked yet. Try: 'find machine learning internships'"
        result = f"📋 **All Tracked Jobs ({len(jobs)}):**\n\n"
        for j in jobs[:15]:
            emoji = {"found": "🔍", "applied": "✅", "rejected": "❌",
                     "interview": "🎯"}.get(j["status"], "📌")
            result += f"{emoji} **{j['title']}** — {j['company']}\n"
            result += f"   Score: {j['match_score']}/10 | Status: {j['status'].upper()}\n"
            result += f"   🔗 {j['url']}\n\n"
        return result

    # ─── Handle (Jarvis dispatch) ─────────────────────────────────────

    def handle(self, task: str) -> str:
        return self.think_and_act(task)