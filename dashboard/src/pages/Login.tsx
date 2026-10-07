import React, { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { AlertCircle } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import { LanguageSelector } from '../components/LanguageSelector';

export const Login: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { login } = useAuth();
  const { t } = useLanguage();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as any)?.from?.pathname || '/';

  React.useEffect(() => {
    document.title = 'Sign In | DoxaRank';
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err: any) {
      if (err?.data?.non_field_errors) {
        setError(err.data.non_field_errors.join(' '));
      } else if (err?.data?.detail) {
        setError(err.data.detail);
      } else if (err?.data && typeof err.data === 'object') {
        const messages = Object.entries(err.data).map(
          ([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`
        );
        setError(messages.join(' | '));
      } else {
        setError('Login failed. Please verify your email and password.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={containerStyle}>
      {/* Ambient Doxa Glow */}
      <div style={glowStyle} />

      <div style={cardStyle}>
        {/* Language Selector in Auth Card */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '12px' }}>
          <LanguageSelector variant="light" />
        </div>

        {/* Brand Header */}
        <div style={{ marginBottom: '28px', textAlign: 'center' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', marginBottom: '14px' }}>
            <img
              src="/doxa-logo.png"
              alt="DoxaRank Logo"
              style={{ width: '56px', height: '56px', objectFit: 'contain', borderRadius: '12px', boxShadow: '0 4px 12px rgba(36, 20, 60, 0.15)' }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '4px' }}>
            <h1 style={{ fontSize: '24px', fontWeight: 800, margin: 0, color: '#24143C', letterSpacing: '-0.02em' }}>
              Doxa<span style={{ color: '#774DA9' }}>Rank</span>
            </h1>
            <span style={{
              fontSize: '10px',
              fontWeight: 800,
              backgroundColor: '#f3eef9',
              color: '#774DA9',
              border: '1px solid #dac8ee',
              padding: '2px 8px',
              borderRadius: '9999px',
            }}>
              ET
            </span>
          </div>

          <p style={{ color: '#64748b', fontSize: '13px', margin: 0 }}>
            {t('auth.login_subtitle', 'Sign in to access your Google Ethiopia SEO intelligence')}
          </p>
        </div>

        {error && (
          <div style={errorBannerStyle}>
            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: '1px' }} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label htmlFor="login-email" style={labelStyle}>
              {t('auth.email', 'Email Address')}
            </label>
            <input
              id="login-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.et"
              style={inputStyle}
              autoComplete="email"
            />
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
              <label htmlFor="login-password" style={{ ...labelStyle, marginBottom: 0 }}>
                {t('auth.password', 'Password')}
              </label>
            </div>
            <input
              id="login-password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              style={inputStyle}
              autoComplete="current-password"
            />
          </div>

          <button
            id="login-submit-button"
            type="submit"
            disabled={isSubmitting}
            style={{
              ...buttonStyle,
              opacity: isSubmitting ? 0.75 : 1,
              cursor: isSubmitting ? 'not-allowed' : 'pointer',
            }}
          >
            {isSubmitting ? t('auth.signing_in', 'Authenticating...') : t('auth.sign_in', 'Sign In to Dashboard')}
          </button>
        </form>

        <div style={{ marginTop: '24px', paddingTop: '20px', borderTop: '1px solid #f1f5f9', textAlign: 'center' }}>
          <p style={{ fontSize: '13px', color: '#64748b', margin: 0 }}>
            {t('auth.no_account', "Don't have an account yet?")}{' '}
            <Link to="/register" style={{ color: '#774DA9', fontWeight: 700, textDecoration: 'none' }}>
              {t('auth.create_account', 'Create one now')}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};

const containerStyle: React.CSSProperties = {
  minHeight: '100vh',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  backgroundColor: '#fbf9fd',
  backgroundImage: `
    radial-gradient(at 15% 12%, rgba(254, 215, 215, 0.6) 0px, transparent 50%),
    radial-gradient(at 85% 10%, rgba(221, 214, 254, 0.7) 0px, transparent 55%),
    radial-gradient(at 50% 28%, rgba(238, 242, 255, 0.65) 0px, transparent 60%),
    radial-gradient(at 90% 45%, rgba(254, 226, 226, 0.4) 0px, transparent 50%),
    radial-gradient(at 20% 60%, rgba(233, 213, 255, 0.45) 0px, transparent 55%)
  `,
  padding: '24px 16px',
  fontFamily: "'Plus Jakarta Sans', system-ui, -apple-system, sans-serif",
  position: 'relative',
  overflow: 'hidden',
  boxSizing: 'border-box',
};

const glowStyle: React.CSSProperties = {
  position: 'absolute',
  width: '540px',
  height: '540px',
  borderRadius: '50%',
  backgroundColor: 'rgba(167, 139, 250, 0.15)',
  filter: 'blur(120px)',
  top: '50%',
  left: '50%',
  transform: 'translate(-50%, -50%)',
  pointerEvents: 'none',
};

const cardStyle: React.CSSProperties = {
  width: '100%',
  maxWidth: '430px',
  backgroundColor: 'rgba(255, 255, 255, 0.94)',
  backdropFilter: 'blur(16px)',
  WebkitBackdropFilter: 'blur(16px)',
  padding: '36px 32px',
  borderRadius: '24px',
  border: '1px solid rgba(167, 139, 250, 0.25)',
  boxShadow: '0 20px 40px -8px rgba(36, 20, 60, 0.08), 0 4px 16px rgba(36, 20, 60, 0.03)',
  position: 'relative',
  zIndex: 1,
  boxSizing: 'border-box',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: '11px',
  fontWeight: 700,
  color: '#475569',
  marginBottom: '6px',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '11px 16px',
  fontSize: '14px',
  color: '#1e1b4b',
  backgroundColor: '#ffffff',
  border: '1px solid rgba(167, 139, 250, 0.35)',
  borderRadius: '9999px',
  boxSizing: 'border-box',
  outline: 'none',
  transition: 'border-color 0.2s, box-shadow 0.2s',
};

const buttonStyle: React.CSSProperties = {
  width: '100%',
  padding: '12px 20px',
  background: 'linear-gradient(135deg, #774DA9 0%, #663e99 100%)',
  color: '#ffffff',
  fontSize: '14px',
  fontWeight: 700,
  border: 'none',
  borderRadius: '9999px',
  marginTop: '8px',
  boxShadow: '0 4px 14px -1px rgba(119, 77, 169, 0.38)',
  cursor: 'pointer',
  transition: 'all 0.2s ease',
};

const errorBannerStyle: React.CSSProperties = {
  backgroundColor: '#fef2f2',
  color: '#991b1b',
  padding: '10px 14px',
  borderRadius: '12px',
  fontSize: '13px',
  marginBottom: '16px',
  border: '1px solid #fecaca',
  display: 'flex',
  alignItems: 'center',
};
