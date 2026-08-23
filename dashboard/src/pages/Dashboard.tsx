import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { apiFetch } from '../api/client';

export const Dashboard: React.FC = () => {
  const { user, logout } = useAuth();
  const [apiData, setApiData] = useState<any>(null);
  const [isLoadingApi, setIsLoadingApi] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  const handleTestProtectedEndpoint = async () => {
    setIsLoadingApi(true);
    setApiError(null);
    try {
      const data = await apiFetch('/api/auth/me/');
      setApiData(data);
    } catch (err: any) {
      setApiError(err?.data?.detail || 'Failed to fetch protected endpoint');
    } finally {
      setIsLoadingApi(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f9fafb', fontFamily: 'system-ui, sans-serif', width: '100%', boxSizing: 'border-box' }}>
      {/* Navigation Header */}
      <header style={headerStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={logoIconStyle}>D</div>
          <div>
            <h1 style={{ fontSize: '18px', margin: 0, fontWeight: 700, color: '#111827' }}>DoxaRank</h1>
            <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 600 }}>● Authenticated Session</span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '14px', fontWeight: 600, color: '#111827' }}>
              {user?.full_name || 'DoxaRank User'}
            </div>
            <div style={{ fontSize: '12px', color: '#6b7280' }}>
              {user?.email}
            </div>
          </div>
          <button
            id="logout-button"
            onClick={logout}
            style={logoutButtonStyle}
          >
            Log out
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main style={{ maxWidth: '960px', margin: '32px auto', padding: '0 16px', textAlign: 'left' }}>
        <div style={welcomeCardStyle}>
          <h2 style={{ margin: '0 0 8px 0', fontSize: '24px', color: '#111827' }}>
            Welcome back, {user?.first_name || user?.email}! 👋
          </h2>
          <p style={{ color: '#4b5563', fontSize: '15px', margin: '0 0 20px 0' }}>
            Your authentication state is active, verified with SimpleJWT, and connected to Neon PostgreSQL.
          </p>

          <div style={gridStyle}>
            <div style={infoBoxStyle}>
              <div style={infoLabelStyle}>User ID</div>
              <div style={infoValueStyle}>{user?.id}</div>
            </div>
            <div style={infoBoxStyle}>
              <div style={infoLabelStyle}>Email</div>
              <div style={infoValueStyle}>{user?.email}</div>
            </div>
            <div style={infoBoxStyle}>
              <div style={infoLabelStyle}>Member Since</div>
              <div style={infoValueStyle}>
                {user?.created_at ? new Date(user.created_at).toLocaleDateString() : 'N/A'}
              </div>
            </div>
          </div>
        </div>

        {/* API Verification Card */}
        <div style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <div>
              <h3 style={{ margin: 0, fontSize: '18px', color: '#111827' }}>Protected API Endpoint Verification</h3>
              <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#6b7280' }}>
                Test calling <code>GET /api/auth/me/</code> with your current Bearer token.
              </p>
            </div>
            <button
              id="test-api-button"
              onClick={handleTestProtectedEndpoint}
              disabled={isLoadingApi}
              style={actionButtonStyle}
            >
              {isLoadingApi ? 'Fetching...' : 'Test GET /api/auth/me/'}
            </button>
          </div>

          {apiError && (
            <div style={{ padding: '12px', backgroundColor: '#fef2f2', color: '#b91c1c', borderRadius: '6px', fontSize: '14px' }}>
              Error: {apiError}
            </div>
          )}

          {apiData && (
            <div style={{ marginTop: '16px' }}>
              <div style={{ fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '6px' }}>
                Server Response (200 OK):
              </div>
              <pre style={codeBlockStyle}>
                {JSON.stringify(apiData, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

const headerStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderBottom: '1px solid #e5e7eb',
  padding: '16px 24px',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
};

const logoIconStyle: React.CSSProperties = {
  width: '36px',
  height: '36px',
  backgroundColor: '#2563eb',
  color: '#ffffff',
  borderRadius: '8px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontWeight: 700,
  fontSize: '18px',
};

const logoutButtonStyle: React.CSSProperties = {
  padding: '8px 16px',
  backgroundColor: '#f3f4f6',
  color: '#374151',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  fontSize: '14px',
  fontWeight: 600,
  cursor: 'pointer',
};

const welcomeCardStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  padding: '24px',
  border: '1px solid #e5e7eb',
  marginBottom: '24px',
};

const cardStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  padding: '24px',
  border: '1px solid #e5e7eb',
};

const gridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
  gap: '16px',
};

const infoBoxStyle: React.CSSProperties = {
  backgroundColor: '#f9fafb',
  padding: '16px',
  borderRadius: '8px',
  border: '1px solid #f3f4f6',
};

const infoLabelStyle: React.CSSProperties = {
  fontSize: '12px',
  color: '#6b7280',
  textTransform: 'uppercase',
  fontWeight: 600,
  marginBottom: '4px',
};

const infoValueStyle: React.CSSProperties = {
  fontSize: '16px',
  fontWeight: 600,
  color: '#111827',
};

const actionButtonStyle: React.CSSProperties = {
  padding: '10px 18px',
  backgroundColor: '#2563eb',
  color: '#ffffff',
  border: 'none',
  borderRadius: '6px',
  fontSize: '14px',
  fontWeight: 600,
  cursor: 'pointer',
};

const codeBlockStyle: React.CSSProperties = {
  backgroundColor: '#1f2937',
  color: '#10b981',
  padding: '16px',
  borderRadius: '8px',
  fontSize: '13px',
  overflowX: 'auto',
  fontFamily: 'Consolas, Monaco, monospace',
};
