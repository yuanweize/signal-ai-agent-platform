import { useEffect, useState } from 'react';
import {
  Smartphone,
  RefreshCw,
  Save,
  Trash2,
  AlertCircle,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
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
                className="w-7 h-7 flex items-center justify-center rounded-lg text-xs bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-muted)] hover:text-white hover:border-[rgba(255,255,255,0.2)] transition-all cursor-pointer"
                onClick={loadProfile}
                disabled={loadingProfile}
                title="Refresh profile"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            }
          >
            {profileError && (
              <div className="bg-[rgba(255,107,107,0.12)] border border-[rgba(255,107,107,0.3)] text-[var(--danger)] px-3.5 py-2.5 rounded-xl text-xs flex items-center gap-2 mb-4">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{profileError}</span>
              </div>
            )}
            {profileSuccess && (
              <div className="bg-[rgba(0,214,143,0.12)] border border-[rgba(0,214,143,0.3)] text-[var(--success)] px-3.5 py-2.5 rounded-xl text-xs flex items-center gap-2 mb-4">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>{profileSuccess}</span>
              </div>
            )}

            {loadingProfile ? (
              <div className="py-12 text-center text-sm text-[var(--text-muted)] flex flex-col items-center justify-center gap-2">
                <div className="w-5 h-5 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
                <span>Loading profile...</span>
              </div>
            ) : (
              <form onSubmit={handleUpdateProfile} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                    Profile Display Name
                  </label>
                  <div className="relative">
                    <input
                      type="text"
                      className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] transition-all"
                      value={profileName}
                      onChange={e => setProfileName(e.target.value)}
                      placeholder="e.g. Signal Market Bot"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                    About / Bio
                  </label>
                  <textarea
                    className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] transition-all resize-none"
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
                    className="gap-1.5"
                  >
                    <Save className="w-3.5 h-3.5" />
                    <span>Save Profile</span>
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
                className="w-7 h-7 flex items-center justify-center rounded-lg text-xs bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-muted)] hover:text-white hover:border-[rgba(255,255,255,0.2)] transition-all cursor-pointer"
                onClick={loadDevices}
                disabled={loadingDevices}
                title="Refresh devices"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            }
          >
            {devicesError && (
              <div className="bg-[rgba(255,217,61,0.12)] border border-[rgba(255,217,61,0.3)] text-[#ffd93d] px-3.5 py-2.5 rounded-xl text-xs flex items-center gap-2 mb-4">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>{devicesError}</span>
              </div>
            )}

            {loadingDevices ? (
              <div className="py-12 text-center text-sm text-[var(--text-muted)] flex flex-col items-center justify-center gap-2">
                <div className="w-5 h-5 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
                <span>Loading linked devices...</span>
              </div>
            ) : devices.length === 0 ? (
              <div className="py-12 text-center text-sm text-[var(--text-muted)]">
                <Smartphone className="w-8 h-8 mx-auto mb-2 opacity-40" />
                <span>No linked devices found.</span>
              </div>
            ) : (
              <div className="border border-[var(--border)] rounded-xl overflow-hidden bg-[rgba(255,255,255,0.01)]">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-[var(--border)] bg-[rgba(255,255,255,0.03)] text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                      <th className="px-3.5 py-2.5">ID</th>
                      <th className="px-3.5 py-2.5">Device Name</th>
                      <th className="px-3.5 py-2.5">Created</th>
                      <th className="px-3.5 py-2.5">Last Seen</th>
                      <th className="px-3.5 py-2.5 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    {devices.map(device => (
                      <tr key={device.id} className="hover:bg-[rgba(255,255,255,0.02)] transition-colors">
                        <td className="px-3.5 py-3 font-mono text-[var(--accent)] font-semibold">#{device.id}</td>
                        <td className="px-3.5 py-3 font-medium text-[var(--text-primary)]">
                          <div className="flex items-center gap-2">
                            <Smartphone className="w-3.5 h-3.5 text-[var(--text-muted)]" />
                            <span>{device.name || 'Primary / Unknown'}</span>
                          </div>
                        </td>
                        <td className="px-3.5 py-3 text-[var(--text-secondary)]">{formatDate(device.created)}</td>
                        <td className="px-3.5 py-3 text-[var(--text-secondary)]">{formatDate(device.lastSeen)}</td>
                        <td className="px-3.5 py-3 text-right">
                          <button
                            type="button"
                            className="px-2.5 py-1 rounded-lg text-xs font-medium text-[var(--danger)] hover:bg-[rgba(255,107,107,0.15)] border border-transparent hover:border-[rgba(255,107,107,0.3)] transition-all cursor-pointer inline-flex items-center gap-1"
                            onClick={() => handleRemoveDevice(device.id)}
                          >
                            <Trash2 className="w-3 h-3" />
                            <span>Unlink</span>
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
