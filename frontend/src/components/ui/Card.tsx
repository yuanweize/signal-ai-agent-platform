import React from 'react';

export interface CardProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
  action?: React.ReactNode;
  headerAction?: React.ReactNode;
}

export const Card: React.FC<CardProps> = ({
  children,
  className = '',
  title,
  subtitle,
  action,
  headerAction,
}) => {
  const rightAction = headerAction || action;
  return (
    <div className={`rounded-xl bg-[var(--bg-card)] border border-[var(--border)] shadow-[var(--shadow)] overflow-hidden transition-all ${className}`}>
      {(title || rightAction) && (
        <div className="px-5 py-4 flex flex-row items-center justify-between border-b border-[var(--border)] bg-[rgba(255,255,255,0.01)]">
          <div>
            {title && <h3 className="text-base font-semibold text-[var(--text-primary)] tracking-wide">{title}</h3>}
            {subtitle && <p className="text-xs text-[var(--text-secondary)] mt-0.5">{subtitle}</p>}
          </div>
          {rightAction && <div>{rightAction}</div>}
        </div>
      )}
      <div className="p-5">{children}</div>
    </div>
  );
};
