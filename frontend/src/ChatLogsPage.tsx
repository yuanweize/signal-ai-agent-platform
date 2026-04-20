import { useState } from 'react';
import SidebarLayout from './SidebarLayout';

interface Contact {
  id: string;
  name: string;
  phone: string;
  lastMessage: string;
  time: string;
  unread: boolean;
}

interface Message {
  id: string;
  text: string;
  isUser: boolean;
  time: string;
}

const MOCK_CONTACTS: Contact[] = [
  { id: '1', name: 'Alice Smith', phone: '+447123456789', lastMessage: 'Jak si mohu objednat?', time: '10:45', unread: true },
  { id: '2', name: 'Bob Johnson', phone: '+447987654321', lastMessage: 'Díky za pomoc!', time: 'Včera', unread: false },
  { id: '3', name: 'Charlie', phone: '+420777123456', lastMessage: 'Chci produkt B.', time: 'Út', unread: false },
];

const MOCK_MESSAGES: Message[] = [
  { id: '1', text: 'Dobrý den, potřeboval bych poradit.', isUser: true, time: '10:42' },
  { id: '2', text: 'Dobrý den! Jsem váš asistent. S čím vám mohu pomoci?', isUser: false, time: '10:42' },
  { id: '3', text: 'Jak si mohu objednat?', isUser: true, time: '10:45' },
];

export default function ChatLogsPage() {
  const [activeContact, setActiveContact] = useState<string>(MOCK_CONTACTS[0].id);

  const currentContact = MOCK_CONTACTS.find(c => c.id === activeContact);

  return (
    <SidebarLayout title="Chat Logs (Audit)">
      <div className="chat-container">
        {/* Sidebar Contacts */}
        <div className="chat-sidebar">
          <div style={{ padding: '1rem', borderBottom: '1px solid var(--border)', background: 'var(--bg-secondary)' }}>
            <input 
              type="text" 
              placeholder="Search conversations..." 
              style={{ width: '100%', padding: '0.6rem 1rem', borderRadius: '1rem', background: 'var(--bg-input)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
            />
          </div>
          <div className="chat-list">
            {MOCK_CONTACTS.map(contact => (
              <div 
                key={contact.id} 
                className={`chat-contact ${activeContact === contact.id ? 'active' : ''}`}
                onClick={() => setActiveContact(contact.id)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div className="contact-name">{contact.name || contact.phone}</div>
                  <div style={{ fontSize: '0.75rem', color: contact.unread ? 'var(--accent)' : 'var(--text-muted)', fontWeight: contact.unread ? 600 : 400 }}>
                    {contact.time}
                  </div>
                </div>
                <div className="contact-preview" style={{ fontWeight: contact.unread ? 600 : 400, color: contact.unread ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                  {contact.lastMessage}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Chat Main Area */}
        <div className="chat-main">
          {currentContact ? (
            <>
              <div className="chat-header">
                <div>{currentContact.name}</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 'normal' }}>{currentContact.phone}</div>
              </div>
              
              <div className="chat-messages">
                <div style={{ textAlign: 'center', fontSize: '0.8rem', color: 'var(--text-muted)', margin: '1rem 0' }}>
                  Today
                </div>
                
                {MOCK_MESSAGES.map(msg => (
                  <div key={msg.id} className={`message ${msg.isUser ? 'user' : 'bot'}`}>
                    <div>{msg.text}</div>
                    <div className="message-time">{msg.time} {msg.isUser ? '' : '🤖'}</div>
                  </div>
                ))}
              </div>

              <div style={{ padding: '1rem', borderTop: '1px solid var(--border)', background: 'var(--bg-secondary)' }}>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <input 
                    type="text" 
                    placeholder="Takeover mode: Send message manually..." 
                    style={{ flex: 1, padding: '0.8rem 1rem', borderRadius: 'var(--radius)', background: 'var(--bg-input)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
                    disabled
                  />
                  <button className="btn-primary" disabled style={{ opacity: 0.5 }}>Send</button>
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.5rem', textAlign: 'center' }}>
                  Manual takeover and real-time logs will be implemented in future backend updates.
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
