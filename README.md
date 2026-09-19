# Orchestrator Agent

[![CI](https://github.com/FarhanAaqil/orchestrater_agent/actions/workflows/ci.yml/badge.svg)](https://github.com/FarhanAaqil/orchestrater_agent/actions/workflows/ci.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

A production-grade, audited multi-agent orchestration service built on FastAPI. Orchestrator Agent routes natural language instructions to specialized agents with a mathematically measured routing confidence harness, an unbypassable human-in-the-loop approval gate, fail-fast circuit breakers, and zero SDK leakage into untrusted modules.

---

## Visual Demo & Interface Screenshots

### 1. Conversational Chatbot & Dispatch Console
*ChatGPT-style conversational interface with live auto-scroll, prompt pill suggestions, auto-clearing input dock, and formatted markdown output.*

![Conversational Chatbot](docs/screenshots/chat_demo.png)

### 2. Human-in-the-Loop Approval Gate
*Immutable audit log and compare-and-set (CAS) state machine preventing unauthorized external actions and payload tampering.*

![Approval Gate](docs/screenshots/approvals_demo.png)

### 3. Multi-Agent Pipeline Execution
*Live telemetry tracing each pipeline step with latency, inputs, outputs, and deterministic error handling.*

![Pipeline Execution](docs/screenshots/pipelines_demo.png)

### 4. Router Benchmark & Confusion Matrix
*Empirical 27-point routing evaluation harness measuring intent boundary classification and prompt drift.*

![Router Benchmark](docs/screenshots/benchmark_demo.png)

### 5. Diagnostics & Circuit Breaker Monitor
*Real-time circuit breaker health metrics, consecutive failure counters, and manual administrative reset controls.*

![System Diagnostics](docs/screenshots/diagnostics_demo.png)

---

## The Problem

Most multi-agent frameworks suffer from three systemic architectural flaws:
1. **Unmeasured Routing**: Systems claim to route commands intelligently, but provide no empirical benchmark or confusion matrix proving classification accuracy or boundary discrimination.
2. **Bypassable Safety & Payload Substitution**: Human-in-the-loop gates frequently allow callers or compromised subagents to submit arbitrary payloads during the execution phase, bypassing what was originally reviewed.
3. **SDK & Side-Effect Leakage**: Third-party API and messaging SDKs (`smtplib`, publishing clients) are scattered across agent prompts and tool definitions, risking unauthorized external side-effects whenever an LLM hallucinates.

Orchestrator Agent solves these vulnerabilities at the API and database boundary.

---

## Core Guarantees & Architecture

```
                    [ Client / API Caller ]
                               │
               Bearer Token Authentication Barrier
                               │
                ┌──────────────┴──────────────┐
                ▼                             ▼
       /route & /dispatch            /pipeline/{name}
                │                             │
       LLM Router (Groq)              Pipeline Engine
       ┌─────────────────┐           ┌────────────────┐
       │ Circuit Breaker │           │ Step Execution │
       │ (Fail-Fast 30s) │           │ Audit Recorder │
       └─────────────────┘           └────────────────┘
                │                             │
    Confidence >= 0.60?                       ▼
    ┌───────────┴───────────┐         Queues Sensitive Action
    │ Yes                   │ No              │
    ▼                       ▼                 ▼
Agent Dispatch       Clarification   ┌───────────────────────┐
(Career/Research/    Needed (422)    │ Unbypassable Gate     │
 Growth/Critic)                      │ (approvals table)     │
                                     └───────────────────────┘
                                              │
                                    Human Review: approve()
                                              │
                                     execute_approved(id)
                                    [CAS Atomic Claim Lock]
                                              │
                                              ▼
                                    Isolated SDK Executor
                                    (_dispatch_action only)
```

### 1. Unbypassable Approval Gate
- **Strict Zero-Parameter Contract**: [`execute_approved(approval_id, db)`](file:///orchestrator_core/core/approval_gate.py) takes **no payload argument**. Callers cannot supply or substitute a payload at execution time; execution loads strictly from the canonical immutable database record.
- **Compare-And-Set (CAS) Concurrency**: Execution claims race on `UPDATE approvals SET status = 'executing' WHERE id = ? AND status = 'approved'`. Exactly one thread claims the execution; concurrent requests fail fast with `ApprovalClaimConflictError`.
- **Verified by Tests**: Verified by [`tests/test_approval_gate.py`](file:///tests/test_approval_gate.py) and [`tests/test_approval_concurrency.py`](file:///tests/test_approval_concurrency.py).

### 2. Strict SDK Isolation (Zero Leakage)
- External side-effect SDKs (`smtplib`, `hashnode`, `devto`) are forbidden across all agent definitions.
- All dispatching is isolated exclusively to `_dispatch_action()` in [`orchestrator_core/core/approval_gate.py`](file:///orchestrator_core/core/approval_gate.py).
- **Verified by Tests & CI**: Enforced at build time via AST inspection in [`tests/test_no_sdk_leakage.py`](file:///tests/test_no_sdk_leakage.py) and GitHub Actions CI grep checks.

### 3. Circuit-Breaker Protected Router
- LLM routing calls pass through a state-machine [`CircuitBreaker`](file:///orchestrator_core/core/circuit_breaker.py).
- Three consecutive external failures trip the breaker to `OPEN` for 30 seconds, preventing cascading timeout hangs and failing fast with `CircuitOpenError` (HTTP 503).
- Verified by [`tests/test_circuit_breaker.py`](file:///tests/test_circuit_breaker.py).

---

## Router Evaluation & Accuracy Benchmark

Router accuracy is continuously measured against a curated 27-command ground-truth dataset ([`eval/fixed_set.json`](file:///eval/fixed_set.json)) containing standard and ambiguous intent boundaries:

- **Overall Accuracy**: **88.9%** (24/27 commands cleanly classified)
- **Staleness Tracking**: Eval reports verify prompt hashing against deployed versions to prevent silent prompt drift.

### Confusion Matrix

```
              career  research    growth    critic      none
------------------------------------------------------------
    career         8         0         0         0         0
  research         0         6         0         1         0
    growth         0         0         6         0         1
    critic         0         0         0         4         1
```

### Per-Agent Metrics

| Agent | Precision | Recall | F1-Score | Scope |
|---|---|---|---|---|
| `career_agent` | 1.00 | 1.00 | 1.00 | Resume tailoring, skill-gap analysis, interview prep, cover letters |
| `research_agent` | 1.00 | 0.86 | 0.92 | ArXiv search, paper drafting, journal ranking, predatory check |
| `growth_content_agent` | 1.00 | 0.86 | 0.92 | Technical blog drafting, Twitter/X threads, devlogs, content calendars |
| `critic_agent` | 0.80 | 0.80 | 0.80 | Objective critique and scoring for resumes, papers, and content |

*Generated via [`eval/run_eval.py`](file:///eval/run_eval.py) and rendered with [`eval/render_confusion_matrix.py`](file:///eval/render_confusion_matrix.py).*

---

## Supported vs. Experimental Agents

To maintain zero hallucination and strict security guarantees, legacy unverified scraping modules have been moved to `experimental/` with explicit boundary disclaimers:

| Agent / Module | Status | Location | Justification / Boundary |
|---|---|---|---|
| **Career Agent** | Supported | [`orchestrator_core/agents/career_agent.py`](file:///orchestrator_core/agents/career_agent.py) | Fully deterministic LLM prompts; resume tailoring and gap analysis. |
| **Research Agent** | Supported | [`orchestrator_core/agents/research_agent.py`](file:///orchestrator_core/agents/research_agent.py) | ArXiv paper drafting and academic journal suggestions. |
| **Growth Agent** | Supported | [`orchestrator_core/agents/growth_content_agent.py`](file:///orchestrator_core/agents/growth_content_agent.py) | Tech writing; publish actions gated behind approvals. |
| **Critic Agent** | Supported | [`orchestrator_core/agents/critic_agent.py`](file:///orchestrator_core/agents/critic_agent.py) | Scoring and improvement feedback. |
| **Info Agent** | Supported | [`orchestrator_core/agents/info_agent.py`](file:///orchestrator_core/agents/info_agent.py) | Farhan Aaqil's portfolio, system architecture documentation, and general conversational talk. |
| **LinkedIn Agent** | Quarantined | [`experimental/linkedin_agent/`](file:///experimental/linkedin_agent/) | Dependent on fragile DOM scraping; prohibited in core API. |
| **Job Search Agent** | Quarantined | [`experimental/job_search_agent/`](file:///experimental/job_search_agent/) | Unofficial job board endpoints; violates stability guarantees. |
| **GitHub Agent** | Quarantined | [`experimental/github_agent/`](file:///experimental/github_agent/) | Direct repository mutations quarantined outside approval gate. |
| **Project Manager** | Quarantined | [`experimental/project_manager_agent/`](file:///experimental/project_manager_agent/) | Unverified state tracking; slated for future sprint. |
| **Voice I/O** | Quarantined | [`experimental/voice_io/`](file:///experimental/voice_io/) | PyAudio/hardware dependencies incompatible with lean containers. |

---

## Production Deployment: Load Balancer, Reverse Proxy & CDN

Orchestrator Agent includes production configurations for high-availability clustering, edge reverse proxying, rate-limiting, and CDN caching.

### 1. Nginx Reverse Proxy & Load Balancer
A production-grade [`nginx/nginx.conf`](nginx/nginx.conf) is provided with:
- **Load Balancing**: `least_conn` distribution across backend worker replicas.
- **Failover & Passive Health Probes**: `max_fails=3 fail_timeout=10s` with persistent TCP reuse (`keepalive 32`).
- **Rate-Limiting**: 30 req/s with burst control for `/route` and `/dispatch`.
- **Edge Microcaching**: 7-day cache with `stale-while-revalidate` for `/static/` assets.
- **Streaming Support**: `proxy_buffering off` for unbuffered LLM response delivery.

```bash
# Launch load-balanced multi-container stack with Nginx
docker compose up -d
```

### 2. Caddyfile (Automatic SSL & HTTP/3)
For zero-config deployments with automatic Let's Encrypt certificates and HTTP/3 support, use the included [`Caddyfile`](Caddyfile):
```bash
caddy run
```

### 3. Edge CDN Caching (Cloudflare / Fastly)
Comprehensive edge rules, origin cache-control policies, and Cloudflare configuration guidelines are documented in [`docs/CDN_AND_LOAD_BALANCER.md`](docs/CDN_AND_LOAD_BALANCER.md).

---

## Quickstart & Setup

### Prerequisites
- Python 3.11+
- Groq Cloud API Key ([console.groq.com](https://console.groq.com))

### 1. Installation
```bash
git clone https://github.com/FarhanAaqil/orchestrater_agent.git
cd orchestrater_agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env and supply your GROQ_API_KEY and optional AUTH_TOKEN
```

### 3. Run Service
```bash
uvicorn orchestrator_core.main:app --host 0.0.0.0 --port 8000 --reload
```
- **React 18 Control Plane Dashboard**: Open [http://localhost:8000/](http://localhost:8000/) (or `/ui`) in your browser to access the conversational chat console, pipelines, approvals queue, and router eval.
- **Interactive OpenAPI Documentation**: Available at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## API Reference

### Authentication
All routes except `GET /health` accept Bearer authentication if `AUTH_TOKEN` is configured:
```http
Authorization: Bearer <your_token>
```

### Key Endpoints

| Method | Path | Description | Request / Response Sample |
|---|---|---|---|
| `GET` | `/health` | System health check | `{"status": "ok", "version": "1.0.0"}` |
| `POST` | `/route` | Classify natural language command | Body: `{"command": "Tailor resume"}`<br>Returns: `RouterResult` or `ClarificationNeeded` (422) |
| `POST` | `/dispatch` | Classify and immediately execute | Body: `{"command": "..."}`<br>Returns: `AgentResult` |
| `POST` | `/pipeline/{name}` | Execute named multi-step pipeline | Supported: `apply`, `publish`, `research`<br>Returns: `{"run_id": "...", "status": "running"}` |
| `GET` | `/runs` | List execution runs with pagination | Query: `limit=20&offset=0`<br>Returns: `RunListResponse` |
| `GET` | `/runs/{run_id}` | Retrieve step audit log for pipeline run | Returns: Full step logs with latencies & outputs |
| `POST` | `/approvals` | Queue sensitive action for review | Body: `{"action_type": "...", "payload": {...}}` |
| `GET` | `/approvals` | List queued approvals with pagination | Query: `status=pending&limit=50`<br>Returns: `ApprovalListResponse` |
| `POST` | `/approvals/{id}/approve` | Grant approval | Transitions status: `pending` → `approved` |
| `POST` | `/approvals/{id}/reject` | Deny approval | Transitions status: `pending` → `rejected` |
| `POST` | `/approvals/{id}/execute` | Execute approved action | Zero payload parameter; executes stored record |
| `GET` | `/router/eval` | Latest eval benchmark & confusion matrix | Returns: Accuracy, per-agent metrics, prompt staleness |
| `GET` | `/router/evals` | Historical eval runs with pagination | Query: `limit=20&offset=0`<br>Returns: `EvalListResponse` |
| `POST` | `/router/eval` | Trigger on-demand eval run | Runs dataset and persists metrics |

---

## Running Verification & Tests

```bash
# Run full test suite (36 tests, unit + integration)
pytest -v

# Run linter
ruff check orchestrator_core/ tests/

# Run AST SDK isolation verification
pytest tests/test_no_sdk_leakage.py -v

# Run offline router evaluation dry-run
python eval/run_eval.py --dry-run
```

---

## Non-Goals & Architectural Limitations

- **Not an Autonomous Unsupervised Agent**: Orchestrator Agent strictly disallows self-directed external actions. Publishing and sending require verified human-in-the-loop approvals.
- **No Browser Scraping**: Web scraping of authenticated social platforms (LinkedIn, etc.) is outside core scope due to anti-bot volatility.
- **Decoupled Frontend**: Built on standalone React 18 and Tailwind with custom design tokens, served directly by FastAPI without Streamlit runtime dependencies.

