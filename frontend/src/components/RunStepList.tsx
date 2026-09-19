/**
 * frontend/src/components/RunStepList.tsx
 * Light-panel-on-dark-frame step trace list with tabular latency figures and step badges.
 */

import React from 'react';
import { PipelineStepRecord } from '../types/api';
import { CheckCircle2, XCircle, Clock } from 'lucide-react';

interface RunStepListProps {
  steps: PipelineStepRecord[];
}

export const RunStepList: React.FC<RunStepListProps> = ({ steps }) => {
  if (!steps || steps.length === 0) {
    return (
      <div className="bg-canvas-light text-text-onLight rounded-2xl p-8 text-center shadow-lg">
        <p className="text-sm font-medium opacity-70">No execution steps recorded yet.</p>
      </div>
    );
  }

  return (
    <div className="bg-canvas-light text-text-onLight rounded-2xl p-6 shadow-2xl space-y-4">
      <div className="flex items-center justify-between pb-3 border-b border-surface-muted/40">
        <h3 className="font-bold text-base tracking-tight">Step Execution Trace</h3>
        <span className="text-xs font-semibold px-3 py-1 rounded-pill bg-surface-primary text-text-primary">
          {steps.length} {steps.length === 1 ? 'Step' : 'Steps'} Completed
        </span>
      </div>

      <div className="space-y-3">
        {steps.map((step) => {
          let parsedOutput = step.output_json;
          try {
            const obj = JSON.parse(step.output_json);
            parsedOutput = obj.output || JSON.stringify(obj, null, 2);
          } catch {}

          return (
            <div
              key={step.step_number}
              className="bg-white/80 rounded-xl p-4 border border-surface-muted/30 shadow-sm flex flex-col gap-2.5 transition-all hover:bg-white"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <span className="w-6 h-6 rounded-full bg-surface-primary text-text-primary font-bold text-xs flex items-center justify-center">
                    {step.step_number}
                  </span>
                  <span className="font-bold text-sm text-surface-primary">{step.agent_name}</span>
                </div>

                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-1 text-xs font-mono tabular-nums text-surface-primary/70">
                    <Clock className="w-3.5 h-3.5" />
                    {step.latency_ms} ms
                  </span>

                  {step.success ? (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-pill bg-state-success text-white text-xs font-semibold">
                      <CheckCircle2 className="w-3 h-3" />
                      SUCCESS
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-pill bg-state-danger text-white text-xs font-semibold">
                      <XCircle className="w-3 h-3" />
                      FAILED
                    </span>
                  )}
                </div>
              </div>

              {/* Output Content */}
              <div className="bg-surface-primary/5 rounded-lg p-3 text-xs font-mono text-surface-primary/90 whitespace-pre-wrap max-h-60 overflow-y-auto border border-surface-muted/20">
                {parsedOutput}
              </div>

              {step.error && (
                <div className="text-xs text-state-danger font-semibold bg-state-danger/10 p-2 rounded border border-state-danger/20">
                  Error: {step.error}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
