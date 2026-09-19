/**
 * frontend/src/pages/DispatchPage.tsx
 * Natural language command dispatch with instant routing feedback and clarification handling.
 */

import React, { useState } from 'react';
import { CommandInput } from '../components/CommandInput';
import { ClarificationPrompt } from '../components/ClarificationPrompt';
import { api } from '../api/client';
import { AgentResult, ClarificationNeeded } from '../types/api';
import { Cpu, CheckCircle2, Zap, HelpCircle } from 'lucide-react';

const SUGGESTIONS = [
  'Tailor my resume for a Senior Machine Learning Engineer role at DeepMind',
  'Write a research paper on federated learning for IoT edge devices',
  'Draft a tech blog post for Hashnode about building multi-agent systems',
  'Critique this cover letter and suggest improvements for higher ATS score',
  'Help me with my career project', // Ambiguous test
];

export const DispatchPage: React.FC = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<AgentResult | null>(null);
  const [clarification, setClarification] = useState<ClarificationNeeded | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleCommand = async (cmd: string) => {
    setIsLoading(true);
    setError(null);
    setResult(null);
    setClarification(null);

    try {
      const data = await api.dispatch(cmd);
      setResult(data);
    } catch (err: any) {
      if (err.isClarification) {
        setClarification({
          candidates: err.candidates || [],
          reasoning: err.reasoning || 'Confidence below threshold.',
        });
      } else {
        setError(err.message || 'An error occurred while dispatching command.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div>
        <h2 className="text-2xl font-black text-text-primary flex items-center gap-2.5">
          <Zap className="w-6 h-6 text-accent-primary" />
          Natural Language Dispatch
        </h2>
        <p className="text-sm text-text-muted mt-1">
          Route instructions to specialist agents through the measured LLM routing engine.
        </p>
      </div>

      <CommandInput onSubmit={handleCommand} isLoading={isLoading} />

      {/* Suggestion Chips */}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <span className="text-xs text-text-muted font-medium mr-1">Suggestions:</span>
        {SUGGESTIONS.map((s, idx) => (
          <button
            key={idx}
            onClick={() => handleCommand(s)}
            disabled={isLoading}
            className="text-xs px-3 py-1.5 rounded-xl bg-surface-primary hover:bg-surface-primary/80 border border-surface-muted/20 hover:border-accent-primary/60 text-text-primary transition-all disabled:opacity-40 truncate max-w-xs"
            title={s}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-state-danger/15 border border-state-danger/40 text-[#EEE9DF] rounded-2xl p-4 text-sm flex items-center gap-3">
          <span className="w-2 h-2 rounded-full bg-state-danger" />
          <span>{error}</span>
        </div>
      )}

      {/* Clarification Needed Banner */}
      {clarification && (
        <ClarificationPrompt
          data={clarification}
          onSelectCandidate={(agent) =>
            handleCommand(`[Target: ${agent}] ${clarification.reasoning}`)
          }
        />
      )}

      {/* Execution Result */}
      {result && (
        <div className="bg-surface-primary rounded-2xl border border-surface-muted/20 p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-surface-muted/20">
            <div className="flex items-center gap-2.5">
              <span className="p-2 rounded-xl bg-accent-primary/10 text-accent-primary">
                <Cpu className="w-5 h-5" />
              </span>
              <div>
                <span className="text-xs text-text-muted uppercase tracking-wider font-semibold">
                  Handled by
                </span>
                <h4 className="text-base font-bold text-accent-primary">{result.agent}</h4>
              </div>
            </div>

            <div className="flex items-center gap-3 text-xs font-mono">
              {result.metadata?.confidence && (
                <span className="px-2.5 py-1 rounded-pill bg-canvas-dark text-[#EEE9DF] border border-surface-muted/30">
                  Confidence: {Math.round(result.metadata.confidence * 100)}%
                </span>
              )}
              {result.metadata?.latency_ms && (
                <span className="px-2.5 py-1 rounded-pill bg-canvas-dark text-[#EEE9DF] border border-surface-muted/30">
                  {result.metadata.latency_ms} ms
                </span>
              )}
            </div>
          </div>

          <div className="bg-canvas-dark rounded-xl p-4 border border-surface-muted/20">
            <h5 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
              Agent Output
            </h5>
            <div className="text-sm text-text-primary whitespace-pre-wrap leading-relaxed font-sans">
              {result.output}
            </div>
          </div>

          {result.action_type && (
            <div className="bg-state-warning/20 border border-state-warning/40 rounded-xl p-3 flex items-center justify-between">
              <div className="text-xs text-text-primary">
                <strong className="text-accent-primary">Approval Queued:</strong> This command requires human review for external side-effect: <code className="font-mono text-xs">{result.action_type}</code>
              </div>
              <a
                href="#approvals"
                className="text-xs px-3 py-1 rounded-pill bg-accent-primary text-text-onLight font-bold hover:brightness-105"
              >
                Go to Approvals &rarr;
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
