import React from 'react';
import { Bot, Hand, PauseCircle, Check, CheckCheck, Clock, AlertCircle, Sparkles } from 'lucide-react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'primary' | 'secondary' | 'accent' | 'info' | 'success' | 'warning' | 'error' | 'ghost' | 'neutral';
  size?: 'xs' | 'sm' | 'md' | 'lg';
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'neutral',
  size = 'sm',
  className = '',
}) => {
  const variantClass = {
    primary: 'bg-[rgba(108,92,231,0.22)] text-[#d9d2ff] border border-[rgba(108,92,231,0.4)]',
    secondary: 'bg-[rgba(255,255,255,0.08)] text-[var(--text-primary)] border border-[rgba(255,255,255,0.12)]',
    accent: 'bg-[rgba(108,92,231,0.3)] text-white border border-[rgba(108,92,231,0.5)]',
    info: 'bg-[rgba(0,180,216,0.18)] text-[#90e0ef] border border-[rgba(0,180,216,0.35)]',
    success: 'bg-[rgba(0,214,143,0.16)] text-[#6effcf] border border-[rgba(0,214,143,0.35)]',
    warning: 'bg-[rgba(255,217,61,0.15)] text-[#ffd93d] border border-[rgba(255,217,61,0.35)]',
    error: 'bg-[rgba(255,107,107,0.16)] text-[#ff9999] border border-[rgba(255,107,107,0.38)]',
    ghost: 'bg-transparent text-[var(--text-muted)] border border-[var(--border)]',
    neutral: 'bg-[rgba(255,255,255,0.05)] text-[var(--text-secondary)] border border-[var(--border)]',
  }[variant];

  const sizeClass = {
    xs: 'px-1.5 py-0.5 text-[10px]',
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-2.5 py-1 text-xs',
    lg: 'px-3 py-1 text-sm',
  }[size];

  return (
    <span className={`inline-flex items-center justify-center font-medium rounded-full leading-none tracking-wide ${variantClass} ${sizeClass} ${className}`}>
      {children}
    </span>
  );
};

export const ModeBadge: React.FC<{ mode: 'auto' | 'copilot' | 'manual' | 'paused' | string }> = ({ mode }) => {
  if (mode === 'auto') {
    return (
      <Badge variant="success" size="xs" className="gap-1">
        <Bot className="w-3 h-3" />
        <span>Auto</span>
      </Badge>
    );
  }
  if (mode === 'copilot') {
    return (
      <Badge variant="primary" size="xs" className="gap-1">
        <Sparkles className="w-3 h-3" />
        <span>Copilot</span>
      </Badge>
    );
  }
  if (mode === 'manual') {
    return (
      <Badge variant="warning" size="xs" className="gap-1">
        <Hand className="w-3 h-3" />
        <span>Manual</span>
      </Badge>
    );
  }
  return (
    <Badge variant="neutral" size="xs" className="gap-1">
      <PauseCircle className="w-3 h-3" />
      <span>Paused</span>
    </Badge>
  );
};

export const DeliveryBadge: React.FC<{ status?: string | null }> = ({ status }) => {
  if (!status) return null;
  switch (status) {
    case 'sent':
      return (
        <span className="text-xs text-blue-400 font-medium inline-flex items-center gap-1" title="Sent to Signal">
          <Check className="w-3 h-3" />
          <span>Sent</span>
        </span>
      );
    case 'delivered':
      return (
        <span className="text-xs text-emerald-400 font-medium inline-flex items-center gap-1" title="Delivered to recipient">
          <CheckCheck className="w-3.5 h-3.5" />
          <span>Delivered</span>
        </span>
      );
    case 'read':
      return (
        <span className="text-xs text-cyan-400 font-medium inline-flex items-center gap-1" title="Read by recipient">
          <CheckCheck className="w-3.5 h-3.5" />
          <span>Read</span>
        </span>
      );
    case 'pending':
      return (
        <span className="text-xs text-amber-400 animate-pulse font-medium inline-flex items-center gap-1" title="Sending...">
          <Clock className="w-3 h-3" />
          <span>Sending...</span>
        </span>
      );
    case 'failed':
      return (
        <span className="text-xs text-red-400 font-semibold inline-flex items-center gap-1" title="Delivery failed">
          <AlertCircle className="w-3 h-3" />
          <span>Failed</span>
        </span>
      );
    default:
      return null;
  }
};
