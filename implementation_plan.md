# Implementation Plan: Trust Scores + Privacy Agent

**Project:** Aaqil AI — Multi-Agent Orchestrator  
**Total Estimated Time:** 4–5 weeks (working part-time, ~2–3 hrs/day)

---

## Overview

Two high-impact features planned in sequence:

| Feature | What It Does | Why It Matters |
|---|---|---|
| **Agent Trust Score System** | Tracks per-agent, per-task-type historical success rates with temporal decay. Feeds scores back into the LLM router so low-trust agents are avoided. | Makes the existing system adaptive/learning, not just reactive. |
| **Personal Data Sovereignty Agent** | Audits your digital footprint, identifies data broker exposures, drafts GDPR/CCPA deletion requests autonomously, and tracks follow-up deadlines. | Genuinely novel agentic loop — no existing tool does scan + draft + send + track. |

---

## Phase 1 — Agent Trust Score System (Weeks 1–2)

### Architecture

```
Every _dispatch_to_agent() call
         │
         ▼
trust_registry.log_handoff(agent, task_type, success, latency_ms)
         │
         ▼
  SQLite: agent_handoff_log
  (agent_name, task_type, success, latency_ms, timestamp)
         │
         ▼
trust_registry.get_scores()
  → Weighted score with exponential decay:
    score = Σ (success_i × decay(t_i)) / total_weighted_events
    decay = e^(-λ × days_ago)   [λ = 0.1, so 7-day-old event = 0.5 weight]
         │
         ▼
route_task(user_input, context, trust_scores=...)
  → LLM prompt now includes:
    "Agent 'research' trust: 0.43 (task_type: web_scraping, 3 recent fails)
     Prefer alternative if available."
```

### Task Type Classification

The LLM router already classifies tasks. We extend it to also emit a `task_type` tag:

```python
# router.py output changes from:
{"agent": "research", "task": "find papers on LLMs"}

# to:
{"agent": "research", "task": "find papers on LLMs", "task_type": "research_lookup"}
```

Task types map to: `web_scraping`, `content_generation`, `data_retrieval`, `email_action`, `code_analysis`, `scheduling`, `general`

### Decay Formula

```
score(agent, task_type) = 
    Σ [outcome_i × e^(-0.1 × days_since_i)] 
    ─────────────────────────────────────────
    Σ [e^(-0.1 × days_since_i)]

Where outcome_i = 1 (success) or 0 (failure)
```

This means: a failure from 14 days ago weighs ~25% of today's failure.

---

### Files Changed / Created

#### [NEW] `orchestrator/trust_registry.py`
- `TrustRegistry` class replacing `HealthMonitor` (or extending it)
- `log_handoff(agent, task_type, success, latency_ms)`
- `get_score(agent, task_type)` → float 0.0–1.0
- `get_all_scores()` → dict keyed by `(agent, task_type)`
- `get_routing_hint(task_type)` → returns sorted agent list by trust score
- Persists to SQLite on every write; loads on startup

#### [MODIFY] `database/tracker.py`
Add new table + CRUD:
```sql
CREATE TABLE IF NOT EXISTS agent_handoff_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name  TEXT NOT NULL,
    task_type   TEXT NOT NULL,
    success     INTEGER NOT NULL,   -- 1 or 0
    latency_ms  INTEGER,
    timestamp   TEXT NOT NULL
);
```
Functions: `log_handoff()`, `get_handoff_history(agent, task_type, days=30)`

#### [MODIFY] `orchestrator/router.py`
- Extend prompt to also return `task_type` field
- Add `trust_scores` parameter → injected into system prompt as a routing hint block
- Change return type to include `task_type`

#### [MODIFY] `orchestrator/master.py`
- Import `TrustRegistry` instead of (or alongside) `HealthMonitor`
- In `_dispatch_to_agent()`: call `trust_registry.log_handoff()` after every success/failure
- In the LLM routing section: call `trust_registry.get_routing_hint(task_type)` and pass to `route_task()`

#### [MODIFY] `orchestrator/health_monitor.py`
- Keep for live session status (processing/idle/error dots in sidebar)
- Add `get_trust_summary()` method that pulls from `TrustRegistry` for display

#### [MODIFY] `dashboard/app.py`
- Replace raw `success_rate` % in sidebar with **Trust Score badge**
- Add a "🧠 Trust Scores" expandable section in the dashboard home
- Color coding: green ≥ 0.8, amber 0.5–0.8, red < 0.5

---

## Phase 2 — Personal Data Sovereignty Agent (Weeks 3–5)

### Architecture

```
User: "audit my privacy" / "send deletion request to LinkedIn"
         │
         ▼
master.py → route to "privacy" agent
         │
         ▼
PrivacyAgent.handle(task)
         │
    ┌────┴────────────────────────────────────────┐
    │                                              │
    ▼                                              ▼
scan_exposure()                        draft_deletion_request()
  → HaveIBeenPwned API                    → LLM-generated GDPR/CCPA email
  → LLM-generated site list               → Routed to EmailAgent for send
  → Stored in data_exposure table         → Deadline tracked (30-day GDPR)
    │                                              │
    ▼                                              ▼
exposure_report()                      track_deletion_status()
  → Timeline of exposures                → Scheduled follow-up reminders
  → Risk score per site                  → Status: pending/acknowledged/confirmed
```

### Data Flow

```
PrivacyAgent
    │
    ├── scan_exposure()
    │       └── HaveIBeenPwned API (email breaches)
    │       └── LLM generates "likely registered sites" from profile data
    │       └── INSERT INTO data_exposure (site, data_leaked, risk_level, found_at)
    │
    ├── draft_deletion_request(site)
    │       └── LLM generates jurisdiction-appropriate email
    │           (GDPR Art. 17 for EU, CCPA for CA, generic for others)
    │       └── Calls EmailAgent.handle("draft email to privacy@{site}.com")
    │       └── Queues for user approval via Pipeline._queue_approval()
    │       └── UPDATE data_exposure SET deletion_requested_at = now()
    │
    ├── check_deletion_status()
    │       └── Shows all pending/overdue requests
    │       └── Flags any that passed the 30-day GDPR window
    │
    └── exposure_dashboard()
            └── Returns markdown report of all exposures + statuses
```

---

### Files Changed / Created

#### [NEW] `agents/privacy_agent.py`
Full agent extending `BaseAgent`. Tools:
- `scan_exposure(email)` — HIBP + LLM site enumeration
- `draft_deletion_request(site, jurisdiction)` — generates deletion email
- `check_deletion_status()` — returns overdue/pending requests
- `exposure_dashboard()` — full privacy health report
- `calculate_risk_score()` — aggregates exposure severity

#### [NEW] `utils/hibp_client.py`
- `check_email_breaches(email)` — wraps HaveIBeenPwned API v3
- Returns list of breach objects: `{name, date, data_classes, is_sensitive}`
- Handles rate limiting (1.5s between calls per HIBP ToS)

> [!IMPORTANT]
> HIBP API requires a paid API key ($3.50/month) for automation. A free fallback (manual breach check + LLM enrichment) will be provided if the user doesn't have a key.

#### [MODIFY] `database/tracker.py`
Add new tables:

```sql
CREATE TABLE IF NOT EXISTS data_exposure (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    site_name               TEXT NOT NULL,
    site_category           TEXT,        -- social, job, shopping, etc.
    data_leaked             TEXT,        -- comma-sep: email, phone, password_hash
    risk_level              TEXT,        -- low / medium / high / critical
    source                  TEXT,        -- hibp / llm_inferred / manual
    found_at                TEXT,
    deletion_requested_at   TEXT,
    deletion_confirmed_at   TEXT,
    deletion_status         TEXT DEFAULT 'not_requested',
    notes                   TEXT
);

CREATE TABLE IF NOT EXISTS deletion_requests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    exposure_id     INTEGER,
    site_name       TEXT,
    email_sent_to   TEXT,
    subject         TEXT,
    body            TEXT,
    sent_at         TEXT,
    deadline_at     TEXT,   -- 30 days from sent_at for GDPR
    status          TEXT DEFAULT 'pending',
    response_notes  TEXT,
    FOREIGN KEY (exposure_id) REFERENCES data_exposure(id)
);
```

Functions: `add_exposure()`, `get_exposures()`, `update_deletion_status()`, `add_deletion_request()`, `get_overdue_deletions()`

#### [MODIFY] `orchestrator/master.py`
- Add `"privacy": PrivacyAgent` to `_agent_factory` and `AGENT_MAP`
- Add fast routes: `"audit privacy"`, `"privacy report"`, `"delete my data"`, `"check breaches"`
- Add `"privacy"` to `AGENTS` registry in `config.py`

#### [MODIFY] `config.py`
```python
AGENTS["privacy"] = "Manages your digital footprint, data deletion requests, and breach monitoring"
HIBP_API_KEY = os.getenv("HIBP_API_KEY", "")  # optional
```

#### [MODIFY] `dashboard/app.py`
- Add `🔒 Privacy` quick action button
- Add **Privacy Health Panel** to the home dashboard (3rd column or new row):
  - Exposure count by risk level
  - Pending deletion requests count
  - Days since last audit
  - Overdue GDPR requests alert
- Add `🔒 Privacy Agent` to agent icon map
- Add privacy-specific steps to `_is_long_operation()` / `_run_with_feedback()`

#### [MODIFY] `scheduler/background.py`
- Add recurring job: every 7 days, run `privacy_agent.check_deletion_status()` 
- Send notification if any GDPR deadline (30-day) is approaching or overdue

---

## Week-by-Week Timeline

```
Week 1 (Days 1–7)  ── Trust Score Foundation
  ├── Day 1–2: Add agent_handoff_log table to tracker.py
  │             Write log_handoff(), get_handoff_history() CRUD
  ├── Day 3–4: Build trust_registry.py
  │             TrustRegistry class, decay formula, get_score(), get_all_scores()
  └── Day 5–7: Integrate into master.py
                _dispatch_to_agent() logs every outcome
                Test: manually trigger failures, verify log fills correctly

Week 2 (Days 8–14) ── Router Intelligence
  ├── Day 8–9:  Extend router.py to emit task_type
  │             Modify route_task() prompt + return schema
  ├── Day 10–11: Pass trust scores into routing prompt
  │              Verify LLM actually changes routing on low scores
  └── Day 12–14: Update dashboard sidebar with trust score badges
                  Test full loop: failure → score drop → routing change

Week 3 (Days 15–21) ── Privacy Agent Core
  ├── Day 15–16: Add data_exposure + deletion_requests tables to tracker.py
  │              Write all CRUD functions
  ├── Day 17–18: Build utils/hibp_client.py
  │              Test HIBP API integration (or build fallback LLM path)
  └── Day 19–21: Build privacy_agent.py shell
                  scan_exposure(), exposure_dashboard() working
                  Register in master.py + config.py

Week 4 (Days 22–28) ── Deletion Workflow
  ├── Day 22–23: Build draft_deletion_request()
  │              LLM generates GDPR/CCPA email from site + jurisdiction
  ├── Day 24–25: Wire to email_agent + pipeline approval queue
  │              Test: "delete my data from LinkedIn" → approval → email drafted
  └── Day 26–28: Build check_deletion_status() + overdue alert
                  Wire scheduled job in background.py

Week 5 (Days 29–35) ── Dashboard + Polish
  ├── Day 29–30: Privacy Health Panel in dashboard home
  ├── Day 31–32: End-to-end integration testing
  │              Simulate: breach found → deletion requested → confirmed
  ├── Day 33–34: Edge cases: no HIBP key, unknown jurisdiction, email bounce
  └── Day 35:    Update README.md with both features documented
```

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| HIBP API key required/paid | Medium | Build LLM-only fallback path that generates likely exposure sites from profile |
| LLM generates legally incorrect GDPR text | Medium | Use templated base text + LLM for personalization only; add disclaimer |
| Trust score system needs data to be useful | High (early) | Pre-seed with neutral scores (0.75) on first run; scores improve over time |
| Router ignores trust hints (LLM non-determinism) | Low-Medium | Use structured prompt with explicit penalty language; add hard block for scores < 0.2 |
| Email sending capability | Depends on setup | Privacy agent drafts + queues via existing approval system; user manually sends initially |

---

## What You'll Have After Each Phase

**After Week 2:**
- Your router gets smarter every time an agent fails
- Dashboard shows trust score per agent (not just raw success %)
- System self-heals routing decisions based on historical behavior

**After Week 5:**
- Ask: `"audit my privacy"` → get a full breach + exposure report
- Ask: `"send deletion request to data broker X"` → LLM drafts a GDPR email, queues it for your approval
- Dashboard shows a privacy health score with pending/overdue requests highlighted
- Weekly automated check runs in the background

---

## Open Questions

> [!IMPORTANT]
> **Q1 — HIBP API Key:** Do you have or want to pay for a HaveIBeenPwned API key (~$3.50/month)? If not, I'll build a fully LLM-based exposure inference path instead (less precise but free).

> [!IMPORTANT]
> **Q2 — Email Sending:** Your `email_agent` currently *drafts* emails but doesn't send them (no SMTP configured). Should we wire up real email sending for deletion requests, or keep the approval-then-manual-send flow for now?

> [!NOTE]
> **Q3 — Trust Score Bootstrapping:** Should new agents start at a neutral 0.75 trust score (recommended) or at 1.0 (optimistic)? Lower starting scores make the system more cautious with untested agents.

> [!NOTE]
> **Q4 — Dashboard Layout:** The Privacy Health Panel will need space on the home dashboard. Should it replace the current 3-column layout with a 4th panel, or go below as its own row?
