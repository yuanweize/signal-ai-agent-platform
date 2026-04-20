import { useState, useEffect, FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from './api';

export default function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [requires2fa, setRequires2fa] = useState<boolean | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Check 2FA requirement on mount
  useEffect(() => {
    api.checkAuth()
      .then(data => setRequires2fa(data.requires_2fa))
      .catch(() => setRequires2fa(false));
  }, []);

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
        <p className="login-subtitle">Admin Access</p>

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

        {requires2fa !== null && (
          <div className={`security-badge ${requires2fa ? 'secure' : 'basic'}`}>
            {requires2fa ? '🛡️ 2FA Enabled' : '⚠️ Password Only'}
          </div>
        )}
      </div>
    </div>
  );
}
