import React, { useEffect, useState, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { exchangeGoogleOAuthCallback } from '../api/googleOAuth';
import type { SearchConsoleConnection } from '../types/searchConsole';

export const GoogleOAuthCallback: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [connection, setConnection] = useState<SearchConsoleConnection | null>(null);

  // Prevent double invocation in React StrictMode
  const hasExecutedRef = useRef(false);

  useEffect(() => {
    if (hasExecutedRef.current) return;
    hasExecutedRef.current = true;

    const code = searchParams.get('code') || undefined;
    const state = searchParams.get('state') || undefined;
    const error = searchParams.get('error') || undefined;
    const errorDescription = searchParams.get('error_description') || undefined;

    if (error) {
      setStatus('error');
      setErrorMessage(
        error === 'access_denied'
          ? 'Google authorization was denied by the user. You can try connecting again whenever you are ready.'
          : `Google authorization error: ${errorDescription || error}`
      );
      return;
    }

    if (!code || !state) {
      setStatus('error');
      setErrorMessage('Missing OAuth authorization code or state parameter from Google redirect.');
      return;
    }

    const performExchange = async () => {
      try {
        const result = await exchangeGoogleOAuthCallback({
          code,
          state,
        });
        setConnection(result);
        setStatus('success');
      } catch (err: any) {
        setStatus('error');
        setErrorMessage(
          err?.data?.detail ||
          err?.message ||
          'Failed to exchange authorization code with Google. Please try connecting again.'
        );
      }
    };

    performExchange();
  }, [searchParams]);

  const handleReturnToDashboard = () => {
    navigate('/', { replace: true });
  };

  return (
    <div style={containerStyle}>
      <div style={cardStyle}>
        {/* Header Icon */}
        <div style={iconBadgeStyle}>
          {status === 'loading' && <span style={{ fontSize: '28px' }}>🔄</span>}
          {status === 'success' && <span style={{ fontSize: '28px' }}>✅</span>}
          {status === 'error' && <span style={{ fontSize: '28px' }}>❌</span>}
        </div>

        {/* Loading State */}
        {status === 'loading' && (
          <div>
            <h2 style={titleStyle}>Connecting to Google Search Console...</h2>
            <p style={subtitleStyle}>
              Exchanging authorization code and securely configuring credentials. Please wait a moment.
            </p>
            <div style={spinnerStyle}></div>
          </div>
        )}

        {/* Success State */}
        {status === 'success' && (
          <div>
            <h2 style={{ ...titleStyle, color: '#15803d' }}>Google Search Console Connected!</h2>
            <p style={subtitleStyle}>
              Your Google account <strong>{connection?.google_account_email || 'authorized identity'}</strong> has been successfully linked to your project.
            </p>

            {connection && (
              <div style={metadataBoxStyle}>
                <div style={metaRowStyle}>
                  <span style={metaLabelStyle}>Property:</span>
                  <span style={metaValueStyle}>{connection.property_url}</span>
                </div>
                <div style={metaRowStyle}>
                  <span style={metaLabelStyle}>Permission Level:</span>
                  <span style={metaValueStyle}>{connection.permission_level}</span>
                </div>
                <div style={metaRowStyle}>
                  <span style={metaLabelStyle}>Status:</span>
                  <span style={{ ...metaValueStyle, color: '#16a34a', fontWeight: 700 }}>● Active</span>
                </div>
              </div>
            )}

            <button
              id="return-to-dashboard-btn"
              onClick={handleReturnToDashboard}
              style={primaryButtonStyle}
            >
              Return to Dashboard
            </button>
          </div>
        )}

        {/* Error State */}
        {status === 'error' && (
          <div>
            <h2 style={{ ...titleStyle, color: '#b91c1c' }}>Authorization Failed</h2>
            <div style={errorAlertStyle}>
              {errorMessage}
            </div>
            <p style={subtitleStyle}>
              No credentials were saved. You can retry the Google Search Console connection from your project dashboard.
            </p>
            <button
              id="return-to-dashboard-error-btn"
              onClick={handleReturnToDashboard}
              style={{ ...primaryButtonStyle, backgroundColor: '#4b5563' }}
            >
              Back to Dashboard
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

// Styles
const containerStyle: React.CSSProperties = {
  minHeight: '100vh',
  backgroundColor: '#f8fafc',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '24px',
  boxSizing: 'border-box',
};

const cardStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '16px',
  border: '1px solid #e2e8f0',
  padding: '40px 32px',
  maxWidth: '520px',
  width: '100%',
  textAlign: 'center',
  boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.05)',
  boxSizing: 'border-box',
};

const iconBadgeStyle: React.CSSProperties = {
  width: '64px',
  height: '64px',
  borderRadius: '50%',
  backgroundColor: '#f1f5f9',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  margin: '0 auto 20px auto',
  border: '1px solid #e2e8f0',
};

const titleStyle: React.CSSProperties = {
  margin: '0 0 10px 0',
  fontSize: '22px',
  fontWeight: 700,
  color: '#0f172a',
};

const subtitleStyle: React.CSSProperties = {
  margin: '0 0 24px 0',
  fontSize: '14px',
  color: '#64748b',
  lineHeight: 1.6,
};

const metadataBoxStyle: React.CSSProperties = {
  backgroundColor: '#f8fafc',
  border: '1px solid #e2e8f0',
  borderRadius: '8px',
  padding: '16px',
  marginBottom: '24px',
  textAlign: 'left',
  display: 'flex',
  flexDirection: 'column',
  gap: '8px',
};

const metaRowStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  fontSize: '13px',
};

const metaLabelStyle: React.CSSProperties = {
  color: '#64748b',
  fontWeight: 500,
};

const metaValueStyle: React.CSSProperties = {
  color: '#0f172a',
  fontWeight: 600,
};

const primaryButtonStyle: React.CSSProperties = {
  width: '100%',
  padding: '12px 20px',
  backgroundColor: '#2563eb',
  color: '#ffffff',
  border: 'none',
  borderRadius: '8px',
  fontSize: '14px',
  fontWeight: 600,
  cursor: 'pointer',
  transition: 'background-color 0.15s ease',
};

const errorAlertStyle: React.CSSProperties = {
  backgroundColor: '#fef2f2',
  color: '#b91c1c',
  padding: '14px 16px',
  borderRadius: '8px',
  fontSize: '13px',
  marginBottom: '20px',
  border: '1px solid #fecaca',
  textAlign: 'left',
  lineHeight: 1.5,
};

const spinnerStyle: React.CSSProperties = {
  width: '32px',
  height: '32px',
  border: '3px solid #e2e8f0',
  borderTop: '3px solid #2563eb',
  borderRadius: '50%',
  margin: '16px auto',
  animation: 'spin 1s linear infinite',
};
