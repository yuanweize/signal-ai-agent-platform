import { useEffect, useRef, useState, useCallback } from 'react';
import SidebarLayout from './SidebarLayout';
import {
  api,
  ConversationDTO,
  ConversationDetailDTO,
  MessageDTO,
} from './api';
import { ConversationMode } from './types/inbox';
import { ModeBadge, DeliveryBadge } from './components/ui/Badge';
import { Button } from './components/ui/Button';

export default function InboxPage() {
  // Conversations list state
  const [conversations, setConversations] = useState<ConversationDTO[]>([]);
  const [totalUnread, setTotalUnread] = useState(0);
  const [loadingList, setLoadingList] = useState(true);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<'all' | 'dm' | 'group'>('all');
  const [modeFilter, setModeFilter] = useState<'all' | 'auto' | 'manual' | 'paused'>('all');
  const [unreadOnly, setUnreadOnly] = useState(false);

  // Active conversation state
  const [activeConvId, setActiveConvId] = useState<number | null>(null);
  const [activeConv, setActiveConv] = useState<ConversationDetailDTO | null>(null);
  const [messages, setMessages] = useState<MessageDTO[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [hasMoreBefore, setHasMoreBefore] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);

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

  // Periodic polling for conversations list (every 10s)
  useEffect(() => {
    const timer = setInterval(() => {
      fetchConversations(true);
    }, 10000);
    return () => clearInterval(timer);
  }, [fetchConversations]);

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
      } catch (err) {
        if (!quiet) setErrorMsg(err instanceof Error ? err.message : 'Failed to load messages');
      } finally {
        if (!quiet) setLoadingMessages(false);
      }
    },
    []
  );

  // On conversation select
  useEffect(() => {
    if (activeConvId !== null) {
      fetchActiveMessages(activeConvId);
    } else {
      setActiveConv(null);
      setMessages([]);
    }
  }, [activeConvId, fetchActiveMessages]);

  // Real-time polling of active conversation messages (every 3s)
  useEffect(() => {
    if (!activeConvId) return;
    const timer = setInterval(() => {
      fetchActiveMessages(activeConvId, true);
    }, 3000);
    return () => clearInterval(timer);
  }, [activeConvId, fetchActiveMessages]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (!loadingOlder && messagesEndRef.current) {
      messagesEndRef.current?.scrollIntoView?.({ behavior: 'smooth' });
    }
  }, [messages, loadingOlder]);

  // Load older messages (cursor pagination)
  const handleLoadOlder = async () => {
    if (!activeConvId || messages.length === 0 || loadingOlder) return;
    const oldestId = messages[0].id;
    setLoadingOlder(true);
    try {
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

    const textToSend = inputText.trim();
    setSending(true);
    setErrorMsg(null);

    try {
      const sentMsg = await api.sendConversationMessage(activeConvId, textToSend);
      setInputText('');
      setMessages(prev => [...prev, sentMsg]);
      // Refresh list to update snippet
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
  const handleModeChange = async (newMode: 'auto' | 'manual' | 'paused') => {
    if (!activeConvId || !activeConv) return;
    try {
      const updated = await api.updateConversationMode(activeConvId, newMode);
      setActiveConv(prev => (prev ? { ...prev, mode: updated.mode } : null));
      setConversations(prev =>
        prev.map(c => (c.id === activeConvId ? { ...c, mode: updated.mode } : c))
      );
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to update conversation mode');
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
      <div className="relative flex h-[calc(100vh-8rem)] bg-base-100 rounded-xl shadow-md border border-base-200 overflow-hidden">
        {/* ============================================================== */}
        {/* LEFT COLUMN: Conversation List & Filters                      */}
        {/* ============================================================== */}
        <aside className={`${activeConvId ? 'hidden md:flex' : 'flex'} w-full md:w-80 lg:w-96 border-r border-base-200 flex-col bg-base-50 shrink-0`}>
          {/* Header & Search */}
          <div className="p-4 border-b border-base-200 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h2 className="font-bold text-lg text-base-content">Conversations</h2>
                {totalUnread > 0 && (
                  <span className="badge badge-primary badge-sm text-white font-bold">
                    {totalUnread} new
                  </span>
                )}
              </div>
              <button
                type="button"
                className="btn btn-ghost btn-xs text-base-content/60"
                onClick={() => fetchConversations()}
                title="Refresh conversations"
              >
                🔄
              </button>
            </div>

            <input
              type="text"
              placeholder="Search conversations..."
              className="input input-bordered input-sm w-full bg-base-100 text-sm"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />

            {/* Filter Chips */}
            <div className="flex items-center justify-between gap-1 text-xs">
              <div className="join">
                <button
                  type="button"
                  className={`btn btn-xs join-item ${typeFilter === 'all' ? 'btn-active btn-neutral' : 'btn-ghost'}`}
                  onClick={() => setTypeFilter('all')}
                >
                  All
                </button>
                <button
                  type="button"
                  className={`btn btn-xs join-item ${typeFilter === 'dm' ? 'btn-active btn-neutral' : 'btn-ghost'}`}
                  onClick={() => setTypeFilter('dm')}
                >
                  DMs
                </button>
                <button
                  type="button"
                  className={`btn btn-xs join-item ${typeFilter === 'group' ? 'btn-active btn-neutral' : 'btn-ghost'}`}
                  onClick={() => setTypeFilter('group')}
                >
                  Groups
                </button>
              </div>

              <button
                type="button"
                className={`btn btn-xs ${unreadOnly ? 'btn-primary text-white' : 'btn-outline border-base-300'}`}
                onClick={() => setUnreadOnly(!unreadOnly)}
              >
                Unread
              </button>
            </div>

            {/* Mode Filter Selector */}
            <div className="flex items-center gap-2 text-xs text-base-content/70">
              <span>Mode:</span>
              <select
                className="select select-bordered select-xs bg-base-100"
                value={modeFilter}
                onChange={e => setModeFilter(e.target.value as 'all' | ConversationMode)}
              >
                <option value="all">Any Mode</option>
                <option value="auto">Auto 🤖</option>
                <option value="manual">Manual ✋</option>
                <option value="paused">Paused ⏸</option>
              </select>
            </div>
          </div>

          {/* Conversation Item List */}
          <div className="flex-1 overflow-y-auto divide-y divide-base-200">
            {loadingList ? (
              <div className="p-8 text-center text-sm text-base-content/50">
                <span className="loading loading-spinner loading-md text-primary mb-2" />
                <p>Loading conversations...</p>
              </div>
            ) : conversations.length === 0 ? (
              <div className="p-8 text-center text-sm text-base-content/50">
                <span className="text-2xl block mb-2">📭</span>
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
                    className={`p-3.5 cursor-pointer transition-colors hover:bg-base-200/60 ${
                      isSelected ? 'bg-primary/10 border-l-4 border-primary' : ''
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-xl flex-shrink-0">{isGroup ? '👥' : '👤'}</span>
                        <div className="min-w-0">
                          <p className="font-semibold text-sm truncate text-base-content">
                            {conv.display_name}
                          </p>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <span className="badge badge-ghost badge-xs text-[10px]">
                              {isGroup ? 'Group' : 'DM'}
                            </span>
                            <ModeBadge mode={conv.mode} />
                            {conv.is_blocked && (
                              <span className="badge badge-error badge-xs text-white text-[10px]">
                                Blocked
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Right indicators */}
                      <div className="flex flex-col items-end gap-1 flex-shrink-0">
                        {conv.last_message_at && (
                          <span className="text-[10px] text-base-content/50">
                            {new Date(conv.last_message_at).toLocaleTimeString([], {
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </span>
                        )}
                        <div className="flex items-center gap-1">
                          {conv.has_failed_outbound && (
                            <span className="badge badge-error badge-xs text-white" title="Outbound message failed">
                              !
                            </span>
                          )}
                          {conv.unread_count > 0 && (
                            <span className="badge badge-primary badge-sm text-white font-bold px-1.5">
                              {conv.unread_count}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Snippet */}
                    <p className="text-xs text-base-content/60 truncate mt-2">
                      {conv.last_message || <span className="italic">No messages yet</span>}
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
        <section className={`${activeConvId ? 'flex' : 'hidden md:flex'} flex-1 flex-col bg-base-100 min-w-0`}>
          {activeConvId === null || activeConv === null ? (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-base-content/40">
              <span className="text-6xl mb-4">💬</span>
              <h3 className="text-lg font-semibold text-base-content/70">No Conversation Selected</h3>
              <p className="text-sm max-w-sm mt-1">
                Select a chat from the left sidebar to view message history, monitor AI replies, or manually take over.
              </p>
            </div>
          ) : (
            <>
              {/* Chat Header */}
              <div className="px-3 sm:px-6 py-3.5 border-b border-base-200 flex items-center justify-between bg-base-100 shadow-xs z-10">
                <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                  <button
                    type="button"
                    className="btn btn-ghost btn-xs md:hidden mr-0.5 px-1.5"
                    onClick={() => {
                      setActiveConvId(null);
                      setActiveConv(null);
                    }}
                    title="Back to conversations"
                  >
                    ←
                  </button>
                  <span className="text-2xl shrink-0">{activeConv.type === 'group' ? '👥' : '👤'}</span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-bold text-base text-base-content truncate">
                        {activeConv.display_name}
                      </h3>
                      <span className="badge badge-ghost badge-sm text-xs">
                        {activeConv.type === 'group' ? 'Group' : 'DM'}
                      </span>
                    </div>
                    <p className="text-xs text-base-content/50 truncate font-mono">
                      {activeConv.signal_id}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  {/* Mode switcher */}
                  <div className="flex items-center gap-2 bg-base-200/60 px-3 py-1.5 rounded-lg border border-base-200">
                    <span className="text-xs font-medium text-base-content/70">Takeover:</span>
                    <select
                      aria-label="Takeover mode"
                      className="select select-xs select-bordered bg-base-100 text-xs font-semibold"
                      value={activeConv.mode}
                      onChange={e => handleModeChange(e.target.value as ConversationMode)}
                    >
                      <option value="auto">🤖 Auto (AI)</option>
                      <option value="manual">✋ Manual (Human)</option>
                      <option value="paused">⏸ Paused (Mute)</option>
                    </select>
                  </div>

                  <button
                    type="button"
                    className="btn btn-ghost btn-sm text-base-content/70"
                    onClick={() => setShowDrawer(true)}
                  >
                    ℹ️ Details
                  </button>
                </div>
              </div>

              {/* Error banner */}
              {errorMsg && (
                <div className="bg-error/15 text-error px-4 py-2 text-xs flex justify-between items-center">
                  <span>{errorMsg}</span>
                  <button type="button" onClick={() => setErrorMsg(null)} className="font-bold">
                    ✕
                  </button>
                </div>
              )}

              {/* Blocked warning */}
              {activeConv.is_blocked && (
                <div className="bg-amber-500/10 border-b border-amber-500/20 text-amber-700 px-6 py-2 text-xs font-medium flex items-center gap-2">
                  <span>🚫</span>
                  <span>
                    This customer is blocked. Incoming messages are recorded, but AI auto-responses are suppressed.
                  </span>
                </div>
              )}

              {/* Messages Timeline */}
              <div
                ref={timelineRef}
                className="flex-1 overflow-y-auto p-6 space-y-4 bg-gradient-to-b from-base-50/50 to-base-100"
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
                  <div className="py-12 text-center text-sm text-base-content/50">
                    <span className="loading loading-spinner loading-md text-primary mb-2" />
                    <p>Loading messages...</p>
                  </div>
                ) : messages.length === 0 ? (
                  <div className="py-12 text-center text-sm text-base-content/50">
                    <p>No messages yet in this conversation.</p>
                  </div>
                ) : (
                  messages.map(msg => {
                    const isOutbound = msg.direction === 'outbound';
                    const isFailed = msg.delivery_status === 'failed';

                    return (
                      <div
                        key={msg.id}
                        className={`chat ${isOutbound ? 'chat-end' : 'chat-start'}`}
                      >
                        <div className="chat-header text-xs text-base-content/60 mb-1 flex items-center gap-2">
                          <span className="font-semibold">
                            {isOutbound
                              ? msg.actor === 'bot'
                                ? '🤖 AI Bot'
                                : '👤 Admin'
                              : msg.sender_name || 'Customer'}
                          </span>
                          <time className="text-[10px] text-base-content/40">
                            {new Date(msg.timestamp).toLocaleTimeString([], {
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </time>
                        </div>

                        <div
                          className={`chat-bubble max-w-lg text-sm leading-relaxed shadow-xs ${
                            isOutbound
                              ? isFailed
                                ? 'bg-red-50 text-red-900 border border-red-200'
                                : 'bg-primary text-white'
                              : 'bg-base-200 text-base-content'
                          }`}
                        >
                          {/* Text content */}
                          <div className="whitespace-pre-wrap break-words">{msg.content}</div>

                          {/* Attachments */}
                          {msg.attachments && msg.attachments.length > 0 && (
                            <div className="mt-2 space-y-1">
                              {msg.attachments.map(att => (
                                <div
                                  key={att.id}
                                  className="flex items-center gap-2 p-2 bg-black/10 rounded text-xs"
                                >
                                  <span>📎</span>
                                  <span className="font-medium truncate">
                                    {att.filename || 'attachment'}
                                  </span>
                                  {att.size && (
                                    <span className="opacity-75">
                                      ({Math.round(att.size / 1024)} KB)
                                    </span>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Reactions */}
                          {msg.reactions && msg.reactions.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-1.5 pt-1 border-t border-black/10">
                              {msg.reactions.map(rx => (
                                <span
                                  key={rx.id}
                                  className="badge badge-xs bg-black/20 text-white font-mono"
                                  title={`Reacted by ${rx.reactor_identity}`}
                                >
                                  {rx.emoji}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>

                        {/* Footer Status and Retry */}
                        <div className="chat-footer text-xs mt-1 flex items-center gap-2">
                          {isOutbound && <DeliveryBadge status={msg.delivery_status} />}
                          {isFailed && (
                            <button
                              type="button"
                              className="text-xs text-error font-bold underline cursor-pointer hover:text-error/80"
                              onClick={() => handleRetry(msg.id)}
                            >
                              Retry Now
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
              <div className="p-4 border-t border-base-200 bg-base-100">
                <form onSubmit={handleSendMessage} className="space-y-2">
                  <div className="relative">
                    <textarea
                      rows={2}
                      className="textarea textarea-bordered w-full text-sm resize-none focus:outline-none focus:border-primary pr-24"
                      placeholder="Type a manual reply... (Press Enter to send, Shift+Enter for newline)"
                      value={inputText}
                      onChange={e => setInputText(e.target.value)}
                      onKeyDown={handleKeyDown}
                      disabled={sending}
                    />
                    <div className="absolute right-3 bottom-3">
                      <Button
                        type="submit"
                        variant="primary"
                        size="sm"
                        disabled={!inputText.trim() || sending}
                        loading={sending}
                      >
                        Send 🚀
                      </Button>
                    </div>
                  </div>
                  <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-1 text-[11px] text-base-content/50 px-1">
                    <span>
                      Mode: <strong className="uppercase">{activeConv.mode}</strong> (Manual replies will be logged as Admin)
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
          <aside className="absolute inset-y-0 right-0 z-30 w-full sm:w-80 border-l border-base-200 bg-base-50 p-6 flex flex-col justify-between overflow-y-auto shadow-2xl md:static md:shadow-none">
            <div className="space-y-6">
              <div className="flex items-center justify-between border-b border-base-200 pb-3">
                <h3 className="font-bold text-base">Conversation Details</h3>
                <button
                  type="button"
                  className="btn btn-ghost btn-xs text-base-content/50"
                  onClick={() => setShowDrawer(false)}
                >
                  ✕
                </button>
              </div>

              <div>
                <span className="text-xs text-base-content/50 uppercase font-semibold">Display Name</span>
                <p className="font-semibold text-sm text-base-content mt-0.5">{activeConv.display_name}</p>
              </div>

              <div>
                <span className="text-xs text-base-content/50 uppercase font-semibold">Signal Identifier</span>
                <p className="text-xs font-mono bg-base-200 p-2 rounded mt-0.5 break-all">
                  {activeConv.signal_id}
                </p>
              </div>

              {activeConv.phone_number && (
                <div>
                  <span className="text-xs text-base-content/50 uppercase font-semibold">Phone</span>
                  <p className="text-sm mt-0.5">{activeConv.phone_number}</p>
                </div>
              )}

              {activeConv.signal_uuid && (
                <div>
                  <span className="text-xs text-base-content/50 uppercase font-semibold">Signal UUID</span>
                  <p className="text-xs font-mono text-base-content/70 mt-0.5 break-all">
                    {activeConv.signal_uuid}
                  </p>
                </div>
              )}

              {activeConv.type === 'group' && (
                <div className="bg-base-200/60 p-3 rounded-lg border border-base-200 space-y-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-base-content/60">Members:</span>
                    <strong className="text-base-content">{activeConv.members_count}</strong>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-base-content/60">Admins:</span>
                    <strong className="text-base-content">{activeConv.admins_count}</strong>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-base-content/60">Sync Status:</span>
                    <span className="badge badge-success badge-xs text-white">
                      {activeConv.sync_status || 'synced'}
                    </span>
                  </div>
                </div>
              )}

              <div>
                <span className="text-xs text-base-content/50 uppercase font-semibold">Stats</span>
                <p className="text-xs text-base-content/70 mt-1">
                  Total messages: <strong>{activeConv.message_count}</strong>
                </p>
                <p className="text-xs text-base-content/70 mt-0.5">
                  Created: {new Date(activeConv.created_at).toLocaleDateString()}
                </p>
              </div>

              {activeConv.notes && (
                <div>
                  <span className="text-xs text-base-content/50 uppercase font-semibold">Admin Notes</span>
                  <p className="text-xs bg-amber-50 p-2.5 rounded border border-amber-200 mt-1 text-amber-900 whitespace-pre-wrap">
                    {activeConv.notes}
                  </p>
                </div>
              )}
            </div>

            <Button
              variant="outline"
              size="sm"
              className="w-full mt-6"
              onClick={() => setShowDrawer(false)}
            >
              Close Drawer
            </Button>
          </aside>
        )}
      </div>
    </SidebarLayout>
  );
}
