/**
 * frontend/src/components/EvalTrendChart.tsx
 * Evaluation accuracy trend chart rendering past eval runs with accent-primary highlights.
 */

import React from 'react';
import { EvalSummary } from '../types/api';
import { TrendingUp, Award } from 'lucide-react';

interface EvalTrendChartProps {
  runs: EvalSummary[];
}

export const EvalTrendChart: React.FC<EvalTrendChartProps> = ({ runs }) => {
  if (!runs || runs.length === 0) {
    return (
      <div className="bg-canvas-light text-text-onLight rounded-2xl p-6 shadow-xl text-center">
        <p className="text-sm opacity-70">No historical eval runs recorded yet.</p>
      </div>
    );
  }

  // Reverse so earliest is first
  const chronological = [...runs].reverse();

  return (
    <div className="bg-canvas-light text-text-onLight rounded-2xl p-6 shadow-xl space-y-4">
      <div className="flex items-center justify-between pb-2 border-b border-surface-muted/30">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-accent-primary" />
          <h4 className="font-bold text-sm text-surface-primary">Historical Accuracy Trend</h4>
        </div>
        <span className="text-xs font-mono font-bold text-surface-primary">
          {runs.length} Evaluated {runs.length === 1 ? 'Run' : 'Runs'}
        </span>
      </div>

      {/* Bar / Trend Visualization */}
      <div className="h-40 flex items-end gap-3 pt-6 px-2 pb-2 bg-white/60 rounded-xl border border-surface-muted/20">
        {chronological.map((run, i) => {
          const pct = Math.round(run.accuracy * 100);
          const height = Math.max(15, Math.min(100, pct));
          const dateStr = new Date(run.run_at).toLocaleDateString([], {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          });

          return (
            <div key={i} className="flex-1 flex flex-col items-center gap-1 group relative">
              {/* Tooltip */}
              <div className="absolute -top-10 opacity-0 group-hover:opacity-100 transition-opacity bg-surface-primary text-text-primary text-[10px] font-mono px-2 py-1 rounded shadow pointer-events-none whitespace-nowrap z-10">
                {dateStr}: {pct}% ({run.correct}/{run.total})
              </div>

              {/* Bar */}
              <div
                style={{ height: `${height}%` }}
                className="w-full max-w-[48px] bg-accent-primary rounded-t-lg transition-all group-hover:brightness-110 shadow-sm flex items-start justify-center pt-1"
              >
                <span className="text-[10px] font-mono font-bold text-text-onLight">{pct}%</span>
              </div>
              <span className="text-[10px] font-mono text-surface-primary/60 truncate max-w-full">
                Run #{runs.length - i}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
