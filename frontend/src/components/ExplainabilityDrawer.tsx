import React from 'react';
import {
  X,
  Sparkles,
  Database,
  Wrench,
  Brain,
  Clock,
  Cpu,
  ShieldAlert,
  Paperclip,
  Mic,
  Image as ImageIcon,
} from 'lucide-react';
import type { AIRunExplainabilityDTO } from '../types/ai';

interface ExplainabilityDrawerProps {
  run: AIRunExplainabilityDTO | null;
  isOpen: boolean;
  onClose: () => void;
  loading?: boolean;
}

export const ExplainabilityDrawer: React.FC<ExplainabilityDrawerProps> = ({
  run,
  isOpen,
  onClose,
  loading = false,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-black/60 backdrop-blur-sm flex justify-end">
      <div className="w-full max-w-md bg-[var(--bg-card)] border-l border-[var(--border-color)] h-full flex flex-col shadow-2xl animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-4 border-b border-[var(--border-color)] flex items-center justify-between bg-[rgba(255,255,255,0.02)]">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-[rgba(108,92,231,0.15)] flex items-center justify-center text-[var(--accent)] border border-[rgba(108,92,231,0.3)]">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-[var(--text-primary)]">AI Decision Context</h3>
              <p className="text-[11px] text-[var(--text-muted)] font-mono">
                {run ? `Trace: ${run.trace_id.slice(0, 16)}...` : 'Inspecting invocation...'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-white hover:bg-[rgba(255,255,255,0.06)]"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
          {loading ? (
            <div className="py-16 text-center text-[var(--text-muted)] space-y-2">
              <div className="animate-spin w-6 h-6 border-2 border-[var(--accent)] border-t-transparent rounded-full mx-auto" />
              <p>Loading decision explainability...</p>
            </div>
          ) : !run ? (
            <div className="py-16 text-center text-[var(--text-muted)]">
              <p>No telemetry trace found for this message.</p>
            </div>
          ) : (
            <>
              {/* Telemetry Summary Cards */}
              <div className="grid grid-cols-2 gap-2">
                <div className="p-2.5 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.08)]">
                  <div className="flex items-center gap-1.5 text-[var(--text-muted)] mb-1">
                    <Cpu className="w-3.5 h-3.5 text-[var(--accent)]" />
                    <span>Model & Prompt</span>
                  </div>
                  <p className="font-semibold text-[var(--text-primary)] truncate">
                    {run.model || 'Standard LLM'}
                  </p>
                  <p className="text-[10px] text-[var(--text-secondary)]">
                    Prompt v{run.prompt_version || '1.0'}
                  </p>
                </div>

                <div className="p-2.5 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.08)]">
                  <div className="flex items-center gap-1.5 text-[var(--text-muted)] mb-1">
                    <Clock className="w-3.5 h-3.5 text-[#00d68f]" />
                    <span>Performance</span>
                  </div>
                  <p className="font-semibold text-[var(--text-primary)]">
                    {run.latency_ms ?? 0} ms
                  </p>
                  <p className="text-[10px] text-[var(--text-secondary)]">
                    {run.tokens ?? 0} tokens used
                  </p>
                </div>
              </div>

              {/* Decision Verdict */}
              <div className="p-3 rounded-lg bg-[rgba(0,214,143,0.06)] border border-[rgba(0,214,143,0.2)]">
                <span className="text-[10px] uppercase font-bold text-[#00d68f] tracking-wider">
                  Action Decision
                </span>
                <p className="text-sm font-semibold text-[var(--text-primary)] capitalize mt-0.5">
                  {run.decision.replace(/_/g, ' ')}
                </p>
                {run.skills && run.skills.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {run.skills.map((s, idx) => (
                      <span
                        key={idx}
                        className="px-2 py-0.5 rounded text-[10px] bg-[rgba(0,214,143,0.15)] text-[#00d68f] font-mono"
                      >
                        skill: {s}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* RAG Citations */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-[var(--text-primary)] flex items-center gap-1.5">
                    <Database className="w-3.5 h-3.5 text-[var(--accent)]" />
                    Knowledge Sources ({run.citations?.length || 0})
                  </span>
                </div>
                {run.citations && run.citations.length > 0 ? (
                  <div className="space-y-2">
                    {run.citations.map((c, i) => (
                      <div
                        key={i}
                        className="p-2.5 rounded-lg bg-[rgba(255,255,255,0.02)] border border-[rgba(255,255,255,0.06)] hover:border-[rgba(108,92,231,0.3)] transition-colors"
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-semibold text-[var(--text-primary)] truncate max-w-[240px]">
                            {c.title || `Chunk #${c.chunk_id}`}
                          </span>
                          {c.score !== undefined && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[rgba(255,255,255,0.05)] text-[#00d68f] font-mono">
                              {(c.score * 100).toFixed(0)}% match
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed italic line-clamp-3">
                          "{c.snippet}"
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-[11px] text-[var(--text-muted)] italic">
                    No external knowledge chunks were retrieved.
                  </p>
                )}
              </div>

              {/* Scoped Memory Consulted */}
              <div className="space-y-2">
                <span className="font-bold text-[var(--text-primary)] flex items-center gap-1.5">
                  <Brain className="w-3.5 h-3.5 text-[#e056fd]" />
                  Scoped Memories ({run.memories?.length || 0})
                </span>
                {run.memories && run.memories.length > 0 ? (
                  <div className="space-y-1.5">
                    {run.memories.map((m, i) => (
                      <div
                        key={i}
                        className="p-2 rounded-lg bg-[rgba(224,86,253,0.05)] border border-[rgba(224,86,253,0.2)] text-[11px]"
                      >
                        <span className="text-[10px] text-[#e056fd] font-semibold uppercase mr-1.5">
                          {m.type || 'Fact'}:
                        </span>
                        <span className="text-[var(--text-primary)]">{m.content}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-[11px] text-[var(--text-muted)] italic">
                    No personal or group memories referenced.
                  </p>
                )}
              </div>

              {/* Tools Called */}
              <div className="space-y-2">
                <span className="font-bold text-[var(--text-primary)] flex items-center gap-1.5">
                  <Wrench className="w-3.5 h-3.5 text-[#ffd93d]" />
                  Tools Invocations ({run.tool_calls?.length || 0})
                </span>
                {run.tool_calls && run.tool_calls.length > 0 ? (
                  <div className="space-y-1.5">
                    {run.tool_calls.map((t, i) => (
                      <div
                        key={i}
                        className="p-2 rounded bg-black/40 border border-[rgba(255,255,255,0.08)] font-mono text-[11px]"
                      >
                        <p className="text-[#ffd93d] font-bold">{t.name}</p>
                        {t.arguments && (
                          <pre className="text-[10px] text-[var(--text-muted)] overflow-x-auto mt-1">
                            {JSON.stringify(t.arguments, null, 2)}
                          </pre>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-[11px] text-[var(--text-muted)] italic">
                    No tool or MCP calls were triggered.
                  </p>
                )}
              </div>

              {/* Multimodal Attachments Provenance (v0.5) */}
              {run.attachments && run.attachments.length > 0 && (
                <div className="space-y-2">
                  <span className="font-bold text-[var(--text-primary)] flex items-center gap-1.5">
                    <Paperclip className="w-3.5 h-3.5 text-indigo-400" />
                    Multimodal Context Inputs ({run.attachments.length})
                  </span>
                  <div className="space-y-1.5">
                    {run.attachments.map((att, i) => {
                      const mime = (att.mime_type || '').toLowerCase();
                      const isImg = mime.startsWith('image/');
                      const isAud = mime.startsWith('audio/');
                      return (
                        <div
                          key={i}
                          className="p-2.5 rounded-lg bg-[rgba(255,255,255,0.02)] border border-[rgba(255,255,255,0.06)] text-[11px] space-y-1"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-[var(--text-primary)] flex items-center gap-1.5 truncate max-w-[200px]">
                              {isImg ? (
                                <ImageIcon className="w-3 h-3 text-indigo-400" />
                              ) : isAud ? (
                                <Mic className="w-3 h-3 text-amber-400" />
                              ) : (
                                <Paperclip className="w-3 h-3 text-zinc-400" />
                              )}
                              {att.filename || 'Attachment'}
                            </span>
                            <span className="text-[9px] px-1.5 py-0.5 rounded font-mono uppercase bg-white/5 text-[var(--text-muted)]">
                              {att.processing_status || 'unsupported'}
                            </span>
                          </div>
                          {att.extracted_text && (
                            <p className="text-[10px] text-[var(--text-secondary)] italic bg-black/30 p-1.5 rounded">
                              "{att.extracted_text}"
                            </p>
                          )}
                          {att.processor_model && (
                            <div className="text-[9px] text-[var(--text-muted)] font-mono">
                              Model: {att.processor_model} ({att.processor_type || 'vision'})
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Safety & Chain-of-Thought Boundary */}
              <div className="p-2.5 rounded-lg bg-[rgba(255,255,255,0.02)] border border-[rgba(255,255,255,0.06)] flex items-start gap-2 text-[10px] text-[var(--text-muted)]">
                <ShieldAlert className="w-4 h-4 text-[var(--accent)] shrink-0 mt-0.5" />
                <span>
                  <strong>Privacy Guard</strong>: Model hidden reasoning tokens are suppressed by policy to maintain portfolio security and strict privacy boundaries.
                </span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
