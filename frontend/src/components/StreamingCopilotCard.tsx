import React from 'react';
import { Sparkles, X } from 'lucide-react';

interface StreamingCopilotCardProps {
  text: string | null;
  onCancel: () => void;
}

export const StreamingCopilotCard: React.FC<StreamingCopilotCardProps> = ({ text, onCancel }) => {
  return (
    <div className="mb-3 rounded-xl border border-[rgba(108,92,231,0.4)] bg-[rgba(108,92,231,0.08)] p-3.5 shadow-[0_4px_20px_rgba(108,92,231,0.12)] backdrop-blur-md animate-in fade-in-50">
      {/* Header bar */}
      <div className="flex items-center justify-between gap-2 mb-2 pb-2 border-b border-[rgba(108,92,231,0.15)]">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-md bg-[var(--accent)] flex items-center justify-center text-white shadow-[0_0_12px_var(--accent-glow)] animate-pulse">
            <Sparkles className="w-3 h-3" />
          </div>
          <span className="text-xs font-bold text-[var(--accent-light)] tracking-wide">
            AI Copilot Generating (Streaming)...
          </span>
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-[rgba(108,92,231,0.2)] text-[#dcd6ff]">
            Realtime
          </span>
        </div>

        <button
          type="button"
          onClick={onCancel}
          className="px-2.5 py-1 text-xs font-semibold rounded-lg bg-[rgba(255,107,107,0.15)] hover:bg-[rgba(255,107,107,0.25)] text-[var(--danger)] border border-[rgba(255,107,107,0.3)] transition-colors flex items-center gap-1 cursor-pointer"
        >
          <X className="w-3 h-3" />
          <span>Cancel</span>
        </button>
      </div>

      {/* Suggested text accumulating */}
      <div className="bg-[rgba(0,0,0,0.35)] rounded-lg p-3 text-xs text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap border border-[rgba(255,255,255,0.06)] min-h-[56px]">
        {text ? (
          <>
            {text}
            <span className="inline-block w-1.5 h-3.5 ml-0.5 bg-[var(--accent)] animate-pulse align-middle" />
          </>
        ) : (
          <div className="flex items-center gap-2 text-[var(--text-muted)] italic">
            <div className="w-3.5 h-3.5 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
            <span>Formulating response with scoped RAG & context...</span>
          </div>
        )}
      </div>

      <div className="mt-2 text-[10px] text-[var(--text-muted)] flex items-center justify-between">
        <span>Tokens streaming securely — partial content is never sent to Signal</span>
        <span className="text-[var(--accent-light)]">Human in the Loop</span>
      </div>
    </div>
  );
};
