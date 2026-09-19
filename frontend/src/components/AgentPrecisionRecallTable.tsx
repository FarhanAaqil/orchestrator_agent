/**
 * frontend/src/components/AgentPrecisionRecallTable.tsx
 * Tabular per-agent precision/recall metrics table on canvas-light surface.
 */

import React from 'react';
import { EvalPerAgentMetrics } from '../types/api';

interface AgentPrecisionRecallTableProps {
  perAgent: Record<string, EvalPerAgentMetrics>;
}

export const AgentPrecisionRecallTable: React.FC<AgentPrecisionRecallTableProps> = ({ perAgent }) => {
  if (!perAgent || Object.keys(perAgent).length === 0) {
    return <p className="text-sm text-surface-primary/70">No per-agent metrics available.</p>;
  }

  return (
    <div className="bg-canvas-light text-text-onLight rounded-2xl p-6 shadow-xl space-y-4">
      <div className="flex items-center justify-between pb-2 border-b border-surface-muted/30">
        <h4 className="font-bold text-sm text-surface-primary">Per-Agent Accuracy &amp; F1 Scores</h4>
        <span className="text-xs font-mono text-surface-primary/60">Tabular metrics</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse font-sans text-xs">
          <thead>
            <tr className="border-b border-surface-muted/40 text-surface-primary/70">
              <th className="py-2.5 px-3 font-bold">Specialist Agent</th>
              <th className="py-2.5 px-3 font-bold text-right">Precision</th>
              <th className="py-2.5 px-3 font-bold text-right">Recall</th>
              <th className="py-2.5 px-3 font-bold text-right">F1-Score</th>
              <th className="py-2.5 px-3 font-bold text-right">TP</th>
              <th className="py-2.5 px-3 font-bold text-right">FP</th>
              <th className="py-2.5 px-3 font-bold text-right">FN</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-muted/20">
            {Object.entries(perAgent).map(([agent, m]) => (
              <tr key={agent} className="hover:bg-white/50 transition-colors">
                <td className="py-2.5 px-3 font-semibold text-surface-primary font-mono">{agent}</td>
                <td className="py-2.5 px-3 text-right font-mono tabular-nums font-bold text-surface-primary">
                  {(m.precision * 100).toFixed(1)}%
                </td>
                <td className="py-2.5 px-3 text-right font-mono tabular-nums font-bold text-surface-primary">
                  {(m.recall * 100).toFixed(1)}%
                </td>
                <td className="py-2.5 px-3 text-right font-mono tabular-nums font-extrabold text-accent-primary bg-surface-primary/5 rounded">
                  {(m.f1 * 100).toFixed(1)}%
                </td>
                <td className="py-2.5 px-3 text-right font-mono tabular-nums opacity-75">{m.tp}</td>
                <td className="py-2.5 px-3 text-right font-mono tabular-nums opacity-75">{m.fp}</td>
                <td className="py-2.5 px-3 text-right font-mono tabular-nums opacity-75">{m.fn}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
