import React from 'react';

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
    primary: 'badge-primary text-white',
    secondary: 'badge-secondary text-white',
    accent: 'badge-accent',
    info: 'badge-info text-white',
    success: 'badge-success text-white',
    warning: 'badge-warning text-zinc-900',
    error: 'badge-error text-white',
    ghost: 'badge-ghost',
    neutral: 'badge-neutral',
  }[variant];

  const sizeClass = {
    xs: 'badge-xs text-[10px]',
    sm: 'badge-sm',
    md: 'badge-md',
    lg: 'badge-lg',
  }[size];

  return <span className={`badge ${variantClass} ${sizeClass} font-medium ${className}`}>{children}</span>;
};

export const ModeBadge: React.FC<{ mode: 'auto' | 'manual' | 'paused' }> = ({ mode }) => {
  if (mode === 'auto') {
    return <Badge variant="success" size="xs">🤖 Auto</Badge>;
  }
  if (mode === 'manual') {
    return <Badge variant="warning" size="xs">✋ Manual</Badge>;
  }
  return <Badge variant="ghost" size="xs">⏸ Paused</Badge>;
};

export const DeliveryBadge: React.FC<{ status?: string | null }> = ({ status }) => {
  if (!status) return null;
  switch (status) {
    case 'sent':
      return <span className="text-xs text-blue-500 font-medium" title="Sent to Signal">✓ Sent</span>;
    case 'delivered':
      return <span className="text-xs text-green-500 font-medium" title="Delivered to recipient">✓✓ Delivered</span>;
    case 'read':
      return <span className="text-xs text-emerald-600 font-medium" title="Read by recipient">✓✓ Read</span>;
    case 'pending':
      return <span className="text-xs text-amber-500 animate-pulse font-medium" title="Sending...">⏳ Sending</span>;
    case 'failed':
      return <span className="text-xs text-red-500 font-semibold" title="Delivery failed">✗ Failed</span>;
    default:
      return null;
  }
};
