# OpenAPI Contract Specification — Orchestrator Agent v2

This document defines the canonical HTTP interface shapes, error envelopes, and lifecycle guarantees for `orchestrator_core`. All route handlers, test suites, and frontend clients must adhere strictly to this contract.

---

## 1. Authentication & Common Headers

All non-health endpoints require Bearer token authentication when configured:

```http
Authorization: Bearer <ORCHESTRATOR_AUTH_TOKEN>
Content-Type: application/json
Accept: application/json
```

---

## 2. Standard Error Envelope

Every `4xx` and `5xx` response returns a uniform JSON envelope:

```json
{
  "error": "ERROR_CODE",
  "detail": "Human-readable error description.",
  "request_id": "optional-uuid-string"
}
```

### Standard Error Codes:
- `APPROVAL_NOT_FOUND` (404)
- `APPROVAL_NOT_GRANTED` (409)
- `APPROVAL_EXPIRED` (410)
- `APPROVAL_ALREADY_EXECUTED` (409)
- `APPROVAL_CLAIM_CONFLICT` (409)
- `CIRCUIT_OPEN` (503)
- `SSRF_VIOLATION` (400)
- `CONFIDENCE_BELOW_THRESHOLD` (422)
- `INTERNAL_SERVER_ERROR` (500)

---

## 3. Endpoints

### 3.1 `GET /health`
System liveness and environment health check.

**Response `200 OK`**:
```json
{
  "status": "ok",
  "version": "2.0.0-alpha",
  "environment": "development"
}
```

---

### 3.2 `POST /route`
Classifies a user natural language command into the appropriate agent target.

**Request**:
```json
{
  "command": "Analyze this research paper: https://arxiv.org/abs/2301.00001"
}
```

**Response `200 OK` (High Confidence)**:
```json
{
  "agent": "research_agent",
  "confidence": 0.94,
  "reasoning": "Command requests parsing and analysis of an arXiv preprint."
}
```

**Response `200 OK` (Clarification Needed - confidence < 0.6)**:
```json
{
  "status": "needs_clarification",
  "candidates": ["research_agent", "growth_content_agent"],
  "reasoning": "Command mentions reviewing a paper for a LinkedIn post."
}
```

---

### 3.3 `POST /dispatch`
Classifies and executes the command against the resolved agent.

**Request**:
```json
{
  "command": "Draft a critique of the system architecture",
  "context": {}
}
```

**Response `200 OK`**:
```json
{
  "agent": "critic_agent",
  "output": "Critique analysis output...",
  "action_type": null,
  "approval_id": null,
  "metadata": {
    "tokens_used": 340
  }
}
```

---

### 3.4 Approvals Management

#### `GET /approvals`
List approval records with pagination.

**Query Parameters**:
- `status`: Optional filter (`pending`, `approved`, `rejected`, `executing`, `executed`, `expired`)
- `limit`: Integer (default 50, max 100)
- `offset`: Integer (default 0)

**Response `200 OK`**:
```json
{
  "items": [
    {
      "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "action_type": "publish_hashnode",
      "payload_json": "{\"title\": \"V2 Launch\", \"content\": \"...\"}",
      "status": "pending",
      "created_at": "2026-09-15T00:00:00Z",
      "expires_at": "2026-09-16T00:00:00Z",
      "executed_at": null
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

#### `POST /approvals/{id}/approve`
Marks a pending approval as approved.

**Response `200 OK`**:
```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "status": "approved",
  "action_type": "publish_hashnode"
}
```

#### `POST /approvals/{id}/reject`
Marks a pending approval as rejected.

**Response `200 OK`**:
```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "status": "rejected",
  "action_type": "publish_hashnode"
}
```

> **Security Rule**: The caller NEVER passes a payload to execution. The executor retrieves the canonical immutable payload stored in the database record.

---

### 3.5 Pipelines & Execution Traces

#### `POST /pipeline/{name}`
Execute a named pipeline (`apply`, `publish`, `research`).

**Request**:
```json
{
  "command": "Research diffusion models for robotics",
  "params": {}
}
```

**Response `202 Accepted`**:
```json
{
  "run_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
  "pipeline_name": "research",
  "status": "running",
  "steps": [],
  "started_at": "2026-09-15T00:01:00Z",
  "completed_at": null
}
```

#### `GET /runs/{run_id}`
Retrieve a pipeline execution run along with every recorded step.

**Response `200 OK`**:
```json
{
  "run_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
  "pipeline_name": "research",
  "status": "completed",
  "started_at": "2026-09-15T00:01:00Z",
  "completed_at": "2026-09-15T00:01:05Z",
  "steps": [
    {
      "run_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
      "step_number": 1,
      "agent_name": "research_agent",
      "input_json": "{\"query\": \"diffusion models for robotics\"}",
      "output_json": "{\"papers_found\": 3}",
      "latency_ms": 1420,
      "success": true,
      "timestamp": "2026-09-15T00:01:02Z",
      "error": null
    }
  ]
}
```

---

### 3.6 Router Evaluation

#### `GET /router/eval`
Returns the latest benchmark evaluation result from `eval/results/`.

**Response `200 OK`**:
```json
{
  "eval_id": "6fa85f64-5717-4562-b3fc-2c963f66afa6",
  "total_commands": 50,
  "accuracy": 0.88,
  "per_agent": {
    "career": {"precision": 0.90, "recall": 0.85},
    "research": {"precision": 0.85, "recall": 0.90},
    "growth_content": {"precision": 0.88, "recall": 0.82},
    "critic": {"precision": 0.91, "recall": 0.87}
  },
  "confusion_matrix": {},
  "model_name": "llama-3.3-70b-versatile",
  "dataset_version": "v1.0",
  "run_at": "2026-09-15T00:00:00Z",
  "is_stale": false
}
```

#### `GET /router/evals`
Returns a bounded historical index of past evaluation runs.

**Response `200 OK`**:
```json
{
  "items": [
    {
      "eval_id": "6fa85f64-5717-4562-b3fc-2c963f66afa6",
      "accuracy": 0.88,
      "model_name": "llama-3.3-70b-versatile",
      "run_at": "2026-09-15T00:00:00Z"
    }
  ],
  "total": 1
}
```
