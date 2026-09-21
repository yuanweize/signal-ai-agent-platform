import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { api, ChatConversation, ChatMessage, ChatMessagesResponse } from './api';
import SidebarLayout from './SidebarLayout';

function formatTime(iso?: string): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatListTime(iso?: string): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  return sameDay
    ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : date.toLocaleDateString();
}

function contactKey(c: ChatConversation): string {
  return c.group_id ? `group::${c.group_id}` : `dm::${c.signal_id}`;
}

function modeBadge(mode: string): string {
  switch (mode) {
    case 'manual': return '✋ Manual';
    case 'paused': return '⏸ Paused';
    default: return '🤖 AI';
  }
}

function modeBadgeClass(mode: string): string {
  switch (mode) {
    case 'manual': return 'badge-manual';
    case 'paused': return 'badge-paused';
    default: return 'badge-auto';
  }
}

function deliveryIcon(status?: string | null): string {
  switch (status) {
    case 'sent': return '✓';
    case 'failed': return '✗';
    case 'pending': return '⏳';
    default: return '';
  }
}

export default function ChatLogsPage() {
  const [loadingContacts, setLoadingContacts] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [settingMode, setSettingMode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [contacts, setContacts] = useState<ChatConversation[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeKey, setActiveKey] = useState<string>('');
  const [activeConvId, setActiveConvId] = useState<number | null>(null);
  const [activeMode, setActiveMode] = useState<'auto' | 'manual' | 'paused'>('auto');
  const [draft, setDraft] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [totalMessages, setTotalMessages] = useState(0);
  const [unreadMap, setUnreadMap] = useState<Record<string, number>>({});
  const lastMessageCountRef = useRef<Record<string, number>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const currentContact = useMemo(
    () => contacts.find(c => contactKey(c) === activeKey),
    [contacts, activeKey]
  );

  // Auto-scroll to bottom when new messages load (only on last page)
  useEffect(() => {
    if (page * pageSize >= totalMessages) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, page, pageSize, totalMessages]);

  useEffect(() => {
    let cancelled = false;

    const loadChats = async (isBackground = false) => {
      try {
        if (!isBackground) setLoadingContacts(true);
        const data = await api.getChats(100);
        if (cancelled) return;

        const prevCounts = lastMessageCountRef.current;
        const nextCounts: Record<string, number> = {};
        data.items.forEach(item => {
          const key = contactKey(item);
          nextCounts[key] = item.message_count;
        });

        setUnreadMap(prevUnread => {
          const nextUnread = { ...prevUnread };
          data.items.forEach(item => {
            const key = contactKey(item);
            const prevCount = prevCounts[key] ?? item.message_count;
            const delta = Math.max(0, item.message_count - prevCount);
            const isActive = activeKey === key;
            nextUnread[key] = isActive ? 0 : (nextUnread[key] || 0) + delta;
          });
          return nextUnread;
        });

        lastMessageCountRef.current = nextCounts;
        setContacts(data.items);
        if (data.items.length > 0) {
          setActiveKey(prev => prev || contactKey(data.items[0]));
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Failed to load chats');
        }
      } finally {
        if (!cancelled && !isBackground) setLoadingContacts(false);
      }
    };

    loadChats();
    const interval = setInterval(() => { void loadChats(true); }, 10000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [activeKey]);

  useEffect(() => {
    let cancelled = false;
    if (!currentContact) {
      setMessages([]);
      return;
    }

    const loadMessages = async () => {
      try {
        setLoadingMessages(true);
        setError(null);

        const signalId = currentContact.group_id
          ? currentContact.group_id
          : currentContact.signal_id;

        const data: ChatMessagesResponse = await api.getChatMessages(
          signalId,
          currentContact.group_id || undefined,
          page,
          pageSize,
        );
        if (cancelled) return;
        setMessages(data.items);
        setTotalMessages(data.total);
        setActiveConvId(data.conversation_id ?? null);
        setActiveMode((data.mode as 'auto' | 'manual' | 'paused') || 'auto');
        setUnreadMap(prev => ({ ...prev, [contactKey(currentContact)]: 0 }));
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Failed to load messages');
        }
      } finally {
        if (!cancelled) setLoadingMessages(false);
      }
    };

    loadMessages();
    return () => { cancelled = true; };
  }, [currentContact?.signal_id, currentContact?.group_id, page, pageSize]);

  const filteredContacts = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    if (!keyword) return contacts;
    return contacts.filter(c => {
      const text = `${c.display_name || ''} ${c.signal_id} ${c.last_message || ''} ${c.group_id || ''}`.toLowerCase();
      return text.includes(keyword);
    });
  }, [contacts, search]);

  const handleSend = async () => {
    if (!currentContact || !draft.trim()) return;
    try {
      setSending(true);
      setError(null);
      await api.sendChatMessage(currentContact.signal_id, {
        message: draft.trim(),
        group_id: currentContact.group_id || undefined,
      });
      const justSent = draft.trim();
      setDraft('');
      setMessages(prev => [
        ...prev,
        {
          id: Date.now(),
          role: 'assistant',
          content: justSent,
          timestamp: new Date().toISOString(),
          delivery_status: 'sent',
        },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send message');
    } finally {
      setSending(false);
    }
  };

  const handleModeChange = useCallback(async (newMode: 'auto' | 'manual' | 'paused') => {
    if (!activeConvId || settingMode) return;
    try {
      setSettingMode(true);
      setError(null);
      await api.setConversationMode(activeConvId, newMode);
      setActiveMode(newMode);
      // Update the contact list entry too
      setContacts(prev => prev.map(c =>
        contactKey(c) === activeKey ? { ...c, mode: newMode } : c
      ));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to set mode');
    } finally {
      setSettingMode(false);
    }
  }, [activeConvId, activeKey, settingMode]);

  const isGroupChat = !!currentContact?.group_id;

  return (
    <SidebarLayout title="Chats">
      {error && (
        <div className="form-error chat-banner-error" style={{ margin: '0.5rem 1rem' }}>
          {error}
        </div>
      )}
      <div className="chat-container">
        {/* ---- Sidebar ---- */}
        <aside className="chat-sidebar">
          <div className="chat-sidebar-search">
            <input
              type="text"
              placeholder="Search conversations..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="chat-search-input"
            />
          </div>

          <div className="chat-list">
            {loadingContacts && <div className="chat-status">Loading chats...</div>}
            {!loadingContacts && filteredContacts.length === 0 && (
              <div className="chat-status">No conversations found</div>
            )}
            {filteredContacts.map(contact => {
              const key = contactKey(contact);
              const unread = unreadMap[key] || 0;
              const isActive = activeKey === key;
              const isGroup = !!contact.group_id;

              return (
                <button
                  type="button"
                  key={key}
                  className={`chat-contact ${isActive ? 'active' : ''}`}
                  onClick={() => {
                    setActiveKey(key);
                    setPage(1);
                  }}
                >
                  <div className="chat-contact-head">
                    <div className="contact-name">
                      <span style={{ marginRight: '0.35rem', fontSize: '0.9rem' }}>
                        {isGroup ? '👥' : '💬'}
                      </span>
                      {contact.display_name || contact.signal_id}
                    </div>
                    <div className="contact-time">{formatListTime(contact.last_message_at)}</div>
                  </div>
                  <div className="contact-preview">{contact.last_message || 'No messages yet'}</div>
                  <div style={{ display: 'flex', gap: '0.4rem', marginTop: '0.2rem', alignItems: 'center' }}>
                    {unread > 0 && (
                      <span className="contact-unread-badge">{unread}</span>
                    )}
                    <span className={`mode-badge ${modeBadgeClass(contact.mode || 'auto')}`} style={{ fontSize: '0.7rem' }}>
                      {modeBadge(contact.mode || 'auto')}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </aside>

        {/* ---- Chat main ---- */}
        <div className="chat-main">
          {currentContact ? (
            <>
              {/* Header */}
              <div className="chat-header">
                <div style={{ flex: 1 }}>
                  <div className="chat-header-title">
                    <span style={{ marginRight: '0.4rem' }}>
                      {isGroupChat ? '👥' : '💬'}
                    </span>
                    {currentContact.display_name || currentContact.signal_id}
                    <span className={`mode-badge ${modeBadgeClass(activeMode)}`} style={{ marginLeft: '0.6rem', fontSize: '0.8rem' }}>
                      {modeBadge(activeMode)}
                    </span>
                  </div>
                  <div className="chat-header-subtitle">
                    {isGroupChat
                      ? `Group · ${currentContact.group_id}`
                      : `DM · ${currentContact.signal_id}`}
                  </div>
                </div>

                {/* Mode switcher — real backend-persisted state */}
                <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                  {(['auto', 'manual', 'paused'] as const).map(m => (
                    <button
                      key={m}
                      className={`btn-secondary ${activeMode === m ? 'active' : ''}`}
                      style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem', opacity: activeMode === m ? 1 : 0.6 }}
                      onClick={() => handleModeChange(m)}
                      disabled={settingMode || activeConvId === null}
                      title={
                        m === 'auto' ? 'AI replies automatically' :
                        m === 'manual' ? 'Admin replies; AI is suppressed' :
                        'No auto-reply; messages recorded only'
                      }
                    >
                      {m === 'auto' ? '🤖 Auto' : m === 'manual' ? '✋ Manual' : '⏸ Pause'}
                    </button>
                  ))}
                </div>
              </div>

              {/* Messages */}
              <div className="chat-messages">
                {loadingMessages && <div className="chat-status">Loading messages...</div>}
                {!loadingMessages && messages.map(msg => {
                  const isUser = msg.role === 'user';
                  const isFailed = msg.delivery_status === 'failed';

                  return (
                    <article key={msg.id} className={`message ${isUser ? 'user' : 'bot'} ${isFailed ? 'message-failed' : ''}`}>
                      {isUser && isGroupChat && msg.sender_name && (
                        <div className="message-sender">{msg.sender_name}</div>
                      )}
                      <div className="message-content">{msg.content}</div>
                      <div className="message-time">
                        {formatTime(msg.timestamp)}
                        {!isUser && msg.delivery_status && (
                          <span
                            title={msg.delivery_error || msg.delivery_status}
                            style={{ marginLeft: '0.3rem', color: isFailed ? '#e53e3e' : undefined }}
                          >
                            {deliveryIcon(msg.delivery_status)}
                          </span>
                        )}
                        {isUser ? '' : ' 🤖'}
                      </div>
                      {isFailed && msg.delivery_error && (
                        <div style={{ color: '#e53e3e', fontSize: '0.7rem', marginTop: '0.2rem' }}>
                          Failed: {msg.delivery_error}
                        </div>
                      )}
                    </article>
                  );
                })}
                <div ref={messagesEndRef} />

                {/* Pagination */}
                <div className="chat-pagination">
                  <span>Total: {totalMessages}</span>
                  <div className="chat-pagination-controls">
                    <button className="btn-secondary" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1 || loadingMessages}>Prev</button>
                    <span className="chat-pagination-label">Page {page}</span>
                    <button className="btn-secondary" onClick={() => setPage(p => p + 1)} disabled={loadingMessages || page * pageSize >= totalMessages}>Next</button>
                  </div>
                </div>
              </div>

              {/* Composer */}
              <div className="chat-composer">
                <div className="chat-composer-row">
                  <textarea
                    placeholder={
                      activeMode === 'auto'
                        ? 'AI is active. Type to send manually anyway...'
                        : activeMode === 'manual'
                        ? 'Manual mode: send your reply...'
                        : 'Paused mode: send message...'
                    }
                    value={draft}
                    onChange={e => setDraft(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        void handleSend();
                      }
                    }}
                    className="chat-composer-input"
                    disabled={sending || loadingMessages}
                    rows={2}
                  />
                  <button
                    className="btn-primary chat-send-button"
                    onClick={handleSend}
                    disabled={sending || !draft.trim() || loadingMessages}
                  >
                    {sending ? 'Sending...' : 'Send'}
                  </button>
                </div>
                <div className="chat-composer-hint" style={{ color: activeMode === 'manual' ? '#2d9748' : undefined }}>
                  {activeMode === 'manual'
                    ? '✋ Manual mode active — AI is suppressed'
                    : activeMode === 'paused'
                    ? '⏸ Paused — no auto-reply'
                    : '🤖 AI auto-reply is active'}
                  {' · '}
                  <span style={{ fontSize: '0.75rem', opacity: 0.7 }}>Shift+Enter for newline</span>
                </div>
              </div>
            </>
          ) : (
            <div className="chat-empty-state">
              Select a conversation to view messages
            </div>
          )}
        </div>
      </div>
    </SidebarLayout>
  );
}
