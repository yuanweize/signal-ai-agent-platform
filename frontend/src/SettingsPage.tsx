import { useState } from 'react';
import SidebarLayout from './SidebarLayout';

export default function SettingsPage() {
  const [aiEnabled, setAiEnabled] = useState(true);
  const [marketEnabled, setMarketEnabled] = useState(true);
  const [prompt, setPrompt] = useState('Jsi přátelský prodejní asistent. Odpovídej přirozeně česky, jako bys byl skutečný člověk. Nikdy neprozrazuj, že jsi AI.');
  const [apiKey, setApiKey] = useState('sk-***************************');
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  return (
    <SidebarLayout title="Settings">
      <div className="settings-group">
        <h3 className="settings-group-title">Module Configuration</h3>
        
        <div className="setting-item">
          <div className="setting-info">
            <div className="setting-label">AI Responses (FEATURE_AI_ENABLED)</div>
            <div className="setting-desc">Enable or disable automatic AI responses to incoming messages.</div>
          </div>
          <div className="setting-action">
            <label className="switch">
              <input type="checkbox" checked={aiEnabled} onChange={e => setAiEnabled(e.target.checked)} />
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
              <input type="checkbox" checked={marketEnabled} onChange={e => setMarketEnabled(e.target.checked)} />
              <span className="slider"></span>
            </label>
          </div>
        </div>
      </div>

      <div className="settings-group">
        <h3 className="settings-group-title">AI Engine Settings</h3>
        
        <div className="form-group" style={{ marginBottom: '1.5rem' }}>
          <label>API Key</label>
          <input 
            type="password" 
            value={apiKey} 
            onChange={e => setApiKey(e.target.value)}
            placeholder="Enter OpenAI-compatible API Key"
          />
        </div>

        <div className="form-group">
          <label>Bot System Prompt</label>
          <textarea 
            rows={4}
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            placeholder="System instructions for the AI"
          />
          <div className="label-hint" style={{ marginTop: '0.5rem', marginLeft: 0 }}>
            This prompt defines the bot's personality and language.
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem', alignItems: 'center' }}>
        {saved && <span style={{ color: 'var(--success)', fontSize: '0.9rem', fontWeight: 500 }}>✅ Settings Saved!</span>}
        <button onClick={handleSave} className="btn-primary" style={{ width: 'auto', padding: '0.7rem 2rem' }}>
          Save Configuration
        </button>
      </div>

      <div style={{ marginTop: '2rem', padding: '1rem', background: 'rgba(255, 217, 61, 0.05)', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(255, 217, 61, 0.2)' }}>
        <p style={{ fontSize: '0.85rem', color: 'var(--warning)', margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '1.2rem' }}>⚠️</span> 
          <span><strong>Note:</strong> Settings page is currently UI-only. To apply these changes to the backend in Phase 5, please edit the <code>.env</code> file directly. Future agents will wire this to the database.</span>
        </p>
      </div>
    </SidebarLayout>
  );
}
