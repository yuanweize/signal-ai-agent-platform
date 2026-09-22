import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'outline';
  size?: 'xs' | 'sm' | 'md' | 'lg';
  loading?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled,
  className = '',
  ...props
}) => {
  const baseClasses = 'inline-flex items-center justify-center font-medium transition-all duration-200 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed select-none focus:outline-none';

  const variantClasses = {
    primary: 'bg-gradient-to-r from-[var(--accent)] to-[#5a4bd1] text-white hover:brightness-110 shadow-sm hover:shadow active:scale-[0.98] border border-[rgba(255,255,255,0.12)]',
    secondary: 'bg-[var(--bg-input)] hover:bg-[var(--bg-card-hover)] text-[var(--text-primary)] border border-[var(--border)] hover:border-[rgba(255,255,255,0.18)] shadow-sm active:scale-[0.98]',
    danger: 'bg-[rgba(255,107,107,0.12)] hover:bg-[rgba(255,107,107,0.22)] text-[var(--danger)] border border-[rgba(255,107,107,0.3)] active:scale-[0.98]',
    ghost: 'bg-transparent hover:bg-[rgba(255,255,255,0.06)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] border border-transparent',
    outline: 'bg-transparent hover:bg-[rgba(108,92,231,0.1)] text-[var(--text-primary)] border border-[var(--border)] hover:border-[var(--accent)] active:scale-[0.98]',
  }[variant];

  const sizeClasses = {
    xs: 'px-2 py-1 text-xs rounded-md gap-1',
    sm: 'px-3 py-1.5 text-xs rounded-lg gap-1.5',
    md: 'px-4 py-2 text-sm rounded-lg gap-2',
    lg: 'px-5 py-2.5 text-base rounded-xl gap-2',
  }[size];

  return (
    <button
      className={`${baseClasses} ${variantClasses} ${sizeClasses} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading && (
        <svg className="animate-spin h-3.5 w-3.5 mr-1" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      )}
      {children}
    </button>
  );
};
