/**
 * frontend/src/api/client.ts
 * Typed HTTP client wrapping Orchestrator v2 endpoints.
 */

import {
  AgentResult,
  ApprovalRecord,
  ClarificationNeeded,
  EvalResult,
  EvalSummary,
  PipelineRunStatus,
  RouterResult,
} from '../types/api';

const API_BASE = import.meta.env?.VITE_API_BASE_URL || '';

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path}`;
  const headers = new Headers(options.headers || {});

  if (!headers.has('Content-Type') && options.body && typeof options.body === 'string') {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(url, { ...options, headers });

  if (response.status === 422) {
    // ClarificationNeeded payload
    const data = await response.json();
    throw { isClarification: true, ...data };
  }

  if (!response.ok) {
    let errDetail = response.statusText;
    try {
      const errJson = await response.json();
      errDetail = errJson.detail || errJson.error || JSON.stringify(errJson);
    } catch {}
    throw new Error(`API Error (${response.status}): ${errDetail}`);
  }

  return response.json();
}

export const api = {
  // ── Dispatch & Route ──
  route: (command: string) =>
    request<RouterResult>('/route', {
      method: 'POST',
      body: JSON.stringify({ command }),
    }),

  dispatch: (command: string, context: Record<string, any> = {}) =>
    request<AgentResult>('/dispatch', {
      method: 'POST',
      body: JSON.stringify({ command, context }),
    }),

  // ── Pipelines ──
  startPipeline: (pipelineName: string, command: string) =>
    request<{ run_id: string; pipeline_name: string; status: string }>(`/pipeline/${pipelineName}`, {
      method: 'POST',
      body: JSON.stringify({ command }),
    }),

  getRun: (runId: string) =>
    request<PipelineRunStatus>(`/runs/${runId}`),

  // ── Approvals ──
  getApprovals: (status?: string) => {
    const q = status ? `?status=${encodeURIComponent(status)}` : '';
    return request<{ items: ApprovalRecord[]; total: number }>(`/approvals${q}`);
  },

  approve: (approvalId: string) =>
    request<{ id: string; status: string }>(`/approvals/${approvalId}/approve`, {
      method: 'POST',
    }),

  reject: (approvalId: string) =>
    request<{ id: string; status: string }>(`/approvals/${approvalId}/reject`, {
      method: 'POST',
    }),

  execute: (approvalId: string) =>
    request<{ id: string; status: string }>(`/approvals/${approvalId}/execute`, {
      method: 'POST',
    }),

  // ── Router Eval ──
  getLatestEval: () =>
    request<EvalResult>('/router/eval'),

  getEvalHistory: () =>
    request<{ runs: EvalSummary[]; total: number }>('/router/evals'),

  triggerEval: () =>
    request<{ eval_id: string; status: string; accuracy?: number }>('/router/eval', {
      method: 'POST',
    }),
};
