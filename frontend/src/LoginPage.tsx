import { useState, useEffect, FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from './api';

export default function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [bootstrapRequired, setBootstrapRequired] = useState(false);
  const [setupPassword, setSetupPassword] = useState('');
  const [setupPasswordConfirm, setSetupPasswordConfirm] = useState('');
  const [setupTotpSecret, setSetupTotpSecret] = useState('');
  const [generatedTotpSecret, setGeneratedTotpSecret] = useState('');
  const [setupSuccess, setSetupSuccess] = useState('');
  const [requires2fa, setRequires2fa] = useState<boolean | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Check 2FA requirement on mount
  useEffect(() => {
    api.checkAuth()
      .then(data => {
        setRequires2fa(data.requires_2fa);
        setBootstrapRequired(Boolean(data.bootstrap_required));
      })
      .catch(() => setRequires2fa(false));
  }, []);

  const handleBootstrapSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const result = await api.initBootstrap({
        username: 'admin',
        password: setupPassword,
        password_confirm: setupPasswordConfirm,
        totp_secret: setupTotpSecret.trim() || undefined,
      });

      setGeneratedTotpSecret(result.generated_totp_secret || '');
      setSetupSuccess('Initialization complete. Please use these credentials to login.');
      setBootstrapRequired(false);
      setUsername(result.username || 'admin');
      setRequires2fa(true);
      setSetupPassword('');
      setSetupPasswordConfirm('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Initialization failed');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const data = await api.login(username, password, totpCode || undefined);
      api.setToken(data.access_token);
      navigate('/');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">🔐</div>
        <h1>Signal Market Bot</h1>
        <p className="login-subtitle">{bootstrapRequired ? 'First-time setup' : 'Admin Access'}</p>

        {bootstrapRequired ? (
          <form onSubmit={handleBootstrapSubmit}>
            <div className="form-group">
              <label htmlFor="setup-password">Admin Password</label>
              <input
                id="setup-password"
                type="password"
                value={setupPassword}
                onChange={e => setSetupPassword(e.target.value)}
                placeholder="At least 12 chars with upper/lower/number/symbol"
                autoFocus
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="setup-password-confirm">Confirm Password</label>
              <input
                id="setup-password-confirm"
                type="password"
                value={setupPasswordConfirm}
                onChange={e => setSetupPasswordConfirm(e.target.value)}
                placeholder="Repeat password"
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="setup-totp">
                TOTP Secret
                <span className="label-hint">leave empty to auto-generate</span>
              </label>
              <input
                id="setup-totp"
                type="text"
                value={setupTotpSecret}
                onChange={e => setSetupTotpSecret(e.target.value.toUpperCase())}
                placeholder="Base32 secret"
              />
            </div>

            {error && <div className="form-error">{error}</div>}
            {setupSuccess && <div className="form-success">{setupSuccess}</div>}
            {generatedTotpSecret && (
              <div className="form-success">
                Save this TOTP secret now: <strong>{generatedTotpSecret}</strong>
              </div>
            )}

            <button
              type="submit"
              className="btn-primary"
              disabled={loading}
            >
              {loading ? 'Initializing...' : 'Initialize Secure Access'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label htmlFor="username">Username</label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="admin"
                autoFocus
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
            </div>

            {requires2fa && (
              <div className="form-group">
                <label htmlFor="totp">
                  2FA Code
                  <span className="label-hint">from authenticator app</span>
                </label>
                <input
                  id="totp"
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={totpCode}
                  onChange={e => setTotpCode(e.target.value.replace(/\D/g, ''))}
                  placeholder="000000"
                  autoComplete="one-time-code"
                />
              </div>
            )}

            {error && <div className="form-error">{error}</div>}

            <button
              type="submit"
              className="btn-primary"
              disabled={loading}
            >
              {loading ? 'Authenticating...' : 'Login'}
            </button>
          </form>
        )}

        {!bootstrapRequired && requires2fa !== null && (
          <div className={`security-badge ${requires2fa ? 'secure' : 'basic'}`}>
            {requires2fa ? '🛡️ 2FA Enabled' : '⚠️ Password Only'}
          </div>
        )}
      </div>
    </div>
  );
}
