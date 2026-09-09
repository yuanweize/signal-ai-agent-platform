import { useEffect, useState } from 'react';
import { api, SignalDevice } from './api';
import SidebarLayout from './SidebarLayout';

export default function DevicesPage() {
  const [devices, setDevices] = useState<SignalDevice[]>([]);
  const [profileName, setProfileName] = useState('');
  const [profileAbout, setProfileAbout] = useState('');
  const [loading, setLoading] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [profileRes, devicesRes] = await Promise.all([
        api.getProfile(),
        api.listDevices(),
      ]);
      setProfileName(profileRes.name || '');
      setProfileAbout(profileRes.about || '');
      setDevices(devicesRes.devices || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load account data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSavingProfile(true);
      setError(null);
      setSuccessMsg(null);
      await api.updateProfile({
        name: profileName || undefined,
        about: profileAbout || undefined,
      });
      setSuccessMsg('Profile updated successfully');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update profile');
    } finally {
      setSavingProfile(false);
    }
  };

  const handleRemoveDevice = async (deviceId: number) => {
    if (!window.confirm('Are you sure you want to unlink this device?')) return;
    try {
      setError(null);
      await api.removeDevice(deviceId);
      setDevices(prev => prev.filter(d => d.id !== deviceId));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to remove device');
    }
  };

  return (
    <SidebarLayout title="Devices & Account">
      {error && <div className="form-error">{error}</div>}
      {successMsg && <div className="form-success" style={{ color: '#4caf50', marginBottom: '1rem' }}>{successMsg}</div>}

      <div className="settings-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
        
        {/* Profile Section */}
        <section className="settings-section">
          <div className="section-header">
            <h2 className="section-title">Signal Profile</h2>
            <p className="section-subtitle">Update how your bot appears to other users.</p>
          </div>
          
          <form className="settings-form" onSubmit={handleUpdateProfile}>
            <div className="form-group">
              <label>Profile Name</label>
              <input
                type="text"
                className="settings-input"
                value={profileName}
                onChange={e => setProfileName(e.target.value)}
                placeholder="e.g. Signal Market Bot"
              />
            </div>
            
            <div className="form-group">
              <label>About / Bio</label>
              <textarea
                className="settings-input"
                rows={3}
                value={profileAbout}
                onChange={e => setProfileAbout(e.target.value)}
                placeholder="e.g. 24/7 Automated Shop"
              />
            </div>
            
            <button type="submit" className="btn-primary" disabled={savingProfile || loading}>
              {savingProfile ? 'Saving...' : 'Save Profile'}
            </button>
          </form>
        </section>

        {/* Devices Section */}
        <section className="settings-section">
          <div className="section-header">
            <h2 className="section-title">Linked Devices</h2>
            <p className="section-subtitle">Manage devices linked to this Signal account.</p>
          </div>

          {loading ? (
            <div>Loading devices...</div>
          ) : devices.length === 0 ? (
            <div className="empty-state" style={{ marginTop: '1rem' }}>No linked devices found.</div>
          ) : (
            <div className="table-container" style={{ marginTop: '1rem' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Device ID</th>
                    <th>Name</th>
                    <th>Created</th>
                    <th>Last Seen</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {devices.map(device => (
                    <tr key={device.id}>
                      <td>{device.id}</td>
                      <td>{device.name || 'Unknown'}</td>
                      <td>{device.created ? new Date(device.created).toLocaleDateString() : 'N/A'}</td>
                      <td>{device.lastSeen ? new Date(device.lastSeen).toLocaleDateString() : 'N/A'}</td>
                      <td>
                        <button 
                          className="btn-danger" 
                          style={{ padding: '0.25rem 0.5rem', fontSize: '0.85rem' }}
                          onClick={() => handleRemoveDevice(device.id)}
                        >
                          Unlink
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

      </div>
    </SidebarLayout>
  );
}
