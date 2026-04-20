import { useEffect, useState } from 'react';
import {
  api,
  CampaignBroadcastResponse,
  CampaignSummaryResponse,
  ChatConversation,
} from './api';
import SidebarLayout from './SidebarLayout';

export default function CampaignsPage() {
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [campaignName, setCampaignName] = useState('daily-promo');
  const [message, setMessage] = useState('');
  const [dryRun, setDryRun] = useState(true);
  const [groups, setGroups] = useState<string[]>([]);
  const [selectedGroups, setSelectedGroups] = useState<Record<string, boolean>>({});
  const [lastResult, setLastResult] = useState<CampaignBroadcastResponse | null>(null);
  const [summary, setSummary] = useState<CampaignSummaryResponse | null>(null);

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const [chats, campaignSummary] = await Promise.all([
        api.getChats(200),
        api.getCampaignSummary(),
      ]);

      const dedup = new Set<string>();
      chats.items.forEach((item: ChatConversation) => {
        if (item.group_id) dedup.add(item.group_id.replace(/^group\./, ''));
      });

      const groupList = Array.from(dedup).sort();
      setGroups(groupList);
      setSummary(campaignSummary);
      setSelectedGroups(prev => {
        if (Object.keys(prev).length > 0) return prev;
        const all: Record<string, boolean> = {};
        groupList.forEach(groupId => {
          all[groupId] = true;
        });
        return all;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load campaign data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const toggleGroup = (groupId: string) => {
    setSelectedGroups(prev => ({ ...prev, [groupId]: !prev[groupId] }));
  };

  const handleSend = async () => {
    const trimmedName = campaignName.trim();
    const trimmedMessage = message.trim();
    if (!trimmedName || !trimmedMessage) {
      setError('Campaign name and message are required.');
      return;
    }

    const targetGroupIds = groups.filter(groupId => selectedGroups[groupId]);
    if (targetGroupIds.length === 0) {
      setError('Select at least one target group.');
      return;
    }

    try {
      setSending(true);
      setError(null);
      const result = await api.runCampaignBroadcast({
        campaign_name: trimmedName,
        message: trimmedMessage,
        target_group_ids: targetGroupIds,
        dry_run: dryRun,
      });
      setLastResult(result);
      const campaignSummary = await api.getCampaignSummary();
      setSummary(campaignSummary);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Campaign broadcast failed');
    } finally {
      setSending(false);
    }
  };

  return (
    <SidebarLayout title="Campaigns">
      {error && <div className="form-error" style={{ marginBottom: '1rem' }}>{error}</div>}

      <div className="settings-group">
        <h3 className="settings-group-title">Broadcast Composer</h3>
        <div className="form-group" style={{ marginBottom: '1rem' }}>
          <label>Campaign Name</label>
          <input
            type="text"
            value={campaignName}
            onChange={e => setCampaignName(e.target.value)}
            placeholder="e.g. daily-promo"
            disabled={loading || sending}
          />
        </div>

        <div className="form-group" style={{ marginBottom: '1rem' }}>
          <label>Message</label>
          <textarea
            rows={4}
            value={message}
            onChange={e => setMessage(e.target.value)}
            placeholder="Campaign message to send into selected groups"
            disabled={loading || sending}
          />
        </div>

        <div className="setting-item" style={{ marginBottom: '1rem' }}>
          <div className="setting-info">
            <div className="setting-label">Dry run mode</div>
            <div className="setting-desc">Preview policy checks without sending real Signal messages.</div>
          </div>
          <div className="setting-action">
            <label className="switch">
              <input
                type="checkbox"
                checked={dryRun}
                onChange={e => setDryRun(e.target.checked)}
                disabled={loading || sending}
              />
              <span className="slider"></span>
            </label>
          </div>
        </div>

        <div className="form-group">
          <label>Target Groups ({groups.length})</label>
          <div style={{ display: 'grid', gap: '0.4rem', maxHeight: '220px', overflowY: 'auto', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '0.6rem' }}>
            {groups.length === 0 && <span style={{ color: 'var(--text-muted)' }}>No group conversations detected yet.</span>}
            {groups.map(groupId => (
              <label key={groupId} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input
                  type="checkbox"
                  checked={!!selectedGroups[groupId]}
                  onChange={() => toggleGroup(groupId)}
                  disabled={loading || sending}
                />
                <span>{groupId}</span>
              </label>
            ))}
          </div>
        </div>

        <div style={{ marginTop: '1rem', display: 'flex', justifyContent: 'flex-end' }}>
          <button
            className="btn-primary"
            onClick={() => { void handleSend(); }}
            disabled={loading || sending}
            style={{ width: 'auto', padding: '0.7rem 2rem' }}
          >
            {sending ? 'Running...' : dryRun ? 'Run Dry-Run' : 'Send Campaign'}
          </button>
        </div>
      </div>

      {lastResult && (
        <div className="settings-group" style={{ marginTop: '1rem' }}>
          <h3 className="settings-group-title">Last Broadcast Result</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(90px, 1fr))', gap: '0.75rem', marginBottom: '0.75rem' }}>
            <div>Attempted: <strong>{lastResult.attempted}</strong></div>
            <div>Sent: <strong>{lastResult.sent}</strong></div>
            <div>Skipped: <strong>{lastResult.skipped}</strong></div>
            <div>Failed: <strong>{lastResult.failed}</strong></div>
          </div>
          <div style={{ display: 'grid', gap: '0.45rem', maxHeight: '260px', overflowY: 'auto' }}>
            {lastResult.items.map((item, index) => (
              <div key={`${item.group_id}-${index}`} style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '0.5rem 0.7rem', display: 'grid', gridTemplateColumns: '1.5fr 0.8fr 1fr', gap: '0.75rem' }}>
                <span>{item.group_id}</span>
                <span>{item.status}</span>
                <span style={{ color: 'var(--text-secondary)' }}>{item.reason || '-'}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {summary && (
        <div className="settings-group" style={{ marginTop: '1rem' }}>
          <h3 className="settings-group-title">Recent Campaign Deliveries</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(100px, 1fr))', gap: '0.75rem', marginBottom: '0.75rem' }}>
            <div>Total attempts: <strong>{summary.total_attempts}</strong></div>
            <div>Total sent: <strong>{summary.total_sent}</strong></div>
            <div>Total failed: <strong>{summary.total_failed}</strong></div>
          </div>

          <div style={{ display: 'grid', gap: '0.45rem', maxHeight: '260px', overflowY: 'auto' }}>
            {summary.recent.length === 0 && <span style={{ color: 'var(--text-muted)' }}>No campaign delivery logs yet.</span>}
            {summary.recent.map(row => (
              <div key={row.id} style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '0.5rem 0.7rem', display: 'grid', gridTemplateColumns: '1.2fr 1fr 0.8fr 1fr', gap: '0.75rem' }}>
                <span>{new Date(row.created_at).toLocaleString()}</span>
                <span>{row.campaign_name}</span>
                <span>{row.status}</span>
                <span style={{ color: 'var(--text-secondary)' }}>{row.group_id}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </SidebarLayout>
  );
}
