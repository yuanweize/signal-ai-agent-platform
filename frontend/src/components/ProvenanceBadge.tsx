import React from 'react';
import { Bot, Sparkles, User, ShieldCheck, Megaphone, Terminal } from 'lucide-react';
import type { MessageOrigin } from '../types/inbox';

interface ProvenanceBadgeProps {
  origin?: MessageOrigin | string | null;
  actor?: string | null;
  model?: string | null;
  promptVersion?: string | null;
  adminIdentity?: string | null;
  aiRunId?: number | null;
  onExplain?: () => void;
}

export const ProvenanceBadge: React.FC<ProvenanceBadgeProps> = ({
  origin,
  actor,
  model,
  promptVersion,
  adminIdentity,
  aiRunId,
  onExplain,
}) => {
  // Resolve badge variant
  let label = 'Customer';
  let icon = <User className="w-3 h-3 text-[var(--text-muted)]" />;
  let badgeStyle = 'bg-[rgba(255,255,255,0.06)] text-[var(--text-muted)] border-[rgba(255,255,255,0.1)]';
  let tooltip = 'Inbound message from customer';

  if (origin === 'ai_auto' || (!origin && actor === 'bot')) {
    label = 'AI Auto';
    icon = <Bot className="w-3 h-3 text-[#00d68f]" />;
    badgeStyle = 'bg-[rgba(0,214,143,0.12)] text-[#00d68f] border-[rgba(0,214,143,0.3)]';
    tooltip = `Autonomous AI reply (${model || 'Standard'} ${promptVersion || ''})`;
  } else if (origin === 'human_ai_assisted') {
    label = 'Human + AI';
    icon = <Sparkles className="w-3 h-3 text-[#a29bfe]" />;
    badgeStyle = 'bg-[rgba(108,92,231,0.16)] text-[#c5bfff] border-[rgba(108,92,231,0.4)] shadow-[0_0_8px_rgba(108,92,231,0.2)]';
    tooltip = `AI drafted, reviewed and approved by operator ${adminIdentity || ''}`;
  } else if (origin === 'human_manual' || (!origin && actor === 'admin')) {
    label = 'Operator';
    icon = <ShieldCheck className="w-3 h-3 text-[var(--danger)]" />;
    badgeStyle = 'bg-[rgba(255,107,107,0.12)] text-[#ff8e8e] border-[rgba(255,107,107,0.3)]';
    tooltip = `Direct manual reply by operator ${adminIdentity || ''}`;
  } else if (origin === 'campaign') {
    label = 'Broadcast';
    icon = <Megaphone className="w-3 h-3 text-[#ffd93d]" />;
    badgeStyle = 'bg-[rgba(255,217,61,0.12)] text-[#ffe680] border-[rgba(255,217,61,0.3)]';
    tooltip = 'Scheduled broadcast message';
  } else if (origin === 'system') {
    label = 'System';
    icon = <Terminal className="w-3 h-3 text-[var(--text-muted)]" />;
    badgeStyle = 'bg-[rgba(255,255,255,0.06)] text-[var(--text-muted)] border-[rgba(255,255,255,0.1)]';
    tooltip = 'System status notification';
  }

  return (
    <div className="inline-flex items-center gap-1.5">
      <span
        title={tooltip}
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border cursor-help ${badgeStyle}`}
      >
        {icon}
        <span>{label}</span>
      </span>

      {/* Why / Context Explainability Button */}
      {aiRunId && onExplain && (
        <button
          type="button"
          onClick={onExplain}
          title="Explain AI decision, citations, and tools used"
          className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-[rgba(108,92,231,0.12)] hover:bg-[rgba(108,92,231,0.25)] text-[#c5bfff] border border-[rgba(108,92,231,0.3)] transition-colors cursor-pointer"
        >
          Why?
        </button>
      )}
    </div>
  );
};
