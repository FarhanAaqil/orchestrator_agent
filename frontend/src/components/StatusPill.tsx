/**
 * frontend/src/components/StatusPill.tsx
 * Accessible status pill component using MP072 design tokens.
 * Always renders a clear textual label alongside color.
 */

import React from 'react';

export type StatusType =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'executing'
  | 'executed'
  | 'expired'
  | 'running'
  | 'completed'
  | 'failed';

interface StatusPillProps {
  status: StatusType | string;
  className?: string;
  size?: 'sm' | 'md';
}

export const StatusPill: React.FC<StatusPillProps> = ({ status, className = '', size = 'md' }) => {
  const norm = status.toLowerCase() as StatusType;

  let bgClass = 'bg-surface-primary text-text-primary border border-surface-muted/30';
  let dotClass = 'bg-surface-muted';
  let label = status.toUpperCase();

  switch (norm) {
    case 'pending':
      bgClass = 'bg-state-warning text-[#EEE9DF] shadow-sm';
      dotClass = 'bg-[#FFB162]';
      label = 'PENDING';
      break;
    case 'approved':
      bgClass = 'bg-state-success text-[#EEE9DF] shadow-sm';
      dotClass = 'bg-[#EEE9DF]';
      label = 'APPROVED';
      break;
    case 'rejected':
      bgClass = 'bg-state-danger text-[#EEE9DF] shadow-sm';
      dotClass = 'bg-[#EEE9DF]';
      label = 'REJECTED';
      break;
    case 'executing':
    case 'running':
      bgClass = 'bg-accent-primary text-text-onLight font-bold animate-pulse';
      dotClass = 'bg-[#1B2632]';
      label = norm === 'executing' ? 'EXECUTING' : 'RUNNING';
      break;
    case 'executed':
    case 'completed':
      bgClass = 'bg-state-success text-[#EEE9DF] shadow-sm';
      dotClass = 'bg-[#EEE9DF]';
      label = norm === 'executed' ? 'EXECUTED' : 'COMPLETED';
      break;
    case 'failed':
      bgClass = 'bg-state-danger text-[#EEE9DF] shadow-sm';
      dotClass = 'bg-[#EEE9DF]';
      label = 'FAILED';
      break;
    case 'expired':
      bgClass = 'bg-surface-primary text-text-muted border border-surface-muted/40';
      dotClass = 'bg-surface-muted';
      label = 'EXPIRED';
      break;
  }

  const sizeClass = size === 'sm' ? 'px-2.5 py-0.5 text-xs' : 'px-3 py-1 text-xs font-semibold';

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-pill uppercase tracking-wider ${sizeClass} ${bgClass} ${className}`}
      role="status"
      aria-label={`Status: ${label}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${dotClass}`} aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
};
