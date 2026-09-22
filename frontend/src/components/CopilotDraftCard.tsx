import React, { useState } from 'react';
import { Send, Edit3, Trash2, RotateCw, ChevronDown, ChevronUp, Database, Wrench, Sparkles, Brain } from 'lucide-react';
import type { AISuggestionDTO } from '../types/ai';

interface CopilotDraftCardProps {
  suggestion: AISuggestionDTO;
  onAccept: () => void;
  onEdit: (text: string) => void;
  onReject: () => void;
  onRegenerate: () => void;
  loading?: boolean;
}

export const CopilotDraftCard: React.FC<CopilotDraftCardProps> = ({
  suggestion,
  onAccept,
  onEdit,
  onReject,
  onRegenerate,
  loading = false,
}) => {
  const [showEvidence, setShowEvidence] = useState(false);
  const metadata = suggestion.metadata || {};
  const citations = metadata.citations || [];
  const tools = metadata.tools_called || [];
  const memories = metadata.memories_used || [];
  const skills = metadata.skills_used || [];

  return (
    <div className="mb-3 rounded-xl border border-[rgba(108,92,231,0.35)] bg-[rgba(108,92,231,0.06)] p-3.5 shadow-[0_4px_20px_rgba(108,92,231,0.08)] backdrop-blur-md transition-all">
      {/* Header bar */}
      <div className="flex items-center justify-between gap-2 mb-2 pb-2 border-b border-[rgba(108,92,231,0.15)]">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-md bg-[var(--accent)] flex items-center justify-center text-white shadow-[0_2px_8px_var(--accent-glow)]">
            <Sparkles className="w-3 h-3" />
          </div>
          <span className="text-xs font-bold text-[var(--accent-light)] tracking-wide">
            AI Copilot Draft
          </span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-[rgba(108,92,231,0.2)] text-[#dcd6ff] font-medium">
            Pending Review
          </span>
        </div>

        {/* Evidence Toggle */}
        <button
          type="button"
          onClick={() => setShowEvidence(!showEvidence)}
          className="text-[11px] text-[var(--text-secondary)] hover:text-white flex items-center gap-1 transition-colors"
        >
          <span>Evidence ({citations.length + tools.length + memories.length})</span>
          {showEvidence ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </button>
      </div>

      {/* Suggested text body */}
      <div className="bg-[rgba(0,0,0,0.25)] rounded-lg p-3 text-xs text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap border border-[rgba(255,255,255,0.05)]">
        {suggestion.suggested_text}
      </div>

      {/* Collapsible Evidence details */}
      {showEvidence && (
        <div className="mt-2.5 p-2.5 rounded-lg bg-[rgba(0,0,0,0.35)] border border-[rgba(255,255,255,0.08)] space-y-2 text-[11px] animate-in fade-in-50 duration-150">
          {skills.length > 0 && (
            <div className="flex items-center gap-1 flex-wrap">
              <span className="text-[10px] text-[var(--text-muted)] font-semibold mr-1">Skills:</span>
              {skills.map((s, idx) => (
                <span key={idx} className="px-1.5 py-0.5 rounded bg-[rgba(0,214,143,0.15)] text-[#00d68f] text-[10px]">
                  {s}
                </span>
              ))}
            </div>
          )}

          {citations.length > 0 && (
            <div>
              <span className="text-[10px] text-[var(--text-muted)] font-semibold flex items-center gap-1 mb-1">
                <Database className="w-3 h-3 text-[var(--accent)]" /> Knowledge Citations:
              </span>
              <div className="space-y-1 pl-1">
                {citations.map((c, idx) => (
                  <div key={idx} className="text-[10px] text-[var(--text-secondary)] border-l-2 border-[var(--accent)] pl-1.5">
                    <strong>{c.title || 'Chunk'}</strong>: {c.snippet}
                  </div>
                ))}
              </div>
            </div>
          )}

          {memories.length > 0 && (
            <div>
              <span className="text-[10px] text-[var(--text-muted)] font-semibold flex items-center gap-1 mb-1">
                <Brain className="w-3 h-3 text-[#e056fd]" /> Consulted Memories:
              </span>
              <div className="space-y-0.5 pl-1">
                {memories.map((m, idx) => (
                  <div key={idx} className="text-[10px] text-[var(--text-secondary)]">
                    • {m.content}
                  </div>
                ))}
              </div>
            </div>
          )}

          {tools.length > 0 && (
            <div>
              <span className="text-[10px] text-[var(--text-muted)] font-semibold flex items-center gap-1 mb-1">
                <Wrench className="w-3 h-3 text-[#ffd93d]" /> Executed Tools:
              </span>
              <div className="font-mono text-[10px] text-[#ffd93d] pl-1">
                {tools.map((t, idx) => (
                  <div key={idx}>• {t.name}()</div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex items-center justify-between gap-2 mt-3 pt-2 border-t border-[rgba(108,92,231,0.15)]">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            disabled={loading}
            onClick={onReject}
            className="px-2.5 py-1 text-xs font-medium rounded-lg bg-[rgba(255,255,255,0.05)] hover:bg-[rgba(255,107,107,0.15)] text-[var(--text-muted)] hover:text-[var(--danger)] border border-transparent hover:border-[rgba(255,107,107,0.3)] transition-colors flex items-center gap-1.5 cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Discard</span>
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={onRegenerate}
            className="px-2.5 py-1 text-xs font-medium rounded-lg bg-[rgba(255,255,255,0.05)] hover:bg-[rgba(255,255,255,0.1)] text-[var(--text-secondary)] hover:text-white transition-colors flex items-center gap-1.5 cursor-pointer"
          >
            <RotateCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Regenerate</span>
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={loading}
            onClick={() => onEdit(suggestion.suggested_text)}
            className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-[rgba(255,255,255,0.08)] hover:bg-[rgba(255,255,255,0.15)] text-[var(--text-primary)] border border-[rgba(255,255,255,0.15)] transition-all flex items-center gap-1.5 cursor-pointer"
          >
            <Edit3 className="w-3.5 h-3.5 text-[var(--accent)]" />
            <span>Edit in Composer</span>
          </button>

          <button
            type="button"
            disabled={loading}
            onClick={onAccept}
            className="px-3.5 py-1.5 text-xs font-bold rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white shadow-[0_2px_12px_rgba(108,92,231,0.35)] transition-all flex items-center gap-1.5 cursor-pointer"
          >
            <Send className="w-3.5 h-3.5" />
            <span>Accept & Send</span>
          </button>
        </div>
      </div>
    </div>
  );
};
