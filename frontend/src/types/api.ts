/**
 * frontend/src/types/api.ts
 * Type definitions matching Orchestrator v2 backend models.
 */

export interface RouterResult {
  agent: string;
  confidence: number;
  reasoning: string;
}

export interface ClarificationNeeded {
  candidates: string[];
  reasoning: string;
}

export interface AgentResult {
  agent: string;
  output: string;
  action_type?: string | null;
  metadata: Record<string, any>;
}

export interface ApprovalRecord {
  id: string;
  action_type: string;
  payload_json: string;
  status: 'pending' | 'approved' | 'rejected' | 'executing' | 'executed' | 'expired';
  created_at: string;
  expires_at?: string | null;
  executed_at?: string | null;
}

export interface PipelineStepRecord {
  run_id: string;
  step_number: number;
  agent_name: string;
  input_json: string;
  output_json: string;
  latency_ms: number;
  success: boolean;
  timestamp: string;
  error?: string | null;
}

export interface PipelineRunStatus {
  run_id: string;
  pipeline_name: string;
  status: 'running' | 'completed' | 'failed';
  steps: PipelineStepRecord[];
  started_at: string;
  completed_at?: string | null;
  error?: string | null;
}

export interface EvalPerAgentMetrics {
  tp: number;
  fp: number;
  fn: number;
  precision: number;
  recall: number;
  f1: number;
}

export interface EvalMetrics {
  accuracy: number;
  correct: number;
  total: number;
  per_agent: Record<string, EvalPerAgentMetrics>;
  confusion_matrix: Record<string, Record<string, number>>;
}

export interface EvalResult {
  run_at: string;
  dataset: string;
  prompt_hash: string;
  metrics: EvalMetrics;
  results: Array<{
    id: number;
    command: string;
    expected: string;
    predicted: string | null;
    confidence: number;
    correct: boolean;
    clarification: boolean;
    ambiguous?: boolean;
  }>;
  stale?: boolean;
}

export interface EvalSummary {
  run_at: string;
  accuracy: number;
  correct: number;
  total: number;
  prompt_hash: string;
  stale: boolean;
  results_file?: string | null;
}
