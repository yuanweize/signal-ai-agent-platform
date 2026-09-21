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
    <div className={`card bg-base-100 shadow-sm border border-base-200 ${className}`}>
      {(title || rightAction) && (
        <div className="card-body pb-2 pt-4 px-5 flex flex-row items-center justify-between border-b border-base-200">
          <div>
            {title && <h3 className="card-title text-base font-semibold">{title}</h3>}
            {subtitle && <p className="text-xs text-base-content/60 mt-0.5">{subtitle}</p>}
          </div>
          {rightAction && <div>{rightAction}</div>}
        </div>
      )}
      <div className="card-body p-5">{children}</div>
    </div>
  );
};
