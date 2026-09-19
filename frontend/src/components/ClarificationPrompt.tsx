/**
 * frontend/src/components/ClarificationPrompt.tsx
 * Low-confidence router fallback card with state-warning border/accent.
 */

import React from 'react';
import { AlertTriangle, ArrowRight } from 'lucide-react';
import { ClarificationNeeded } from '../types/api';

interface ClarificationPromptProps {
  data: ClarificationNeeded;
  onSelectCandidate?: (candidate: string) => void;
}

export const ClarificationPrompt: React.FC<ClarificationPromptProps> = ({
  data,
  onSelectCandidate,
}) => {
  return (
    <div className="bg-surface-primary rounded-2xl border-2 border-state-warning p-6 shadow-xl text-text-primary">
      <div className="flex items-start gap-4">
        <div className="p-3 bg-state-warning/20 rounded-xl text-state-warning flex-shrink-0">
          <AlertTriangle className="w-6 h-6 text-[#FFB162]" />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h3 className="text-lg font-bold text-[#EEE9DF]">Routing Clarification Needed</h3>
            <span className="text-xs px-2.5 py-0.5 rounded-pill bg-state-warning/30 text-[#FFB162] font-semibold uppercase tracking-wider">
              Low Confidence (&lt; 60%)
            </span>
          </div>

          <p className="text-sm text-text-muted mt-2 leading-relaxed">
            {data.reasoning ||
              'The command is ambiguous across multiple specialist agents. Please select the intended target agent:'}
          </p>

          <div className="mt-4 flex flex-wrap gap-2.5">
            {data.candidates.map((agent) => (
              <button
                key={agent}
                onClick={() => onSelectCandidate?.(agent)}
                className="flex items-center gap-2 px-4 py-2 bg-canvas-dark hover:bg-canvas-dark/80 border border-surface-muted/30 hover:border-accent-primary text-sm font-medium rounded-xl text-text-primary transition-all group shadow-sm"
              >
                <span>{agent}</span>
                <ArrowRight className="w-4 h-4 text-text-muted group-hover:text-accent-primary transition-colors" />
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
