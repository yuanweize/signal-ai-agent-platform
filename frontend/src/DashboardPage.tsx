import { useEffect, useState } from 'react';
import { api } from './api';
import SidebarLayout from './SidebarLayout';

interface Stats {
  users: number;
  products: number;
  conversations: number;
  messages: number;
  groups: number;
  orders: number;
  features: Record<string, boolean>;
}

interface HealthData {
  status: string;
  version: string;
  bot_name: string;
  features: Record<string, boolean>;
}

const MODULE_INFO: Record<string, { icon: string; label: string; desc: string }> = {
  signal: { icon: '📡', label: 'Signal', desc: 'Message listener' },
  ai: { icon: '🧠', label: 'AI Engine', desc: 'LLM responses' },
  market: { icon: '📦', label: 'Market', desc: 'Product catalog' },
  admin_2fa: { icon: '🔐', label: '2FA', desc: 'Admin security' },
};

const STAT_CARDS: { key: keyof Stats; icon: string; label: string }[] = [
  { key: 'users', icon: '👤', label: 'Users' },
  { key: 'messages', icon: '💬', label: 'Messages' },
  { key: 'products', icon: '📦', label: 'Products' },
  { key: 'conversations', icon: '🗂️', label: 'Conversations' },
  { key: 'groups', icon: '👥', label: 'Groups' },
  { key: 'orders', icon: '🧾', label: 'Orders' },
];

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch('/health')
      .then(r => r.json())
      .then(setHealth)
      .catch(() => setError('Backend offline'));

    api.getStats()
      .then(setStats)
      .catch(() => {});
  }, []);

  const features = health?.features || stats?.features;

  return (
    <SidebarLayout title="Dashboard Overview">
      {/* Connection Status */}
      <div className="status-strip">
        {error ? (
          <span className="status-indicator offline">⚫ Backend Offline</span>
        ) : health ? (
          <span className="status-indicator online">🟢 Connected (v{health.version})</span>
        ) : (
          <span className="status-indicator loading">🟡 Connecting...</span>
        )}
      </div>

      {/* Module Status */}
      {features && (
        <section className="section">
          <h2 className="section-title">Modules</h2>
          <div className="module-row">
            {Object.entries(MODULE_INFO).map(([key, mod]) => {
              const isOn = features[key] ?? false;
              return (
                <div
                  key={key}
                  className={`module-chip ${isOn ? 'module-on' : 'module-off'}`}
                >
                  <span className="module-icon">{mod.icon}</span>
                  <div className="module-text">
                    <span className="module-label">{mod.label}</span>
                    <span className="module-desc">{mod.desc}</span>
                  </div>
                  <span className={`module-dot ${isOn ? 'active' : 'inactive'}`} />
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Stats Grid */}
      {stats && (
        <section className="section">
          <h2 className="section-title">Statistics</h2>
          <div className="stats-grid">
            {STAT_CARDS.map(card => (
              <div key={card.key} className="stat-card">
                <div className="stat-icon">{card.icon}</div>
                <div className="stat-value">{stats[card.key] as number}</div>
                <div className="stat-label">{card.label}</div>
              </div>
            ))}
          </div>
        </section>
      )}
    </SidebarLayout>
  );
}
