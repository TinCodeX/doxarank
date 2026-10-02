import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { AlertCircle } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export const Register: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      await register(email, password, firstName, lastName);
      navigate('/', { replace: true });
    } catch (err: any) {
      if (err?.data && typeof err.data === 'object') {
        const messages = Object.entries(err.data).map(
          ([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`
        );
        setError(messages.join(' | '));
      } else {
        setError('Registration failed. Please check your information and try again.');
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
        {/* Brand Header */}
        <div style={{ marginBottom: '24px', textAlign: 'center' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', marginBottom: '12px' }}>
            <img
              src="/doxa-logo.png"
              alt="DoxaRank Logo"
              style={{ width: '52px', height: '52px', objectFit: 'contain', borderRadius: '12px', boxShadow: '0 4px 12px rgba(36, 20, 60, 0.15)' }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '4px' }}>
            <h1 style={{ fontSize: '22px', fontWeight: 800, margin: 0, color: '#24143C', letterSpacing: '-0.02em' }}>
              Create your Doxa<span style={{ color: '#774DA9' }}>Rank</span> account
            </h1>
            <span style={{
              fontSize: '10px',
              fontWeight: 700,
              backgroundColor: '#ecfdf5',
              color: '#065f46',
              border: '1px solid #a7f3d0',
              padding: '2px 6px',
              borderRadius: '9999px',
            }}>
              ET
            </span>
          </div>

          <p style={{ color: '#64748b', fontSize: '13px', margin: 0 }}>
            Start tracking rankings on Google Ethiopia and optimizing technical SEO
          </p>
        </div>

        {error && (
          <div style={errorBannerStyle}>
            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: '1px' }} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', gap: '12px' }}>
            <div style={{ flex: 1 }}>
              <label htmlFor="reg-first-name" style={labelStyle}>
                First Name
              </label>
              <input
                id="reg-first-name"
                type="text"
                required
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                placeholder="Abebe"
                style={inputStyle}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label htmlFor="reg-last-name" style={labelStyle}>
                Last Name
              </label>
              <input
                id="reg-last-name"
                type="text"
                required
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                placeholder="Kebede"
                style={inputStyle}
              />
            </div>
          </div>

          <div>
            <label htmlFor="reg-email" style={labelStyle}>
              Work Email Address
            </label>
            <input
              id="reg-email"
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
            <label htmlFor="reg-password" style={labelStyle}>
              Password
            </label>
            <input
              id="reg-password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              style={inputStyle}
              autoComplete="new-password"
            />
          </div>

          <button
            id="register-submit-button"
            type="submit"
            disabled={isSubmitting}
            style={{
              ...buttonStyle,
              opacity: isSubmitting ? 0.75 : 1,
              cursor: isSubmitting ? 'not-allowed' : 'pointer',
            }}
          >
            {isSubmitting ? 'Creating account...' : 'Create Account & Start Free'}
          </button>
        </form>

        <div style={{ marginTop: '20px', paddingTop: '18px', borderTop: '1px solid #f1f5f9', textAlign: 'center' }}>
          <p style={{ fontSize: '13px', color: '#64748b', margin: 0 }}>
            Already have an account?{' '}
            <Link to="/login" style={{ color: '#774DA9', fontWeight: 700, textDecoration: 'none' }}>
              Sign in
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
  backgroundColor: '#24143C',
  backgroundImage: 'radial-gradient(ellipse at 50% 20%, #3b1d5f 0%, #24143C 70%)',
  padding: '24px 16px',
  fontFamily: "'Plus Jakarta Sans', system-ui, -apple-system, sans-serif",
  position: 'relative',
  overflow: 'hidden',
  boxSizing: 'border-box',
};

const glowStyle: React.CSSProperties = {
  position: 'absolute',
  width: '500px',
  height: '500px',
  borderRadius: '50%',
  backgroundColor: 'rgba(119, 77, 169, 0.18)',
  filter: 'blur(100px)',
  top: '50%',
  left: '50%',
  transform: 'translate(-50%, -50%)',
  pointerEvents: 'none',
};

const cardStyle: React.CSSProperties = {
  width: '100%',
  maxWidth: '440px',
  backgroundColor: '#ffffff',
  padding: '36px 32px',
  borderRadius: '16px',
  boxShadow: '0 20px 35px -5px rgba(10, 5, 20, 0.4), 0 0 0 1px rgba(255, 255, 255, 0.15)',
  position: 'relative',
  zIndex: 1,
  boxSizing: 'border-box',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: '12px',
  fontWeight: 700,
  color: '#334155',
  marginBottom: '6px',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 14px',
  fontSize: '14px',
  color: '#0f172a',
  backgroundColor: '#f8fafc',
  border: '1px solid #cbd5e1',
  borderRadius: '8px',
  boxSizing: 'border-box',
  outline: 'none',
  transition: 'border-color 0.15s, box-shadow 0.15s',
};

const buttonStyle: React.CSSProperties = {
  width: '100%',
  padding: '12px 16px',
  backgroundColor: '#774DA9',
  color: '#ffffff',
  fontSize: '14px',
  fontWeight: 700,
  border: 'none',
  borderRadius: '8px',
  marginTop: '8px',
  boxShadow: '0 4px 14px rgba(119, 77, 169, 0.35)',
  transition: 'all 0.15s ease',
};

const errorBannerStyle: React.CSSProperties = {
  backgroundColor: '#fef2f2',
  color: '#991b1b',
  padding: '10px 14px',
  borderRadius: '8px',
  fontSize: '13px',
  marginBottom: '16px',
  border: '1px solid #fecaca',
  display: 'flex',
  alignItems: 'center',
};
