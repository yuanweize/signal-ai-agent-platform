import { useEffect, useState } from 'react';
import { api } from './api';
import SidebarLayout from './SidebarLayout';

function inferProvider(model: string): string {
  const value = (model || '').trim();
  if (!value) return 'unknown';
  if (value.includes('/')) return value.split('/')[0];
  if (value.startsWith('gpt-') || value.startsWith('o1') || value.startsWith('o3')) return 'openai';
  if (value.startsWith('claude-')) return 'anthropic';
  if (value.startsWith('qwen-')) return 'qwen';
  if (value.startsWith('deepseek-')) return 'deepseek';
  if (value.startsWith('gemini-')) return 'google';
  return 'other';
}

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [botName, setBotName] = useState('MarketBot');
  const [botDefaultLanguage, setBotDefaultLanguage] = useState('cs');
  const [signalApiUrl, setSignalApiUrl] = useState('');
  const [signalPhoneNumber, setSignalPhoneNumber] = useState('');
  const [signalApiToken, setSignalApiToken] = useState('');
  const [signalApiTokenMasked, setSignalApiTokenMasked] = useState('');
  const [aiEnabled, setAiEnabled] = useState(false);
  const [marketEnabled, setMarketEnabled] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [apiKeyMasked, setApiKeyMasked] = useState('');
  const [aiBaseUrl, setAiBaseUrl] = useState('https://api.openai.com/v1');
  const [aiProviderDetected, setAiProviderDetected] = useState('unknown');
  const [aiModel, setAiModel] = useState('gpt-4o');
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [modelProviderFilter, setModelProviderFilter] = useState('all');
  const [cachedModelPicker, setCachedModelPicker] = useState('');
  const [listedModelTotal, setListedModelTotal] = useState(0);
  const [modelsCachedAt, setModelsCachedAt] = useState<string | null>(null);
  const [aiTemperature, setAiTemperature] = useState(0.7);
  const [aiMaxTokens, setAiMaxTokens] = useState(1000);
  const [aiContextMessages, setAiContextMessages] = useState(20);
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
  const [testingSignal, setTestingSignal] = useState(false);
  const [signalTestResult, setSignalTestResult] = useState<{
    ok: boolean;
    message: string;
    status_code?: number | null;
    latency_ms: number;
    listener_running: boolean;
    listener_connected: boolean;
  } | null>(null);
  const [probingAi, setProbingAi] = useState(false);
  const [checkingModel, setCheckingModel] = useState(false);
  const [modelVerifyResult, setModelVerifyResult] = useState<{
    ok: boolean;
    model: string;
    effective_model?: string | null;
    effective_base_url?: string | null;
    checked_at: string;
    message: string;
    preview?: string | null;
    attempts: Array<{ base_url: string; model: string; status?: number | null; message: string }>;
  } | null>(null);
  const [probeResult, setProbeResult] = useState<{
    ok: boolean;
    provider_detected: string;
    requested_base_url?: string | null;
    candidate_base_urls?: string[];
    verification_base_candidates?: string[];
    effective_base_url?: string | null;
    effective_model?: string | null;
    listed_total?: number;
    models_count?: number;
    verified_total?: number;
    message: string;
    cached_at?: string | null;
    preview?: string | null;
    models?: string[];
    invalid_models?: Array<{ model: string; reason?: string }>;
    attempts: Array<{ base_url: string; model: string; status?: number | null; message: string }>;
  } | null>(null);

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
        setBotDefaultLanguage(data.bot_default_language || 'cs');
        setSignalApiUrl(data.signal_api_url || '');
        setSignalPhoneNumber(data.signal_phone_number || '');
        setSignalApiTokenMasked(data.signal_api_token_masked || '');
        setSignalApiToken('');
        setPrompt(data.ai_prompt || '');
        setApiKeyMasked(data.ai_api_key_masked || '');

        setAiBaseUrl(data.ai_api_base_url || 'https://api.openai.com/v1');
        setAiProviderDetected(data.ai_provider_detected || 'unknown');
        setAiModel(data.ai_model || 'gpt-4o');
        setModelOptions(Array.isArray(data.ai_models_cached) ? data.ai_models_cached : []);
        setListedModelTotal(Number(data.ai_models_listed_total || 0));
        setModelsCachedAt(data.ai_models_cached_at || null);
        setAiTemperature(data.ai_temperature ?? 0.7);
        setAiMaxTokens(data.ai_max_tokens ?? 1000);
        setAiContextMessages(data.ai_context_messages ?? 20);
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
        bot_default_language: string;
        signal_api_url: string;
        signal_phone_number: string;
        ai_api_base_url: string;
        ai_model: string;
        ai_temperature: number;
        ai_max_tokens: number;
        ai_context_messages: number;
        retention_days: number;
        ad_automation_enabled: boolean;
        ad_min_interval_minutes: number;
        ad_quiet_hour_start: number;
        ad_quiet_hour_end: number;
        ad_group_blacklist: string[];
        ai_api_key?: string;
        signal_api_token?: string;
      } = {
        ai_prompt: prompt,
        bot_name: botName,
        bot_default_language: botDefaultLanguage.trim(),
        is_ai_enabled: aiEnabled,
        is_market_enabled: marketEnabled,
        signal_api_url: signalApiUrl.trim(),
        signal_phone_number: signalPhoneNumber.trim(),
        ai_api_base_url: aiBaseUrl.trim(),
        ai_model: aiModel.trim(),
        ai_temperature: Math.min(2, Math.max(0, aiTemperature)),
        ai_max_tokens: Math.min(32000, Math.max(1, aiMaxTokens)),
        ai_context_messages: Math.min(200, Math.max(1, aiContextMessages)),
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
      if (signalApiToken.trim()) {
        payload.signal_api_token = signalApiToken.trim();
      }

      const updated = await api.updateSettings(payload);
      setSignalApiUrl(updated.signal_api_url || signalApiUrl);
      setSignalPhoneNumber(updated.signal_phone_number || signalPhoneNumber);
      setSignalApiTokenMasked(updated.signal_api_token_masked || '');
      setSignalApiToken('');
      setBotDefaultLanguage(updated.bot_default_language || botDefaultLanguage);
      setApiKeyMasked(updated.ai_api_key_masked || '');

      setAiBaseUrl(updated.ai_api_base_url || aiBaseUrl);
      setAiProviderDetected(updated.ai_provider_detected || 'unknown');
      setAiModel(updated.ai_model || aiModel);
      setModelOptions(Array.isArray(updated.ai_models_cached) ? updated.ai_models_cached : modelOptions);
      setListedModelTotal(Number(updated.ai_models_listed_total || listedModelTotal));
      setModelsCachedAt(updated.ai_models_cached_at || modelsCachedAt);
      setAiTemperature(updated.ai_temperature ?? aiTemperature);
      setAiMaxTokens(updated.ai_max_tokens ?? aiMaxTokens);
      setAiContextMessages(updated.ai_context_messages ?? aiContextMessages);
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
      setBotDefaultLanguage(restored.bot_default_language || 'cs');
      setSignalApiUrl(restored.signal_api_url || '');
      setSignalPhoneNumber(restored.signal_phone_number || '');
      setSignalApiTokenMasked(restored.signal_api_token_masked || '');
      setSignalApiToken('');
      setPrompt(restored.ai_prompt || '');
      setApiKeyMasked(restored.ai_api_key_masked || '');

      setAiBaseUrl(restored.ai_api_base_url || 'https://api.openai.com/v1');
      setAiProviderDetected(restored.ai_provider_detected || 'unknown');
      setAiModel(restored.ai_model || 'gpt-4o');
      setModelOptions(Array.isArray(restored.ai_models_cached) ? restored.ai_models_cached : []);
      setListedModelTotal(Number(restored.ai_models_listed_total || 0));
      setModelsCachedAt(restored.ai_models_cached_at || null);
      setAiTemperature(restored.ai_temperature ?? 0.7);
      setAiMaxTokens(restored.ai_max_tokens ?? 1000);
      setAiContextMessages(restored.ai_context_messages ?? 20);
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
      setError(`${mode} completed. Deleted messages=${result.messages_deleted}, conversations=${result.conversations_deleted}, audit=${result.audit_logs_deleted}, campaignLogs=${result.campaign_logs_deleted}, users=${result.users_deleted}, orders=${result.orders_deleted}, payments=${result.payments_deleted}, groups=${result.groups_deleted}`);
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

  const handleTestSignal = async () => {
    try {
      setTestingSignal(true);
      setError(null);
      const result = await api.testSignalConnection({
        signal_api_url: signalApiUrl.trim(),
        signal_phone_number: signalPhoneNumber.trim(),
        signal_api_token: signalApiToken.trim() ? signalApiToken.trim() : undefined,
      });
      setSignalTestResult(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Signal connection test failed');
    } finally {
      setTestingSignal(false);
    }
  };

  const handleProbeAi = async () => {
    try {
      setProbingAi(true);
      setError(null);
      setProbeResult(null);

      const result = await api.probeAiCompatibility({
        ai_api_base_url: aiBaseUrl.trim(),
        ai_api_key: apiKey.trim() ? apiKey.trim() : undefined,
      });
      setProbeResult(result);
      setAiProviderDetected(result.provider_detected || aiProviderDetected);
      setModelProviderFilter('all');
      setCachedModelPicker('');
      setModelOptions(Array.isArray(result.models) ? result.models : []);
      setListedModelTotal(Number(result.listed_total || 0));
      setModelsCachedAt(result.cached_at || result.probed_at || null);

      const latest = await api.getSettings();
      setModelOptions(Array.isArray(latest.ai_models_cached) ? latest.ai_models_cached : (Array.isArray(result.models) ? result.models : []));
      setListedModelTotal(Number(latest.ai_models_listed_total || result.listed_total || 0));
      setModelsCachedAt(latest.ai_models_cached_at || result.cached_at || result.probed_at || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'AI Base URL probe failed');
    } finally {
      setProbingAi(false);
    }
  };

  const handleVerifyModel = async (silent = false) => {
    const targetModel = aiModel.trim();
    if (!targetModel || checkingModel) return;
    try {
      setCheckingModel(true);
      if (!silent) {
        setError(null);
      }
      const result = await api.verifyAiModel({
        ai_api_base_url: aiBaseUrl.trim(),
        ai_model: targetModel,
        ai_api_key: apiKey.trim() ? apiKey.trim() : undefined,
      });
      setModelVerifyResult(result);
    } catch (e) {
      if (!silent) {
        setError(e instanceof Error ? e.message : 'Model verification failed');
      }
    } finally {
      setCheckingModel(false);
    }
  };

  useEffect(() => {
    const targetModel = aiModel.trim();
    if (!targetModel) return;
    if (!modelOptions.includes(targetModel)) return;

    const timer = setTimeout(() => {
      void handleVerifyModel(true);
    }, 700);

    return () => clearTimeout(timer);
  }, [aiModel, aiBaseUrl, modelOptions]);

  useEffect(() => {
    if (!modelVerifyResult) return;
    if (modelVerifyResult.model !== aiModel.trim()) {
      setModelVerifyResult(null);
    }
  }, [aiModel, modelVerifyResult]);

  const providerStats = Object.entries(
    modelOptions.reduce((acc, model) => {
      const key = inferProvider(model);
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {} as Record<string, number>)
  ).sort((a, b) => a[0].localeCompare(b[0]));

  const filteredModelOptions = modelProviderFilter === 'all'
    ? modelOptions
    : modelOptions.filter(model => inferProvider(model) === modelProviderFilter);

  const providerFilterOptions = [
    { key: 'all', label: `All providers (${modelOptions.length})` },
    ...providerStats.map(([provider, count]) => ({ key: provider, label: `${provider} (${count})` })),
  ];

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
            <div className="setting-label">AI Responses</div>
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
            <div className="setting-label">Market Catalog</div>
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
        <h3 className="settings-group-title">Signal Gateway Settings</h3>

        <div className="form-group" style={{ marginBottom: '1rem' }}>
          <label>Signal API URL</label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '0.6rem', alignItems: 'center' }}>
            <input
              type="text"
              value={signalApiUrl}
              onChange={e => setSignalApiUrl(e.target.value.slice(0, 500))}
              placeholder="http://signal-api:8080"
              disabled={loading || saving}
            />
            <button
              type="button"
              className="btn-secondary"
              onClick={handleTestSignal}
              disabled={loading || saving || testingSignal || !signalApiUrl.trim() || !signalPhoneNumber.trim()}
              style={{ width: 'auto', whiteSpace: 'nowrap', padding: '0.65rem 0.9rem' }}
            >
              {testingSignal ? 'Testing...' : 'Test Signal Connection'}
            </button>
          </div>
          {signalTestResult && (
            <div
              style={{
                marginTop: '0.75rem',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                padding: '0.75rem',
                background: 'rgba(255,255,255,0.02)',
                display: 'grid',
                gap: '0.3rem',
              }}
            >
              <div style={{ color: signalTestResult.ok ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>
                {signalTestResult.ok ? 'Signal Gateway Reachable' : 'Signal Gateway Unreachable'}
              </div>
              <div className="label-hint">Message: {signalTestResult.message}</div>
              {typeof signalTestResult.status_code === 'number' && (
                <div className="label-hint">HTTP status: {signalTestResult.status_code}</div>
              )}
              <div className="label-hint">Latency: {signalTestResult.latency_ms} ms</div>
              <div className="label-hint">
                Listener running: {signalTestResult.listener_running ? 'yes' : 'no'} · connected: {signalTestResult.listener_connected ? 'yes' : 'no'}
              </div>
            </div>
          )}
        </div>

        <div className="form-group" style={{ marginBottom: '1rem' }}>
          <label>Signal Phone Number</label>
          <input
            type="text"
            value={signalPhoneNumber}
            onChange={e => setSignalPhoneNumber(e.target.value.slice(0, 64))}
            placeholder="+420123456789"
            disabled={loading || saving}
          />
        </div>

        <div className="form-group" style={{ marginBottom: '1rem' }}>
          <label>Signal API Token</label>
          <input
            type="password"
            value={signalApiToken}
            onChange={e => setSignalApiToken(e.target.value)}
            placeholder={signalApiTokenMasked ? `Current: ${signalApiTokenMasked}` : 'Optional if gateway is public'}
            disabled={loading || saving}
          />
        </div>

        <div className="form-group" style={{ marginBottom: '0.5rem' }}>
          <label>Default Language</label>
          <input
            type="text"
            value={botDefaultLanguage}
            onChange={e => setBotDefaultLanguage(e.target.value.slice(0, 12))}
            placeholder="cs"
            disabled={loading || saving}
          />
          <div className="label-hint" style={{ marginTop: '0.4rem', marginLeft: 0 }}>
            Used as the initial language for newly discovered users.
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

        <div className="form-group" style={{ marginBottom: '1rem' }}>
          <label>API Base URL</label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '0.6rem', alignItems: 'center' }}>
            <input
              type="text"
              value={aiBaseUrl}
              onChange={e => setAiBaseUrl(e.target.value.slice(0, 500))}
              placeholder="https://api.openai.com/v1"
              disabled={loading || saving}
            />
            <button
              type="button"
              className="btn-secondary"
              onClick={handleProbeAi}
              disabled={loading || saving || probingAi || !aiBaseUrl.trim()}
              style={{ width: 'auto', whiteSpace: 'nowrap', padding: '0.65rem 0.9rem' }}
            >
              {probingAi ? 'Probing...' : 'Probe Base URL'}
            </button>
          </div>
          <div className="label-hint" style={{ marginTop: '0.4rem', marginLeft: 0 }}>
            Auto-detected provider: {aiProviderDetected}
          </div>
          <div className="label-hint" style={{ marginTop: '0.3rem', marginLeft: 0 }}>
            {modelsCachedAt
              ? `Last probe: ${new Date(modelsCachedAt).toLocaleString()}`
              : 'No probe record yet.'}
          </div>
          {probeResult && (
            <div
              style={{
                marginTop: '0.75rem',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                padding: '0.75rem',
                background: 'rgba(255,255,255,0.02)',
                display: 'grid',
                gap: '0.35rem',
              }}
            >
              <div style={{ color: probeResult.ok ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>
                {probeResult.ok ? 'Base URL Available' : 'Base URL Probe Failed'}
              </div>
              <div className="label-hint">Provider: {probeResult.provider_detected}</div>
              <div className="label-hint">Models listed: {probeResult.listed_total ?? listedModelTotal}</div>
              {probeResult.cached_at && (
                <div className="label-hint">Cache updated at: {new Date(probeResult.cached_at).toLocaleString()}</div>
              )}
              <div className="label-hint">Message: {probeResult.message}</div>
            </div>
          )}
        </div>

        <div className="form-group" style={{ marginBottom: '1rem' }}>
          <label>Model</label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.6rem', marginBottom: '0.55rem' }}>
            <select
              value={modelProviderFilter}
              onChange={e => {
                setModelProviderFilter(e.target.value);
                setCachedModelPicker('');
              }}
              disabled={loading || saving}
            >
              {providerFilterOptions.map(item => (
                <option key={item.key} value={item.key}>{item.label}</option>
              ))}
            </select>
            <select
              value={cachedModelPicker}
              onChange={e => {
                const selected = e.target.value;
                setCachedModelPicker(selected);
                if (selected) {
                  setAiModel(selected);
                }
              }}
              disabled={loading || saving || filteredModelOptions.length === 0}
            >
              <option value="">Select cached model...</option>
              {filteredModelOptions.slice(0, 500).map(model => (
                <option key={model} value={model}>{model}</option>
              ))}
            </select>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '0.6rem', alignItems: 'center' }}>
            <input
              type="text"
              value={aiModel}
              onChange={e => setAiModel(e.target.value.slice(0, 120))}
              placeholder="gpt-4o"
              disabled={loading || saving}
            />
            <button
              type="button"
              className="btn-secondary"
              onClick={() => { void handleVerifyModel(false); }}
              disabled={loading || saving || checkingModel || !aiModel.trim()}
              style={{ width: 'auto', whiteSpace: 'nowrap', padding: '0.65rem 0.9rem' }}
            >
              {checkingModel ? 'Checking...' : 'Check Model'}
            </button>
          </div>
          <div className="label-hint" style={{ marginTop: '0.4rem', marginLeft: 0 }}>
            {modelOptions.length > 0
              ? `Cached models: ${modelOptions.length} · Listed total: ${listedModelTotal || modelOptions.length}`
              : 'No model cache yet. Probe Base URL to fetch model list.'}
          </div>
          {modelVerifyResult && (
            <div
              style={{
                marginTop: '0.6rem',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                padding: '0.55rem 0.65rem',
                background: 'rgba(255,255,255,0.02)',
                display: 'grid',
                gap: '0.25rem',
              }}
            >
              <div style={{ color: modelVerifyResult.ok ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>
                {modelVerifyResult.ok ? 'Model Available' : 'Model Unavailable'}
              </div>
              <div className="label-hint">Last checked: {new Date(modelVerifyResult.checked_at).toLocaleString()}</div>
              <div className="label-hint">Message: {modelVerifyResult.message}</div>
              {modelVerifyResult.effective_model && (
                <div className="label-hint">Effective model: {modelVerifyResult.effective_model}</div>
              )}
              {modelVerifyResult.effective_base_url && (
                <div className="label-hint">Effective base URL: {modelVerifyResult.effective_base_url}</div>
              )}
            </div>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
          <div className="form-group" style={{ marginBottom: '1rem' }}>
            <label>Temperature (0-2)</label>
            <input
              type="number"
              min={0}
              max={2}
              step={0.1}
              value={aiTemperature}
              onChange={e => setAiTemperature(Math.min(2, Math.max(0, Number(e.target.value) || 0)))}
              disabled={loading || saving}
            />
          </div>

          <div className="form-group" style={{ marginBottom: '1rem' }}>
            <label>Max Tokens (1-32000)</label>
            <input
              type="number"
              min={1}
              max={32000}
              value={aiMaxTokens}
              onChange={e => setAiMaxTokens(Math.min(32000, Math.max(1, Number(e.target.value) || 1)))}
              disabled={loading || saving}
            />
          </div>

          <div className="form-group" style={{ marginBottom: '1rem' }}>
            <label>Context Messages (1-200)</label>
            <input
              type="number"
              min={1}
              max={200}
              value={aiContextMessages}
              onChange={e => setAiContextMessages(Math.min(200, Math.max(1, Number(e.target.value) || 1)))}
              disabled={loading || saving}
            />
          </div>
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
          <div className="label-hint" style={{ marginTop: '0.3rem', marginLeft: 0 }}>
            Configuration is stored in the internal runtime database and applies immediately.
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
