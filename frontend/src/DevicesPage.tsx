import { useEffect, useState } from 'react';
import { api, SignalDevice } from './api';
import SidebarLayout from './SidebarLayout';
import { Card } from './components/ui/Card';
import { Button } from './components/ui/Button';

function formatDate(val?: number | string | null): string {
  if (!val) return 'N/A';
  if (typeof val === 'number') {
    // If seconds (< 10^11), convert to ms
    const ms = val < 100000000000 ? val * 1000 : val;
    return new Date(ms).toLocaleString();
  }
  const d = new Date(val);
  return isNaN(d.getTime()) ? String(val) : d.toLocaleString();
}

export default function DevicesPage() {
  // Profile state
  const [profileName, setProfileName] = useState('');
  const [profileAbout, setProfileAbout] = useState('');
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileSuccess, setProfileSuccess] = useState<string | null>(null);

  // Devices state - isolated from profile
  const [devices, setDevices] = useState<SignalDevice[]>([]);
  const [loadingDevices, setLoadingDevices] = useState(true);
  const [devicesError, setDevicesError] = useState<string | null>(null);

  const loadProfile = async () => {
    try {
      setLoadingProfile(true);
      setProfileError(null);
      const res = await api.getProfile();
      setProfileName(res.name || '');
      setProfileAbout(res.about || '');
    } catch (e) {
      setProfileError(e instanceof Error ? e.message : 'Failed to load profile');
    } finally {
      setLoadingProfile(false);
    }
  };

  const loadDevices = async () => {
    try {
      setLoadingDevices(true);
      setDevicesError(null);
      const res = await api.listDevices();
      setDevices(res.devices || []);
    } catch (e) {
      setDevicesError(e instanceof Error ? e.message : 'Failed to load devices');
    } finally {
      setLoadingDevices(false);
    }
  };

  useEffect(() => {
    // Load independently — failure in one does NOT block the other
    void loadProfile();
    void loadDevices();
  }, []);

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSavingProfile(true);
      setProfileError(null);
      setProfileSuccess(null);
      await api.updateProfile({
        name: profileName || undefined,
        about: profileAbout || undefined,
      });
      setProfileSuccess('Profile updated successfully');
      setTimeout(() => setProfileSuccess(null), 3000);
    } catch (e) {
      setProfileError(e instanceof Error ? e.message : 'Failed to update profile');
    } finally {
      setSavingProfile(false);
    }
  };

  const handleRemoveDevice = async (deviceId: number) => {
    if (!window.confirm(`Are you sure you want to unlink device #${deviceId}?`)) return;
    try {
      setDevicesError(null);
      await api.removeDevice(deviceId);
      setDevices(prev => prev.filter(d => d.id !== deviceId));
    } catch (e) {
      setDevicesError(e instanceof Error ? e.message : 'Failed to remove device');
    }
  };

  return (
    <SidebarLayout title="Devices & Account">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Profile Section */}
          <Card
            title="Signal Profile"
            subtitle="Update how your bot appears to Signal users"
            headerAction={
              <button
                type="button"
                className="btn btn-ghost btn-xs"
                onClick={loadProfile}
                disabled={loadingProfile}
              >
                ↻ Refresh
              </button>
            }
          >
            {profileError && (
              <div className="alert alert-error text-xs mb-4">
                <span>{profileError}</span>
              </div>
            )}
            {profileSuccess && (
              <div className="alert alert-success text-xs mb-4">
                <span>{profileSuccess}</span>
              </div>
            )}

            {loadingProfile ? (
              <div className="py-8 text-center text-sm text-base-content/50">
                <span className="loading loading-spinner loading-sm mr-2" />
                Loading profile...
              </div>
            ) : (
              <form onSubmit={handleUpdateProfile} className="space-y-4">
                <div>
                  <label className="label">
                    <span className="label-text font-medium text-xs">Profile Display Name</span>
                  </label>
                  <input
                    type="text"
                    className="input input-bordered input-sm w-full"
                    value={profileName}
                    onChange={e => setProfileName(e.target.value)}
                    placeholder="e.g. Signal Market Bot"
                  />
                </div>

                <div>
                  <label className="label">
                    <span className="label-text font-medium text-xs">About / Bio</span>
                  </label>
                  <textarea
                    className="textarea textarea-bordered textarea-sm w-full"
                    rows={3}
                    value={profileAbout}
                    onChange={e => setProfileAbout(e.target.value)}
                    placeholder="e.g. 24/7 Automated Shop Assistant"
                  />
                </div>

                <div className="pt-2">
                  <Button
                    type="submit"
                    variant="primary"
                    size="sm"
                    loading={savingProfile}
                    disabled={loadingProfile}
                  >
                    Save Profile
                  </Button>
                </div>
              </form>
            )}
          </Card>

          {/* Linked Devices Section */}
          <Card
            title="Linked Devices"
            subtitle="Devices currently linked to this Signal account"
            headerAction={
              <button
                type="button"
                className="btn btn-ghost btn-xs"
                onClick={loadDevices}
                disabled={loadingDevices}
              >
                ↻ Refresh
              </button>
            }
          >
            {devicesError && (
              <div className="alert alert-warning text-xs mb-4">
                <span>{devicesError}</span>
              </div>
            )}

            {loadingDevices ? (
              <div className="py-8 text-center text-sm text-base-content/50">
                <span className="loading loading-spinner loading-sm mr-2" />
                Loading linked devices...
              </div>
            ) : devices.length === 0 ? (
              <div className="py-8 text-center text-sm text-base-content/50">
                No linked devices found.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="table table-sm w-full">
                  <thead>
                    <tr className="text-xs text-base-content/70">
                      <th>ID</th>
                      <th>Device Name</th>
                      <th>Created</th>
                      <th>Last Seen</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {devices.map(device => (
                      <tr key={device.id} className="hover">
                        <td className="font-mono text-xs">#{device.id}</td>
                        <td className="font-medium text-xs">{device.name || 'Primary / Unknown'}</td>
                        <td className="text-xs text-base-content/70">{formatDate(device.created)}</td>
                        <td className="text-xs text-base-content/70">{formatDate(device.lastSeen)}</td>
                        <td>
                          <button
                            type="button"
                            className="btn btn-ghost btn-xs text-error"
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
          </Card>
        </div>
      </div>
    </SidebarLayout>
  );
}
