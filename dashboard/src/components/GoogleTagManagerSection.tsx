import React, { useState, useEffect, useCallback } from 'react';
import {
  getIntegrationsStatus,
  getGoogleConnectUrl,
  getGTMContainers,
  associateGTMContainer,
  getProjectGTMConnection,
  disconnectProjectGTM,
  type IntegrationConnectionStatus,
  type GTMContainer,
  type ProjectGTMConnectionResponse,
} from '../api/integrations';
import type { Project } from '../types/project';

interface GoogleTagManagerSectionProps {
  project?: Project | null;
  onContainerAssociated?: () => void;
}

export const GoogleTagManagerSection: React.FC<GoogleTagManagerSectionProps> = ({
  project,
  onContainerAssociated,
}) => {
  const [googleStatus, setGoogleStatus] = useState<IntegrationConnectionStatus | null>(null);
  const [projectGtm, setProjectGtm] = useState<ProjectGTMConnectionResponse | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState<boolean>(true);
  const [isConnecting, setIsConnecting] = useState<boolean>(false);
  const [isDisconnecting, setIsDisconnecting] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Containers list state
  const [containers, setContainers] = useState<GTMContainer[] | null>(null);
  const [isLoadingContainers, setIsLoadingContainers] = useState<boolean>(false);
  const [showContainers, setShowContainers] = useState<boolean>(false);
  const [associatingContainerId, setAssociatingContainerId] = useState<string | null>(null);

  // Fetch status and active project GTM connection
  const fetchStatus = useCallback(async () => {
    setIsLoadingStatus(true);
    setActionError(null);
    try {
      const res = await getIntegrationsStatus(project?.id);
      if (res && res.google) {
        setGoogleStatus(res.google);
        if (res.google.project_gtm) {
          setProjectGtm(res.google.project_gtm);
        } else if (project?.id) {
          // Fallback fetch project GTM connection directly
          try {
            const conn = await getProjectGTMConnection(project.id);
            setProjectGtm(conn);
          } catch {
            setProjectGtm(null);
          }
        } else {
          setProjectGtm(null);
        }
      } else {
        setGoogleStatus({
          connected: false,
          status: 'disconnected',
        });
        setProjectGtm(null);
      }
    } catch (err: any) {
      console.warn('Failed to fetch GTM integration status:', err);
      setGoogleStatus({
        connected: false,
        status: 'disconnected',
      });
      setProjectGtm(null);
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
        setActionError('Google Tag Manager integration requires a Starter or Agency plan subscription.');
      } else {
        const detail = err?.data?.detail || err?.data?.message || err?.message;
        setActionError(detail || 'Failed to initiate Google authorization.');
      }
    } finally {
      setIsConnecting(false);
    }
  };

  // Toggle containers drawer
  const handleToggleContainers = async () => {
    if (showContainers) {
      setShowContainers(false);
      return;
    }

    setShowContainers(true);
    if (containers === null) {
      setIsLoadingContainers(true);
      setActionError(null);
      try {
        const conts = await getGTMContainers();
        setContainers(conts);
      } catch (err: any) {
        const code = err?.data?.code;
        if (code === 'FEATURE_NOT_ENTITLED') {
          setActionError('Google Tag Manager integration requires a Starter or Agency plan subscription.');
        } else if (code === 'GTM_SCOPE_MISSING') {
          setActionError('Google Tag Manager scope is missing. Please click Reconnect Google below to grant access.');
        } else {
          setActionError(err?.data?.detail || 'Failed to fetch GTM containers from Google Tag Manager.');
        }
        setShowContainers(false);
      } finally {
        setIsLoadingContainers(false);
      }
    }
  };

  // Associate container with project
  const handleAssociateContainer = async (container: GTMContainer) => {
    if (!project?.id) {
      setActionError('Please select a project before linking a Google Tag Manager container.');
      return;
    }

    setAssociatingContainerId(container.container_id);
    setActionError(null);
    setSuccessMessage(null);
    try {
      const res = await associateGTMContainer({
        project_id: project.id,
        container_id: container.container_id,
        account_id: container.account_id,
        container_public_id: container.public_id,
        name: container.name,
        usage_context: container.usage_context,
      });
      setProjectGtm(res);
      setSuccessMessage(
        `Successfully linked GTM container '${container.name}' (${container.public_id}) to project '${project.name}'.`
      );
      onContainerAssociated?.();
    } catch (err: any) {
      const code = err?.data?.code;
      if (code === 'FEATURE_NOT_ENTITLED') {
        setActionError('Google Tag Manager integration requires a Starter or Agency plan subscription.');
      } else {
        setActionError(err?.data?.detail || 'Failed to link GTM container to project.');
      }
    } finally {
      setAssociatingContainerId(null);
    }
  };

  // Disconnect container from project
  const handleDisconnectContainer = async () => {
    if (!project?.id) return;
    setIsDisconnecting(true);
    setActionError(null);
    setSuccessMessage(null);
    try {
      await disconnectProjectGTM(project.id);
      setProjectGtm(null);
      setSuccessMessage(`Disconnected GTM container from project '${project.name}'.`);
      onContainerAssociated?.();
    } catch (err: any) {
      setActionError(err?.data?.detail || 'Failed to disconnect GTM container from project.');
    } finally {
      setIsDisconnecting(false);
    }
  };

  const isGoogleConnected = Boolean(googleStatus?.connected && googleStatus?.has_valid_credentials);
  const hasGtmScope = Boolean(googleStatus?.has_gtm_scope);
  const isFullyConnected = isGoogleConnected && hasGtmScope;

  return (
    <div style={containerCardStyle} id="google-tag-manager-section">
      {/* Header */}
      <div style={headerRowStyle}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#111827' }}>
              Google Tag Manager (GTM)
            </h4>
            {isLoadingStatus ? (
              <span style={badgeNeutralStyle}>Checking...</span>
            ) : isFullyConnected ? (
              <span style={badgeConnectedStyle} id="gtm-connection-status-badge">● Connected</span>
            ) : isGoogleConnected && !hasGtmScope ? (
              <span style={badgeWarningStyle} id="gtm-connection-status-badge">⚠️ Scope Missing</span>
            ) : (
              <span style={badgeDisconnectedStyle} id="gtm-connection-status-badge">○ Not connected</span>
            )}
          </div>
          <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#6b7280' }}>
            Connect your Google account and link GTM containers to deploy and manage marketing tags.
          </p>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {!isLoadingStatus && (
            isFullyConnected ? (
              <button
                id="view-gtm-containers-btn"
                onClick={handleToggleContainers}
                disabled={isLoadingContainers}
                style={secondaryBtnStyle}
              >
                {isLoadingContainers ? 'Loading...' : showContainers ? 'Hide Containers' : 'View Containers'}
              </button>
            ) : isGoogleConnected && !hasGtmScope ? (
              <button
                id="reconnect-google-gtm-btn"
                onClick={handleConnectOrReconnectGoogle}
                disabled={isConnecting}
                style={warningBtnStyle}
              >
                {isConnecting ? 'Reconnecting...' : 'Reconnect Google'}
              </button>
            ) : (
              <button
                id="connect-google-gtm-btn"
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
      {!isLoadingStatus && isGoogleConnected && !hasGtmScope && (
        <div style={warningBannerStyle} id="gtm-scope-missing-banner">
          <span>⚠️ <strong>Tag Manager permissions required:</strong> Your Google account is connected, but Google Tag Manager permissions are missing. Please click <strong>Reconnect Google</strong> to authorize Tag Manager access. Existing Search Console and Analytics permissions will be preserved.</span>
        </div>
      )}

      {/* Active Project GTM Association Card */}
      {project && projectGtm && projectGtm.is_connected && (
        <div style={associatedCardStyle} id="gtm-project-association-box">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
            <div>
              <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700, color: '#047857' }}>
                Connected GTM Container
              </div>
              <div style={{ fontSize: '14px', fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>
                {projectGtm.name || projectGtm.container_public_id}{' '}
                <span style={{ color: '#64748b', fontWeight: 400 }}>
                  ({projectGtm.container_public_id})
                </span>
              </div>
              <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
                Account ID: <strong>{projectGtm.account_id}</strong> • Project: <strong>{project.name}</strong>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={badgeConnectedStyle}>Active Link</span>
              <button
                id="disconnect-project-gtm-btn"
                onClick={handleDisconnectContainer}
                disabled={isDisconnecting}
                style={dangerBtnStyle}
                title="Unlink this GTM container from the current project"
              >
                {isDisconnecting ? 'Unlinking...' : 'Unlink Container'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Feedback Messages */}
      {actionError && (
        <div style={errorBannerStyle} id="gtm-integration-error">
          ⚠️ {actionError}
        </div>
      )}
      {successMessage && (
        <div style={successBannerStyle} id="gtm-integration-success">
          ✅ {successMessage}
        </div>
      )}

      {/* Accessible GTM Containers Drawer */}
      {showContainers && (
        <div style={containersDrawerStyle} id="gtm-containers-container">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h5 style={{ margin: 0, fontSize: '14px', fontWeight: 600, color: '#111827' }}>
              Accessible GTM Containers ({containers ? containers.length : 0})
            </h5>
            <button
              onClick={() => {
                setContainers(null);
                handleToggleContainers();
              }}
              style={{ fontSize: '12px', background: 'none', border: 'none', color: '#2563eb', cursor: 'pointer', padding: 0 }}
            >
              🔄 Refresh List
            </button>
          </div>

          {isLoadingContainers ? (
            <div style={{ padding: '16px', textAlign: 'center', color: '#6b7280', fontSize: '13px' }}>
              Discovering GTM containers from Google Tag Manager API...
            </div>
          ) : !containers || containers.length === 0 ? (
            <div style={{ padding: '16px', textAlign: 'center', color: '#6b7280', fontSize: '13px', backgroundColor: '#f9fafb', borderRadius: '6px' }}>
              No accessible Google Tag Manager containers found for this account.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {containers.map((cont) => {
                const isAssociating = associatingContainerId === cont.container_id;
                const isCurrentlyLinked =
                  (projectGtm?.container_id === cont.container_id || projectGtm?.container_public_id === cont.public_id) &&
                  projectGtm?.is_connected;
                return (
                  <div key={cont.container_id} style={containerCardRowStyle} className="gtm-container-row">
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontWeight: 600, fontSize: '13px', color: '#0f172a' }}>
                        {cont.name}{' '}
                        <span style={{ fontWeight: 500, fontFamily: 'monospace', color: '#2563eb', marginLeft: '6px' }}>
                          {cont.public_id}
                        </span>
                      </div>
                      <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                        Account: <span>{cont.account_name || cont.account_id}</span> • Context:{' '}
                        <span>{(cont.usage_context || ['web']).join(', ')}</span>
                      </div>
                    </div>

                    {project && (
                      isCurrentlyLinked ? (
                        <span style={badgeConnectedStyle}>Currently Linked</span>
                      ) : (
                        <button
                          id={`associate-gtm-${cont.container_id}-btn`}
                          onClick={() => handleAssociateContainer(cont)}
                          disabled={isAssociating}
                          style={{
                            ...linkContainerBtnStyle,
                            opacity: isAssociating ? 0.6 : 1,
                          }}
                          title={`Link ${cont.name} to active project ${project.name}`}
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
  padding: '8px 16px',
  backgroundColor: '#2563eb',
  color: '#ffffff',
  border: 'none',
  borderRadius: '6px',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
};

const secondaryBtnStyle: React.CSSProperties = {
  padding: '8px 14px',
  backgroundColor: '#f8fafc',
  color: '#334155',
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
};

const warningBtnStyle: React.CSSProperties = {
  padding: '8px 14px',
  backgroundColor: '#f59e0b',
  color: '#ffffff',
  border: 'none',
  borderRadius: '6px',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
};

const dangerBtnStyle: React.CSSProperties = {
  padding: '4px 10px',
  backgroundColor: '#fef2f2',
  color: '#b91c1c',
  border: '1px solid #fecaca',
  borderRadius: '4px',
  fontSize: '12px',
  fontWeight: 600,
  cursor: 'pointer',
};

const warningBannerStyle: React.CSSProperties = {
  backgroundColor: '#fffbeb',
  color: '#92400e',
  border: '1px solid #fde68a',
  borderRadius: '6px',
  padding: '10px 14px',
  fontSize: '13px',
  marginTop: '14px',
  lineHeight: '1.4',
};

const associatedCardStyle: React.CSSProperties = {
  backgroundColor: '#f0fdf4',
  border: '1px solid #bbf7d0',
  borderRadius: '6px',
  padding: '12px 14px',
  marginTop: '14px',
};

const errorBannerStyle: React.CSSProperties = {
  backgroundColor: '#fef2f2',
  color: '#b91c1c',
  border: '1px solid #fca5a5',
  borderRadius: '6px',
  padding: '10px 14px',
  fontSize: '13px',
  marginTop: '12px',
};

const successBannerStyle: React.CSSProperties = {
  backgroundColor: '#ecfdf5',
  color: '#065f46',
  border: '1px solid #a7f3d0',
  borderRadius: '6px',
  padding: '10px 14px',
  fontSize: '13px',
  marginTop: '12px',
};

const containersDrawerStyle: React.CSSProperties = {
  marginTop: '16px',
  paddingTop: '16px',
  borderTop: '1px solid #f1f5f9',
};

const containerCardRowStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '10px 14px',
  backgroundColor: '#f8fafc',
  borderRadius: '6px',
  border: '1px solid #e2e8f0',
  gap: '12px',
};

const linkContainerBtnStyle: React.CSSProperties = {
  padding: '6px 12px',
  backgroundColor: '#2563eb',
  color: '#ffffff',
  border: 'none',
  borderRadius: '4px',
  fontSize: '12px',
  fontWeight: 600,
  cursor: 'pointer',
  whiteSpace: 'nowrap',
};
