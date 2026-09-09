import { useEffect, useMemo, useRef, useState } from 'react';
import { api, ChatConversation, ChatMessage } from './api';
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

/** Build a unique key for list entry: group_id for groups, signal_id for DMs */
function contactKey(c: ChatConversation): string {
  return c.group_id ? `group::${c.group_id}` : `dm::${c.signal_id}`;
}

export default function ChatLogsPage() {
  const [loadingContacts, setLoadingContacts] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [contacts, setContacts] = useState<ChatConversation[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeKey, setActiveKey] = useState<string>('');
  const [draft, setDraft] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [totalMessages, setTotalMessages] = useState(0);
  const [unreadMap, setUnreadMap] = useState<Record<string, number>>({});
  const lastMessageCountRef = useRef<Record<string, number>>({});

  const currentContact = useMemo(
    () => contacts.find(c => contactKey(c) === activeKey),
    [contacts, activeKey]
  );

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
    const interval = setInterval(() => {
      void loadChats(true);
    }, 10000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
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

        // For groups: pass group_id. For DMs: pass signal_id with no group_id.
        const signalId = currentContact.group_id
          ? currentContact.group_id  // API accepts group_id in signal_id path param for groups
          : currentContact.signal_id;

        const data = await api.getChatMessages(
          signalId,
          currentContact.group_id || undefined,
          page,
          pageSize,
        );
        if (cancelled) return;
        setMessages(data.items);
        setTotalMessages(data.total);
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
    return () => {
      cancelled = true;
    };
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
        },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send message');
    } finally {
      setSending(false);
    }
  };

  const isGroupChat = !!currentContact?.group_id;

  return (
    <SidebarLayout title="Chat Logs (Audit)">
      {error && (
        <div className="form-error chat-banner-error">
          {error}
        </div>
      )}
      <div className="chat-container">
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
            {loadingContacts && (
              <div className="chat-status">Loading chats...</div>
            )}
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
                  {unread > 0 && (
                    <span className="contact-unread-badge">{unread} unread</span>
                  )}
                </button>
              );
            })}
          </div>
        </aside>

        <div className="chat-main">
          {currentContact ? (
            <>
              <div className="chat-header">
                <div className="chat-header-title">
                  <span style={{ marginRight: '0.4rem' }}>
                    {isGroupChat ? '👥' : '💬'}
                  </span>
                  {currentContact.display_name || currentContact.signal_id}
                </div>
                <div className="chat-header-subtitle">
                  {isGroupChat
                    ? `Group ID: ${currentContact.group_id}`
                    : `${currentContact.signal_id} · Direct Message`}
                </div>
              </div>

              <div className="chat-messages">
                {loadingMessages && (
                  <div className="chat-status">Loading messages...</div>
                )}
                {!loadingMessages && messages.map(msg => {
                  const isUser = msg.role === 'user';

                  return (
                    <article key={msg.id} className={`message ${isUser ? 'user' : 'bot'}`}>
                      {isUser && isGroupChat && msg.sender_name && (
                        <div className="message-sender">{msg.sender_name}</div>
                      )}
                      <div className="message-content">{msg.content}</div>
                      <div className="message-time">
                        {formatTime(msg.timestamp)} {isUser ? '' : '🤖'}
                      </div>
                    </article>
                  );
                })}

                <div className="chat-pagination">
                  <span>Total: {totalMessages}</span>
                  <div className="chat-pagination-controls">
                    <button className="btn-secondary" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1 || loadingMessages}>Prev</button>
                    <span className="chat-pagination-label">Page {page}</span>
                    <button className="btn-secondary" onClick={() => setPage(p => p + 1)} disabled={loadingMessages || page * pageSize >= totalMessages}>Next</button>
                    <button className="btn-secondary" onClick={() => {
                      if (!currentContact) return;
                      setError(null);
                      setLoadingMessages(true);
                      const signalId = currentContact.group_id
                        ? currentContact.group_id
                        : currentContact.signal_id;
                      void api.getChatMessages(signalId, currentContact.group_id || undefined, page, pageSize)
                        .then(data => {
                          setMessages(data.items);
                          setTotalMessages(data.total);
                        })
                        .catch(e => setError(e instanceof Error ? e.message : 'Failed to load messages'))
                        .finally(() => setLoadingMessages(false));
                    }} disabled={loadingMessages}>Retry</button>
                  </div>
                </div>
              </div>

              <div className="chat-composer">
                <div className="chat-composer-row">
                  <input
                    type="text"
                    placeholder="Takeover mode: Send message manually..."
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
                  />
                  <button
                    className="btn-primary chat-send-button"
                    onClick={handleSend}
                    disabled={sending || !draft.trim() || loadingMessages}
                  >
                    {sending ? 'Sending...' : 'Send'}
                  </button>
                </div>
                <div className="chat-composer-hint">
                  Manual takeover is active. New messages are stored in conversation history.
                </div>
              </div>
            </>
          ) : (
            <div className="chat-empty-state">
              Select a conversation to view logs
            </div>
          )}
        </div>
      </div>
    </SidebarLayout>
  );
}
