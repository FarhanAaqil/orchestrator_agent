# Aaqil - Personal AI Chief of Staff

> **Status (2026-09-13):** Active v2 rewrite in progress.
> The current codebase is the original v1 implementation. The v2 refactor is being
> built in `orchestrator_core/` as a standalone FastAPI service with a measured router,
> an unbypassable approval gate, a full test suite, and CI. This README will be
> rewritten in Phase 5 once every claim in it can be backed by a passing test.
> See `New plan/01-PRD.md` and `BASELINE.md` for the current rewrite scope and status.

Aaqil is a Python-based multi-agent assistant that routes natural-language commands to specialized agents for career planning, job search, research writing, content creation, GitHub support, email drafting, daily briefings, and project tracking.

The project uses a Streamlit chat interface, Groq-hosted LLM calls, ChromaDB memory, SQLite persistence, browser automation, web search, ArXiv search, voice input/output, and an APScheduler background worker.

## What It Does

- Routes user requests to the right specialist agent through an LLM router.
- Runs multi-step pipelines for job applications, content publishing, and research submissions.
- Keeps vector memory in ChromaDB so agents can recall previous outputs.
- Tracks jobs, projects, tasks, goals, skills, certificates, papers, content, and emails in SQLite.
- Starts a background scheduler for briefings, job search, GitHub checks, AI news, weekly reports, and reminders.
- Provides a Streamlit dashboard with chat, quick actions, approvals, notifications, and optional voice response.

## Main Components

| Area | Files | Purpose |
| --- | --- | --- |
| Streamlit UI | `dashboard/app.py` | Chat interface, quick actions, approvals tab, notification display, voice controls |
| Orchestrator | `orchestrator/master.py`, `orchestrator/router.py`, `orchestrator/pipeline.py` | Agent initialization, request routing, approval queue, multi-agent workflows |
| Agents | `agents/*.py` | Specialist agents for GitHub, LinkedIn, jobs, projects, career, content, research, email, briefings, and critique |
| Memory | `memory/chroma_store.py` | Persistent ChromaDB collections for agent memory |
| Database | `database/tracker.py` | SQLite schema and helper functions |
| Scheduler | `scheduler/background.py` | APScheduler jobs and in-app notifications |
| Utilities | `utils/web_search.py` | DuckDuckGo web/news search, ArXiv search, page fetching |
| Voice | `voice/voice_handler.py` | Speech recognition and text-to-speech |
| Config | `config.py` | Environment loading, model name, Chroma path, agent descriptions |

## Agents

| Agent | Module | Capabilities |
| --- | --- | --- |
| Orchestrator | `orchestrator/master.py` | Stores incoming tasks, triggers pipelines, routes normal commands, manages approvals |
| GitHub Agent | `agents/github_agent.py` | Lists repos, generates READMEs, creates commit messages, summarizes GitHub profile |
| LinkedIn Agent | `agents/linkedin_agent.py` | Scrapes LinkedIn job listings, drafts connection requests, outreach, follow-ups, and job analyses |
| Job Agent | `agents/job_agent.py` | Scrapes Internshala and Wellfound, filters/ranks roles, stores matches, drafts cover letters |
| Project Manager Agent | `agents/project_manager_agent.py` | Tracks projects, tasks, goals, sprint plans, weekly reports, and next-action suggestions |
| Career Agent | `agents/career_agent.py` | Tracks skills/certificates/milestones, tailors resumes, analyzes skill gaps, prepares interviews |
| Growth Agent | `agents/growth_agent.py` | Generates LinkedIn posts, Twitter/X threads, Hashnode/Dev.to blogs, devlogs, SEO metadata, content calendars |
| Research Agent | `agents/research_agent.py` | Searches ArXiv, drafts long-form research papers, finds journals, checks predatory journals, drafts submission material |
| Email Agent | `agents/email_agent.py` | Drafts recruiter, application, follow-up, and publisher emails; sends approved email through Gmail SMTP |
| Briefing Agent | `agents/briefing_agent.py` | Builds morning briefings, quick status reports, AI news summaries, and GitHub activity summaries |
| Critic Agent | `agents/critic_agent.py` | Silently scores and improves emails, cover letters, posts, papers, and job matches |

## Pipelines

Pipelines are handled by `orchestrator/pipeline.py` and always queue sensitive actions for approval before sending email or publishing content.

### Apply Pipeline

```text
apply pipeline <company>, <role>, <job description>, <recruiter email>
```

Flow:

1. Searches the web for company context.
2. Runs skill-gap analysis when a job description is provided.
3. Generates a tailored cover letter.
4. Drafts an application email.
5. Runs the critic pass.
6. Queues the email for approval.

### Publish Pipeline

```text
publish pipeline <project>, <details>
```

Flow:

1. Generates a blog post.
2. Generates a LinkedIn post.
3. Generates a Twitter/X thread.
4. Runs critic improvements where configured.
5. Queues content for approval.

### Research Pipeline

```text
research pipeline <project>, <description>, <target journal>
```

Flow:

1. Searches ArXiv and web sources for related work.
2. Generates a structured IEEE-style paper draft.
3. Recommends journals and conferences.
4. Drafts a submission email if a target journal is provided.
5. Queues submission email for approval.

## Background Schedule

The scheduler starts when `orchestrator.master` is imported by the Streamlit app.

| Time | Job |
| --- | --- |
| 8:00 AM | Generate morning briefing |
| 10:00 AM | Search Internshala for ML and AI internships |
| 6:00 PM | Check GitHub activity |
| Every 4 hours | Fetch AI/ML news |
| Sunday 9:00 PM | Generate weekly reflection/report |
| 9:00 AM and 3:00 PM | Remind about high-priority tasks |

Notifications are stored in memory for the current running process and shown in the Streamlit UI.

## Data Storage

| Path | Purpose |
| --- | --- |
| `aaqil.db` | Main SQLite database used by `database/tracker.py` |
| `chroma_db/` | Persistent ChromaDB vector memory |
| `.env` | Local secrets and API credentials |
| `__pycache__/` | Python runtime cache files |

The repo currently contains runtime data files. Treat `.env`, database files, and `chroma_db/` as local/private state if you publish or share this project.

## Setup

Run these commands from the project root.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

On macOS/Linux, activate the virtual environment with:

```bash
source .venv/bin/activate
```

Voice features use `SpeechRecognition`, `pyttsx3`, and `pyaudio`. If microphone or TTS setup fails, the rest of the app can still run without voice.

## Environment Variables

Create a `.env` file in the project root. There is no `.env.example` file in the current repo, so use this as the template:

```env
GROQ_API_KEY=

GITHUB_TOKEN=
LINKEDIN_EMAIL=
LINKEDIN_PASSWORD=
HASHNODE_TOKEN=
HASHNODE_PUBLICATION_ID=
DEVTO_API_KEY=
EMAIL_ADDRESS=
EMAIL_APP_PASSWORD=
```

Required:

- `GROQ_API_KEY` for LLM routing and agent responses.

Optional:

- `GITHUB_TOKEN` for GitHub profile/repo features.
- `LINKEDIN_EMAIL` and `LINKEDIN_PASSWORD` for LinkedIn-related automation if login support is extended.
- `HASHNODE_TOKEN` and `HASHNODE_PUBLICATION_ID` for Hashnode publishing.
- `DEVTO_API_KEY` for Dev.to publishing.
- `EMAIL_ADDRESS` and `EMAIL_APP_PASSWORD` for Gmail SMTP sending.

## Run The App

```bash
streamlit run dashboard/app.py
```

Then open the local Streamlit URL shown in the terminal.

## Example Commands

### General

```text
generate morning briefing
quick status
show approvals
approve 1
reject 1
```

### Jobs And Career

```text
find machine learning internships on Internshala
find python internships on Internshala
job dashboard
cover letter for AI/ML Intern, Sarvam AI, LangChain and Python role
tailor resume for <job description>
skill gap for <job description>
interview prep for Sarvam AI, Python AI Engineer, <job description>
career dashboard
show skills
show certificates
```

### Projects And Tasks

```text
add project Aaqil, multi-agent chief of staff, 2026-06-15
show projects
add task Aaqil, polish Streamlit approvals tab, high, 2026-05-30
show tasks
complete task 1
add goal publish 3 posts, 3, weekly
show goals
weekly report
plan week
what should I work on next
```

### Content

```text
generate linkedin post for Aaqil, built a multi-agent assistant
generate twitter thread for Aaqil, architecture and lessons learned
generate blog post for Aaqil, agents plus memory plus scheduler
generate devlog 9, finished approval pipeline, scheduler bugs
content calendar 2
content dashboard
publish hashnode Building Aaqil
publish devto Building Aaqil
```

### Research

```text
write paper for Self-Improving Code Agent, LLM agent with critique loop and vector memory
find journals for LLM agents
recommend journals for AI agent systems
check journal International Journal of Example
submission email for Self-Improving Code Agent, IEEE Access
research dashboard
show papers
```

### GitHub, LinkedIn, And Email

```text
show github profile summary
list github repos
generate commit message for fixed scheduler notification bug
draft connection for Jane Doe, AI Recruiter, Example Labs
draft outreach to Jane Doe, Recruiter, Example Labs, AI/ML Intern
draft recruiter email to Jane Doe, Example Labs, AI/ML Intern, jane@example.com
draft application email for Example Labs, AI/ML Intern, LangChain agent role, jobs@example.com
email dashboard
send email 1, jobs@example.com
```

## Project Structure

```text
.
|-- agents/
|   |-- base_agent.py
|   |-- briefing_agent.py
|   |-- career_agent.py
|   |-- critic_agent.py
|   |-- email_agent.py
|   |-- github_agent.py
|   |-- growth_agent.py
|   |-- job_agent.py
|   |-- linkedin_agent.py
|   |-- project_manager_agent.py
|   `-- research_agent.py
|-- dashboard/
|   `-- app.py
|-- database/
|   |-- tracker.py
|   `-- tracker.db
|-- memory/
|   `-- chroma_store.py
|-- orchestrator/
|   |-- master.py
|   |-- pipeline.py
|   `-- router.py
|-- scheduler/
|   `-- background.py
|-- utils/
|   `-- web_search.py
|-- voice/
|   |-- __init__.py
|   `-- voice_handler.py
|-- aaqil.db
|-- chroma_db/
|-- config.py
|-- requirements.txt
`-- README.md
```

## Notes And Limitations

- The app depends on live APIs and websites. Web scraping can break if LinkedIn, Internshala, or Wellfound change their markup.
- Sending email and publishing posts are guarded by the approval queue in pipeline flows, but direct agent commands such as `send email` can send through configured SMTP credentials.
- `database/tracker.py` defines `DB_PATH = "./aaqil.db"`, so run commands from the project root unless you change the database path.
- Some generated research/content claims still need human review before external submission or publication.
- The current repo has no automated test suite.

## Tech Stack

| Layer | Tooling |
| --- | --- |
| LLM | Groq Python SDK, `llama-3.3-70b-versatile` |
| UI | Streamlit |
| Memory | ChromaDB |
| Database | SQLite |
| Scheduling | APScheduler |
| Browser automation | Playwright, playwright-stealth |
| Search | DuckDuckGo Search, ArXiv |
| GitHub | PyGithub |
| Voice | SpeechRecognition, pyttsx3, PyAudio |
| Publishing/email | Hashnode GraphQL API, Dev.to API, Gmail SMTP |

## Author

Farhan Aaqil  
B.Tech AI/ML 

- GitHub: <https://github.com/FarhanAaqil>
- LinkedIn: <https://linkedin.com/in/farhan-aaqil-4730432bb>
