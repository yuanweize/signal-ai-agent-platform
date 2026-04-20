import { useEffect, useState } from 'react';
import { api } from './api';
import SidebarLayout from './SidebarLayout';

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [botName, setBotName] = useState('MarketBot');
  const [aiEnabled, setAiEnabled] = useState(false);
  const [marketEnabled, setMarketEnabled] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [apiKeyMasked, setApiKeyMasked] = useState('');
  const [retentionDays, setRetentionDays] = useState(30);
  const [adAutomationEnabled, setAdAutomationEnabled] = useState(true);
  const [adMinIntervalMinutes, setAdMinIntervalMinutes] = useState(180);
  const [adQuietStart, setAdQuietStart] = useState(23);
  const [adQuietEnd, setAdQuietEnd] = useState(8);
  const [adBlacklistInput, setAdBlacklistInput] = useState('');
  const [cleanuping, setCleanuping] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);
  const [auditLogs, setAuditLogs] = useState<Array<{ id: number; created_at: string; actor: string; action: string; status: string }>>([]);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const loadSettings = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await api.getSettings();
        if (cancelled) return;

        setAiEnabled(data.is_ai_enabled);
        setMarketEnabled(data.is_market_enabled);
        setBotName(data.bot_name || 'MarketBot');
        setPrompt(data.ai_prompt || '');
        setApiKeyMasked(data.ai_api_key_masked || '');
        setRetentionDays(data.retention_days || 30);
        setAdAutomationEnabled(data.ad_automation_enabled ?? true);
        setAdMinIntervalMinutes(data.ad_min_interval_minutes ?? 180);
        setAdQuietStart(data.ad_quiet_hour_start ?? 23);
        setAdQuietEnd(data.ad_quiet_hour_end ?? 8);
        setAdBlacklistInput((data.ad_group_blacklist || []).join(', '));
        setApiKey('');

        const logs = await api.getAuditLogs(1, 20, 'settings.');
        if (!cancelled) {
          setAuditLogs(logs.items.map(item => ({
            id: item.id,
            created_at: item.created_at,
            actor: item.actor,
            action: item.action,
            status: item.status,
          })));
        }
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : 'Failed to load settings');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadSettings();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);

      const payload: {
        ai_prompt: string;
        is_ai_enabled: boolean;
        is_market_enabled: boolean;
        bot_name: string;
        retention_days: number;
        ad_automation_enabled: boolean;
        ad_min_interval_minutes: number;
        ad_quiet_hour_start: number;
        ad_quiet_hour_end: number;
        ad_group_blacklist: string[];
        ai_api_key?: string;
      } = {
        ai_prompt: prompt,
        bot_name: botName,
        is_ai_enabled: aiEnabled,
        is_market_enabled: marketEnabled,
        retention_days: retentionDays,
        ad_automation_enabled: adAutomationEnabled,
        ad_min_interval_minutes: adMinIntervalMinutes,
        ad_quiet_hour_start: adQuietStart,
        ad_quiet_hour_end: adQuietEnd,
        ad_group_blacklist: adBlacklistInput
          .split(',')
          .map(item => item.trim())
          .filter(Boolean),
      };

      if (apiKey.trim()) {
        payload.ai_api_key = apiKey.trim();
      }

      const updated = await api.updateSettings(payload);
      setApiKey('');
      setBotName(updated.bot_name || botName);
      setApiKeyMasked(updated.ai_api_key_masked || '');
      setRetentionDays(updated.retention_days || retentionDays);
      setAdAutomationEnabled(updated.ad_automation_enabled ?? adAutomationEnabled);
      setAdMinIntervalMinutes(updated.ad_min_interval_minutes ?? adMinIntervalMinutes);
      setAdQuietStart(updated.ad_quiet_hour_start ?? adQuietStart);
      setAdQuietEnd(updated.ad_quiet_hour_end ?? adQuietEnd);
      setAdBlacklistInput((updated.ad_group_blacklist || []).join(', '));
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);

      const logs = await api.getAuditLogs(1, 20, 'settings.');
      setAuditLogs(logs.items.map(item => ({
        id: item.id,
        created_at: item.created_at,
        actor: item.actor,
        action: item.action,
        status: item.status,
      })));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleRollback = async () => {
    try {
      setRollingBack(true);
      setError(null);
      const restored = await api.rollbackSettings();
      setAiEnabled(restored.is_ai_enabled);
      setMarketEnabled(restored.is_market_enabled);
      setBotName(restored.bot_name || 'MarketBot');
      setPrompt(restored.ai_prompt || '');
      setApiKeyMasked(restored.ai_api_key_masked || '');
      setRetentionDays(restored.retention_days || 30);
      setAdAutomationEnabled(restored.ad_automation_enabled ?? true);
      setAdMinIntervalMinutes(restored.ad_min_interval_minutes ?? 180);
      setAdQuietStart(restored.ad_quiet_hour_start ?? 23);
      setAdQuietEnd(restored.ad_quiet_hour_end ?? 8);
      setAdBlacklistInput((restored.ad_group_blacklist || []).join(', '));
      const logs = await api.getAuditLogs(1, 20, 'settings.');
      setAuditLogs(logs.items.map(item => ({
        id: item.id,
        created_at: item.created_at,
        actor: item.actor,
        action: item.action,
        status: item.status,
      })));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to rollback settings');
    } finally {
      setRollingBack(false);
    }
  };

  const handleCleanup = async (purgeAll: boolean) => {
    try {
      setCleanuping(true);
      setError(null);
      const result = await api.cleanupData(purgeAll);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
      const mode = purgeAll ? 'Full purge' : `Retention cleanup (${result.retention_days ?? retentionDays}d)`;
      setError(`${mode} completed. Deleted messages=${result.messages_deleted}, conversations=${result.conversations_deleted}, audit=${result.audit_logs_deleted}, campaignLogs=${result.campaign_logs_deleted}`);
      const logs = await api.getAuditLogs(1, 20, 'settings.');
      setAuditLogs(logs.items.map(item => ({
        id: item.id,
        created_at: item.created_at,
        actor: item.actor,
        action: item.action,
        status: item.status,
      })));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Cleanup failed');
    } finally {
      setCleanuping(false);
    }
  };

  return (
    <SidebarLayout title="Settings">
      {error && (
        <div className="form-error" style={{ marginBottom: '1rem' }}>
          {error}
        </div>
      )}

      <div className="settings-group">
        <h3 className="settings-group-title">Module Configuration</h3>
        
        <div className="setting-item">
          <div className="setting-info">
            <div className="setting-label">AI Responses (FEATURE_AI_ENABLED)</div>
            <div className="setting-desc">Enable or disable automatic AI responses to incoming messages.</div>
          </div>
          <div className="setting-action">
            <label className="switch">
              <input
                type="checkbox"
                checked={aiEnabled}
                onChange={e => setAiEnabled(e.target.checked)}
                disabled={loading || saving}
              />
              <span className="slider"></span>
            </label>
          </div>
        </div>

        <div className="setting-item">
          <div className="setting-info">
            <div className="setting-label">Market Catalog (FEATURE_MARKET_ENABLED)</div>
            <div className="setting-desc">Allow users to view products and place orders.</div>
          </div>
          <div className="setting-action">
            <label className="switch">
              <input
                type="checkbox"
                checked={marketEnabled}
                onChange={e => setMarketEnabled(e.target.checked)}
                disabled={loading || saving}
              />
              <span className="slider"></span>
            </label>
          </div>
        </div>
      </div>

      <div className="settings-group">
        <h3 className="settings-group-title">AI Engine Settings</h3>

        <div className="form-group" style={{ marginBottom: '1.5rem' }}>
          <label>Bot Name</label>
          <input
            type="text"
            value={botName}
            onChange={e => setBotName(e.target.value.slice(0, 80))}
            placeholder="Displayed bot name in system"
            disabled={loading || saving}
          />
        </div>
        
        <div className="form-group" style={{ marginBottom: '1.5rem' }}>
          <label>API Key</label>
          <input 
            type="password" 
            value={apiKey} 
            onChange={e => setApiKey(e.target.value)}
            placeholder={apiKeyMasked ? `Current: ${apiKeyMasked}` : 'Enter OpenAI-compatible API Key'}
            disabled={loading || saving}
          />
        </div>

        <div className="form-group">
          <label>Bot System Prompt</label>
          <textarea 
            rows={4}
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            placeholder="System instructions for the AI"
            disabled={loading || saving}
          />
          <div className="label-hint" style={{ marginTop: '0.5rem', marginLeft: 0 }}>
            This prompt defines the bot's personality and language.
          </div>
        </div>

        <div className="form-group" style={{ marginTop: '1rem' }}>
          <label>Data retention (days)</label>
          <input
            type="number"
            min={1}
            max={3650}
            value={retentionDays}
            onChange={e => setRetentionDays(Math.max(1, Number(e.target.value) || 1))}
            disabled={loading || saving}
          />
          <div className="label-hint" style={{ marginTop: '0.5rem', marginLeft: 0 }}>
            Chat and audit data older than this threshold are cleaned by retention policy.
          </div>
        </div>
      </div>

      <div className="settings-group">
        <h3 className="settings-group-title">Ad Campaign Controls</h3>

        <div className="setting-item">
          <div className="setting-info">
            <div className="setting-label">Ad automation enabled</div>
            <div className="setting-desc">Global switch for campaign broadcast APIs.</div>
          </div>
          <div className="setting-action">
            <label className="switch">
              <input
                type="checkbox"
                checked={adAutomationEnabled}
                onChange={e => setAdAutomationEnabled(e.target.checked)}
                disabled={loading || saving}
              />
              <span className="slider"></span>
            </label>
          </div>
        </div>

        <div className="form-group" style={{ marginTop: '1rem' }}>
          <label>Minimum interval between broadcasts to same group (minutes)</label>
          <input
            type="number"
            min={1}
            max={1440}
            value={adMinIntervalMinutes}
            onChange={e => setAdMinIntervalMinutes(Math.min(1440, Math.max(1, Number(e.target.value) || 1)))}
            disabled={loading || saving}
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
          <div className="form-group" style={{ marginTop: '1rem' }}>
            <label>Quiet hours start (0-23)</label>
            <input
              type="number"
              min={0}
              max={23}
              value={adQuietStart}
              onChange={e => setAdQuietStart(Math.min(23, Math.max(0, Number(e.target.value) || 0)))}
              disabled={loading || saving}
            />
          </div>
          <div className="form-group" style={{ marginTop: '1rem' }}>
            <label>Quiet hours end (0-23)</label>
            <input
              type="number"
              min={0}
              max={23}
              value={adQuietEnd}
              onChange={e => setAdQuietEnd(Math.min(23, Math.max(0, Number(e.target.value) || 0)))}
              disabled={loading || saving}
            />
          </div>
        </div>

        <div className="form-group" style={{ marginTop: '1rem' }}>
          <label>Group blacklist (comma separated group IDs)</label>
          <textarea
            rows={3}
            value={adBlacklistInput}
            onChange={e => setAdBlacklistInput(e.target.value)}
            placeholder="group-id-1, group-id-2"
            disabled={loading || saving}
          />
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem', alignItems: 'center' }}>
        {saved && <span style={{ color: 'var(--success)', fontSize: '0.9rem', fontWeight: 500 }}>✅ Settings Saved!</span>}
        <button
          onClick={handleRollback}
          className="btn-secondary"
          style={{ width: 'auto', padding: '0.7rem 1rem' }}
          disabled={loading || saving || rollingBack}
        >
          {rollingBack ? 'Rolling back...' : 'Rollback Last Change'}
        </button>
        <button
          onClick={handleSave}
          className="btn-primary"
          style={{ width: 'auto', padding: '0.7rem 2rem' }}
          disabled={loading || saving}
        >
          {saving ? 'Saving...' : loading ? 'Loading...' : 'Save Configuration'}
        </button>
      </div>

      <div className="settings-group" style={{ marginTop: '1rem' }}>
        <h3 className="settings-group-title">Data Cleanup</h3>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <button className="btn-secondary" onClick={() => { void handleCleanup(false); }} disabled={cleanuping}>Run retention cleanup</button>
          <button className="btn-secondary" style={{ borderColor: 'rgba(255,107,107,0.45)', color: 'var(--danger)' }} onClick={() => { void handleCleanup(true); }} disabled={cleanuping}>One-click purge chats + audit logs</button>
        </div>
      </div>

      <div className="settings-group" style={{ marginTop: '1rem' }}>
        <h3 className="settings-group-title">Audit Trail</h3>
        <div style={{ display: 'grid', gap: '0.5rem' }}>
          {auditLogs.length === 0 && <div style={{ color: 'var(--text-muted)' }}>No audit logs yet.</div>}
          {auditLogs.map(log => (
            <div key={log.id} style={{ display: 'grid', gridTemplateColumns: '1.5fr 1.5fr 1fr 0.8fr', gap: '0.75rem', padding: '0.6rem 0.8rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>{new Date(log.created_at).toLocaleString()}</span>
              <span>{log.action}</span>
              <span style={{ color: 'var(--text-secondary)' }}>{log.actor}</span>
              <span style={{ color: log.status === 'success' ? 'var(--success)' : 'var(--danger)' }}>{log.status}</span>
            </div>
          ))}
        </div>
      </div>
    </SidebarLayout>
  );
}
