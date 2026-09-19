/**
 * frontend/src/App.tsx
 * Application shell with MP072 design tokens, persistent navigation, and route view management.
 */

import React, { useState, useEffect } from 'react';
import { DispatchPage } from './pages/DispatchPage';
import { PipelinesPage } from './pages/PipelinesPage';
import { RunDetailPage } from './pages/RunDetailPage';
import { ApprovalsPage } from './pages/ApprovalsPage';
import { EvalPage } from './pages/EvalPage';
import { api } from './api/client';
import {
  Zap,
  Workflow,
  ShieldCheck,
  BarChart3,
  Bot,
  Activity,
  Layers,
} from 'lucide-react';

type TabType = 'dispatch' | 'pipelines' | 'runs' | 'approvals' | 'eval';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('dispatch');
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [pendingApprovalsCount, setPendingApprovalsCount] = useState(0);
  const [healthStatus, setHealthStatus] = useState<string>('checking...');

  // Check health and approvals count periodically
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch('/health');
        if (res.ok) {
          const data = await res.json();
          setHealthStatus(data.version || 'v2.0.0-alpha');
        } else {
          setHealthStatus('degraded');
        }
      } catch {
        setHealthStatus('offline');
      }
    };

    const pollApprovals = async () => {
      try {
        const data = await api.getApprovals('pending');
        setPendingApprovalsCount(data.total || 0);
      } catch {}
    };

    checkHealth();
    pollApprovals();
    const interval = setInterval(pollApprovals, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleNavigateToRun = (runId: string) => {
    setActiveRunId(runId);
    setActiveTab('runs');
  };

  const navItems = [
    { id: 'dispatch', label: 'Dispatch', icon: Zap },
    { id: 'pipelines', label: 'Pipelines', icon: Workflow },
    {
      id: 'approvals',
      label: 'Approvals',
      icon: ShieldCheck,
      badge: pendingApprovalsCount > 0 ? pendingApprovalsCount : null,
    },
    { id: 'eval', label: 'Router Eval', icon: BarChart3 },
  ];

  return (
    <div className="min-h-screen bg-canvas-dark text-text-primary flex flex-col md:flex-row font-sans selection:bg-accent-primary selection:text-text-onLight">
      {/* Sidebar Navigation */}
      <aside className="w-full md:w-64 bg-surface-primary border-b md:border-b-0 md:border-r border-surface-muted/20 flex flex-col justify-between p-5 flex-shrink-0">
        <div className="space-y-6">
          {/* Brand Header */}
          <div className="flex items-center gap-3 px-2">
            <div className="w-10 h-10 rounded-2xl bg-accent-primary flex items-center justify-center text-text-onLight shadow-lg shadow-accent-primary/20">
              <Bot className="w-6 h-6" />
            </div>
            <div>
              <h1 className="font-extrabold text-lg text-[#EEE9DF] tracking-tight leading-none">
                Orchestrator
              </h1>
              <span className="text-[11px] font-mono text-accent-primary font-bold tracking-widest uppercase mt-0.5 block">
                Agent v2 Core
              </span>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="space-y-1.5" aria-label="Main Navigation">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    setActiveTab(item.id as TabType);
                    if (item.id === 'pipelines') setActiveRunId(null);
                  }}
                  className={`w-full flex items-center justify-between px-3.5 py-3 rounded-xl text-sm font-semibold transition-all ${
                    isActive
                      ? 'bg-accent-primary text-text-onLight shadow-md'
                      : 'text-text-muted hover:text-text-primary hover:bg-canvas-dark/50'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Icon className="w-4 h-4" />
                    <span>{item.label}</span>
                  </div>
                  {item.badge !== null && item.badge !== undefined && (
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                        isActive
                          ? 'bg-canvas-dark text-accent-primary'
                          : 'bg-state-warning text-[#EEE9DF]'
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}

            {activeRunId && (
              <button
                onClick={() => setActiveTab('runs')}
                className={`w-full flex items-center gap-3 px-3.5 py-3 rounded-xl text-sm font-semibold transition-all ${
                  activeTab === 'runs'
                    ? 'bg-accent-primary text-text-onLight shadow-md'
                    : 'text-accent-primary/80 hover:bg-canvas-dark/50'
                }`}
              >
                <Layers className="w-4 h-4" />
                <span className="truncate">Run #{activeRunId.slice(0, 6)}</span>
              </button>
            )}
          </nav>
        </div>

        {/* System Health Footer */}
        <div className="pt-6 border-t border-surface-muted/10">
          <div className="bg-canvas-dark/60 rounded-xl p-3 flex items-center justify-between border border-surface-muted/10">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-state-success animate-pulse" />
              <span className="text-xs font-mono text-text-muted">{healthStatus}</span>
            </div>
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="text-[11px] text-accent-primary hover:underline font-mono"
            >
              API Docs &rarr;
            </a>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 p-6 md:p-8 overflow-y-auto">
        {activeTab === 'dispatch' && <DispatchPage />}
        {activeTab === 'pipelines' && (
          <PipelinesPage onNavigateToRun={handleNavigateToRun} />
        )}
        {activeTab === 'runs' && (
          activeRunId ? (
            <RunDetailPage
              runId={activeRunId}
              onBack={() => setActiveTab('pipelines')}
            />
          ) : (
            <PipelinesPage onNavigateToRun={handleNavigateToRun} />
          )
        )}
        {activeTab === 'approvals' && <ApprovalsPage />}
        {activeTab === 'eval' && <EvalPage />}
      </main>
    </div>
  );
};

export default App;
