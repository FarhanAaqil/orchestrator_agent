/**
 * frontend/src/components/ConfusionMatrixHeatmap.tsx
 * Confusion matrix heatmap component with dynamic cell intensity scaling from surface-muted to accent-primary.
 */

import React from 'react';

interface ConfusionMatrixHeatmapProps {
  matrix: Record<string, Record<string, number>>;
}

const SHORT_NAMES: Record<string, string> = {
  career_agent: 'Career',
  research_agent: 'Research',
  growth_content_agent: 'Growth',
  critic_agent: 'Critic',
  none: 'None',
};

export const ConfusionMatrixHeatmap: React.FC<ConfusionMatrixHeatmapProps> = ({ matrix }) => {
  if (!matrix || Object.keys(matrix).length === 0) {
    return <p className="text-sm text-surface-primary/70">No confusion matrix data available.</p>;
  }

  const expectedAgents = Object.keys(matrix);
  const predictedAgents = [...expectedAgents, 'none'];

  // Find max value in matrix for scaling intensity
  let maxVal = 1;
  expectedAgents.forEach((exp) => {
    predictedAgents.forEach((pred) => {
      const v = matrix[exp]?.[pred] || 0;
      if (v > maxVal) maxVal = v;
    });
  });

  return (
    <div className="bg-canvas-light text-text-onLight rounded-2xl p-6 shadow-xl space-y-4">
      <div className="flex items-center justify-between pb-2 border-b border-surface-muted/30">
        <div>
          <h4 className="font-bold text-sm text-surface-primary">Confusion Matrix</h4>
          <p className="text-xs text-surface-primary/60">Rows: Expected Agent | Columns: Predicted Agent</p>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono text-surface-primary/70">
          <span>Scale:</span>
          <span className="w-3 h-3 rounded bg-[#C9C1B1]" title="0 / Low" />
          <span className="w-3 h-3 rounded bg-[#FFB162]" title="High" />
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-center border-collapse">
          <thead>
            <tr>
              <th className="p-2 text-xs font-bold text-surface-primary text-left">Expected \ Predicted</th>
              {predictedAgents.map((pred) => (
                <th key={pred} className="p-2 text-xs font-bold text-surface-primary">
                  {SHORT_NAMES[pred] || pred}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {expectedAgents.map((exp) => (
              <tr key={exp} className="border-t border-surface-muted/20">
                <td className="p-2 text-xs font-bold text-surface-primary text-left bg-surface-muted/10">
                  {SHORT_NAMES[exp] || exp}
                </td>
                {predictedAgents.map((pred) => {
                  const count = matrix[exp]?.[pred] || 0;
                  const intensity = count / maxVal;
                  const isDiagonal = exp === pred;

                  // Intensity styling
                  let bgStyle = 'bg-white/40 text-surface-primary/60';
                  if (count > 0) {
                    if (isDiagonal) {
                      bgStyle = 'bg-accent-primary text-text-onLight font-bold shadow-sm';
                    } else {
                      bgStyle = 'bg-state-warning/30 text-surface-primary font-semibold';
                    }
                  }

                  return (
                    <td key={pred} className="p-1">
                      <div
                        className={`py-2 px-3 rounded-lg text-xs font-mono tabular-nums transition-all hover:scale-105 ${bgStyle}`}
                        title={`${count} commands (${SHORT_NAMES[exp]} -> ${SHORT_NAMES[pred]})`}
                      >
                        {count}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
