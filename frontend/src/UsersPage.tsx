import { FormEvent, useEffect, useState } from 'react';
import {
  api,
  ManagedUserActivityResponse,
  ManagedUserItem,
  ManagedUserUpdateRequest,
} from './api';
import SidebarLayout from './SidebarLayout';

const PAGE_SIZE = 20;

export default function UsersPage() {
  const [users, setUsers] = useState<ManagedUserItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [blockedOnly, setBlockedOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedUserIds, setSelectedUserIds] = useState<number[]>([]);
  const [batchRunning, setBatchRunning] = useState(false);
  const [activeUserId, setActiveUserId] = useState<number | null>(null);
  const [activity, setActivity] = useState<ManagedUserActivityResponse | null>(null);
  const [loadingActivity, setLoadingActivity] = useState(false);

  const [editing, setEditing] = useState<ManagedUserItem | null>(null);
  const [form, setForm] = useState<ManagedUserUpdateRequest>({});
  const [saving, setSaving] = useState(false);

  const loadUsers = async (targetPage = page) => {
    setLoading(true);
    setError('');
    try {
      const data = await api.getUsers(
        targetPage,
        PAGE_SIZE,
        search.trim(),
        blockedOnly ? true : undefined,
      );
      setUsers(data.items);
      setTotal(data.total);
      setPage(data.page);
      setSelectedUserIds(prev => prev.filter(id => data.items.some(item => item.id === id)));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadUsers(1);
  }, [blockedOnly]);

  const openEdit = (user: ManagedUserItem) => {
    setEditing(user);
    setForm({
      display_name: user.display_name || '',
      role: user.role,
      language: user.language,
      is_blocked: user.is_blocked,
      notes: user.notes || '',
    });
  };

  const closeEdit = () => {
    setEditing(null);
    setForm({});
  };

  const toggleSelection = (userId: number) => {
    setSelectedUserIds(prev => (
      prev.includes(userId)
        ? prev.filter(id => id !== userId)
        : [...prev, userId]
    ));
  };

  const loadActivity = async (userId: number) => {
    setActiveUserId(userId);
    setLoadingActivity(true);
    try {
      const detail = await api.getUserActivity(userId, 20, 10);
      setActivity(detail);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load user activity');
    } finally {
      setLoadingActivity(false);
    }
  };

  const runBatchAction = async (action: 'block' | 'unblock') => {
    if (selectedUserIds.length === 0) return;
    setBatchRunning(true);
    setError('');
    try {
      await api.batchUsersAction({ user_ids: selectedUserIds, action });
      await loadUsers(page);
      if (activeUserId) {
        await loadActivity(activeUserId);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Batch action failed');
    } finally {
      setBatchRunning(false);
    }
  };

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    if (!editing) return;
    setSaving(true);
    setError('');
    try {
      await api.updateUser(editing.id, form);
      closeEdit();
      await loadUsers(page);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update user');
    } finally {
      setSaving(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <SidebarLayout title="Users Management">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        <div className="form-group" style={{ marginBottom: 0, minWidth: '280px', maxWidth: '420px' }}>
          <label>Search (signal ID / name / notes)</label>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="keyword"
            onKeyDown={e => {
              if (e.key === 'Enter') {
                e.preventDefault();
                void loadUsers(1);
              }
            }}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'end', gap: '0.6rem' }}>
          <label className="form-check" style={{ marginBottom: 0 }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <input
                type="checkbox"
                checked={blockedOnly}
                onChange={e => setBlockedOnly(e.target.checked)}
              />
              Blocked only
            </span>
          </label>
          <button className="btn-secondary" onClick={() => { void loadUsers(1); }}>
            Search
          </button>
          <button
            className="btn-secondary"
            disabled={selectedUserIds.length === 0 || batchRunning}
            onClick={() => { void runBatchAction('block'); }}
            style={{ borderColor: 'rgba(255,107,107,0.45)', color: 'var(--danger)' }}
          >
            {batchRunning ? 'Running...' : `Block Selected (${selectedUserIds.length})`}
          </button>
          <button
            className="btn-secondary"
            disabled={selectedUserIds.length === 0 || batchRunning}
            onClick={() => { void runBatchAction('unblock'); }}
          >
            Unblock Selected
          </button>
        </div>
      </div>

      {error && <div className="form-error" style={{ marginBottom: '1rem' }}>{error}</div>}

      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  checked={users.length > 0 && selectedUserIds.length === users.length}
                  onChange={e => {
                    if (e.target.checked) {
                      setSelectedUserIds(users.map(user => user.id));
                    } else {
                      setSelectedUserIds([]);
                    }
                  }}
                />
              </th>
              <th>Signal ID</th>
              <th>Name</th>
              <th>Role</th>
              <th>Lang</th>
              <th>Status</th>
              <th>Last Seen</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="table-empty">Loading...</td></tr>
            ) : users.length === 0 ? (
              <tr><td colSpan={8} className="table-empty">No users found.</td></tr>
            ) : users.map(user => (
              <tr key={user.id}>
                <td>
                  <input
                    type="checkbox"
                    checked={selectedUserIds.includes(user.id)}
                    onChange={() => toggleSelection(user.id)}
                  />
                </td>
                <td>{user.signal_id}</td>
                <td>{user.display_name || '-'}</td>
                <td>{user.role}</td>
                <td>{user.language}</td>
                <td>
                  <span className={`stock-badge ${user.is_blocked ? 'out' : 'ok'}`}>
                    {user.is_blocked ? 'Blocked' : 'Active'}
                  </span>
                </td>
                <td>{new Date(user.last_seen).toLocaleString()}</td>
                <td>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <button className="btn-secondary" onClick={() => openEdit(user)}>Edit</button>
                    <button className="btn-secondary" onClick={() => { void loadActivity(user.id); }}>
                      Details
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="settings-group" style={{ marginTop: '1rem' }}>
        <h3 className="settings-group-title">User Activity</h3>
        {!activeUserId && (
          <div style={{ color: 'var(--text-muted)' }}>Select a user and click Details to inspect conversations and recent messages.</div>
        )}
        {loadingActivity && (
          <div style={{ color: 'var(--text-muted)' }}>Loading activity...</div>
        )}
        {!!activity && !loadingActivity && (
          <div style={{ display: 'grid', gap: '0.9rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(140px, 1fr))', gap: '0.75rem' }}>
              <div>Total conversations: <strong>{activity.conversation_count}</strong></div>
              <div>Total messages: <strong>{activity.message_count}</strong></div>
              <div>User: <strong>{activity.user.display_name || activity.user.signal_id}</strong></div>
            </div>

            <div>
              <div style={{ marginBottom: '0.45rem', fontWeight: 600 }}>Recent Conversations</div>
              <div style={{ display: 'grid', gap: '0.45rem', maxHeight: '220px', overflowY: 'auto' }}>
                {activity.recent_conversations.length === 0 && <span style={{ color: 'var(--text-muted)' }}>No conversations.</span>}
                {activity.recent_conversations.map(conversation => (
                  <div
                    key={conversation.conversation_id}
                    style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '0.55rem 0.7rem', display: 'grid', gridTemplateColumns: '1fr 120px', gap: '0.75rem' }}
                  >
                    <div>
                      <div style={{ fontWeight: 500 }}>{conversation.group_id ? `Group ${conversation.group_id}` : 'Direct message'}</div>
                      <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                        {conversation.last_message || '-'}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right', color: 'var(--text-secondary)', fontSize: '0.82rem' }}>
                      <div>{conversation.message_count} msgs</div>
                      <div>{new Date(conversation.updated_at).toLocaleString()}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div style={{ marginBottom: '0.45rem', fontWeight: 600 }}>Recent Messages</div>
              <div style={{ display: 'grid', gap: '0.45rem', maxHeight: '260px', overflowY: 'auto' }}>
                {activity.recent_messages.length === 0 && <span style={{ color: 'var(--text-muted)' }}>No messages.</span>}
                {activity.recent_messages.map(message => (
                  <div
                    key={message.id}
                    style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '0.55rem 0.7rem' }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                      <span style={{ color: 'var(--text-secondary)' }}>{message.role}</span>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{new Date(message.timestamp).toLocaleString()}</span>
                    </div>
                    <div>{message.content}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="pagination">
        <button disabled={page <= 1} onClick={() => { void loadUsers(page - 1); }}>←</button>
        <span>{page} / {totalPages}</span>
        <button disabled={page >= totalPages} onClick={() => { void loadUsers(page + 1); }}>→</button>
      </div>

      {editing && (
        <div className="modal-overlay" onClick={closeEdit}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h2>Edit User</h2>
            <form onSubmit={handleSave}>
              <div className="form-group">
                <label>Signal ID</label>
                <input value={editing.signal_id} disabled />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Display Name</label>
                  <input
                    value={form.display_name || ''}
                    onChange={e => setForm(prev => ({ ...prev, display_name: e.target.value }))}
                  />
                </div>
                <div className="form-group">
                  <label>Language</label>
                  <input
                    value={form.language || ''}
                    onChange={e => setForm(prev => ({ ...prev, language: e.target.value.slice(0, 10) }))}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Role</label>
                  <select
                    value={form.role || 'customer'}
                    onChange={e => setForm(prev => ({ ...prev, role: e.target.value }))}
                  >
                    <option value="customer">customer</option>
                    <option value="admin">admin</option>
                  </select>
                </div>
                <div className="form-group" style={{ display: 'flex', alignItems: 'center' }}>
                  <label className="form-check" style={{ marginBottom: 0 }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <input
                        type="checkbox"
                        checked={!!form.is_blocked}
                        onChange={e => setForm(prev => ({ ...prev, is_blocked: e.target.checked }))}
                      />
                      Block user
                    </span>
                  </label>
                </div>
              </div>

              <div className="form-group">
                <label>Notes</label>
                <textarea
                  rows={3}
                  value={form.notes || ''}
                  onChange={e => setForm(prev => ({ ...prev, notes: e.target.value }))}
                />
              </div>

              <div className="form-actions">
                <button type="button" className="btn-secondary" onClick={closeEdit}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </SidebarLayout>
  );
}
