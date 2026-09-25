import React, { useState, useEffect, useCallback } from 'react';
import {
  getIntegrationsStatus,
  getGoogleConnectUrl,
  getGA4Properties,
  associateGA4Property,
  getProjectGA4Connection,
  type IntegrationConnectionStatus,
  type GA4Property,
  type ProjectGA4ConnectionResponse,
} from '../api/integrations';
import type { Project } from '../types/project';

interface GoogleAnalyticsSectionProps {
  project?: Project | null;
  onPropertyAssociated?: () => void;
}

export const GoogleAnalyticsSection: React.FC<GoogleAnalyticsSectionProps> = ({
  project,
  onPropertyAssociated,
}) => {
  const [googleStatus, setGoogleStatus] = useState<IntegrationConnectionStatus | null>(null);
  const [projectGa4, setProjectGa4] = useState<ProjectGA4ConnectionResponse | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState<boolean>(true);
  const [isConnecting, setIsConnecting] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Properties list state
  const [properties, setProperties] = useState<GA4Property[] | null>(null);
  const [isLoadingProperties, setIsLoadingProperties] = useState<boolean>(false);
  const [showProperties, setShowProperties] = useState<boolean>(false);
  const [associatingPropertyId, setAssociatingPropertyId] = useState<string | null>(null);

  // Fetch status and active project GA4 connection
  const fetchStatus = useCallback(async () => {
    setIsLoadingStatus(true);
    setActionError(null);
    try {
      const res = await getIntegrationsStatus(project?.id);
      if (res && res.google) {
        setGoogleStatus(res.google);
        if (res.google.project_ga4) {
          setProjectGa4(res.google.project_ga4);
        } else if (project?.id) {
          // Fallback fetch project GA4 connection directly
          try {
            const conn = await getProjectGA4Connection(project.id);
            setProjectGa4(conn);
          } catch {
            setProjectGa4(null);
          }
        } else {
          setProjectGa4(null);
        }
      } else {
        setGoogleStatus({
          connected: false,
          status: 'disconnected',
        });
        setProjectGa4(null);
      }
    } catch (err: any) {
      console.warn('Failed to fetch GA4 integration status:', err);
      setGoogleStatus({
        connected: false,
        status: 'disconnected',
      });
      setProjectGa4(null);
    } finally {
      setIsLoadingStatus(false);
    }
  }, [project?.id]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Connect / Reconnect Google OAuth handler
  const handleConnectOrReconnectGoogle = async () => {
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
      const code = err?.data?.code;
      if (code === 'FEATURE_NOT_ENTITLED') {
        setActionError('Google Analytics 4 integration requires a Starter or Agency plan subscription.');
      } else {
        const detail = err?.data?.detail || err?.data?.message || err?.message;
        setActionError(detail || 'Failed to initiate Google authorization.');
      }
    } finally {
      setIsConnecting(false);
    }
  };

  // Toggle properties drawer
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
        const props = await getGA4Properties();
        setProperties(props);
      } catch (err: any) {
        const code = err?.data?.code;
        if (code === 'FEATURE_NOT_ENTITLED') {
          setActionError('Google Analytics 4 integration requires a Starter or Agency plan subscription.');
        } else if (code === 'ANALYTICS_SCOPE_MISSING') {
          setActionError('Google Analytics scope is missing. Please click Reconnect Google below to grant access.');
        } else {
          setActionError(err?.data?.detail || 'Failed to fetch GA4 properties from Google Analytics.');
        }
        setShowProperties(false);
      } finally {
        setIsLoadingProperties(false);
      }
    }
  };

  // Associate property with project
  const handleAssociateProperty = async (property: GA4Property) => {
    if (!project?.id) {
      setActionError('Please select a project before linking a Google Analytics 4 property.');
      return;
    }

    setAssociatingPropertyId(property.property_id);
    setActionError(null);
    setSuccessMessage(null);
    try {
      const res = await associateGA4Property({
        project_id: project.id,
        property_id: property.property_id,
        display_name: property.display_name,
      });
      setProjectGa4(res);
      setSuccessMessage(
        `Successfully linked GA4 property '${property.display_name}' (${property.property_id}) to project '${project.name}'.`
      );
      onPropertyAssociated?.();
    } catch (err: any) {
      const code = err?.data?.code;
      if (code === 'FEATURE_NOT_ENTITLED') {
        setActionError('Google Analytics 4 integration requires a Starter or Agency plan subscription.');
      } else {
        setActionError(err?.data?.detail || 'Failed to link GA4 property to project.');
      }
    } finally {
      setAssociatingPropertyId(null);
    }
  };

  const isGoogleConnected = Boolean(googleStatus?.connected && googleStatus?.has_valid_credentials);
  const hasAnalyticsScope = Boolean(googleStatus?.has_analytics_scope);
  const isFullyConnected = isGoogleConnected && hasAnalyticsScope;

  return (
    <div style={containerCardStyle} id="google-analytics-section">
      {/* Header */}
      <div style={headerRowStyle}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#111827' }}>
              Google Analytics 4 (GA4)
            </h4>
            {isLoadingStatus ? (
              <span style={badgeNeutralStyle}>Checking...</span>
            ) : isFullyConnected ? (
              <span style={badgeConnectedStyle} id="ga4-connection-status-badge">● Connected</span>
            ) : isGoogleConnected && !hasAnalyticsScope ? (
              <span style={badgeWarningStyle} id="ga4-connection-status-badge">⚠️ Scope Missing</span>
            ) : (
              <span style={badgeDisconnectedStyle} id="ga4-connection-status-badge">○ Not connected</span>
            )}
          </div>
          <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#6b7280' }}>
            Connect your Google account and discover GA4 properties to monitor website performance.
          </p>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {!isLoadingStatus && (
            isFullyConnected ? (
              <button
                id="view-ga4-properties-btn"
                onClick={handleToggleProperties}
                disabled={isLoadingProperties}
                style={secondaryBtnStyle}
              >
                {isLoadingProperties ? 'Loading...' : showProperties ? 'Hide Properties' : 'View Properties'}
              </button>
            ) : isGoogleConnected && !hasAnalyticsScope ? (
              <button
                id="reconnect-google-btn"
                onClick={handleConnectOrReconnectGoogle}
                disabled={isConnecting}
                style={warningBtnStyle}
              >
                {isConnecting ? 'Reconnecting...' : 'Reconnect Google'}
              </button>
            ) : (
              <button
                id="connect-google-btn"
                onClick={handleConnectOrReconnectGoogle}
                disabled={isConnecting}
                style={primaryBtnStyle}
              >
                {isConnecting ? 'Connecting...' : 'Connect Google'}
              </button>
            )
          )}
        </div>
      </div>

      {/* Scope Missing Notice */}
      {!isLoadingStatus && isGoogleConnected && !hasAnalyticsScope && (
        <div style={warningBannerStyle} id="ga4-scope-missing-banner">
          <span>⚠️ <strong>Analytics permissions required:</strong> Your Google account is connected, but Google Analytics 4 permissions are missing. Please click <strong>Reconnect Google</strong> to authorize Analytics access. Existing Search Console permissions will be preserved.</span>
        </div>
      )}

      {/* Active Project GA4 Association Card */}
      {project && projectGa4 && projectGa4.is_connected && (
        <div style={associatedCardStyle} id="ga4-project-association-box">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
            <div>
              <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700, color: '#047857' }}>
                Connected GA4 Property
              </div>
              <div style={{ fontSize: '14px', fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>
                {projectGa4.display_name} <span style={{ color: '#64748b', fontWeight: 400 }}>(Property ID: {projectGa4.property_id})</span>
              </div>
              <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
                Connected to project: <strong>{project.name}</strong>
              </div>
            </div>
            <span style={badgeConnectedStyle}>Active Link</span>
          </div>
        </div>
      )}

      {/* Feedback Messages */}
      {actionError && (
        <div style={errorBannerStyle} id="ga4-integration-error">
          ⚠️ {actionError}
        </div>
      )}
      {successMessage && (
        <div style={successBannerStyle} id="ga4-integration-success">
          ✅ {successMessage}
        </div>
      )}

      {/* Accessible GA4 Properties Drawer */}
      {showProperties && (
        <div style={propertiesDrawerStyle} id="ga4-properties-container">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h5 style={{ margin: 0, fontSize: '14px', fontWeight: 600, color: '#111827' }}>
              Accessible GA4 Properties ({properties ? properties.length : 0})
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
              Discovering GA4 properties from Google Analytics Admin API...
            </div>
          ) : !properties || properties.length === 0 ? (
            <div style={{ padding: '16px', textAlign: 'center', color: '#6b7280', fontSize: '13px', backgroundColor: '#f9fafb', borderRadius: '6px' }}>
              No accessible Google Analytics 4 properties found for this account.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {properties.map((prop) => {
                const isAssociating = associatingPropertyId === prop.property_id;
                const isCurrentlyLinked = projectGa4?.property_id === prop.property_id && projectGa4?.is_connected;
                return (
                  <div key={prop.property_id} style={propertyCardStyle} className="ga4-property-row">
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontWeight: 600, fontSize: '13px', color: '#0f172a' }}>
                        {prop.display_name}
                      </div>
                      <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                        Property ID: <span style={{ fontWeight: 500, fontFamily: 'monospace' }}>{prop.property_id}</span> • Type: <span>{prop.property_type}</span>
                      </div>
                    </div>

                    {project && (
                      isCurrentlyLinked ? (
                        <span style={badgeConnectedStyle}>Currently Linked</span>
                      ) : (
                        <button
                          id={`associate-ga4-${prop.property_id}-btn`}
                          onClick={() => handleAssociateProperty(prop)}
                          disabled={isAssociating}
                          style={{
                            ...linkPropertyBtnStyle,
                            opacity: isAssociating ? 0.6 : 1,
                          }}
                          title={`Link ${prop.display_name} to active project ${project.name}`}
                        >
                          {isAssociating ? 'Linking...' : `Link to ${project.name}`}
                        </button>
                      )
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

const badgeWarningStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: '2px 8px',
  borderRadius: '12px',
  fontSize: '12px',
  fontWeight: 600,
  backgroundColor: '#fef3c7',
  color: '#b45309',
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

const warningBtnStyle: React.CSSProperties = {
  padding: '8px 14px',
  backgroundColor: '#d97706',
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

const associatedCardStyle: React.CSSProperties = {
  marginTop: '12px',
  padding: '12px 14px',
  backgroundColor: '#f0fdf4',
  borderRadius: '6px',
  border: '1px solid #bbf7d0',
};

const warningBannerStyle: React.CSSProperties = {
  marginTop: '12px',
  padding: '10px 12px',
  backgroundColor: '#fffbeb',
  color: '#92400e',
  borderRadius: '6px',
  border: '1px solid #fde68a',
  fontSize: '13px',
  lineHeight: 1.4,
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
