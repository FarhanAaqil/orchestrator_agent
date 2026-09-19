/**
 * frontend/src/pages/PipelinesPage.tsx
 * Multi-step pipeline launcher for research, job applications, and content publishing.
 */

import React, { useState } from 'react';
import { api } from '../api/client';
import { Workflow, BookOpen, Briefcase, Share2, ArrowRight } from 'lucide-react';

interface PipelinesPageProps {
  onNavigateToRun: (runId: string) => void;
}

const PIPELINES = [
  {
    id: 'research',
    name: 'Research Pipeline',
    icon: BookOpen,
    description:
      'Literature review, ArXiv paper search, IEEE-format draft creation, and journal verification.',
    defaultCommand: 'Research physics-informed neural networks for turbulence modeling',
  },
  {
    id: 'apply',
    name: 'Application Pipeline',
    icon: Briefcase,
    description:
      'Job description parsing, skill gap analysis, customized cover letter tailoring, and reviewer pass.',
    defaultCommand: 'Apply to Senior AI Engineer at OpenAI, tailor for LLM agent architecture',
  },
  {
    id: 'publish',
    name: 'Publishing Pipeline',
    icon: Share2,
    description:
      'Technical blog post generation, Twitter/X thread drafting, and automatic routing to approval gate.',
    defaultCommand: 'Publish technical breakdown of the Orchestrator v2 approval gate architecture to Hashnode',
  },
];

export const PipelinesPage: React.FC<PipelinesPageProps> = ({ onNavigateToRun }) => {
  const [selectedPipeline, setSelectedPipeline] = useState('research');
  const [command, setCommand] = useState(PIPELINES[0].defaultCommand);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePipelineSelect = (pId: string) => {
    setSelectedPipeline(pId);
    const p = PIPELINES.find((item) => item.id === pId);
    if (p) setCommand(p.defaultCommand);
  };

  const handleLaunch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!command.trim() || isLoading) return;

    setIsLoading(true);
    setError(null);

    try {
      const res = await api.startPipeline(selectedPipeline, command.trim());
      if (res.run_id) {
        onNavigateToRun(res.run_id);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to start pipeline run.');
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div>
        <h2 className="text-2xl font-black text-text-primary flex items-center gap-2.5">
          <Workflow className="w-6 h-6 text-accent-primary" />
          Autonomous Multi-Agent Pipelines
        </h2>
        <p className="text-sm text-text-muted mt-1">
          Execute multi-step coordinated agent workflows with step latency tracing and human-in-the-loop safety.
        </p>
      </div>

      {/* Pipeline Selection Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {PIPELINES.map((p) => {
          const Icon = p.icon;
          const isSelected = selectedPipeline === p.id;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => handlePipelineSelect(p.id)}
              className={`p-5 rounded-2xl border text-left transition-all flex flex-col justify-between gap-3 ${
                isSelected
                  ? 'bg-surface-primary border-accent-primary shadow-xl ring-1 ring-accent-primary'
                  : 'bg-surface-primary/60 border-surface-muted/20 hover:border-surface-muted/50 hover:bg-surface-primary'
              }`}
            >
              <div>
                <div
                  className={`w-10 h-10 rounded-xl flex items-center justify-center mb-3 ${
                    isSelected
                      ? 'bg-accent-primary text-text-onLight'
                      : 'bg-canvas-dark text-text-muted'
                  }`}
                >
                  <Icon className="w-5 h-5" />
                </div>
                <h4 className="font-bold text-base text-text-primary">{p.name}</h4>
                <p className="text-xs text-text-muted mt-1 leading-relaxed">{p.description}</p>
              </div>

              <span
                className={`text-xs font-semibold uppercase tracking-wider ${
                  isSelected ? 'text-accent-primary' : 'text-text-muted'
                }`}
              >
                {isSelected ? 'Selected' : 'Select'} &rarr;
              </span>
            </button>
          );
        })}
      </div>

      {/* Launch Form */}
      <form
        onSubmit={handleLaunch}
        className="bg-surface-primary rounded-2xl border border-surface-muted/20 p-6 shadow-xl space-y-4"
      >
        <div>
          <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
            Pipeline Input Command &amp; Context
          </label>
          <textarea
            rows={4}
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            placeholder="Specify pipeline instructions..."
            className="w-full bg-canvas-dark text-text-primary rounded-xl p-4 text-sm border border-surface-muted/20 focus:outline-none focus:ring-2 focus:ring-accent-primary placeholder:text-text-muted"
            disabled={isLoading}
          />
        </div>

        {error && (
          <div className="bg-state-danger/20 border border-state-danger/40 text-[#EEE9DF] rounded-xl p-3 text-xs">
            {error}
          </div>
        )}

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={!command.trim() || isLoading}
            className="px-6 py-3 bg-accent-primary hover:bg-[#ffa343] text-text-onLight font-bold text-sm rounded-pill flex items-center gap-2 transition-all shadow-lg active:scale-95 disabled:opacity-40"
          >
            {isLoading ? (
              <span className="inline-block w-4 h-4 border-2 border-text-onLight border-t-transparent rounded-full animate-spin" />
            ) : (
              <>
                <span>Launch {selectedPipeline.toUpperCase()} Pipeline</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};
