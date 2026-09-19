# Changelog

All notable changes to the Orchestrator Agent service will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0-alpha] - 2026-09-19

### Phase 0 — Safety Baseline & Environment Sanitization
- Isolated `.env` secrets and provided documented [`.env.example`](.env.example) with required/optional parameter flags.
- Removed legacy bypass tools and insecure direct-execution utilities.
- Established `.gitignore` rules for WAL files, SQLite artifacts, and planning documentation.

### Phase 1 — FastAPI Core Architecture & Persistence
- Implemented modular FastAPI core service in [`orchestrator_core/`](orchestrator_core/).
- Added lazy, cached settings configuration with `pydantic-settings` in [`config.py`](orchestrator_core/config.py).
- Implemented declarative SQLite migrations with Write-Ahead Logging (WAL) and foreign key enforcement in [`storage/db.py`](orchestrator_core/storage/db.py).
- Isolated ChromaDB client within [`storage/chroma_client.py`](orchestrator_core/storage/chroma_client.py) avoiding global import side-effects.
- Added public, zero-dependency `GET /health` endpoint.

### Phase 2 — LLM Router & Accuracy Evaluation Harness
- Created LLM router in [`core/router.py`](orchestrator_core/core/router.py) mapping commands to 4 core agents (`career_agent`, `research_agent`, `growth_content_agent`, `critic_agent`).
- Built offline evaluation dataset with 27 curated commands in [`eval/fixed_set.json`](eval/fixed_set.json).
- Implemented evaluation harness [`eval/run_eval.py`](eval/run_eval.py) calculating overall accuracy, per-agent precision, recall, F1, and confusion matrices.
- Added [`eval/render_confusion_matrix.py`](eval/render_confusion_matrix.py) for rendering formatted markdown matrix tables.
- Added router evaluation API endpoints `GET /router/eval`, `GET /router/evals`, and `POST /router/eval`.

### Phase 3 — Unbypassable Approval Gate
- Designed state machine approval gate in [`core/approval_gate.py`](orchestrator_core/core/approval_gate.py) (`pending` → `approved` → `executing` → `executed`).
- Enforced strict zero-payload security contract on `execute_approved(approval_id, db)` preventing payload substitution attacks.
- Added compare-and-set (CAS) update concurrency locks ensuring exactly one thread claims execution.
- Added crash recovery guarantees: failed executions remain in `executing` status for auditable reconciliation without silent revert.
- Added pipeline execution engine in [`core/pipeline_engine.py`](orchestrator_core/core/pipeline_engine.py) recording every step to `pipeline_steps` with latency and trace data.

### Phase 4 — Testing Suite & Concurrency Verification
- Created pytest test suite in [`tests/`](tests/) totaling 34 unit and integration tests:
  - Approval state machine transitions and expiry handling.
  - Concurrent CAS execution races and replay protection.
  - Router classification boundaries, low-confidence clarification fallbacks, and prompt hashing.
  - Circuit breaker counting, fail-fast `OPEN` states, cooldown timers, and `HALF_OPEN` trial recovery.
  - Static AST inspection verifying zero external side-effect SDK imports outside `approval_gate.py`.
- Configured [`pytest.ini`](pytest.ini) with `real_llm` marker to run completely offline by default.

### Phase 5 — Quarantine, Authentication, Containerization & CI
- Quarantined 6 legacy v1 modules into [`experimental/`](experimental/) with [`NOT_SUPPORTED.md`](experimental/) boundary notes.
- Implemented HTTP Bearer token authentication in [`dependencies.py`](orchestrator_core/dependencies.py) protecting all non-health routes.
- Engineered multi-stage [`Dockerfile`](Dockerfile) running under non-root `appuser` with built-in healthchecks.
- Created GitHub Actions CI workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) enforcing ruff linting, zero experimental imports, zero SDK leakage, and full test execution.

### Phase 6 — Documentation & Release Polish
- Rewrote [`README.md`](README.md) with comprehensive problem statements, architectural diagrams, confusion matrix benchmarks, and setup guides.
- Published updated [`BASELINE.md`](BASELINE.md) documenting verification telemetry.
