import React, { useEffect } from 'react';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  footer,
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fade-in" role="dialog" aria-modal="true">
      <div className="relative z-10 w-full max-w-lg bg-[var(--bg-card)] border border-[var(--border)] rounded-2xl shadow-[var(--shadow)] p-6 text-[var(--text-primary)]">
        {title && <h3 className="font-bold text-lg text-white mb-4 border-b border-[var(--border)] pb-3">{title}</h3>}
        <div className="py-2">{children}</div>
        <div className="mt-6 flex justify-end gap-2">
          {footer ? (
            footer
          ) : (
            <button
              className="px-3 py-1.5 text-xs rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-[rgba(255,255,255,0.06)] border border-transparent transition-all cursor-pointer"
              onClick={onClose}
            >
              Close
            </button>
          )}
        </div>
      </div>
      <div className="fixed inset-0" onClick={onClose} />
    </div>
  );
};
