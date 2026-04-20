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

export default function ChatLogsPage() {
  const [loadingContacts, setLoadingContacts] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [contacts, setContacts] = useState<ChatConversation[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeContact, setActiveContact] = useState<string>('');
  const [draft, setDraft] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [totalMessages, setTotalMessages] = useState(0);
  const [unreadMap, setUnreadMap] = useState<Record<string, number>>({});
  const lastMessageCountRef = useRef<Record<string, number>>({});

  const currentContact = useMemo(
    () => contacts.find(c => c.signal_id === activeContact),
    [contacts, activeContact]
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
          nextCounts[`${item.signal_id}::${item.group_id || 'dm'}`] = item.message_count;
        });

        setUnreadMap(prevUnread => {
          const nextUnread = { ...prevUnread };
          data.items.forEach(item => {
            const key = `${item.signal_id}::${item.group_id || 'dm'}`;
            const prevCount = prevCounts[key] ?? item.message_count;
            const delta = Math.max(0, item.message_count - prevCount);
            const isActive =
              activeContact === item.signal_id &&
              (!!currentContact ? currentContact.group_id === item.group_id : !item.group_id);
            nextUnread[key] = isActive ? 0 : (nextUnread[key] || 0) + delta;
          });
          return nextUnread;
        });

        lastMessageCountRef.current = nextCounts;

        setContacts(data.items);
        if (data.items.length > 0) {
          setActiveContact(prev => prev || data.items[0].signal_id);
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
  }, [activeContact, currentContact?.group_id]);


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
        const data = await api.getChatMessages(
          currentContact.signal_id,
          currentContact.group_id,
          page,
          pageSize,
        );
        if (cancelled) return;
        setMessages(data.items);
        setTotalMessages(data.total);
        setUnreadMap(prev => ({ ...prev, [`${currentContact.signal_id}::${currentContact.group_id || 'dm'}`]: 0 }));
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
      const text = `${c.display_name || ''} ${c.signal_id} ${c.last_message || ''}`.toLowerCase();
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

  return (
    <SidebarLayout title="Chat Logs (Audit)">
      {error && (
        <div className="form-error" style={{ marginBottom: '1rem' }}>
          {error}
        </div>
      )}
      <div className="chat-container">
        {/* Sidebar Contacts */}
        <div className="chat-sidebar">
          <div style={{ padding: '1rem', borderBottom: '1px solid var(--border)', background: 'var(--bg-secondary)' }}>
            <input 
              type="text" 
              placeholder="Search conversations..." 
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{ width: '100%', padding: '0.6rem 1rem', borderRadius: '1rem', background: 'var(--bg-input)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
            />
          </div>
          <div className="chat-list">
            {loadingContacts && (
              <div style={{ padding: '1rem', color: 'var(--text-muted)' }}>Loading chats...</div>
            )}
            {!loadingContacts && filteredContacts.length === 0 && (
              <div style={{ padding: '1rem', color: 'var(--text-muted)' }}>No conversations found</div>
            )}
            {filteredContacts.map(contact => (
              <div 
                key={`${contact.signal_id}-${contact.group_id || 'dm'}`}
                className={`chat-contact ${activeContact === contact.signal_id ? 'active' : ''}`}
                onClick={() => {
                  setActiveContact(contact.signal_id);
                  setPage(1);
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div className="contact-name">{contact.display_name || contact.signal_id}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 500 }}>
                    {formatListTime(contact.last_message_at)}
                  </div>
                </div>
                <div className="contact-preview" style={{ color: 'var(--text-muted)' }}>
                  {contact.last_message || 'No messages yet'}
                </div>
                {!!unreadMap[`${contact.signal_id}::${contact.group_id || 'dm'}`] && (
                  <div style={{ marginTop: '0.4rem', fontSize: '0.75rem', color: 'var(--accent)', fontWeight: 600 }}>
                    {unreadMap[`${contact.signal_id}::${contact.group_id || 'dm'}`]} unread
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Chat Main Area */}
        <div className="chat-main">
          {currentContact ? (
            <>
              <div className="chat-header">
                <div>{currentContact.display_name || currentContact.signal_id}</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 'normal' }}>
                  {currentContact.group_id ? `${currentContact.signal_id} · ${currentContact.group_id}` : currentContact.signal_id}
                </div>
              </div>
              
              <div className="chat-messages">
                {loadingMessages && (
                  <div style={{ textAlign: 'center', fontSize: '0.9rem', color: 'var(--text-muted)', margin: '1rem 0' }}>
                    Loading messages...
                  </div>
                )}
                {!loadingMessages && messages.map(msg => {
                  const isUser = msg.role === 'user';
                  return (
                  <div key={msg.id} className={`message ${isUser ? 'user' : 'bot'}`}>
                    <div>{msg.content}</div>
                    <div className="message-time">{formatTime(msg.timestamp)} {isUser ? '' : '🤖'}</div>
                  </div>
                )})}

                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '1rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  <span>Total: {totalMessages}</span>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <button className="btn-secondary" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1 || loadingMessages}>Prev</button>
                    <span style={{ alignSelf: 'center' }}>Page {page}</span>
                    <button className="btn-secondary" onClick={() => setPage(p => p + 1)} disabled={loadingMessages || page * pageSize >= totalMessages}>Next</button>
                    <button className="btn-secondary" onClick={() => {
                      if (!currentContact) return;
                      setError(null);
                      setLoadingMessages(true);
                      void api.getChatMessages(currentContact.signal_id, currentContact.group_id, page, pageSize)
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

              <div style={{ padding: '1.25rem', borderTop: '1px solid var(--border)', background: 'var(--bg-secondary)' }}>
                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'stretch' }}>
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
                    style={{ 
                      flex: 1, 
                      padding: '0.8rem 1.25rem', 
                      borderRadius: 'var(--radius)', 
                      background: 'var(--bg-input)', 
                      border: '1px solid var(--border)', 
                      color: 'var(--text-primary)',
                      fontSize: '0.95rem'
                    }}
                    disabled={sending || loadingMessages}
                  />
                  <button 
                    className="btn-primary" 
                    onClick={handleSend} 
                    disabled={sending || !draft.trim() || loadingMessages}
                    style={{ 
                      width: 'auto', 
                      padding: '0 2.5rem', 
                      whiteSpace: 'nowrap', 
                      borderRadius: 'var(--radius)', 
                      margin: 0,
                      fontWeight: 600,
                      fontSize: '1rem',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center'
                    }}
                  >
                    {sending ? 'Sending...' : 'Send'}
                  </button>
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.75rem', textAlign: 'center' }}>
                  Manual takeover is active. New messages are stored in conversation history.
                </div>
              </div>
            </>
          ) : (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
              Select a conversation to view logs
            </div>
          )}
        </div>
      </div>
    </SidebarLayout>
  );
}
