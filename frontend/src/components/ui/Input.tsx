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
    <div className="form-control w-full">
      {label && (
        <label htmlFor={inputId} className="label py-1">
          <span className="label-text font-medium text-xs">{label}</span>
        </label>
      )}
      <input
        id={inputId}
        className={`input input-bordered w-full text-sm ${error ? 'input-error' : ''} ${className}`}
        {...props}
      />
      {error && (
        <label className="label py-0.5">
          <span className="label-text-alt text-error text-xs">{error}</span>
        </label>
      )}
      {!error && helperText && (
        <label className="label py-0.5">
          <span className="label-text-alt text-base-content/60 text-xs">{helperText}</span>
        </label>
      )}
    </div>
  );
};
