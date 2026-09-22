import { useEffect, useState, useCallback } from 'react';
import {
  Sliders,
  Radio,
  Bot,
  Megaphone,
  ShieldCheck,
  Database,
  Activity,
  Save,
  Zap,
  Search,
  CheckCircle2,
  Trash2,
  Undo2,
  AlertCircle,
  BookOpen,
} from 'lucide-react';
import { api } from './api';
import SidebarLayout from './SidebarLayout';
import { Card } from './components/ui/Card';
import { Button } from './components/ui/Button';

type SettingsTab = 'general' | 'signal' | 'ai' | 'rag' | 'campaign' | 'security' | 'retention' | 'diagnostics';

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

  // RAG & Vector Store settings
  const [ragEnabled, setRagEnabled] = useState(true);
  const [embeddingBaseUrl, setEmbeddingBaseUrl] = useState('');
  const [embeddingModel, setEmbeddingModel] = useState('text-embedding-3-small');
  const [embeddingApiKey, setEmbeddingApiKey] = useState('');
  const [embeddingApiKeyMasked, setEmbeddingApiKeyMasked] = useState('');
  const [vectorStoreProvider, setVectorStoreProvider] = useState('qdrant');
  const [qdrantUrl, setQdrantUrl] = useState('http://localhost:6333');
  const [qdrantApiKey, setQdrantApiKey] = useState('');
  const [qdrantApiKeyMasked, setQdrantApiKeyMasked] = useState('');
  const [testingEmbedding, setTestingEmbedding] = useState(false);
  const [embeddingTestResult, setEmbeddingTestResult] = useState<{
    ok: boolean;
    configured: boolean;
    connected: boolean;
    latency_ms: number;
    message: string;
    error?: string | null;
  } | null>(null);
  const [testingVectorStore, setTestingVectorStore] = useState(false);
  const [vectorStoreTestResult, setVectorStoreTestResult] = useState<{
    ok: boolean;
    configured: boolean;
    connected: boolean;
    latency_ms: number;
    message: string;
    error?: string | null;
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

      setRagEnabled(data.rag_enabled ?? true);
      setEmbeddingBaseUrl(data.embedding_base_url || '');
      setEmbeddingModel(data.embedding_model || 'text-embedding-3-small');
      setEmbeddingApiKeyMasked(data.embedding_api_key_masked || '');
      setEmbeddingApiKey('');
      setVectorStoreProvider(data.vector_store_provider || 'qdrant');
      setQdrantUrl(data.qdrant_url || 'http://localhost:6333');
      setQdrantApiKeyMasked(data.qdrant_api_key_masked || '');
      setQdrantApiKey('');

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
        rag_enabled: ragEnabled,
        embedding_base_url: embeddingBaseUrl.trim(),
        embedding_model: embeddingModel.trim(),
        vector_store_provider: vectorStoreProvider.trim(),
        qdrant_url: qdrantUrl.trim(),
      };

      if (apiKey.trim()) {
        payload.ai_api_key = apiKey.trim();
      }
      if (signalApiToken.trim()) {
        payload.signal_api_token = signalApiToken.trim();
      }
      if (embeddingApiKey.trim()) {
        payload.embedding_api_key = embeddingApiKey.trim();
      }
      if (qdrantApiKey.trim()) {
        payload.qdrant_api_key = qdrantApiKey.trim();
      }

      const updated = await api.updateSettings(payload);
      setSignalApiTokenMasked(updated.signal_api_token_masked || '');
      setSignalApiToken('');
      setApiKeyMasked(updated.ai_api_key_masked || '');
      setApiKey('');
      setEmbeddingApiKeyMasked(updated.embedding_api_key_masked || '');
      setEmbeddingApiKey('');
      setQdrantApiKeyMasked(updated.qdrant_api_key_masked || '');
      setQdrantApiKey('');
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

  const handleTestEmbedding = async () => {
    try {
      setTestingEmbedding(true);
      setError(null);
      const res = await api.testEmbedding({
        embedding_base_url: embeddingBaseUrl.trim() || undefined,
        embedding_model: embeddingModel.trim() || undefined,
        embedding_api_key: embeddingApiKey.trim() || undefined,
      });
      setEmbeddingTestResult(res as any);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Embedding connection test failed');
    } finally {
      setTestingEmbedding(false);
    }
  };

  const handleTestVectorStore = async () => {
    try {
      setTestingVectorStore(true);
      setError(null);
      const res = await api.testVectorStore({
        qdrant_url: qdrantUrl.trim() || undefined,
        qdrant_api_key: qdrantApiKey.trim() || undefined,
      });
      setVectorStoreTestResult(res as any);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Vector store connection test failed');
    } finally {
      setTestingVectorStore(false);
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

  const tabs = [
    { id: 'general' as const, label: 'General', icon: Sliders },
    { id: 'signal' as const, label: 'Signal Gateway', icon: Radio },
    { id: 'ai' as const, label: 'AI Engine', icon: Bot },
    { id: 'rag' as const, label: 'RAG & Vectors', icon: BookOpen },
    { id: 'campaign' as const, label: 'Campaigns', icon: Megaphone },
    { id: 'security' as const, label: 'Security & Audit', icon: ShieldCheck },
    { id: 'retention' as const, label: 'Data & Retention', icon: Database },
    { id: 'diagnostics' as const, label: 'Diagnostics', icon: Activity },
  ];

  return (
    <SidebarLayout title="Settings">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Navigation Tabs */}
        <div role="tablist" className="bg-[var(--bg-card)] p-1.5 rounded-2xl border border-[var(--border)] shadow-[var(--shadow)] flex items-center gap-1.5 overflow-x-auto no-scrollbar">
          {tabs.map(t => (
            <button
              key={t.id}
              role="tab"
              type="button"
              className={`px-3.5 py-2 rounded-xl text-xs md:text-sm font-medium transition-all cursor-pointer flex items-center gap-2 whitespace-nowrap ${
                activeTab === t.id
                  ? 'bg-[rgba(108,92,231,0.22)] text-white border border-[rgba(108,92,231,0.45)] shadow-[0_2px_10px_rgba(108,92,231,0.15)] font-semibold'
                  : 'text-[var(--text-secondary)] hover:text-white hover:bg-[rgba(255,255,255,0.04)] border border-transparent'
              }`}
              onClick={() => setActiveTab(t.id)}
            >
              <t.icon className={`w-4 h-4 ${activeTab === t.id ? 'text-[var(--accent)]' : 'opacity-70'}`} />
              <span>{t.label}</span>
            </button>
          ))}
        </div>

        {error && (
          <div className="bg-[rgba(255,107,107,0.12)] border border-[rgba(255,107,107,0.3)] text-[var(--danger)] px-4 py-3 rounded-xl text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
            <button type="button" onClick={() => setError(null)} className="font-bold hover:opacity-80 cursor-pointer">✕</button>
          </div>
        )}
        {saved && (
          <div className="bg-[rgba(0,214,143,0.12)] border border-[rgba(0,214,143,0.3)] text-[var(--success)] px-4 py-3 rounded-xl text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>Settings saved successfully!</span>
            </div>
            <button type="button" onClick={() => setSaved(false)} className="font-bold hover:opacity-80 cursor-pointer">✕</button>
          </div>
        )}

        {loading ? (
          <div className="py-16 text-center text-sm text-[var(--text-muted)] flex flex-col items-center justify-center gap-2">
            <div className="w-6 h-6 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
            <span>Loading settings...</span>
          </div>
        ) : (
          <form onSubmit={handleSave} className="space-y-6">
            {/* TAB: General */}
            {activeTab === 'general' && (
              <Card title="General Settings" subtitle="Basic bot identity and behavior configuration">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                      Bot Name
                    </label>
                    <input
                      type="text"
                      className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] transition-all"
                      value={botName}
                      onChange={e => setBotName(e.target.value)}
                      placeholder="MarketBot"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                      Default Language
                    </label>
                    <input
                      type="text"
                      className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] transition-all"
                      value={botDefaultLanguage}
                      onChange={e => setBotDefaultLanguage(e.target.value)}
                      placeholder="cs, en, de"
                    />
                  </div>
                </div>

                <div className="border-t border-[var(--border)] my-5" />

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="flex items-center justify-between p-3.5 bg-[rgba(255,255,255,0.02)] rounded-xl border border-[var(--border)]">
                    <div>
                      <div className="font-semibold text-xs text-[var(--text-primary)]">AI Auto-Reply</div>
                      <div className="text-[11px] text-[var(--text-muted)] mt-0.5">Enable automatic LLM responses</div>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        className="sr-only peer"
                        checked={aiEnabled}
                        onChange={e => setAiEnabled(e.target.checked)}
                      />
                      <div className="w-11 h-6 bg-[rgba(255,255,255,0.1)] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[var(--accent)] border border-[var(--border)]" />
                    </label>
                  </div>

                  <div className="flex items-center justify-between p-3.5 bg-[rgba(255,255,255,0.02)] rounded-xl border border-[var(--border)]">
                    <div>
                      <div className="font-semibold text-xs text-[var(--text-primary)]">Market Order System</div>
                      <div className="text-[11px] text-[var(--text-muted)] mt-0.5">Enable product catalog and order handling</div>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        className="sr-only peer"
                        checked={marketEnabled}
                        onChange={e => setMarketEnabled(e.target.checked)}
                      />
                      <div className="w-11 h-6 bg-[rgba(255,255,255,0.1)] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[var(--accent)] border border-[var(--border)]" />
                    </label>
                  </div>
                </div>

                <div className="mt-4">
                  <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                    System Prompt Template
                  </label>
                  <textarea
                    className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs font-mono text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] transition-all resize-none"
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
                    className="gap-1.5"
                  >
                    <Zap className="w-3.5 h-3.5" />
                    <span>Test Connection</span>
                  </Button>
                }
              >
                {signalTestResult && (
                  <div className={`p-3.5 rounded-xl text-xs mb-4 border ${signalTestResult.ok ? 'bg-[rgba(0,214,143,0.12)] border-[rgba(0,214,143,0.3)] text-[var(--success)]' : 'bg-[rgba(255,107,107,0.12)] border-[rgba(255,107,107,0.3)] text-[var(--danger)]'}`}>
                    <div className="font-bold">{signalTestResult.ok ? 'Signal Gateway Reachable' : 'Connection Failed'}</div>
                    <div className="text-[11px] mt-1">{signalTestResult.message} (latency: {signalTestResult.latency_ms}ms)</div>
                    <div className="text-[11px] opacity-80">Listener running: {signalTestResult.listener_running ? 'yes' : 'no'} · connected: {signalTestResult.listener_connected ? 'yes' : 'no'}</div>
                  </div>
                )}

                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                      Signal Gateway REST URL
                    </label>
                    <input
                      type="text"
                      className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs font-mono text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] transition-all"
                      value={signalApiUrl}
                      onChange={e => setSignalApiUrl(e.target.value)}
                      placeholder="http://127.0.0.1:8080"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                      Signal Bot Phone Number
                    </label>
                    <input
                      type="text"
                      className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs font-mono text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] transition-all"
                      value={signalPhoneNumber}
                      onChange={e => setSignalPhoneNumber(e.target.value)}
                      placeholder="+420123456789"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-xs font-semibold text-[var(--text-secondary)]">
                        Gateway API Token
                      </label>
                      {signalApiTokenMasked && (
                        <span className="text-[11px] text-[var(--text-muted)] font-mono">Current: {signalApiTokenMasked}</span>
                      )}
                    </div>
                    <input
                      type="password"
                      className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs font-mono text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] transition-all"
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
                    <Button type="button" variant="secondary" size="xs" loading={probingAi} onClick={handleProbeAi} className="gap-1.5">
                      <Search className="w-3 h-3" />
                      <span>Probe Models</span>
                    </Button>
                    <Button type="button" variant="secondary" size="xs" loading={checkingModel} onClick={handleVerifyModel} className="gap-1.5">
                      <CheckCircle2 className="w-3 h-3" />
                      <span>Verify Model</span>
                    </Button>
                  </div>
                }
              >
                {modelVerifyResult && (
                  <div className={`p-3.5 rounded-xl text-xs mb-4 border ${modelVerifyResult.ok ? 'bg-[rgba(0,214,143,0.12)] border-[rgba(0,214,143,0.3)] text-[var(--success)]' : 'bg-[rgba(255,107,107,0.12)] border-[rgba(255,107,107,0.3)] text-[var(--danger)]'}`}>
                    <div className="font-bold">Model Check: {modelVerifyResult.model} — {modelVerifyResult.ok ? 'PASSED' : 'FAILED'}</div>
                    <div className="text-[11px] mt-1">{modelVerifyResult.message}</div>
                    {modelVerifyResult.preview && (
                      <div className="text-[11px] font-mono mt-2 bg-[var(--bg-input)] p-2.5 rounded-lg border border-[var(--border)] text-[var(--text-secondary)] break-all">
                        Response: {modelVerifyResult.preview}
                      </div>
                    )}
                  </div>
                )}

                {probeResult && (
                  <div className="p-3.5 bg-[rgba(0,180,216,0.12)] border border-[rgba(0,180,216,0.3)] text-[#90e0ef] rounded-xl text-xs mb-4">
                    <div className="font-bold">Provider Detected: {probeResult.provider_detected}</div>
                    <div className="text-[11px] mt-0.5">{probeResult.message}</div>
                  </div>
                )}

                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                        API Base URL
                      </label>
                      <input
                        type="text"
                        className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs font-mono text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] transition-all"
                        value={aiBaseUrl}
                        onChange={e => setAiBaseUrl(e.target.value)}
                        placeholder="https://api.openai.com/v1"
                      />
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <label className="text-xs font-semibold text-[var(--text-secondary)]">
                          API Key
                        </label>
                        {apiKeyMasked && (
                          <span className="text-[11px] text-[var(--text-muted)] font-mono">Current: {apiKeyMasked}</span>
                        )}
                      </div>
                      <input
                        type="password"
                        className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs font-mono text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] transition-all"
                        value={apiKey}
                        onChange={e => setApiKey(e.target.value)}
                        placeholder="Leave blank to keep existing key"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="md:col-span-2">
                      <div className="flex items-center justify-between mb-1.5">
                        <label className="text-xs font-semibold text-[var(--text-secondary)]">
                          Model Name
                        </label>
                        {aiProviderDetected !== 'unknown' && (
                          <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-[rgba(108,92,231,0.2)] text-[var(--accent)] border border-[rgba(108,92,231,0.3)]">
                            {aiProviderDetected}
                          </span>
                        )}
                      </div>
                      <input
                        type="text"
                        className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs font-mono text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] transition-all"
                        value={aiModel}
                        onChange={e => setAiModel(e.target.value)}
                        placeholder="gpt-4o, claude-3-5-sonnet, deepseek-chat"
                      />
                    </div>

                    {modelOptions.length > 0 && (
                      <div>
                        <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                          Pick Cached Model ({listedModelTotal})
                        </label>
                        <select
                          className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent)] cursor-pointer"
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
                            <option key={m} value={m} className="bg-[#1a1a2e]">{m}</option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                        Temperature ({aiTemperature})
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="2"
                        step="0.05"
                        className="w-full accent-[var(--accent)] cursor-pointer"
                        value={aiTemperature}
                        onChange={e => setAiTemperature(parseFloat(e.target.value))}
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                        Max Tokens
                      </label>
                      <input
                        type="number"
                        className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
                        value={aiMaxTokens}
                        onChange={e => setAiMaxTokens(parseInt(e.target.value, 10) || 1000)}
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                        Context History (Messages)
                      </label>
                      <input
                        type="number"
                        className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
                        value={aiContextMessages}
                        onChange={e => setAiContextMessages(parseInt(e.target.value, 10) || 20)}
                      />
                    </div>
                  </div>
                </div>
              </Card>
            )}

            {/* TAB: RAG & Vectors */}
            {activeTab === 'rag' && (
              <Card
                title="RAG & Vector Store Configuration"
                subtitle="Manage embedding endpoint, vector database, and retrieval pipeline"
                headerAction={
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      size="xs"
                      loading={testingEmbedding}
                      onClick={handleTestEmbedding}
                      className="gap-1.5"
                    >
                      <Zap className="w-3 h-3" />
                      <span>Test Embedding</span>
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      size="xs"
                      loading={testingVectorStore}
                      onClick={handleTestVectorStore}
                      className="gap-1.5"
                    >
                      <Database className="w-3 h-3" />
                      <span>Test Vector Store</span>
                    </Button>
                  </div>
                }
              >
                {embeddingTestResult && (
                  <div
                    className={`p-3.5 rounded-xl text-xs mb-4 border ${
                      embeddingTestResult.connected
                        ? 'bg-[rgba(0,214,143,0.12)] border-[rgba(0,214,143,0.3)] text-[var(--success)]'
                        : 'bg-[rgba(255,107,107,0.12)] border-[rgba(255,107,107,0.3)] text-[var(--danger)]'
                    }`}
                  >
                    <div className="font-bold">
                      Embedding Service: {embeddingTestResult.connected ? 'CONNECTED' : 'FAILED'} (Latency: {embeddingTestResult.latency_ms}ms)
                    </div>
                    <div className="text-[11px] mt-1">{embeddingTestResult.message}</div>
                    {embeddingTestResult.error && (
                      <div className="text-[11px] font-mono mt-1 text-[var(--text-muted)]">
                        Error: {embeddingTestResult.error}
                      </div>
                    )}
                  </div>
                )}

                {vectorStoreTestResult && (
                  <div
                    className={`p-3.5 rounded-xl text-xs mb-4 border ${
                      vectorStoreTestResult.connected
                        ? 'bg-[rgba(0,214,143,0.12)] border-[rgba(0,214,143,0.3)] text-[var(--success)]'
                        : 'bg-[rgba(255,107,107,0.12)] border-[rgba(255,107,107,0.3)] text-[var(--danger)]'
                    }`}
                  >
                    <div className="font-bold">
                      Vector Store: {vectorStoreTestResult.connected ? 'CONNECTED' : 'FAILED'} (Latency: {vectorStoreTestResult.latency_ms}ms)
                    </div>
                    <div className="text-[11px] mt-1">{vectorStoreTestResult.message}</div>
                    {vectorStoreTestResult.error && (
                      <div className="text-[11px] font-mono mt-1 text-[var(--text-muted)]">
                        Error: {vectorStoreTestResult.error}
                      </div>
                    )}
                  </div>
                )}

                <div className="space-y-6">
                  {/* Pipeline toggle */}
                  <div className="flex items-center justify-between p-3.5 bg-[rgba(255,255,255,0.02)] rounded-xl border border-[var(--border)]">
                    <div>
                      <div className="font-semibold text-xs text-[var(--text-primary)]">
                        RAG Knowledge Retrieval Enabled
                      </div>
                      <div className="text-[11px] text-[var(--text-muted)] mt-0.5">
                        Enable semantic search and context injection from knowledge documents
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      className="w-4 h-4 accent-[var(--accent)] cursor-pointer"
                      checked={ragEnabled}
                      onChange={e => setRagEnabled(e.target.checked)}
                    />
                  </div>

                  {/* Embedding settings */}
                  <div className="border-t border-[var(--border)] pt-4 space-y-4">
                    <h4 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider">
                      Embedding Model Settings
                    </h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                          Embedding Endpoint Base URL
                        </label>
                        <input
                          type="text"
                          className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs font-mono text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)]"
                          value={embeddingBaseUrl}
                          onChange={e => setEmbeddingBaseUrl(e.target.value)}
                          placeholder="Defaults to AI Base URL (e.g. https://api.openai.com/v1)"
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                          Embedding Model Name
                        </label>
                        <input
                          type="text"
                          className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs font-mono text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)]"
                          value={embeddingModel}
                          onChange={e => setEmbeddingModel(e.target.value)}
                          placeholder="text-embedding-3-small"
                        />
                      </div>
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <label className="text-xs font-semibold text-[var(--text-secondary)]">
                          Embedding API Key
                        </label>
                        {embeddingApiKeyMasked && (
                          <span className="text-[11px] text-[var(--text-muted)] font-mono">
                            Current: {embeddingApiKeyMasked}
                          </span>
                        )}
                      </div>
                      <input
                        type="password"
                        className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs font-mono text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)]"
                        value={embeddingApiKey}
                        onChange={e => setEmbeddingApiKey(e.target.value)}
                        placeholder="Leave blank to use main AI API key or existing value"
                      />
                    </div>
                  </div>

                  {/* Vector Store settings */}
                  <div className="border-t border-[var(--border)] pt-4 space-y-4">
                    <h4 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider">
                      Vector Database (Qdrant)
                    </h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                          Vector Backend Provider
                        </label>
                        <select
                          className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
                          value={vectorStoreProvider}
                          onChange={e => setVectorStoreProvider(e.target.value)}
                        >
                          <option value="qdrant">Qdrant Vector Database</option>
                          <option value="in_memory">In-Memory (Ephemeral / Dev)</option>
                        </select>
                      </div>

                      <div>
                        <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                          Qdrant URL
                        </label>
                        <input
                          type="text"
                          className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs font-mono text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)]"
                          value={qdrantUrl}
                          onChange={e => setQdrantUrl(e.target.value)}
                          placeholder="http://localhost:6333"
                        />
                      </div>
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <label className="text-xs font-semibold text-[var(--text-secondary)]">
                          Qdrant API Key
                        </label>
                        {qdrantApiKeyMasked && (
                          <span className="text-[11px] text-[var(--text-muted)] font-mono">
                            Current: {qdrantApiKeyMasked}
                          </span>
                        )}
                      </div>
                      <input
                        type="password"
                        className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs font-mono text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)]"
                        value={qdrantApiKey}
                        onChange={e => setQdrantApiKey(e.target.value)}
                        placeholder="Leave blank if no auth required or to keep existing key"
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
                  <div className="flex items-center justify-between p-3.5 bg-[rgba(255,255,255,0.02)] rounded-xl border border-[var(--border)]">
                    <div>
                      <div className="font-semibold text-xs text-[var(--text-primary)]">Campaign Broadcast Enabled</div>
                      <div className="text-[11px] text-[var(--text-muted)] mt-0.5">Allow scheduled/manual marketing broadcasts</div>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        className="sr-only peer"
                        checked={adAutomationEnabled}
                        onChange={e => setAdAutomationEnabled(e.target.checked)}
                      />
                      <div className="w-11 h-6 bg-[rgba(255,255,255,0.1)] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[var(--accent)] border border-[var(--border)]" />
                    </label>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                        Min Interval (Minutes)
                      </label>
                      <input
                        type="number"
                        className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
                        value={adMinIntervalMinutes}
                        onChange={e => setAdMinIntervalMinutes(parseInt(e.target.value, 10) || 180)}
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                        Quiet Hours Start (0-23)
                      </label>
                      <input
                        type="number"
                        min="0"
                        max="23"
                        className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
                        value={adQuietStart}
                        onChange={e => setAdQuietStart(parseInt(e.target.value, 10) || 23)}
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                        Quiet Hours End (0-23)
                      </label>
                      <input
                        type="number"
                        min="0"
                        max="23"
                        className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
                        value={adQuietEnd}
                        onChange={e => setAdQuietEnd(parseInt(e.target.value, 10) || 8)}
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                      Group Blacklist (comma-separated IDs)
                    </label>
                    <input
                      type="text"
                      className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs font-mono text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] transition-all"
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
                  <div className="p-4 bg-[rgba(255,255,255,0.02)] rounded-xl border border-[var(--border)] text-xs space-y-1">
                    <div className="font-semibold text-white">Security Policy</div>
                    <div className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
                      • Authentication tokens and gateway credentials are encrypted or masked at rest.<br />
                      • Admin actions are logged with actor identity and timestamp.<br />
                      • Manual takeover overrides automated AI execution deterministically.
                    </div>
                  </div>

                  <div className="border border-[var(--border)] rounded-xl overflow-hidden bg-[rgba(255,255,255,0.01)]">
                    <table className="w-full text-left text-xs border-collapse">
                      <thead>
                        <tr className="border-b border-[var(--border)] bg-[rgba(255,255,255,0.03)] text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                          <th className="px-3.5 py-2.5">Time</th>
                          <th className="px-3.5 py-2.5">Actor</th>
                          <th className="px-3.5 py-2.5">Action</th>
                          <th className="px-3.5 py-2.5">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[var(--border)]">
                        {auditLogs.length === 0 ? (
                          <tr>
                            <td colSpan={4} className="text-center py-6 text-[var(--text-muted)]">
                              No recent settings audit logs.
                            </td>
                          </tr>
                        ) : (
                          auditLogs.map(log => (
                            <tr key={log.id} className="hover:bg-[rgba(255,255,255,0.02)] transition-colors">
                              <td className="px-3.5 py-2.5 text-[11px] text-[var(--text-secondary)]">{new Date(log.created_at).toLocaleString()}</td>
                              <td className="px-3.5 py-2.5 font-mono text-[11px] text-[var(--text-primary)]">{log.actor}</td>
                              <td className="px-3.5 py-2.5 font-medium text-[11px] text-[var(--text-primary)]">{log.action}</td>
                              <td className="px-3.5 py-2.5">
                                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                  log.status === 'success'
                                    ? 'bg-[rgba(0,214,143,0.15)] text-[var(--success)] border border-[rgba(0,214,143,0.3)]'
                                    : 'bg-[rgba(255,255,255,0.05)] text-[var(--text-muted)] border border-[var(--border)]'
                                }`}>
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
                    <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-1.5">
                      Message Retention (Days)
                    </label>
                    <input
                      type="number"
                      min="1"
                      className="w-48 px-3 py-2 bg-[var(--bg-input)] border border-[var(--border)] rounded-lg text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
                      value={retentionDays}
                      onChange={e => setRetentionDays(parseInt(e.target.value, 10) || 30)}
                    />
                    <div className="text-[11px] text-[var(--text-muted)] mt-1.5">
                      Messages older than this threshold will be pruned during scheduled cleanup.
                    </div>
                  </div>

                  <div className="border-t border-[var(--border)] my-5" />

                  <div className="flex flex-wrap gap-4 items-center">
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      loading={cleanuping}
                      onClick={handleCleanupData}
                      className="gap-1.5"
                    >
                      <Trash2 className="w-3.5 h-3.5 text-[var(--danger)]" />
                      <span>Run Data Cleanup Now</span>
                    </Button>

                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      loading={rollingBack}
                      onClick={handleRollback}
                      className="gap-1.5 text-[var(--text-secondary)] hover:text-white"
                    >
                      <Undo2 className="w-3.5 h-3.5" />
                      <span>Roll Back Settings</span>
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
                    <div className="p-4 bg-[rgba(255,255,255,0.02)] rounded-xl border border-[var(--border)]">
                      <div className="font-semibold text-xs text-white mb-2.5 flex items-center gap-1.5">
                        <Radio className="w-4 h-4 text-[var(--accent)]" />
                        <span>Signal Connection</span>
                      </div>
                      <div className="text-xs space-y-1.5 text-[var(--text-secondary)]">
                        <div>Gateway: <span className="font-mono text-[var(--text-primary)]">{signalApiUrl || 'Not configured'}</span></div>
                        <div>Phone: <span className="font-mono text-[var(--text-primary)]">{signalPhoneNumber || 'Not configured'}</span></div>
                        <div className="pt-1">
                          Status: {signalTestResult ? (
                            signalTestResult.ok ? (
                              <span className="text-[var(--success)] font-medium inline-flex items-center gap-1">
                                <CheckCircle2 className="w-3.5 h-3.5" /> Connected
                              </span>
                            ) : (
                              <span className="text-[var(--danger)] font-medium inline-flex items-center gap-1">
                                <AlertCircle className="w-3.5 h-3.5" /> Error
                              </span>
                            )
                          ) : (
                            <span className="text-[var(--text-muted)]">Untested</span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="p-4 bg-[rgba(255,255,255,0.02)] rounded-xl border border-[var(--border)]">
                      <div className="font-semibold text-xs text-white mb-2.5 flex items-center gap-1.5">
                        <Bot className="w-4 h-4 text-[var(--accent)]" />
                        <span>AI Engine</span>
                      </div>
                      <div className="text-xs space-y-1.5 text-[var(--text-secondary)]">
                        <div>Model: <span className="font-mono text-[var(--text-primary)]">{aiModel}</span></div>
                        <div>Provider: <span className="font-mono text-[var(--text-primary)]">{inferProvider(aiModel)}</span></div>
                        <div className="pt-1">
                          Status: {modelVerifyResult ? (
                            modelVerifyResult.ok ? (
                              <span className="text-[var(--success)] font-medium inline-flex items-center gap-1">
                                <CheckCircle2 className="w-3.5 h-3.5" /> Verified
                              </span>
                            ) : (
                              <span className="text-[var(--danger)] font-medium inline-flex items-center gap-1">
                                <AlertCircle className="w-3.5 h-3.5" /> Failed
                              </span>
                            )
                          ) : (
                            <span className="text-[var(--text-muted)]">Unchecked</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </Card>
            )}

            {/* Bottom Save Action Bar */}
            <div className="flex items-center justify-between p-4 bg-[var(--bg-card)] rounded-2xl shadow-[var(--shadow)] border border-[var(--border)]">
              <div className="text-xs text-[var(--text-muted)]">
                Changes will take effect immediately upon saving.
              </div>
              <Button type="submit" variant="primary" size="sm" loading={saving} className="gap-1.5">
                <Save className="w-4 h-4" />
                <span>Save Settings</span>
              </Button>
            </div>
          </form>
        )}
      </div>
    </SidebarLayout>
  );
}
