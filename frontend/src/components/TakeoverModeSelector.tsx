import React, { useState, useRef, useEffect } from 'react';
import { Bot, Sparkles, Hand, PauseCircle, ChevronDown, Check } from 'lucide-react';
import { ConversationMode } from '../types/inbox';

export interface TakeoverModeSelectorProps {
  mode: ConversationMode;
  onChange: (mode: ConversationMode) => void;
  disabled?: boolean;
  className?: string;
}

interface ModeMeta {
  key: ConversationMode;
  label: string;
  badge: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  badgeBg: string;
  badgeBorder: string;
  glow: string;
  dotColor: string;
}

const MODES: ModeMeta[] = [
  {
    key: 'auto',
    label: 'Auto (AI)',
    badge: 'AI Autonomous',
    description: 'AI handles customer replies autonomously with RAG knowledge & tools',
    icon: Bot,
    color: 'text-[#00d68f]',
    badgeBg: 'bg-[rgba(0,214,143,0.12)]',
    badgeBorder: 'border-[rgba(0,214,143,0.3)]',
    glow: 'shadow-[0_0_12px_rgba(0,214,143,0.18)]',
    dotColor: 'bg-[#00d68f]',
  },
  {
    key: 'copilot',
    label: 'Copilot (Human + AI)',
    badge: 'Draft Review',
    description: 'AI generates response drafts for human operator review & approval',
    icon: Sparkles,
    color: 'text-[#a29bfe]',
    badgeBg: 'bg-[rgba(108,92,231,0.16)]',
    badgeBorder: 'border-[rgba(108,92,231,0.35)]',
    glow: 'shadow-[0_0_12px_rgba(108,92,231,0.22)]',
    dotColor: 'bg-[#a29bfe]',
  },
  {
    key: 'manual',
    label: 'Manual (Human)',
    badge: 'Human Only',
    description: 'AI execution is muted; human operators reply directly to the customer',
    icon: Hand,
    color: 'text-[#ffd93d]',
    badgeBg: 'bg-[rgba(255,217,61,0.12)]',
    badgeBorder: 'border-[rgba(255,217,61,0.32)]',
    glow: 'shadow-[0_0_12px_rgba(255,217,61,0.18)]',
    dotColor: 'bg-[#ffd93d]',
  },
  {
    key: 'paused',
    label: 'Paused (Mute)',
    badge: 'Muted',
    description: 'All message responses and bot notifications are temporarily silenced',
    icon: PauseCircle,
    color: 'text-[#ff9999]',
    badgeBg: 'bg-[rgba(255,107,107,0.12)]',
    badgeBorder: 'border-[rgba(255,107,107,0.3)]',
    glow: 'shadow-[0_0_12px_rgba(255,107,107,0.16)]',
    dotColor: 'bg-[#ff6b6b]',
  },
];

export const TakeoverModeSelector: React.FC<TakeoverModeSelectorProps> = ({
  mode,
  onChange,
  disabled = false,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const currentMode = MODES.find(m => m.key === mode) || MODES[0];
  const CurrentIcon = currentMode.icon;

  // Handle clicking outside to close popover
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Handle Escape key to close (only when open)
  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  return (
    <div className={`relative inline-block text-left ${className}`} ref={dropdownRef}>
      {/* Hidden native select for accessibility and testing compatibility fallback */}
      <select
        aria-hidden="true"
        aria-label="Takeover mode"
        className="sr-only"
        value={mode}
        onChange={e => {
          const nextMode = e.target.value as ConversationMode;
          if (nextMode !== mode) {
            onChange(nextMode);
          }
        }}
        disabled={disabled}
        tabIndex={-1}
      >
        {MODES.map(m => (
          <option key={m.key} value={m.key}>
            {m.label}
          </option>
        ))}
      </select>

      {/* Styled Interactive Trigger */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen(!isOpen)}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        className={`group flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-all duration-200 cursor-pointer select-none ${
          currentMode.badgeBg
        } ${currentMode.badgeBorder} ${isOpen ? currentMode.glow : 'hover:brightness-110'} ${
          disabled ? 'opacity-50 cursor-not-allowed' : ''
        }`}
      >
        <span className="text-xs font-medium text-[var(--text-secondary)]">Takeover:</span>

        <div className="flex items-center gap-1.5">
          {/* Animated Pulsing Status Dot */}
          <span className="relative flex h-2 w-2">
            <span
              className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${currentMode.dotColor}`}
            />
            <span className={`relative inline-flex rounded-full h-2 w-2 ${currentMode.dotColor}`} />
          </span>

          <CurrentIcon className={`w-3.5 h-3.5 ${currentMode.color}`} />
          <span className={`text-xs font-semibold ${currentMode.color}`}>
            {currentMode.label}
          </span>
        </div>

        <ChevronDown
          className={`w-3.5 h-3.5 text-[var(--text-muted)] transition-transform duration-200 group-hover:text-[var(--text-secondary)] ${
            isOpen ? 'rotate-180' : ''
          }`}
        />
      </button>

      {/* Dropdown Popover Menu */}
      {isOpen && (
        <div
          role="menu"
          aria-label="Takeover options"
          className="absolute right-0 mt-2 w-80 rounded-xl bg-[rgba(26,26,46,0.96)] border border-[var(--border)] shadow-[0_16px_40px_rgba(0,0,0,0.6)] backdrop-blur-xl p-1.5 z-50 animate-in fade-in zoom-in-95 duration-150"
        >
          <div className="px-3 py-2 border-b border-[var(--border)] mb-1">
            <p className="text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">
              Conversation Takeover Mode
            </p>
            <p className="text-[11px] text-[var(--text-secondary)] mt-0.5">
              Control autonomous AI execution and human takeover for this chat
            </p>
          </div>

          <div className="space-y-1">
            {MODES.map(item => {
              const Icon = item.icon;
              const isSelected = item.key === mode;

              return (
                <button
                  key={item.key}
                  type="button"
                  role="menuitemradio"
                  aria-checked={isSelected}
                  onClick={() => {
                    if (item.key !== mode) {
                      onChange(item.key);
                    }
                    setIsOpen(false);
                  }}
                  className={`w-full flex items-start gap-3 p-2.5 rounded-lg text-left transition-all duration-150 cursor-pointer ${
                    isSelected
                      ? `${item.badgeBg} ${item.badgeBorder} border ${item.glow}`
                      : 'hover:bg-[rgba(255,255,255,0.04)] border border-transparent'
                  }`}
                >
                  <div
                    className={`p-1.5 rounded-md shrink-0 mt-0.5 border ${item.badgeBg} ${item.badgeBorder} ${item.color}`}
                  >
                    <Icon className="w-4 h-4" />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className={`text-xs font-bold ${isSelected ? item.color : 'text-[var(--text-primary)]'}`}>
                        {item.label}
                      </span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium border ${item.badgeBg} ${item.badgeBorder} ${item.color}`}>
                        {item.badge}
                      </span>
                    </div>
                    <p className="text-[11px] text-[var(--text-secondary)] mt-1 leading-snug">
                      {item.description}
                    </p>
                  </div>

                  {isSelected && (
                    <div className={`shrink-0 mt-1 ${item.color}`}>
                      <Check className="w-4 h-4" />
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
