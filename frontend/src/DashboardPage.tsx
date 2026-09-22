import { useEffect, useState } from 'react';
import {
  Radio,
  Bot,
  Package,
  ShieldCheck,
  Users,
  MessageSquare,
  MessagesSquare,
  Receipt,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from 'lucide-react';
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

const MODULE_INFO: Record<string, { icon: React.ComponentType<{ className?: string }>; label: string; desc: string }> = {
  signal: { icon: Radio, label: 'Signal', desc: 'Message listener' },
  ai: { icon: Bot, label: 'AI Engine', desc: 'LLM responses' },
  market: { icon: Package, label: 'Market', desc: 'Product catalog' },
  admin_2fa: { icon: ShieldCheck, label: '2FA', desc: 'Admin security' },
};

const STAT_CARDS: { key: keyof Stats; icon: React.ComponentType<{ className?: string }>; label: string }[] = [
  { key: 'users', icon: Users, label: 'Users' },
  { key: 'messages', icon: MessageSquare, label: 'Messages' },
  { key: 'products', icon: Package, label: 'Products' },
  { key: 'conversations', icon: MessagesSquare, label: 'Conversations' },
  { key: 'groups', icon: Users, label: 'Groups' },
  { key: 'orders', icon: Receipt, label: 'Orders' },
];

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    const loadDashboard = async () => {
      try {
        const [healthData, statsData] = await Promise.all([
          fetch('/health').then(r => r.json()),
          api.getStats(),
        ]);
        if (cancelled) return;
        setHealth(healthData);
        setStats(statsData);
        setError('');
      } catch {
        if (!cancelled) {
          setError('Backend offline');
        }
      }
    };

    void loadDashboard();
    const timer = setInterval(() => {
      void loadDashboard();
    }, 10000);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const features = stats?.features || health?.features;

  return (
    <SidebarLayout title="Dashboard Overview">
      {/* Connection Status */}
      <div className="status-strip">
        {error ? (
          <span className="status-indicator offline inline-flex items-center gap-1.5">
            <AlertCircle className="w-3.5 h-3.5 text-[var(--danger)]" />
            <span>Backend Offline</span>
          </span>
        ) : health ? (
          <span className="status-indicator online inline-flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-[var(--success)]" />
            <span>Connected (v{health.version})</span>
          </span>
        ) : (
          <span className="status-indicator loading inline-flex items-center gap-1.5">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-[var(--warning)]" />
            <span>Connecting...</span>
          </span>
        )}
      </div>

      {/* Module Status */}
      {features && (
        <section className="section">
          <h2 className="section-title">Modules</h2>
          <div className="module-row">
            {Object.entries(MODULE_INFO).map(([key, mod]) => {
              const isOn = features[key] ?? false;
              const IconComp = mod.icon;
              return (
                <div
                  key={key}
                  className={`module-chip ${isOn ? 'module-on' : 'module-off'}`}
                >
                  <span className="module-icon">
                    <IconComp className={`w-4 h-4 ${isOn ? 'text-[var(--success)]' : 'text-[var(--text-muted)]'}`} />
                  </span>
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
            {STAT_CARDS.map(card => {
              const IconComp = card.icon;
              return (
                <div key={card.key} className="stat-card">
                  <div className="stat-icon">
                    <IconComp className="w-5 h-5 text-[var(--accent)]" />
                  </div>
                  <div className="stat-value">{stats[card.key] as number}</div>
                  <div className="stat-label">{card.label}</div>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </SidebarLayout>
  );
}
