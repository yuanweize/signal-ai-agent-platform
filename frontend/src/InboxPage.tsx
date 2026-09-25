import { useEffect, useRef, useState, useCallback } from 'react';
import {
  Search,
  RefreshCw,
  MessageSquare,
  User,
  Users,
  BellDot,
  ShieldCheck,
  Send,
  Info,
  X,
  ArrowLeft,
  RotateCw,
  SlidersHorizontal,
  Inbox,
  Sparkles,
} from 'lucide-react';
import SidebarLayout from './SidebarLayout';
import {
  api,
  ConversationDTO,
  ConversationDetailDTO,
  MessageDTO,
  AISuggestionDTO,
  AIRunExplainabilityDTO,
} from './api';
import { ConversationMode } from './types/inbox';
import { ModeBadge, DeliveryBadge } from './components/ui/Badge';
import { Button } from './components/ui/Button';
import { ProvenanceBadge } from './components/ProvenanceBadge';
import { ExplainabilityDrawer } from './components/ExplainabilityDrawer';
import { CopilotDraftCard } from './components/CopilotDraftCard';
import { TakeoverModeSelector } from './components/TakeoverModeSelector';
import { InboxAttachmentItem } from './components/InboxAttachmentItem';
import { StreamingCopilotCard } from './components/StreamingCopilotCard';
import { useRealtime } from './context/RealtimeContext';

export default function InboxPage() {
  const { status: realtimeStatus, lastEvent } = useRealtime();

  // Conversations list state
  const [conversations, setConversations] = useState<ConversationDTO[]>([]);
  const [totalUnread, setTotalUnread] = useState(0);
  const [loadingList, setLoadingList] = useState(true);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<'all' | 'dm' | 'group'>('all');
  const [modeFilter, setModeFilter] = useState<'all' | 'auto' | 'copilot' | 'manual' | 'paused'>('all');
  const [unreadOnly, setUnreadOnly] = useState(false);

  // Active conversation state
  const [activeConvId, setActiveConvId] = useState<number | null>(null);
  const [activeConv, setActiveConv] = useState<ConversationDetailDTO | null>(null);
  const [messages, setMessages] = useState<MessageDTO[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [hasMoreBefore, setHasMoreBefore] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);

  // Copilot state
  const [pendingSuggestion, setPendingSuggestion] = useState<AISuggestionDTO | null>(null);
  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [streamingAbortController, setStreamingAbortController] = useState<AbortController | null>(null);

  // Explainability drawer state
  const [selectedAIRun, setSelectedAIRun] = useState<AIRunExplainabilityDTO | null>(null);
  const [explainLoading, setExplainLoading] = useState(false);
  const [showExplainDrawer, setShowExplainDrawer] = useState(false);

  // Composer state
  const [inputText, setInputText] = useState('');
  const [sending, setSending] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Detail drawer
  const [showDrawer, setShowDrawer] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const timelineRef = useRef<HTMLDivElement>(null);

  // Fetch conversation list
  const fetchConversations = useCallback(async (quiet = false) => {
    if (!quiet) setLoadingList(true);
    try {
      const res = await api.getConversations({
        search: search || undefined,
        type: typeFilter === 'all' ? undefined : typeFilter,
        mode: modeFilter === 'all' ? undefined : modeFilter,
        unread_only: unreadOnly,
        limit: 100,
      });
      setConversations(res.items);
      setTotalUnread(res.total_unread);
    } catch (err) {
      if (!quiet) setErrorMsg(err instanceof Error ? err.message : 'Failed to load conversations');
    } finally {
      if (!quiet) setLoadingList(false);
    }
  }, [search, typeFilter, modeFilter, unreadOnly]);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  // Realtime SSE event listener
  useEffect(() => {
    if (!lastEvent) return;
    const event = lastEvent;

    if (
      event.type === 'message.received' ||
      event.type === 'message.sent' ||
      event.type === 'message.updated'
    ) {
      const payload = event.payload as any;
      if (payload?.conversation_id === activeConvId && payload?.message) {
        const incomingMsg = payload.message as MessageDTO;
        setMessages(prev => {
          const exists = prev.some(m => m.id === incomingMsg.id);
          if (exists) {
            return prev.map(m => (m.id === incomingMsg.id ? incomingMsg : m));
          }
          return [...prev, incomingMsg];
        });
      }
      fetchConversations(true);
    } else if (event.type === 'conversation.updated') {
      const payload = event.payload as any;
      if (payload?.conversation_id === activeConvId) {
        if (payload.mode && activeConv) {
          setActiveConv(prev => (prev ? { ...prev, mode: payload.mode } : null));
        }
      }
      fetchConversations(true);
    } else if (
      event.type === 'copilot.suggestion.created' ||
      event.type === 'copilot.suggestion.updated'
    ) {
      const payload = event.payload as any;
      if (payload?.conversation_id === activeConvId) {
        if (payload.suggestion) {
          setPendingSuggestion(payload.suggestion);
        } else if (activeConvId) {
          api.getPendingSuggestion(activeConvId).then(s => setPendingSuggestion(s)).catch(() => {});
        }
      }
    }
  }, [lastEvent, activeConvId, fetchConversations, activeConv]);

  // Periodic polling for conversations list (adaptive: 20s if SSE connected, 8s if disconnected)
  useEffect(() => {
    const intervalMs = realtimeStatus === 'connected' ? 20000 : 8000;
    const timer = setInterval(() => {
      fetchConversations(true);
    }, intervalMs);
    return () => clearInterval(timer);
  }, [fetchConversations, realtimeStatus]);

  // Fetch active conversation detail and messages
  const fetchActiveMessages = useCallback(
    async (convId: number, quiet = false) => {
      if (!quiet) setLoadingMessages(true);
      try {
        const [convDetail, msgRes] = await Promise.all([
          api.getConversation(convId),
          api.getConversationMessages(convId, { limit: 50 }),
        ]);
        setActiveConv(convDetail);
        setMessages(msgRes.items);
        setHasMoreBefore(msgRes.has_more_before);

        // Mark as read on server
        const newestMsgId = msgRes.newest_id ?? (msgRes.items.length > 0 ? msgRes.items[msgRes.items.length - 1].id : undefined);
        if (newestMsgId) {
          api.markConversationRead(convId, newestMsgId).then(() => {
            // Update local badge
            setConversations(prev =>
              prev.map(c => (c.id === convId ? { ...c, unread_count: 0 } : c))
            );
          });
        }

        // Check Copilot suggestion
        api.getPendingSuggestion(convId)
          .then(sug => setPendingSuggestion(sug))
          .catch(() => setPendingSuggestion(null));
      } catch (err) {
        if (!quiet) setErrorMsg(err instanceof Error ? err.message : 'Failed to load messages');
      } finally {
        if (!quiet) setLoadingMessages(false);
      }
    },
    []
  );

  // Copilot actions
  const handleAcceptSuggestion = async () => {
    if (!activeConvId || !pendingSuggestion) return;
    setSuggestionLoading(true);
    try {
      const sentMsg = await api.acceptSuggestion(activeConvId, pendingSuggestion.id);
      setMessages(prev => [...prev, sentMsg]);
      setPendingSuggestion(null);
      fetchConversations(true);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to accept AI draft');
    } finally {
      setSuggestionLoading(false);
    }
  };

  const handleEditSuggestionInComposer = (text: string) => {
    setInputText(text);
  };

  const handleRejectSuggestion = async () => {
    if (!activeConvId || !pendingSuggestion) return;
    setSuggestionLoading(true);
    try {
      await api.rejectSuggestion(activeConvId, 'operator_dismissed', pendingSuggestion.id);
      setPendingSuggestion(null);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to dismiss AI draft');
    } finally {
      setSuggestionLoading(false);
    }
  };

  // Streaming Copilot Draft Generation
  const handleGenerateStream = useCallback(async () => {
    if (!activeConvId || isStreaming) return;
    setIsStreaming(true);
    setStreamingText('');
    setPendingSuggestion(null);
    const ac = new AbortController();
    setStreamingAbortController(ac);
    try {
      const finalPayload = await api.generateSuggestionStream(
        activeConvId,
        (chunk) => {
          setStreamingText(chunk.accumulated || chunk.delta);
        },
        ac.signal
      );
      if (finalPayload && finalPayload.suggestion) {
        setPendingSuggestion(finalPayload.suggestion);
      } else {
        const refreshed = await api.getPendingSuggestion(activeConvId);
        setPendingSuggestion(refreshed);
      }
      setIsStreaming(false);
      setStreamingText(null);
      setStreamingAbortController(null);
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        setErrorMsg(e.message || 'Streaming failed');
      }
      setIsStreaming(false);
      setStreamingText(null);
      setStreamingAbortController(null);
    }
  }, [activeConvId, isStreaming]);

  const handleCancelStream = useCallback(() => {
    if (streamingAbortController) {
      streamingAbortController.abort();
      setStreamingAbortController(null);
    }
    setIsStreaming(false);
    setStreamingText(null);
  }, [streamingAbortController]);

  const handleRegenerateSuggestion = async () => {
    await handleGenerateStream();
  };

  const handleOpenExplainability = async (aiRunId: number) => {
    if (!activeConvId) return;
    setShowExplainDrawer(true);
    setExplainLoading(true);
    try {
      const detail = await api.getAIRunExplainability(activeConvId, aiRunId);
      setSelectedAIRun(detail);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to load AI trace');
      setShowExplainDrawer(false);
    } finally {
      setExplainLoading(false);
    }
  };

  // On conversation select
  useEffect(() => {
    if (activeConvId !== null) {
      fetchActiveMessages(activeConvId);
    } else {
      setActiveConv(null);
      setMessages([]);
      setPendingSuggestion(null);
    }
  }, [activeConvId, fetchActiveMessages]);

  // Real-time polling fallback of active conversation messages (25s if SSE connected, 5s if disconnected)
  useEffect(() => {
    if (activeConvId === null) return;
    const intervalMs = realtimeStatus === 'connected' ? 25000 : 5000;
    const timer = setInterval(() => {
      fetchActiveMessages(activeConvId, true);
    }, intervalMs);
    return () => clearInterval(timer);
  }, [activeConvId, fetchActiveMessages, realtimeStatus]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load older messages (cursor pagination)
  const handleLoadOlder = async () => {
    if (!activeConvId || messages.length === 0 || loadingOlder) return;
    setLoadingOlder(true);
    try {
      const oldestId = messages[0].id;
      const res = await api.getConversationMessages(activeConvId, {
        limit: 50,
        before_id: oldestId,
      });
      setMessages(prev => [...res.items, ...prev]);
      setHasMoreBefore(res.has_more_before);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to load older messages');
    } finally {
      setLoadingOlder(false);
    }
  };

  // Send message
  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputText.trim() || !activeConvId || sending) return;

    const content = inputText.trim();
    setSending(true);
    setErrorMsg(null);

    try {
      const newMsg = await api.sendConversationMessage(activeConvId, content);
      setMessages(prev => [...prev, newMsg]);
      setInputText('');
      fetchConversations(true);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to send message');
    } finally {
      setSending(false);
    }
  };

  // Handle Enter to send, Shift+Enter for newline
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Update conversation mode
  const handleModeChange = async (newMode: ConversationMode) => {
    if (!activeConvId) return;
    try {
      const updated = await api.updateConversationMode(activeConvId, newMode);
      setActiveConv(prev => (prev ? { ...prev, mode: updated.mode } : null));
      setConversations(prev =>
        prev.map(c => (c.id === activeConvId ? { ...c, mode: newMode } : c))
      );
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to change mode');
    }
  };

  // Retry failed outbound message
  const handleRetry = async (messageId: number) => {
    if (!activeConvId) return;
    try {
      const retried = await api.retryConversationMessage(activeConvId, messageId);
      setMessages(prev => prev.map(m => (m.id === messageId ? retried : m)));
      fetchConversations(true);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to retry message');
    }
  };

  return (
    <SidebarLayout title="Inbox">
      <div className="inbox-shell">
        {/* ============================================================== */}
        {/* LEFT COLUMN: Conversation List & Filters                      */}
        {/* ============================================================== */}
        <aside className={`${activeConvId ? 'hidden md:flex' : 'flex'} inbox-sidebar`}>
          {/* Header & Search */}
          <div className="p-4 border-b border-[var(--border)] space-y-3 bg-[rgba(255,255,255,0.01)]">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h2 className="font-bold text-sm text-[var(--text-primary)] tracking-wide">Conversations</h2>
                {totalUnread > 0 && (
                  <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-[rgba(108,92,231,0.3)] text-[#d9d2ff] border border-[rgba(108,92,231,0.5)]">
                    {totalUnread} new
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-mono border bg-[var(--bg-input)] border-[var(--border)]"
                  title={`Realtime transport: ${realtimeStatus}`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      realtimeStatus === 'connected'
                        ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]'
                        : realtimeStatus === 'connecting'
                        ? 'bg-amber-400 animate-pulse'
                        : 'bg-zinc-400'
                    }`}
                  />
                  <span className="text-[var(--text-muted)] text-[9px] uppercase tracking-wider">
                    {realtimeStatus === 'connected' ? 'SSE' : 'Poll'}
                  </span>
                </div>
                <button
                  type="button"
                  className="w-7 h-7 flex items-center justify-center rounded-lg text-xs bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-muted)] hover:text-white hover:border-[rgba(255,255,255,0.2)] transition-all cursor-pointer"
                  onClick={() => fetchConversations()}
                  title="Refresh conversations"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <div className="inbox-search-wrap">
              <span className="inbox-search-icon">
                <Search className="w-3.5 h-3.5" />
              </span>
              <input
                type="text"
                placeholder="Search conversations..."
                className="inbox-search-input"
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>

            {/* Filter Segmented Control */}
            <div className="grid grid-cols-4 gap-1 p-1 bg-[var(--bg-input)] rounded-xl border border-[var(--border)]">
              <button
                type="button"
                className={`flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                  typeFilter === 'all' && !unreadOnly
                    ? 'bg-[var(--accent)] text-white shadow-[0_2px_8px_var(--accent-glow)] font-semibold'
                    : 'text-[var(--text-secondary)] hover:text-white hover:bg-[rgba(255,255,255,0.04)]'
                }`}
                onClick={() => {
                  setTypeFilter('all');
                  setUnreadOnly(false);
                }}
              >
                <MessageSquare className="w-3.5 h-3.5" />
                <span>All</span>
              </button>

              <button
                type="button"
                className={`flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                  typeFilter === 'dm' && !unreadOnly
                    ? 'bg-[var(--accent)] text-white shadow-[0_2px_8px_var(--accent-glow)] font-semibold'
                    : 'text-[var(--text-secondary)] hover:text-white hover:bg-[rgba(255,255,255,0.04)]'
                }`}
                onClick={() => {
                  setTypeFilter('dm');
                  setUnreadOnly(false);
                }}
              >
                <User className="w-3.5 h-3.5" />
                <span>DMs</span>
              </button>

              <button
                type="button"
                className={`flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                  typeFilter === 'group' && !unreadOnly
                    ? 'bg-[var(--accent)] text-white shadow-[0_2px_8px_var(--accent-glow)] font-semibold'
                    : 'text-[var(--text-secondary)] hover:text-white hover:bg-[rgba(255,255,255,0.04)]'
                }`}
                onClick={() => {
                  setTypeFilter('group');
                  setUnreadOnly(false);
                }}
              >
                <Users className="w-3.5 h-3.5" />
                <span>Groups</span>
              </button>

              <button
                type="button"
                className={`flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                  unreadOnly
                    ? 'bg-[rgba(108,92,231,0.3)] text-[#d9d2ff] border border-[rgba(108,92,231,0.5)] shadow-[0_2px_8px_var(--accent-glow)] font-semibold'
                    : 'text-[var(--text-secondary)] hover:text-white hover:bg-[rgba(255,255,255,0.04)]'
                }`}
                onClick={() => setUnreadOnly(!unreadOnly)}
              >
                <BellDot className="w-3.5 h-3.5" />
                <span>Unread</span>
              </button>
            </div>

            {/* Mode Filter Selector */}
            <div className="flex items-center justify-between text-xs text-[var(--text-secondary)] pt-0.5">
              <div className="flex items-center gap-1.5">
                <SlidersHorizontal className="w-3 h-3 text-[var(--text-muted)]" />
                <span>Mode:</span>
              </div>
              <select
                className="select-custom px-2.5 py-1 rounded-lg bg-[var(--bg-input)] border border-[var(--border)] text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent)] cursor-pointer"
                value={modeFilter}
                onChange={e => setModeFilter(e.target.value as 'all' | ConversationMode)}
              >
                <option value="all">Any Mode</option>
                <option value="auto">Auto (AI)</option>
                <option value="copilot">Copilot</option>
                <option value="manual">Manual</option>
                <option value="paused">Paused</option>
              </select>
            </div>
          </div>

          {/* Conversation Item List */}
          <div className="flex-1 overflow-y-auto divide-y divide-[var(--border)]">
            {loadingList ? (
              <div className="p-8 text-center text-sm text-[var(--text-muted)]">
                <svg className="animate-spin h-6 w-6 mx-auto mb-3 text-[var(--accent)]" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <p>Loading conversations...</p>
              </div>
            ) : conversations.length === 0 ? (
              <div className="p-8 text-center text-sm text-[var(--text-muted)]">
                <Inbox className="w-8 h-8 mx-auto mb-2 opacity-40 text-[var(--text-muted)]" />
                <p>No conversations found</p>
              </div>
            ) : (
              conversations.map(conv => {
                const isSelected = conv.id === activeConvId;
                const isGroup = conv.type === 'group';

                return (
                  <div
                    key={conv.id}
                    onClick={() => setActiveConvId(conv.id)}
                    className={`inbox-conv-item ${isSelected ? 'active' : ''}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 border ${
                          isGroup
                            ? 'bg-[rgba(0,214,143,0.12)] border-[rgba(0,214,143,0.25)] text-[#00d68f]'
                            : 'bg-[rgba(108,92,231,0.14)] border-[rgba(108,92,231,0.3)] text-[#a29bfe]'
                        }`}>
                          {isGroup ? <Users className="w-4 h-4" /> : <User className="w-4 h-4" />}
                        </div>
                        <div className="min-w-0">
                          <p className="font-semibold text-sm truncate text-[var(--text-primary)]">
                            {conv.display_name}
                          </p>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <span className="px-1.5 py-0.2 text-[10px] font-medium rounded bg-[rgba(255,255,255,0.06)] text-[var(--text-muted)]">
                              {isGroup ? 'Group' : 'DM'}
                            </span>
                            <ModeBadge mode={conv.mode} />
                            {conv.is_blocked && (
                              <span className="px-1.5 py-0.2 text-[10px] font-semibold rounded bg-[rgba(255,107,107,0.2)] text-[var(--danger)] border border-[rgba(255,107,107,0.4)]">
                                Blocked
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Right indicators */}
                      <div className="flex flex-col items-end gap-1 flex-shrink-0">
                        {conv.last_message_at && (
                          <span className="text-[10px] text-[var(--text-muted)]">
                            {new Date(conv.last_message_at).toLocaleTimeString([], {
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </span>
                        )}
                        <div className="flex items-center gap-1">
                          {conv.has_failed_outbound && (
                            <span className="px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-[rgba(255,107,107,0.2)] text-[var(--danger)] border border-[rgba(255,107,107,0.4)]" title="Outbound message failed">
                              !
                            </span>
                          )}
                          {conv.unread_count > 0 && (
                            <span className="px-1.5 py-0.5 text-xs font-bold rounded-full bg-[var(--accent)] text-white shadow-[0_2px_8px_var(--accent-glow)]">
                              {conv.unread_count}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Snippet */}
                    <p className="text-xs text-[var(--text-secondary)] truncate mt-2 leading-relaxed">
                      {conv.last_message || <span className="italic opacity-60">No messages yet</span>}
                    </p>
                  </div>
                );
              })
            )}
          </div>
        </aside>

        {/* ============================================================== */}
        {/* RIGHT COLUMN: Active Chat Timeline & Composer                 */}
        {/* ============================================================== */}
        <section className={`${activeConvId ? 'flex' : 'hidden md:flex'} inbox-chat-main`}>
          {activeConvId === null || activeConv === null ? (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-[var(--text-muted)]">
              <div className="w-16 h-16 rounded-2xl bg-[rgba(108,92,231,0.08)] flex items-center justify-center mb-4 border border-[rgba(108,92,231,0.2)] shadow-[0_4px_20px_rgba(108,92,231,0.1)]">
                <MessageSquare className="w-8 h-8 text-[var(--accent)] opacity-80" />
              </div>
              <h3 className="text-lg font-semibold text-[var(--text-primary)]">No Conversation Selected</h3>
              <p className="text-sm max-w-sm mt-1.5 text-[var(--text-secondary)] leading-relaxed">
                Select a chat from the left sidebar to view message history, monitor AI replies, or manually take over.
              </p>
            </div>
          ) : (
            <>
              {/* Chat Header */}
              <div className="inbox-chat-header">
                <div className="flex items-center gap-3 min-w-0">
                  <button
                    type="button"
                    className="md:hidden p-1.5 rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-[rgba(255,255,255,0.06)] cursor-pointer"
                    onClick={() => {
                      setActiveConvId(null);
                      setActiveConv(null);
                    }}
                    title="Back to conversations"
                  >
                    <ArrowLeft className="w-4 h-4" />
                  </button>
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 border ${
                    activeConv.type === 'group'
                      ? 'bg-[rgba(0,214,143,0.12)] border-[rgba(0,214,143,0.25)] text-[#00d68f]'
                      : 'bg-[rgba(108,92,231,0.14)] border-[rgba(108,92,231,0.3)] text-[#a29bfe]'
                  }`}>
                    {activeConv.type === 'group' ? <Users className="w-5 h-5" /> : <User className="w-5 h-5" />}
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-bold text-base text-[var(--text-primary)] truncate">
                        {activeConv.display_name}
                      </h3>
                      <span className="px-2 py-0.5 text-[10px] font-medium rounded-full bg-[rgba(255,255,255,0.06)] text-[var(--text-muted)] border border-[var(--border)]">
                        {activeConv.type === 'group' ? 'Group' : 'DM'}
                      </span>
                    </div>
                    <p className="text-xs text-[var(--text-muted)] truncate font-mono mt-0.5">
                      {activeConv.signal_id}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  {/* Modern Takeover Mode Selector */}
                  <TakeoverModeSelector
                    mode={activeConv.mode}
                    onChange={handleModeChange}
                  />

                  <button
                    type="button"
                    className="px-3 py-1.5 text-xs font-medium rounded-lg text-[var(--text-secondary)] hover:text-white bg-[var(--bg-input)] hover:bg-[var(--bg-card-hover)] border border-[var(--border)] transition-all cursor-pointer flex items-center gap-1.5"
                    onClick={() => setShowDrawer(true)}
                  >
                    <Info className="w-3.5 h-3.5 text-[var(--accent)]" />
                    <span>Details</span>
                  </button>
                </div>
              </div>

              {/* Error banner */}
              {errorMsg && (
                <div className="bg-[rgba(255,107,107,0.12)] border-b border-[rgba(255,107,107,0.25)] text-[var(--danger)] px-4 py-2 text-xs flex justify-between items-center">
                  <span>{errorMsg}</span>
                  <button type="button" onClick={() => setErrorMsg(null)} className="font-bold hover:opacity-80 cursor-pointer">
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}

              {/* Blocked warning */}
              {activeConv.is_blocked && (
                <div className="bg-[rgba(255,217,61,0.08)] border-b border-[rgba(255,217,61,0.2)] text-[#ffe680] px-6 py-2.5 text-xs font-medium flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-[#ffd93d]" />
                  <span>
                    This customer is blocked. Incoming messages are recorded, but AI auto-responses are suppressed.
                  </span>
                </div>
              )}

              {/* Messages Timeline */}
              <div
                ref={timelineRef}
                className="inbox-timeline"
              >
                {/* Load older button */}
                {hasMoreBefore && (
                  <div className="text-center py-2">
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={handleLoadOlder}
                      loading={loadingOlder}
                    >
                      ↑ Load earlier messages
                    </Button>
                  </div>
                )}

                {loadingMessages && messages.length === 0 ? (
                  <div className="py-12 text-center text-sm text-[var(--text-muted)]">
                    <svg className="animate-spin h-6 w-6 mx-auto mb-3 text-[var(--accent)]" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    <p>Loading messages...</p>
                  </div>
                ) : messages.length === 0 ? (
                  <div className="py-12 text-center text-sm text-[var(--text-muted)]">
                    <p>No messages yet in this conversation.</p>
                  </div>
                ) : (
                  messages.map(msg => {
                    const isOutbound = msg.direction === 'outbound';
                    const isFailed = msg.delivery_status === 'failed';
                    const isAdmin = msg.actor === 'admin';

                    return (
                      <div
                        key={msg.id}
                        className={`flex flex-col ${isOutbound ? 'items-end' : 'items-start'}`}
                      >
                        <div className="text-xs text-[var(--text-secondary)] mb-1 flex items-center justify-between gap-2 px-1 w-full max-w-lg">
                          <ProvenanceBadge
                            origin={msg.origin}
                            actor={msg.actor}
                            model={msg.model}
                            promptVersion={msg.prompt_version}
                            adminIdentity={msg.admin_identity}
                            aiRunId={msg.ai_run_id}
                            onExplain={() => msg.ai_run_id && handleOpenExplainability(msg.ai_run_id)}
                          />
                          <time className="text-[10px] text-[var(--text-muted)] shrink-0">
                            {new Date(msg.timestamp).toLocaleTimeString([], {
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </time>
                        </div>

                        <div
                          className={
                            isOutbound
                              ? isFailed
                                ? 'inbox-bubble-failed'
                                : isAdmin
                                ? 'inbox-bubble-admin'
                                : 'inbox-bubble-bot'
                              : 'inbox-bubble-user'
                          }
                        >
                          {/* Text content */}
                          <div className="whitespace-pre-wrap break-words">{msg.content}</div>

                          {/* Attachments */}
                          {msg.attachments && msg.attachments.length > 0 && (
                            <div className="mt-2 space-y-1.5 w-full">
                              {msg.attachments.map(att => (
                                <InboxAttachmentItem key={att.id} attachment={att} />
                              ))}
                            </div>
                          )}

                          {/* Reactions */}
                          {msg.reactions && msg.reactions.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-1.5 pt-1 border-t border-[rgba(255,255,255,0.08)]">
                              {msg.reactions.map(rx => (
                                <span
                                  key={rx.id}
                                  className="px-1.5 py-0.5 rounded text-xs bg-[rgba(0,0,0,0.3)] text-white font-mono"
                                  title={`Reacted by ${rx.reactor_identity}`}
                                >
                                  {rx.emoji}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>

                        {/* Footer Status and Retry */}
                        <div className="text-xs mt-1 flex items-center gap-2 px-1">
                          {isOutbound && <DeliveryBadge status={msg.delivery_status} />}
                          {isFailed && (
                            <button
                              type="button"
                              className="text-xs text-[var(--danger)] font-bold underline cursor-pointer hover:brightness-125 inline-flex items-center gap-1"
                              onClick={() => handleRetry(msg.id)}
                            >
                              <RotateCw className="w-3 h-3" />
                              <span>Retry Now</span>
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Composer */}
              <div className="inbox-composer">
                {/* Streaming Copilot Card */}
                {isStreaming && (
                  <StreamingCopilotCard
                    text={streamingText}
                    onCancel={handleCancelStream}
                  />
                )}

                {/* Copilot Draft Suggestion Card */}
                {!isStreaming && pendingSuggestion && (
                  <CopilotDraftCard
                    suggestion={pendingSuggestion}
                    loading={suggestionLoading}
                    onAccept={handleAcceptSuggestion}
                    onEdit={handleEditSuggestionInComposer}
                    onReject={handleRejectSuggestion}
                    onRegenerate={handleRegenerateSuggestion}
                  />
                )}

                {/* Generator Trigger when in Copilot/Manual mode and no draft */}
                {!isStreaming && !pendingSuggestion && (activeConv.mode === 'copilot' || activeConv.mode === 'manual') && (
                  <div className="mb-2 flex justify-end">
                    <button
                      type="button"
                      onClick={handleGenerateStream}
                      disabled={suggestionLoading || sending}
                      className="px-2.5 py-1 text-xs font-semibold rounded-lg bg-[rgba(108,92,231,0.12)] hover:bg-[rgba(108,92,231,0.22)] text-[var(--accent-light)] border border-[rgba(108,92,231,0.25)] transition-all flex items-center gap-1.5 cursor-pointer shadow-sm"
                    >
                      <Sparkles className="w-3 h-3 text-[var(--accent)]" />
                      <span>Generate AI Draft (Stream)</span>
                    </button>
                  </div>
                )}

                <form onSubmit={handleSendMessage} className="space-y-2">
                  <div className="relative">
                    <textarea
                      rows={2}
                      className="inbox-composer-textarea pr-28"
                      placeholder="Type a manual reply... (Press Enter to send, Shift+Enter for newline)"
                      value={inputText}
                      onChange={e => setInputText(e.target.value)}
                      onKeyDown={handleKeyDown}
                      disabled={sending}
                    />
                    <div className="absolute right-2.5 bottom-3">
                      <Button
                        type="submit"
                        variant="primary"
                        size="sm"
                        disabled={!inputText.trim() || sending}
                        loading={sending}
                        className="gap-1.5"
                      >
                        <Send className="w-3.5 h-3.5" />
                        <span>Send</span>
                      </Button>
                    </div>
                  </div>
                  <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-1 text-[11px] text-[var(--text-muted)] px-1">
                    <span>
                      Mode: <strong className="text-[var(--text-primary)] uppercase">{activeConv.mode}</strong> (Manual replies will be logged as Admin)
                    </span>
                    <span>Enter to send · Shift+Enter for newline</span>
                  </div>
                </form>
              </div>
            </>
          )}
        </section>

        {/* ============================================================== */}
        {/* RIGHT DRAWER: Conversation Details                             */}
        {/* ============================================================== */}
        {showDrawer && activeConv && (
          <aside className="inbox-drawer absolute inset-y-0 right-0 shadow-2xl md:static md:shadow-none">
            <div className="space-y-5">
              <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
                <h3 className="font-bold text-base text-white">Conversation Details</h3>
                <button
                  type="button"
                  className="w-7 h-7 flex items-center justify-center rounded-lg text-xs bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-muted)] hover:text-white hover:border-[rgba(255,255,255,0.2)] transition-all cursor-pointer"
                  onClick={() => setShowDrawer(false)}
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>

              <div>
                <span className="text-[10px] text-[var(--text-muted)] uppercase font-semibold tracking-wider">Display Name</span>
                <p className="font-semibold text-sm text-[var(--text-primary)] mt-0.5">{activeConv.display_name}</p>
              </div>

              <div>
                <span className="text-[10px] text-[var(--text-muted)] uppercase font-semibold tracking-wider">Signal Identifier</span>
                <p className="text-xs font-mono bg-[var(--bg-input)] border border-[var(--border)] p-2 rounded-lg mt-0.5 break-all text-[var(--text-secondary)]">
                  {activeConv.signal_id}
                </p>
              </div>

              {activeConv.phone_number && (
                <div>
                  <span className="text-[10px] text-[var(--text-muted)] uppercase font-semibold tracking-wider">Phone</span>
                  <p className="text-sm mt-0.5 text-[var(--text-primary)]">{activeConv.phone_number}</p>
                </div>
              )}

              {activeConv.signal_uuid && (
                <div>
                  <span className="text-[10px] text-[var(--text-muted)] uppercase font-semibold tracking-wider">Signal UUID</span>
                  <p className="text-xs font-mono text-[var(--text-secondary)] mt-0.5 break-all">
                    {activeConv.signal_uuid}
                  </p>
                </div>
              )}

              {activeConv.type === 'group' && (
                <div className="bg-[var(--bg-input)] p-3 rounded-xl border border-[var(--border)] space-y-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-[var(--text-secondary)]">Members:</span>
                    <strong className="text-white">{activeConv.members_count}</strong>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-[var(--text-secondary)]">Admins:</span>
                    <strong className="text-white">{activeConv.admins_count}</strong>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-[var(--text-secondary)]">Sync Status:</span>
                    <span className="px-1.5 py-0.2 text-[10px] rounded bg-[rgba(0,214,143,0.16)] text-[#6effcf] border border-[rgba(0,214,143,0.35)]">
                      {activeConv.sync_status || 'synced'}
                    </span>
                  </div>
                </div>
              )}

              <div>
                <span className="text-[10px] text-[var(--text-muted)] uppercase font-semibold tracking-wider">Stats</span>
                <p className="text-xs text-[var(--text-secondary)] mt-1">
                  Total messages: <strong className="text-white">{activeConv.message_count}</strong>
                </p>
                <p className="text-xs text-[var(--text-secondary)] mt-0.5">
                  Created: {new Date(activeConv.created_at).toLocaleDateString()}
                </p>
              </div>

              {activeConv.notes && (
                <div>
                  <span className="text-[10px] text-[var(--text-muted)] uppercase font-semibold tracking-wider">Admin Notes</span>
                  <p className="text-xs bg-[rgba(255,217,61,0.08)] p-2.5 rounded-lg border border-[rgba(255,217,61,0.2)] mt-1 text-[#ffe680] whitespace-pre-wrap leading-relaxed">
                    {activeConv.notes}
                  </p>
                </div>
              )}
            </div>

            <Button
              variant="secondary"
              size="sm"
              className="w-full mt-6"
              onClick={() => setShowDrawer(false)}
            >
              Close Drawer
            </Button>
          </aside>
        )}

        {/* AI Explainability / Why Drawer */}
        <ExplainabilityDrawer
          run={selectedAIRun}
          isOpen={showExplainDrawer}
          onClose={() => setShowExplainDrawer(false)}
          loading={explainLoading}
        />
      </div>
    </SidebarLayout>
  );
}

