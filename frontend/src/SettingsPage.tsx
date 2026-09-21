import { useEffect, useState, useCallback } from 'react';
import { api } from './api';
import SidebarLayout from './SidebarLayout';
import { Card } from './components/ui/Card';
import { Button } from './components/ui/Button';

type SettingsTab = 'general' | 'signal' | 'ai' | 'campaign' | 'security' | 'retention' | 'diagnostics';

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
  const [activeTab, setActiveTab] = useState<SettingsTab>('general');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // General settings
  const [botName, setBotName] = useState('MarketBot');
  const [botDefaultLanguage, setBotDefaultLanguage] = useState('cs');
  const [aiEnabled, setAiEnabled] = useState(false);
  const [marketEnabled, setMarketEnabled] = useState(false);
  const [prompt, setPrompt] = useState('');

  // Signal settings
  const [signalApiUrl, setSignalApiUrl] = useState('');
  const [signalPhoneNumber, setSignalPhoneNumber] = useState('');
  const [signalApiToken, setSignalApiToken] = useState('');
  const [signalApiTokenMasked, setSignalApiTokenMasked] = useState('');
  const [testingSignal, setTestingSignal] = useState(false);
  const [signalTestResult, setSignalTestResult] = useState<{
    ok: boolean;
    message: string;
    status_code?: number | null;
    latency_ms: number;
    listener_running: boolean;
    listener_connected: boolean;
  } | null>(null);

  // AI settings
  const [apiKey, setApiKey] = useState('');
  const [apiKeyMasked, setApiKeyMasked] = useState('');
  const [aiBaseUrl, setAiBaseUrl] = useState('https://api.openai.com/v1');
  const [aiProviderDetected, setAiProviderDetected] = useState('unknown');
  const [aiModel, setAiModel] = useState('gpt-4o');
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [cachedModelPicker, setCachedModelPicker] = useState('');
  const [listedModelTotal, setListedModelTotal] = useState(0);
  const [aiTemperature, setAiTemperature] = useState(0.7);
  const [aiMaxTokens, setAiMaxTokens] = useState(1000);
  const [aiContextMessages, setAiContextMessages] = useState(20);
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
    message: string;
    cached_at?: string | null;
    preview?: string | null;
    models?: string[];
  } | null>(null);

  // Campaign settings
  const [adAutomationEnabled, setAdAutomationEnabled] = useState(true);
  const [adMinIntervalMinutes, setAdMinIntervalMinutes] = useState(180);
  const [adQuietStart, setAdQuietStart] = useState(23);
  const [adQuietEnd, setAdQuietEnd] = useState(8);
  const [adBlacklistInput, setAdBlacklistInput] = useState('');

  // Retention & Audit settings
  const [retentionDays, setRetentionDays] = useState(30);
  const [cleanuping, setCleanuping] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);
  const [auditLogs, setAuditLogs] = useState<Array<{ id: number; created_at: string; actor: string; action: string; status: string }>>([]);

  const loadSettings = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getSettings();
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
      setAiTemperature(data.ai_temperature ?? 0.7);
      setAiMaxTokens(data.ai_max_tokens ?? 1000);
      setAiContextMessages(data.ai_context_messages ?? 20);
      setRetentionDays(data.retention_days || 30);
      setAdAutomationEnabled(data.ad_automation_enabled ?? true);
      setAdMinIntervalMinutes(data.ad_min_interval_minutes ?? 180);
      setAdQuietStart(data.ad_quiet_hour_start ?? 23);
      setAdQuietEnd(data.ad_quiet_hour_end ?? 8);
      setAdBlacklistInput((data.ad_group_blacklist || []).join(', '));

      // Audit logs
      try {
        const logs = await api.getAuditLogs(1, 15, 'settings.');
        setAuditLogs(logs.items.map(item => ({
          id: item.id,
          created_at: item.created_at,
          actor: item.actor,
          action: item.action,
          status: item.status,
        })));
      } catch {
        // non-blocking
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load settings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSaving(true);
      setError(null);

      const payload: Record<string, unknown> = {
        is_ai_enabled: aiEnabled,
        is_market_enabled: marketEnabled,
        bot_name: botName.trim(),
        bot_default_language: botDefaultLanguage.trim() || 'cs',
        signal_api_url: signalApiUrl.trim(),
        signal_phone_number: signalPhoneNumber.trim(),
        ai_prompt: prompt,
        ai_api_base_url: aiBaseUrl.trim(),
        ai_model: aiModel.trim(),
        ai_temperature: aiTemperature,
        ai_max_tokens: aiMaxTokens,
        ai_context_messages: aiContextMessages,
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
      setSignalApiTokenMasked(updated.signal_api_token_masked || '');
      setSignalApiToken('');
      setApiKeyMasked(updated.ai_api_key_masked || '');
      setApiKey('');
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleTestSignal = async () => {
    try {
      setTestingSignal(true);
      setError(null);
      const res = await api.testSignalConnection({
        signal_api_url: signalApiUrl.trim(),
        signal_phone_number: signalPhoneNumber.trim(),
        signal_api_token: signalApiToken.trim() || undefined,
      });
      setSignalTestResult(res);
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
      const res = await api.probeAiCompatibility({
        ai_api_base_url: aiBaseUrl.trim(),
        ai_api_key: apiKey.trim() || undefined,
      });
      setProbeResult({
        ok: res.ok,
        provider_detected: res.provider_detected,
        message: res.message,
        cached_at: res.cached_at,
        preview: res.preview,
        models: res.models,
      });
      if (Array.isArray(res.models) && res.models.length > 0) {
        setModelOptions(res.models);
        setListedModelTotal(res.listed_total || res.models.length);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'AI probe failed');
    } finally {
      setProbingAi(false);
    }
  };

  const handleVerifyModel = async () => {
    try {
      setCheckingModel(true);
      setError(null);
      const res = await api.verifyAiModel({
        ai_model: aiModel.trim(),
        ai_api_base_url: aiBaseUrl.trim(),
        ai_api_key: apiKey.trim() || undefined,
      });
      setModelVerifyResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Model verification failed');
    } finally {
      setCheckingModel(false);
    }
  };

  const handleCleanupData = async () => {
    if (!window.confirm(`Delete messages older than ${retentionDays} days?`)) return;
    try {
      setCleanuping(true);
      setError(null);
      const res = await api.cleanupData(false);
      alert(`Cleanup finished: removed ${res.messages_deleted} messages.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Data cleanup failed');
    } finally {
      setCleanuping(false);
    }
  };

  const handleRollback = async () => {
    if (!window.confirm('Roll back to previously saved settings?')) return;
    try {
      setRollingBack(true);
      setError(null);
      await api.rollbackSettings();
      await loadSettings();
      alert('Settings rolled back successfully.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Rollback failed');
    } finally {
      setRollingBack(false);
    }
  };

  const tabs: { id: SettingsTab; label: string; icon: string }[] = [
    { id: 'general', label: 'General', icon: '⚙️' },
    { id: 'signal', label: 'Signal Gateway', icon: '📡' },
    { id: 'ai', label: 'AI Engine', icon: '🤖' },
    { id: 'campaign', label: 'Campaigns', icon: '📢' },
    { id: 'security', label: 'Security & Audit', icon: '🛡️' },
    { id: 'retention', label: 'Data & Retention', icon: '💾' },
    { id: 'diagnostics', label: 'Diagnostics', icon: '🩺' },
  ];

  return (
    <SidebarLayout title="Settings">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Navigation Tabs */}
        <div role="tablist" className="bg-[var(--bg-card)] p-1.5 rounded-xl border border-[var(--border)] shadow-[var(--shadow)] flex flex-wrap gap-1.5">
          {tabs.map(t => (
            <button
              key={t.id}
              role="tab"
              type="button"
              className={`px-3.5 py-2 rounded-lg text-xs md:text-sm font-medium transition-all cursor-pointer flex items-center ${
                activeTab === t.id
                  ? 'bg-[rgba(108,92,231,0.22)] text-white border border-[rgba(108,92,231,0.45)] shadow-[0_2px_10px_rgba(108,92,231,0.15)] font-semibold'
                  : 'text-[var(--text-secondary)] hover:text-white hover:bg-[rgba(255,255,255,0.04)] border border-transparent'
              }`}
              onClick={() => setActiveTab(t.id)}
            >
              <span className="mr-1.5">{t.icon}</span>
              {t.label}
            </button>
          ))}
        </div>

        {error && (
          <div className="bg-[rgba(255,107,107,0.12)] border border-[rgba(255,107,107,0.3)] text-[var(--danger)] px-4 py-3 rounded-xl text-xs flex items-center justify-between">
            <span>{error}</span>
            <button type="button" onClick={() => setError(null)} className="font-bold hover:opacity-80 cursor-pointer">✕</button>
          </div>
        )}
        {saved && (
          <div className="bg-[rgba(0,214,143,0.12)] border border-[rgba(0,214,143,0.3)] text-[var(--success)] px-4 py-3 rounded-xl text-xs flex items-center justify-between">
            <span>Settings saved successfully!</span>
            <button type="button" onClick={() => setSaved(false)} className="font-bold hover:opacity-80 cursor-pointer">✕</button>
          </div>
        )}

        {loading ? (
          <div className="py-16 text-center text-sm text-base-content/50">
            <span className="loading loading-spinner loading-md mr-2" />
            Loading settings...
          </div>
        ) : (
          <form onSubmit={handleSave} className="space-y-6">
            {/* TAB: General */}
            {activeTab === 'general' && (
              <Card title="General Settings" subtitle="Basic bot identity and behavior configuration">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="label">
                      <span className="label-text font-medium text-xs">Bot Name</span>
                    </label>
                    <input
                      type="text"
                      className="input input-bordered input-sm w-full"
                      value={botName}
                      onChange={e => setBotName(e.target.value)}
                      placeholder="MarketBot"
                    />
                  </div>

                  <div>
                    <label className="label">
                      <span className="label-text font-medium text-xs">Default Language</span>
                    </label>
                    <input
                      type="text"
                      className="input input-bordered input-sm w-full"
                      value={botDefaultLanguage}
                      onChange={e => setBotDefaultLanguage(e.target.value)}
                      placeholder="cs, en, de"
                    />
                  </div>
                </div>

                <div className="divider my-4" />

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="flex items-center justify-between p-3 bg-base-200/50 rounded-lg">
                    <div>
                      <div className="font-semibold text-xs">AI Auto-Reply</div>
                      <div className="text-2xs text-base-content/60">Enable automatic LLM responses</div>
                    </div>
                    <input
                      type="checkbox"
                      className="toggle toggle-primary toggle-sm"
                      checked={aiEnabled}
                      onChange={e => setAiEnabled(e.target.checked)}
                    />
                  </div>

                  <div className="flex items-center justify-between p-3 bg-base-200/50 rounded-lg">
                    <div>
                      <div className="font-semibold text-xs">Market Order System</div>
                      <div className="text-2xs text-base-content/60">Enable product catalog and order handling</div>
                    </div>
                    <input
                      type="checkbox"
                      className="toggle toggle-primary toggle-sm"
                      checked={marketEnabled}
                      onChange={e => setMarketEnabled(e.target.checked)}
                    />
                  </div>
                </div>

                <div className="mt-4">
                  <label className="label">
                    <span className="label-text font-medium text-xs">System Prompt Template</span>
                  </label>
                  <textarea
                    className="textarea textarea-bordered textarea-sm w-full font-mono text-xs"
                    rows={6}
                    value={prompt}
                    onChange={e => setPrompt(e.target.value)}
                    placeholder="Instructions for the AI assistant..."
                  />
                </div>
              </Card>
            )}

            {/* TAB: Signal Gateway */}
            {activeTab === 'signal' && (
              <Card
                title="Signal Gateway Configuration"
                subtitle="Connection details to the signal-cli-rest-api daemon"
                headerAction={
                  <Button
                    type="button"
                    variant="secondary"
                    size="xs"
                    loading={testingSignal}
                    onClick={handleTestSignal}
                  >
                    ⚡ Test Connection
                  </Button>
                }
              >
                {signalTestResult && (
                  <div className={`p-3 rounded-lg text-xs mb-4 ${signalTestResult.ok ? 'bg-success/10 text-success' : 'bg-error/10 text-error'}`}>
                    <div className="font-bold">{signalTestResult.ok ? 'Signal Gateway Reachable' : 'Connection Failed'}</div>
                    <div className="text-2xs mt-1">{signalTestResult.message} (latency: {signalTestResult.latency_ms}ms)</div>
                    <div className="text-2xs">Listener running: {signalTestResult.listener_running ? 'yes' : 'no'} · connected: {signalTestResult.listener_connected ? 'yes' : 'no'}</div>
                  </div>
                )}

                <div className="space-y-4">
                  <div>
                    <label className="label">
                      <span className="label-text font-medium text-xs">Signal Gateway REST URL</span>
                    </label>
                    <input
                      type="text"
                      className="input input-bordered input-sm w-full font-mono text-xs"
                      value={signalApiUrl}
                      onChange={e => setSignalApiUrl(e.target.value)}
                      placeholder="http://127.0.0.1:8080"
                    />
                  </div>

                  <div>
                    <label className="label">
                      <span className="label-text font-medium text-xs">Signal Bot Phone Number</span>
                    </label>
                    <input
                      type="text"
                      className="input input-bordered input-sm w-full font-mono text-xs"
                      value={signalPhoneNumber}
                      onChange={e => setSignalPhoneNumber(e.target.value)}
                      placeholder="+420123456789"
                    />
                  </div>

                  <div>
                    <label className="label">
                      <span className="label-text font-medium text-xs">Gateway API Token</span>
                      {signalApiTokenMasked && (
                        <span className="label-text-alt text-2xs text-base-content/60">Current: {signalApiTokenMasked}</span>
                      )}
                    </label>
                    <input
                      type="password"
                      className="input input-bordered input-sm w-full font-mono text-xs"
                      value={signalApiToken}
                      onChange={e => setSignalApiToken(e.target.value)}
                      placeholder="Leave blank to keep existing token"
                    />
                  </div>
                </div>
              </Card>
            )}

            {/* TAB: AI Engine */}
            {activeTab === 'ai' && (
              <Card
                title="AI Engine Settings"
                subtitle="LLM provider configuration, base URL, model, and sampling parameters"
                headerAction={
                  <div className="flex gap-2">
                    <Button type="button" variant="secondary" size="xs" loading={probingAi} onClick={handleProbeAi}>
                      🔍 Probe Models
                    </Button>
                    <Button type="button" variant="secondary" size="xs" loading={checkingModel} onClick={handleVerifyModel}>
                      ✓ Verify Model
                    </Button>
                  </div>
                }
              >
                {modelVerifyResult && (
                  <div className={`p-3 rounded-lg text-xs mb-4 ${modelVerifyResult.ok ? 'bg-success/10 text-success' : 'bg-error/10 text-error'}`}>
                    <div className="font-bold">Model Check: {modelVerifyResult.model} — {modelVerifyResult.ok ? 'PASSED' : 'FAILED'}</div>
                    <div className="text-2xs mt-1">{modelVerifyResult.message}</div>
                    {modelVerifyResult.preview && <div className="text-2xs font-mono mt-1 bg-base-100/50 p-2 rounded">Response: {modelVerifyResult.preview}</div>}
                  </div>
                )}

                {probeResult && (
                  <div className="p-3 bg-info/10 text-info rounded-lg text-xs mb-4">
                    <div className="font-bold">Provider Detected: {probeResult.provider_detected}</div>
                    <div className="text-2xs">{probeResult.message}</div>
                  </div>
                )}

                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="label">
                        <span className="label-text font-medium text-xs">API Base URL</span>
                      </label>
                      <input
                        type="text"
                        className="input input-bordered input-sm w-full font-mono text-xs"
                        value={aiBaseUrl}
                        onChange={e => setAiBaseUrl(e.target.value)}
                        placeholder="https://api.openai.com/v1"
                      />
                    </div>

                    <div>
                      <label className="label">
                        <span className="label-text font-medium text-xs">API Key</span>
                        {apiKeyMasked && (
                          <span className="label-text-alt text-2xs text-base-content/60">Current: {apiKeyMasked}</span>
                        )}
                      </label>
                      <input
                        type="password"
                        className="input input-bordered input-sm w-full font-mono text-xs"
                        value={apiKey}
                        onChange={e => setApiKey(e.target.value)}
                        placeholder="Leave blank to keep existing key"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="md:col-span-2">
                      <label className="label">
                        <span className="label-text font-medium text-xs">Model Name</span>
                        {aiProviderDetected !== 'unknown' && (
                          <span className="label-text-alt text-2xs uppercase badge badge-xs">{aiProviderDetected}</span>
                        )}
                      </label>
                      <input
                        type="text"
                        className="input input-bordered input-sm w-full font-mono text-xs"
                        value={aiModel}
                        onChange={e => setAiModel(e.target.value)}
                        placeholder="gpt-4o, claude-3-5-sonnet, deepseek-chat"
                      />
                    </div>

                    {modelOptions.length > 0 && (
                      <div>
                        <label className="label">
                          <span className="label-text font-medium text-xs">Pick Cached Model ({listedModelTotal})</span>
                        </label>
                        <select
                          className="select select-bordered select-sm w-full text-xs"
                          value={cachedModelPicker}
                          onChange={e => {
                            if (e.target.value) {
                              setAiModel(e.target.value);
                              setCachedModelPicker('');
                            }
                          }}
                        >
                          <option value="">-- Choose cached --</option>
                          {modelOptions.map(m => (
                            <option key={m} value={m}>{m}</option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <label className="label">
                        <span className="label-text font-medium text-xs">Temperature ({aiTemperature})</span>
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="2"
                        step="0.05"
                        className="range range-xs range-primary"
                        value={aiTemperature}
                        onChange={e => setAiTemperature(parseFloat(e.target.value))}
                      />
                    </div>

                    <div>
                      <label className="label">
                        <span className="label-text font-medium text-xs">Max Tokens</span>
                      </label>
                      <input
                        type="number"
                        className="input input-bordered input-sm w-full text-xs"
                        value={aiMaxTokens}
                        onChange={e => setAiMaxTokens(parseInt(e.target.value, 10) || 1000)}
                      />
                    </div>

                    <div>
                      <label className="label">
                        <span className="label-text font-medium text-xs">Context History (Messages)</span>
                      </label>
                      <input
                        type="number"
                        className="input input-bordered input-sm w-full text-xs"
                        value={aiContextMessages}
                        onChange={e => setAiContextMessages(parseInt(e.target.value, 10) || 20)}
                      />
                    </div>
                  </div>
                </div>
              </Card>
            )}

            {/* TAB: Campaign */}
            {activeTab === 'campaign' && (
              <Card title="Campaign & Broadcast Settings" subtitle="Broadcast frequency, quiet hours, and group exclusions">
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-3 bg-base-200/50 rounded-lg">
                    <div>
                      <div className="font-semibold text-xs">Campaign Broadcast Enabled</div>
                      <div className="text-2xs text-base-content/60">Allow scheduled/manual marketing broadcasts</div>
                    </div>
                    <input
                      type="checkbox"
                      className="toggle toggle-primary toggle-sm"
                      checked={adAutomationEnabled}
                      onChange={e => setAdAutomationEnabled(e.target.checked)}
                    />
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <label className="label">
                        <span className="label-text font-medium text-xs">Min Interval (Minutes)</span>
                      </label>
                      <input
                        type="number"
                        className="input input-bordered input-sm w-full text-xs"
                        value={adMinIntervalMinutes}
                        onChange={e => setAdMinIntervalMinutes(parseInt(e.target.value, 10) || 180)}
                      />
                    </div>

                    <div>
                      <label className="label">
                        <span className="label-text font-medium text-xs">Quiet Hours Start (Hour 0-23)</span>
                      </label>
                      <input
                        type="number"
                        min="0"
                        max="23"
                        className="input input-bordered input-sm w-full text-xs"
                        value={adQuietStart}
                        onChange={e => setAdQuietStart(parseInt(e.target.value, 10) || 23)}
                      />
                    </div>

                    <div>
                      <label className="label">
                        <span className="label-text font-medium text-xs">Quiet Hours End (Hour 0-23)</span>
                      </label>
                      <input
                        type="number"
                        min="0"
                        max="23"
                        className="input input-bordered input-sm w-full text-xs"
                        value={adQuietEnd}
                        onChange={e => setAdQuietEnd(parseInt(e.target.value, 10) || 8)}
                      />
                    </div>
                  </div>

                  <div>
                    <label className="label">
                      <span className="label-text font-medium text-xs">Group Blacklist (comma-separated IDs)</span>
                    </label>
                    <input
                      type="text"
                      className="input input-bordered input-sm w-full text-xs font-mono"
                      value={adBlacklistInput}
                      onChange={e => setAdBlacklistInput(e.target.value)}
                      placeholder="e.g. group.abc123, group.xyz456"
                    />
                  </div>
                </div>
              </Card>
            )}

            {/* TAB: Security & Audit */}
            {activeTab === 'security' && (
              <Card title="Security & Audit Logs" subtitle="Recent administrative actions and configuration events">
                <div className="space-y-4">
                  <div className="p-3 bg-base-200/50 rounded-lg text-xs space-y-1">
                    <div className="font-semibold">Security Policy</div>
                    <div className="text-2xs text-base-content/70">
                      • Authentication tokens and gateway credentials are encrypted or masked at rest.<br />
                      • Admin actions are logged with actor identity and timestamp.<br />
                      • Manual takeover overrides automated AI execution deterministically.
                    </div>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="table table-xs w-full">
                      <thead>
                        <tr className="text-base-content/70">
                          <th>Time</th>
                          <th>Actor</th>
                          <th>Action</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {auditLogs.length === 0 ? (
                          <tr>
                            <td colSpan={4} className="text-center py-4 text-base-content/50">
                              No recent settings audit logs.
                            </td>
                          </tr>
                        ) : (
                          auditLogs.map(log => (
                            <tr key={log.id} className="hover">
                              <td className="text-2xs text-base-content/70">{new Date(log.created_at).toLocaleString()}</td>
                              <td className="font-mono text-2xs">{log.actor}</td>
                              <td className="font-medium text-2xs">{log.action}</td>
                              <td>
                                <span className={`badge badge-2xs ${log.status === 'success' ? 'badge-success' : 'badge-ghost'}`}>
                                  {log.status}
                                </span>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </Card>
            )}

            {/* TAB: Data & Retention */}
            {activeTab === 'retention' && (
              <Card title="Data Retention & Maintenance" subtitle="Message pruning and configuration rollback">
                <div className="space-y-4">
                  <div>
                    <label className="label">
                      <span className="label-text font-medium text-xs">Message Retention (Days)</span>
                    </label>
                    <input
                      type="number"
                      min="1"
                      className="input input-bordered input-sm w-48 text-xs"
                      value={retentionDays}
                      onChange={e => setRetentionDays(parseInt(e.target.value, 10) || 30)}
                    />
                    <div className="text-2xs text-base-content/60 mt-1">
                      Messages older than this threshold will be pruned during scheduled cleanup.
                    </div>
                  </div>

                  <div className="divider my-4" />

                  <div className="flex flex-wrap gap-4 items-center">
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      loading={cleanuping}
                      onClick={handleCleanupData}
                    >
                      🗑️ Run Data Cleanup Now
                    </Button>

                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      loading={rollingBack}
                      onClick={handleRollback}
                    >
                      ↩️ Roll Back Settings
                    </Button>
                  </div>
                </div>
              </Card>
            )}

            {/* TAB: Diagnostics */}
            {activeTab === 'diagnostics' && (
              <Card title="Diagnostics & System Health" subtitle="Runtime status and component checks">
                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="p-4 bg-base-200/50 rounded-lg">
                      <div className="font-semibold text-xs mb-2">Signal Connection</div>
                      <div className="text-xs space-y-1 text-base-content/70">
                        <div>Gateway: <span className="font-mono">{signalApiUrl || 'Not configured'}</span></div>
                        <div>Phone: <span className="font-mono">{signalPhoneNumber || 'Not configured'}</span></div>
                        <div>Status: {signalTestResult ? (signalTestResult.ok ? '🟢 Connected' : '🔴 Error') : '⚪ Untested'}</div>
                      </div>
                    </div>

                    <div className="p-4 bg-base-200/50 rounded-lg">
                      <div className="font-semibold text-xs mb-2">AI Engine</div>
                      <div className="text-xs space-y-1 text-base-content/70">
                        <div>Model: <span className="font-mono">{aiModel}</span></div>
                        <div>Provider: <span className="font-mono">{inferProvider(aiModel)}</span></div>
                        <div>Status: {modelVerifyResult ? (modelVerifyResult.ok ? '🟢 Verified' : '🔴 Failed') : '⚪ Unchecked'}</div>
                      </div>
                    </div>
                  </div>
                </div>
              </Card>
            )}

            {/* Bottom Save Action Bar */}
            <div className="flex items-center justify-between p-4 bg-base-100 rounded-box shadow-sm border border-base-200">
              <div className="text-xs text-base-content/60">
                Changes will take effect immediately upon saving.
              </div>
              <Button type="submit" variant="primary" size="sm" loading={saving}>
                💾 Save Settings
              </Button>
            </div>
          </form>
        )}
      </div>
    </SidebarLayout>
  );
}
