/**
 * frontend/src/components/ApprovalCard.tsx
 * Approval queue card on surface-primary with StatusPill, payload inspector, and action buttons.
 */

import React, { useState } from 'react';
import { Check, X, Play, Clock, Code } from 'lucide-react';
import { ApprovalRecord } from '../types/api';
import { StatusPill } from './StatusPill';

interface ApprovalCardProps {
  approval: ApprovalRecord;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onExecute: (id: string) => void;
  isActionLoading?: boolean;
}

export const ApprovalCard: React.FC<ApprovalCardProps> = ({
  approval,
  onApprove,
  onReject,
  onExecute,
  isActionLoading = false,
}) => {
  const [showPayload, setShowPayload] = useState(false);

  let formattedPayload = approval.payload_json;
  try {
    formattedPayload = JSON.stringify(JSON.parse(approval.payload_json), null, 2);
  } catch {}

  const isPending = approval.status === 'pending';
  const isApproved = approval.status === 'approved';

  return (
    <div className="bg-surface-primary rounded-2xl border border-surface-muted/20 p-5 shadow-lg flex flex-col gap-4 text-text-primary transition-all hover:border-surface-muted/40">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="font-mono text-xs text-text-muted">#{approval.id.slice(0, 8)}</span>
            <span className="font-semibold text-base text-accent-primary">{approval.action_type}</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-text-muted mt-1">
            <Clock className="w-3.5 h-3.5" />
            <span>Queued: {new Date(approval.created_at).toLocaleString()}</span>
          </div>
        </div>
        <StatusPill status={approval.status} />
      </div>

      <div className="bg-canvas-dark rounded-xl p-3 border border-surface-muted/20">
        <button
          onClick={() => setShowPayload(!showPayload)}
          className="w-full flex items-center justify-between text-xs font-mono text-text-muted hover:text-text-primary transition-colors"
        >
          <span className="flex items-center gap-1.5">
            <Code className="w-3.5 h-3.5 text-accent-primary" />
            <span>Canonical Payload</span>
          </span>
          <span>{showPayload ? 'Collapse [-]' : 'Inspect [+]'}</span>
        </button>
        {showPayload && (
          <pre className="mt-2 text-xs font-mono text-text-primary overflow-x-auto p-2 bg-black/30 rounded border border-white/5 max-h-48">
            {formattedPayload}
          </pre>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-surface-muted/10">
        {isPending && (
          <>
            <button
              disabled={isActionLoading}
              onClick={() => onReject(approval.id)}
              className="px-4 py-2 bg-state-danger/20 hover:bg-state-danger/30 text-[#EEE9DF] border border-state-danger/40 text-xs font-semibold rounded-pill flex items-center gap-1.5 transition-all disabled:opacity-40"
            >
              <X className="w-3.5 h-3.5" />
              <span>Reject</span>
            </button>
            <button
              disabled={isActionLoading}
              onClick={() => onApprove(approval.id)}
              className="px-4 py-2 bg-state-success hover:bg-[#4f7b5e] text-[#EEE9DF] text-xs font-semibold rounded-pill flex items-center gap-1.5 transition-all shadow-md disabled:opacity-40"
            >
              <Check className="w-3.5 h-3.5" />
              <span>Approve</span>
            </button>
          </>
        )}

        {isApproved && (
          <button
            disabled={isActionLoading}
            onClick={() => onExecute(approval.id)}
            className="px-5 py-2 bg-accent-primary hover:bg-[#ffa343] text-text-onLight text-xs font-bold rounded-pill flex items-center gap-1.5 transition-all shadow-md disabled:opacity-40"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>Execute Approved</span>
          </button>
        )}

        {approval.status === 'executed' && (
          <span className="text-xs text-state-success font-medium">
            Executed at {approval.executed_at ? new Date(approval.executed_at).toLocaleTimeString() : 'N/A'}
          </span>
        )}
      </div>
    </div>
  );
};
