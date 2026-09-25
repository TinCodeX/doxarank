import React, { useState, useEffect, useCallback } from 'react';
import {
  getIntegrationsStatus,
  getGoogleConnectUrl,
  disconnectGoogle,
  getSearchConsoleProperties,
  associateSearchConsoleProperty,
  type IntegrationConnectionStatus,
  type SearchConsoleProperty,
} from '../api/integrations';
import type { Project } from '../types/project';

interface GoogleIntegrationSectionProps {
  project?: Project | null;
  onPropertyAssociated?: () => void;
}

export const GoogleIntegrationSection: React.FC<GoogleIntegrationSectionProps> = ({
  project,
  onPropertyAssociated,
}) => {
  const [googleStatus, setGoogleStatus] = useState<IntegrationConnectionStatus | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState<boolean>(true);
  const [isConnecting, setIsConnecting] = useState<boolean>(false);
  const [isDisconnecting, setIsDisconnecting] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Properties state
  const [properties, setProperties] = useState<SearchConsoleProperty[] | null>(null);
  const [isLoadingProperties, setIsLoadingProperties] = useState<boolean>(false);
  const [showProperties, setShowProperties] = useState<boolean>(false);
  const [associatingUrl, setAssociatingUrl] = useState<string | null>(null);

  // Fetch integration status
  const fetchStatus = useCallback(async () => {
    setIsLoadingStatus(true);
    setActionError(null);
    try {
      const res = await getIntegrationsStatus();
      if (res && res.google) {
        setGoogleStatus(res.google);
      } else {
        setGoogleStatus({
          connected: false,
          status: 'disconnected',
        });
      }
    } catch (err: any) {
      console.warn('Failed to fetch integrations status:', err);
      setGoogleStatus({
        connected: false,
        status: 'disconnected',
      });
    } finally {
      setIsLoadingStatus(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Connect Google handler
  const handleConnectGoogle = async () => {
    setIsConnecting(true);
    setActionError(null);
    try {
      const res = await getGoogleConnectUrl();
      if (res?.authorization_url) {
        window.location.href = res.authorization_url;
      } else {
        setActionError('Failed to generate Google authorization URL.');
      }
    } catch (err: any) {
      const detail = err?.data?.detail || err?.data?.message || err?.message;
      if (err?.data?.code === 'FEATURE_NOT_ENTITLED') {
        setActionError('Google Search Console integration requires a Starter or Agency plan subscription.');
      } else {
        setActionError(detail || 'Failed to initiate Google connection.');
      }
    } finally {
      setIsConnecting(false);
    }
  };

  // Disconnect Google handler
  const handleDisconnectGoogle = async () => {
    if (!window.confirm('Are you sure you want to disconnect your Google account from DoxaRank?')) {
      return;
    }
    setIsDisconnecting(true);
    setActionError(null);
    setSuccessMessage(null);
    try {
      await disconnectGoogle();
      setProperties(null);
      setShowProperties(false);
      setSuccessMessage('Google account disconnected successfully.');
      await fetchStatus();
    } catch (err: any) {
      setActionError(err?.data?.detail || 'Failed to disconnect Google account.');
    } finally {
      setIsDisconnecting(false);
    }
  };

  // View properties handler
  const handleToggleProperties = async () => {
    if (showProperties) {
      setShowProperties(false);
      return;
    }

    setShowProperties(true);
    if (properties === null) {
      setIsLoadingProperties(true);
      setActionError(null);
      try {
        const props = await getSearchConsoleProperties();
        setProperties(props);
      } catch (err: any) {
        setActionError(
          err?.data?.detail || 'Failed to fetch verified Search Console properties from Google.'
        );
        setShowProperties(false);
      } finally {
        setIsLoadingProperties(false);
      }
    }
  };

  // Associate property with project
  const handleAssociateProperty = async (property: SearchConsoleProperty) => {
    if (!project?.id) {
      setActionError('Please select a project before linking a Search Console property.');
      return;
    }

    setAssociatingUrl(property.site_url);
    setActionError(null);
    setSuccessMessage(null);
    try {
      await associateSearchConsoleProperty({
        project_id: project.id,
        site_url: property.site_url,
        permission_level: property.permission_level,
      });
      setSuccessMessage(`Successfully linked '${property.site_url}' to project '${project.name}'.`);
      onPropertyAssociated?.();
    } catch (err: any) {
      setActionError(err?.data?.detail || 'Failed to link property to project.');
    } finally {
      setAssociatingUrl(null);
    }
  };

  const isConnected = Boolean(googleStatus?.connected && googleStatus?.has_valid_credentials);

  return (
    <div style={containerCardStyle} id="google-integration-section">
      {/* Header */}
      <div style={headerRowStyle}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#111827' }}>
              Google Search Console
            </h4>
            {isLoadingStatus ? (
              <span style={badgeNeutralStyle}>Checking...</span>
            ) : isConnected ? (
              <span style={badgeConnectedStyle} id="gsc-connection-status-badge">● Connected</span>
            ) : (
              <span style={badgeDisconnectedStyle} id="gsc-connection-status-badge">○ Not connected</span>
            )}
          </div>
          <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#6b7280' }}>
            Connect your Google account to discover and sync verified Search Console properties.
          </p>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {!isLoadingStatus && (
            isConnected ? (
              <>
                <button
                  id="view-gsc-properties-btn"
                  onClick={handleToggleProperties}
                  disabled={isLoadingProperties}
                  style={secondaryBtnStyle}
                >
                  {isLoadingProperties ? 'Loading...' : showProperties ? 'Hide Properties' : 'View Properties'}
                </button>
                <button
                  id="disconnect-google-btn"
                  onClick={handleDisconnectGoogle}
                  disabled={isDisconnecting}
                  style={dangerBtnStyle}
                >
                  {isDisconnecting ? 'Disconnecting...' : 'Disconnect'}
                </button>
              </>
            ) : (
              <button
                id="connect-google-btn"
                onClick={handleConnectGoogle}
                disabled={isConnecting}
                style={primaryBtnStyle}
              >
                {isConnecting ? 'Connecting...' : 'Connect Google'}
              </button>
            )
          )}
        </div>
      </div>

      {/* Account Info Details if Connected */}
      {isConnected && googleStatus?.account_email && (
        <div style={accountInfoBoxStyle}>
          <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', fontSize: '13px' }}>
            <div>
              <span style={{ color: '#6b7280' }}>Connected Account: </span>
              <strong style={{ color: '#047857' }}>{googleStatus.account_email}</strong>
            </div>
            {googleStatus.connected_at && (
              <div>
                <span style={{ color: '#6b7280' }}>Connected On: </span>
                <span style={{ color: '#374151' }}>
                  {new Date(googleStatus.connected_at).toLocaleDateString()}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Feedback Messages */}
      {actionError && (
        <div style={errorBannerStyle} id="gsc-integration-error">
          ⚠️ {actionError}
        </div>
      )}
      {successMessage && (
        <div style={successBannerStyle} id="gsc-integration-success">
          ✅ {successMessage}
        </div>
      )}

      {/* Verified Properties List Drawer */}
      {showProperties && (
        <div style={propertiesDrawerStyle} id="gsc-properties-container">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h5 style={{ margin: 0, fontSize: '14px', fontWeight: 600, color: '#111827' }}>
              Verified Search Console Properties ({properties ? properties.length : 0})
            </h5>
            <button
              onClick={() => {
                setProperties(null);
                handleToggleProperties();
              }}
              style={{ fontSize: '12px', background: 'none', border: 'none', color: '#2563eb', cursor: 'pointer', padding: 0 }}
            >
              🔄 Refresh List
            </button>
          </div>

          {isLoadingProperties ? (
            <div style={{ padding: '16px', textAlign: 'center', color: '#6b7280', fontSize: '13px' }}>
              Fetching verified properties from Google Search Console...
            </div>
          ) : !properties || properties.length === 0 ? (
            <div style={{ padding: '16px', textAlign: 'center', color: '#6b7280', fontSize: '13px', backgroundColor: '#f9fafb', borderRadius: '6px' }}>
              No verified Search Console properties were found for this Google account.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {properties.map((prop) => {
                const isAssociating = associatingUrl === prop.site_url;
                return (
                  <div key={prop.site_url} style={propertyCardStyle} className="gsc-property-row">
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontWeight: 600, fontSize: '13px', color: '#0f172a', wordBreak: 'break-all' }}>
                        {prop.site_url}
                      </div>
                      <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                        Permission: <span style={{ fontWeight: 500 }}>{prop.permission_level}</span>
                      </div>
                    </div>

                    {project && (
                      <button
                        onClick={() => handleAssociateProperty(prop)}
                        disabled={isAssociating}
                        style={{
                          ...linkPropertyBtnStyle,
                          opacity: isAssociating ? 0.6 : 1,
                        }}
                        title={`Link ${prop.site_url} to active project ${project.name}`}
                      >
                        {isAssociating ? 'Linking...' : `Link to ${project.name}`}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// Styles
const containerCardStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '8px',
  border: '1px solid #e5e7eb',
  padding: '16px',
  marginBottom: '20px',
  boxShadow: '0 1px 2px rgba(0, 0, 0, 0.04)',
};

const headerRowStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  flexWrap: 'wrap',
  gap: '12px',
};

const badgeConnectedStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: '2px 8px',
  borderRadius: '12px',
  fontSize: '12px',
  fontWeight: 600,
  backgroundColor: '#dcfce7',
  color: '#15803d',
};

const badgeDisconnectedStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: '2px 8px',
  borderRadius: '12px',
  fontSize: '12px',
  fontWeight: 600,
  backgroundColor: '#f3f4f6',
  color: '#4b5563',
};

const badgeNeutralStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: '2px 8px',
  borderRadius: '12px',
  fontSize: '12px',
  fontWeight: 500,
  backgroundColor: '#e0e7ff',
  color: '#4338ca',
};

const primaryBtnStyle: React.CSSProperties = {
  padding: '8px 14px',
  backgroundColor: '#2563eb',
  color: '#ffffff',
  border: 'none',
  borderRadius: '6px',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
  transition: 'background-color 0.15s ease',
};

const secondaryBtnStyle: React.CSSProperties = {
  padding: '8px 12px',
  backgroundColor: '#f8fafc',
  color: '#334155',
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  fontSize: '13px',
  fontWeight: 500,
  cursor: 'pointer',
};

const dangerBtnStyle: React.CSSProperties = {
  padding: '8px 12px',
  backgroundColor: '#fee2e2',
  color: '#991b1b',
  border: '1px solid #fecaca',
  borderRadius: '6px',
  fontSize: '13px',
  fontWeight: 500,
  cursor: 'pointer',
};

const accountInfoBoxStyle: React.CSSProperties = {
  marginTop: '12px',
  padding: '10px 12px',
  backgroundColor: '#f8fafc',
  borderRadius: '6px',
  border: '1px solid #e2e8f0',
};

const errorBannerStyle: React.CSSProperties = {
  marginTop: '12px',
  padding: '10px 12px',
  backgroundColor: '#fef2f2',
  color: '#991b1b',
  borderRadius: '6px',
  border: '1px solid #fecaca',
  fontSize: '13px',
};

const successBannerStyle: React.CSSProperties = {
  marginTop: '12px',
  padding: '10px 12px',
  backgroundColor: '#ecfdf5',
  color: '#065f46',
  borderRadius: '6px',
  border: '1px solid #a7f3d0',
  fontSize: '13px',
};

const propertiesDrawerStyle: React.CSSProperties = {
  marginTop: '16px',
  padding: '14px',
  backgroundColor: '#f8fafc',
  borderRadius: '6px',
  border: '1px solid #e2e8f0',
};

const propertyCardStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '10px 12px',
  backgroundColor: '#ffffff',
  borderRadius: '6px',
  border: '1px solid #e2e8f0',
  gap: '12px',
};

const linkPropertyBtnStyle: React.CSSProperties = {
  padding: '6px 10px',
  backgroundColor: '#eff6ff',
  color: '#1d4ed8',
  border: '1px solid #bfdbfe',
  borderRadius: '4px',
  fontSize: '12px',
  fontWeight: 600,
  cursor: 'pointer',
  whiteSpace: 'nowrap',
};
