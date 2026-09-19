/**
 * frontend/src/pages/RunDetailPage.tsx
 * Full step execution audit trace with live conditional polling while running.
 */

import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { PipelineRunStatus } from '../types/api';
import { RunStepList } from '../components/RunStepList';
import { StatusPill } from '../components/StatusPill';
import { ArrowLeft, Clock, RefreshCw, AlertCircle } from 'lucide-react';

interface RunDetailPageProps {
  runId: string;
  onBack: () => void;
}

export const RunDetailPage: React.FC<RunDetailPageProps> = ({ runId, onBack }) => {
  const [run, setRun] = useState<PipelineRunStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRun = async () => {
    try {
      const data = await api.getRun(runId);
      setRun(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch pipeline run details.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchRun();

    // Conditional polling while status === 'running'
    const interval = setInterval(() => {
      if (run?.status === 'running' || !run) {
        fetchRun();
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [runId, run?.status]);

  if (isLoading && !run) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-text-muted gap-3">
        <span className="w-8 h-8 border-3 border-accent-primary border-t-transparent rounded-full animate-spin" />
        <span className="text-sm font-mono">Loading pipeline run trace...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <button
        onClick={onBack}
        className="flex items-center gap-2 text-xs font-semibold text-text-muted hover:text-accent-primary transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        <span>Back to Pipelines</span>
      </button>

      {error && (
        <div className="bg-state-danger/20 border border-state-danger/40 text-[#EEE9DF] rounded-2xl p-4 text-sm flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-state-danger" />
          <span>{error}</span>
        </div>
      )}

      {run && (
        <>
          {/* Run Header Banner */}
          <div className="bg-surface-primary rounded-2xl border border-surface-muted/20 p-6 shadow-xl space-y-3">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-xs font-mono text-text-muted">Run ID: {run.run_id}</span>
                <h2 className="text-xl font-black text-text-primary capitalize mt-0.5">
                  {run.pipeline_name} Pipeline Run
                </h2>
              </div>
              <StatusPill status={run.status} />
            </div>

            <div className="flex flex-wrap items-center gap-4 text-xs font-mono text-text-muted pt-2 border-t border-surface-muted/10">
              <span className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5" />
                Started: {new Date(run.started_at).toLocaleTimeString()}
              </span>
              {run.completed_at && (
                <span>Completed: {new Date(run.completed_at).toLocaleTimeString()}</span>
              )}
              {run.status === 'running' && (
                <span className="flex items-center gap-1 text-accent-primary animate-pulse">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  Tracing live steps...
                </span>
              )}
            </div>
          </div>

          {/* Inset Light Panel Step Trace */}
          <RunStepList steps={run.steps} />
        </>
      )}
    </div>
  );
};
