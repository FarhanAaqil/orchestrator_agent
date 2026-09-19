/**
 * frontend/src/pages/ApprovalsPage.tsx
 * Near-real-time approval queue with 5s polling, optimistic state updates, and status filters.
 */

import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { ApprovalRecord } from '../types/api';
import { ApprovalCard } from '../components/ApprovalCard';
import { ShieldCheck, Filter, RefreshCw } from 'lucide-react';

export const ApprovalsPage: React.FC = () => {
  const [approvals, setApprovals] = useState<ApprovalRecord[]>([]);
  const [filter, setFilter] = useState<string>('all');
  const [isLoading, setIsLoading] = useState(true);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);

  const fetchApprovals = async () => {
    try {
      const statusParam = filter === 'all' ? undefined : filter;
      const res = await api.getApprovals(statusParam);
      setApprovals(res.items || []);
    } catch (err) {
      console.error('Failed to fetch approvals:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchApprovals();

    // 5s polling for near-real-time updates without user interaction
    const interval = setInterval(fetchApprovals, 5000);
    return () => clearInterval(interval);
  }, [filter]);

  const handleApprove = async (id: string) => {
    setActionLoadingId(id);
    // Optimistic update
    setApprovals((prev) =>
      prev.map((a) => (a.id === id ? { ...a, status: 'approved' } : a))
    );
    try {
      await api.approve(id);
    } catch (err) {
      console.error('Approve failed:', err);
      fetchApprovals();
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleReject = async (id: string) => {
    setActionLoadingId(id);
    // Optimistic update
    setApprovals((prev) =>
      prev.map((a) => (a.id === id ? { ...a, status: 'rejected' } : a))
    );
    try {
      await api.reject(id);
    } catch (err) {
      console.error('Reject failed:', err);
      fetchApprovals();
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleExecute = async (id: string) => {
    setActionLoadingId(id);
    // Optimistic update
    setApprovals((prev) =>
      prev.map((a) => (a.id === id ? { ...a, status: 'executing' } : a))
    );
    try {
      await api.execute(id);
      fetchApprovals();
    } catch (err) {
      console.error('Execute failed:', err);
      fetchApprovals();
    } finally {
      setActionLoadingId(null);
    }
  };

  const pendingCount = approvals.filter((a) => a.status === 'pending').length;

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-text-primary flex items-center gap-2.5">
            <ShieldCheck className="w-6 h-6 text-accent-primary" />
            Human-in-the-Loop Approvals
          </h2>
          <p className="text-sm text-text-muted mt-1">
            Zero-parameter execution gate. Sensitive actions require explicit human review.
          </p>
        </div>

        {/* Status Filters */}
        <div className="flex items-center gap-1.5 bg-surface-primary p-1.5 rounded-2xl border border-surface-muted/20">
          <Filter className="w-4 h-4 text-text-muted ml-2 mr-1" />
          {['all', 'pending', 'approved', 'executed', 'rejected'].map((st) => (
            <button
              key={st}
              onClick={() => setFilter(st)}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold uppercase tracking-wider transition-all ${
                filter === st
                  ? 'bg-accent-primary text-text-onLight shadow'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              {st}
              {st === 'pending' && pendingCount > 0 && (
                <span className="ml-1 px-1.5 py-0.2 rounded-full bg-state-warning text-[#EEE9DF] text-[10px]">
                  {pendingCount}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Approvals List */}
      {isLoading && approvals.length === 0 ? (
        <div className="flex justify-center p-12 text-text-muted">
          <RefreshCw className="w-6 h-6 animate-spin text-accent-primary" />
        </div>
      ) : approvals.length === 0 ? (
        <div className="bg-surface-primary rounded-2xl p-12 text-center border border-surface-muted/20 text-text-muted space-y-2">
          <ShieldCheck className="w-10 h-10 text-surface-muted mx-auto opacity-50" />
          <h4 className="text-base font-bold text-text-primary">No Approvals in Queue</h4>
          <p className="text-xs max-w-sm mx-auto text-text-muted">
            Actions requiring approval (e.g. publishing blog posts, sending emails) will appear here for review.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {approvals.map((approval) => (
            <ApprovalCard
              key={approval.id}
              approval={approval}
              onApprove={handleApprove}
              onReject={handleReject}
              onExecute={handleExecute}
              isActionLoading={actionLoadingId === approval.id}
            />
          ))}
        </div>
      )}
    </div>
  );
};
