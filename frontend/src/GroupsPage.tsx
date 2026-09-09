import { useEffect, useState } from 'react';
import { api, SignalGroup } from './api';
import SidebarLayout from './SidebarLayout';

export default function GroupsPage() {
  const [groups, setGroups] = useState<SignalGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal / form states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [newGroupMembers, setNewGroupMembers] = useState('');
  const [creating, setCreating] = useState(false);

  const loadGroups = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.listGroups();
      setGroups(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load groups');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadGroups();
  }, []);

  const handleCreateGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newGroupName.trim()) return;

    const membersList = newGroupMembers
      .split(',')
      .map(m => m.trim())
      .filter(m => m.startsWith('+') && m.length > 5);

    try {
      setCreating(true);
      setError(null);
      await api.createGroup(newGroupName, membersList);
      setShowCreateModal(false);
      setNewGroupName('');
      setNewGroupMembers('');
      await loadGroups();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create group');
    } finally {
      setCreating(false);
    }
  };

  return (
    <SidebarLayout title="Groups Management">
      <div className="section-header">
        <h2 className="section-title">Signal Groups</h2>
        <button className="btn-primary" onClick={() => setShowCreateModal(true)}>
          Create Group
        </button>
      </div>

      {error && <div className="form-error">{error}</div>}

      {showCreateModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h3>Create New Group</h3>
            <form onSubmit={handleCreateGroup}>
              <div className="form-group">
                <label>Group Name</label>
                <input
                  type="text"
                  required
                  value={newGroupName}
                  onChange={e => setNewGroupName(e.target.value)}
                  placeholder="e.g. VIP Customers"
                  className="settings-input"
                />
              </div>
              <div className="form-group">
                <label>Initial Members (comma-separated, incl. country code)</label>
                <input
                  type="text"
                  value={newGroupMembers}
                  onChange={e => setNewGroupMembers(e.target.value)}
                  placeholder="e.g. +447123456789, +12025550100"
                  className="settings-input"
                />
                <small style={{ display: 'block', marginTop: '0.5rem', color: '#888' }}>
                  Numbers must start with "+" to be valid Signal IDs.
                </small>
              </div>
              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowCreateModal(false)}
                  disabled={creating}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={creating}>
                  {creating ? 'Creating...' : 'Create Group'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {loading ? (
        <div>Loading groups...</div>
      ) : groups.length === 0 ? (
        <div className="empty-state">No groups found in the local database.</div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Group Name</th>
                <th>Group ID</th>
                <th>Description</th>
                <th>Created At</th>
              </tr>
            </thead>
            <tbody>
              {groups.map(group => (
                <tr key={group.id}>
                  <td>
                    <strong>{group.name || 'Unnamed Group'}</strong>
                  </td>
                  <td>
                    <code className="uuid-badge">{group.group_id.slice(0, 16)}...</code>
                  </td>
                  <td>{group.description || <span style={{ color: '#666' }}>None</span>}</td>
                  <td>{new Date(group.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SidebarLayout>
  );
}
