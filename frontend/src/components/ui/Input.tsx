import React from 'react';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Input: React.FC<InputProps> = ({
  label,
  error,
  helperText,
  className = '',
  id,
  ...props
}) => {
  const inputId = id || (label ? `input-${label.toLowerCase().replace(/\s+/g, '-')}` : undefined);

  return (
    <div className="w-full flex flex-col gap-1.5">
      {label && (
        <label htmlFor={inputId} className="text-xs font-medium text-[var(--text-secondary)]">
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`w-full px-3 py-2 bg-[var(--bg-input)] border rounded-lg text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] transition-all outline-none ${
          error
            ? 'border-[var(--danger)] focus:ring-2 focus:ring-[rgba(255,107,107,0.25)]'
            : 'border-[var(--border)] focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-glow)]'
        } ${className}`}
        {...props}
      />
      {error && (
        <span className="text-xs text-[var(--danger)] mt-0.5">{error}</span>
      )}
      {!error && helperText && (
        <span className="text-xs text-[var(--text-muted)] mt-0.5">{helperText}</span>
      )}
    </div>
  );
};
