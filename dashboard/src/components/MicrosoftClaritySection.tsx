import React, { useState, useEffect, useCallback } from 'react';
import {
  getIntegrationsStatus,
  getMicrosoftClarityConnectUrl,
  disconnectMicrosoftClarity,
  getClarityProjects,
  associateClarityProject,
  getProjectClarityConnection,
  type IntegrationConnectionStatus,
  type ClarityProject,
  type ProjectClarityConnectionResponse,
} from '../api/integrations';
import type { Project } from '../types/project';

interface MicrosoftClaritySectionProps {
  project?: Project | null;
  onProjectAssociated?: () => void;
}

export const MicrosoftClaritySection: React.FC<MicrosoftClaritySectionProps> = ({
  project,
  onProjectAssociated,
}) => {
  const [clarityStatus, setClarityStatus] = useState<IntegrationConnectionStatus | null>(null);
  const [projectClarity, setProjectClarity] = useState<ProjectClarityConnectionResponse | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState<boolean>(true);
  const [isConnecting, setIsConnecting] = useState<boolean>(false);
  const [isDisconnecting, setIsDisconnecting] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Projects drawer state
  const [projects, setProjects] = useState<ClarityProject[] | null>(null);
  const [isLoadingProjects, setIsLoadingProjects] = useState<boolean>(false);
  const [showProjects, setShowProjects] = useState<boolean>(false);
  const [associatingProjectId, setAssociatingProjectId] = useState<string | null>(null);

  // Manual project ID link form
  const [showManualForm, setShowManualForm] = useState<boolean>(false);
  const [manualProjectId, setManualProjectId] = useState<string>('');
  const [manualProjectName, setManualProjectName] = useState<string>('');
  const [isSavingManual, setIsSavingManual] = useState<boolean>(false);

  // Fetch status and active project Clarity connection
  const fetchStatus = useCallback(async () => {
    setIsLoadingStatus(true);
    setActionError(null);
    try {
      const res = await getIntegrationsStatus(project?.id);
      if (res && res.microsoft) {
        setClarityStatus(res.microsoft);
        if (res.microsoft.project_clarity) {
          setProjectClarity(res.microsoft.project_clarity);
        } else if (project?.id) {
          try {
            const conn = await getProjectClarityConnection(project.id);
            setProjectClarity(conn);
          } catch {
            setProjectClarity(null);
          }
        } else {
          setProjectClarity(null);
        }
      } else {
        setClarityStatus({
          connected: false,
          status: 'disconnected',
        });
        setProjectClarity(null);
      }
    } catch (err: any) {
      console.warn('Failed to fetch Microsoft Clarity status:', err);
      setClarityStatus({
        connected: false,
        status: 'disconnected',
      });
      setProjectClarity(null);
    } finally {
      setIsLoadingStatus(false);
    }
  }, [project?.id]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Connect Microsoft OAuth handler
  const handleConnectMicrosoft = async () => {
    setIsConnecting(true);
    setActionError(null);
    try {
      const res = await getMicrosoftClarityConnectUrl();
      if (res?.authorization_url) {
        window.location.href = res.authorization_url;
      } else {
        setActionError('Failed to generate Microsoft authorization URL.');
      }
    } catch (err: any) {
      const code = err?.data?.code;
      if (code === 'FEATURE_NOT_ENTITLED') {
        setActionError('Microsoft Clarity integration requires a Starter or Agency plan subscription.');
      } else {
        const detail = err?.data?.detail || err?.data?.message || err?.message;
        setActionError(detail || 'Failed to initiate Microsoft connection.');
      }
    } finally {
      setIsConnecting(false);
    }
  };

  // Disconnect Microsoft handler
  const handleDisconnectMicrosoft = async () => {
    if (!window.confirm('Are you sure you want to disconnect Microsoft Clarity from DoxaRank?')) {
      return;
    }

    setIsDisconnecting(true);
    setActionError(null);
    setSuccessMessage(null);
    try {
      await disconnectMicrosoftClarity();
      setProjects(null);
      setShowProjects(false);
      setProjectClarity(null);
      setSuccessMessage('Microsoft Clarity disconnected successfully.');
      await fetchStatus();
    } catch (err: any) {
      setActionError(err?.data?.detail || 'Failed to disconnect Microsoft Clarity.');
    } finally {
      setIsDisconnecting(false);
    }
  };

  // Toggle projects drawer
  const handleToggleProjects = async () => {
    if (showProjects) {
      setShowProjects(false);
      return;
    }

    setShowProjects(true);
    if (projects === null) {
      setIsLoadingProjects(true);
      setActionError(null);
      try {
        const props = await getClarityProjects();
        setProjects(props);
      } catch (err: any) {
        const code = err?.data?.code;
        if (code === 'FEATURE_NOT_ENTITLED') {
          setActionError('Microsoft Clarity integration requires a Starter or Agency plan subscription.');
        } else {
          setActionError(err?.data?.detail || 'Failed to fetch accessible Clarity projects.');
        }
        setShowProjects(false);
      } finally {
        setIsLoadingProjects(false);
      }
    }
  };

  // Associate project handler
  const handleAssociateProject = async (clarityProject: { project_id: string; name?: string; website?: string }) => {
    if (!project?.id) {
      setActionError('Please select a project before linking a Microsoft Clarity project.');
      return;
    }

    setAssociatingProjectId(clarityProject.project_id);
    setActionError(null);
    setSuccessMessage(null);
    try {
      const res = await associateClarityProject({
        project_id: project.id,
        clarity_project_id: clarityProject.project_id,
        name: clarityProject.name,
        website: clarityProject.website,
      });
      setProjectClarity(res);
      setSuccessMessage(
        `Successfully linked Clarity project '${res.name}' (${res.clarity_project_id}) to project '${project.name}'.`
      );
      onProjectAssociated?.();
    } catch (err: any) {
      const code = err?.data?.code;
      if (code === 'FEATURE_NOT_ENTITLED') {
        setActionError('Microsoft Clarity integration requires a Starter or Agency plan subscription.');
      } else {
        setActionError(err?.data?.detail || 'Failed to link Clarity project to project.');
      }
    } finally {
      setAssociatingProjectId(null);
    }
  };

  // Manual project ID link handler
  const handleManualAssociate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualProjectId.trim()) {
      setActionError('Please enter a valid Clarity Project ID.');
      return;
    }

    setIsSavingManual(true);
    setActionError(null);
    try {
      await handleAssociateProject({
        project_id: manualProjectId.trim(),
        name: manualProjectName.trim() || undefined,
      });
      setManualProjectId('');
      setManualProjectName('');
      setShowManualForm(false);
    } finally {
      setIsSavingManual(false);
    }
  };

  const isConnected = Boolean(clarityStatus?.connected);

  return (
    <div style={containerCardStyle} id="microsoft-clarity-section">
      {/* Header */}
      <div style={headerRowStyle}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#111827' }}>
              Microsoft Clarity
            </h4>
            {isLoadingStatus ? (
              <span style={badgeNeutralStyle}>Checking...</span>
            ) : isConnected ? (
              <span style={badgeConnectedStyle} id="clarity-connection-status-badge">● Connected</span>
            ) : (
              <span style={badgeDisconnectedStyle} id="clarity-connection-status-badge">○ Not connected</span>
            )}
          </div>
          <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#6b7280' }}>
            Connect your Microsoft account and link Clarity projects for heatmaps and session behavioral insights.
          </p>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {!isLoadingStatus && (
            isConnected ? (
              <>
                <button
                  id="view-clarity-projects-btn"
                  onClick={handleToggleProjects}
                  disabled={isLoadingProjects}
                  style={secondaryBtnStyle}
                >
                  {isLoadingProjects ? 'Loading...' : showProjects ? 'Hide Projects' : 'View Projects'}
                </button>
                <button
                  id="disconnect-clarity-btn"
                  onClick={handleDisconnectMicrosoft}
                  disabled={isDisconnecting}
                  style={dangerBtnStyle}
                >
                  {isDisconnecting ? 'Disconnecting...' : 'Disconnect'}
                </button>
              </>
            ) : (
              <button
                id="connect-clarity-btn"
                onClick={handleConnectMicrosoft}
                disabled={isConnecting}
                style={primaryBtnStyle}
              >
                {isConnecting ? 'Connecting...' : 'Connect Microsoft'}
              </button>
            )
          )}
        </div>
      </div>

      {/* Account Info Details if Connected */}
      {isConnected && clarityStatus?.account_email && (
        <div style={accountInfoBoxStyle}>
          <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', fontSize: '13px' }}>
            <div>
              <span style={{ color: '#6b7280' }}>Connected Account: </span>
              <strong style={{ color: '#047857' }}>{clarityStatus.account_email}</strong>
            </div>
            {clarityStatus.account_name && (
              <div>
                <span style={{ color: '#6b7280' }}>Name: </span>
                <span style={{ color: '#374151' }}>{clarityStatus.account_name}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Active Project Clarity Association Card */}
      {project && projectClarity && projectClarity.is_connected && (
        <div style={associatedCardStyle} id="clarity-project-association-box">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
            <div>
              <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700, color: '#047857' }}>
                Connected Clarity Project
              </div>
              <div style={{ fontSize: '14px', fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>
                {projectClarity.name}{' '}
                <span style={{ color: '#64748b', fontWeight: 400 }}>(Project ID: {projectClarity.clarity_project_id})</span>
              </div>
              <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
                Connected to project: <strong>{project.name}</strong>
                {projectClarity.website && ` • Website: ${projectClarity.website}`}
              </div>
            </div>
            <span style={badgeConnectedStyle}>Active Link</span>
          </div>
        </div>
      )}

      {/* Feedback Messages */}
      {actionError && (
        <div style={errorBannerStyle} id="clarity-integration-error">
          ⚠️ {actionError}
        </div>
      )}
      {successMessage && (
        <div style={successBannerStyle} id="clarity-integration-success">
          ✅ {successMessage}
        </div>
      )}

      {/* Accessible Projects Drawer */}
      {showProjects && (
        <div style={propertiesDrawerStyle} id="clarity-projects-container">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h5 style={{ margin: 0, fontSize: '14px', fontWeight: 600, color: '#111827' }}>
              Accessible Microsoft Clarity Projects ({projects ? projects.length : 0})
            </h5>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={() => setShowManualForm(!showManualForm)}
                style={{ fontSize: '12px', background: 'none', border: 'none', color: '#2563eb', cursor: 'pointer', padding: 0 }}
              >
                {showManualForm ? 'Hide Manual Entry' : '+ Link by Project ID'}
              </button>
              <button
                onClick={() => {
                  setProjects(null);
                  handleToggleProjects();
                }}
                style={{ fontSize: '12px', background: 'none', border: 'none', color: '#2563eb', cursor: 'pointer', padding: 0 }}
              >
                🔄 Refresh List
              </button>
            </div>
          </div>

          {/* Manual Link Form */}
          {showManualForm && (
            <form onSubmit={handleManualAssociate} style={manualFormStyle}>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                <input
                  type="text"
                  placeholder="Clarity Project ID (e.g. k9xyz123)"
                  value={manualProjectId}
                  onChange={(e) => setManualProjectId(e.target.value)}
                  style={inputStyle}
                  required
                />
                <input
                  type="text"
                  placeholder="Display Name (optional)"
                  value={manualProjectName}
                  onChange={(e) => setManualProjectName(e.target.value)}
                  style={inputStyle}
                />
                <button
                  type="submit"
                  disabled={isSavingManual}
                  style={primaryBtnStyle}
                >
                  {isSavingManual ? 'Saving...' : 'Link Project'}
                </button>
              </div>
            </form>
          )}

          {isLoadingProjects ? (
            <div style={{ padding: '16px', textAlign: 'center', color: '#6b7280', fontSize: '13px' }}>
              Discovering Clarity projects...
            </div>
          ) : !projects || projects.length === 0 ? (
            <div style={{ padding: '16px', textAlign: 'center', color: '#6b7280', fontSize: '13px', backgroundColor: '#f9fafb', borderRadius: '6px' }}>
              No accessible Clarity projects found. Click <strong>+ Link by Project ID</strong> above to link your Clarity project directly.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {projects.map((p) => {
                const isAssociating = associatingProjectId === p.project_id;
                const isCurrentlyLinked = projectClarity?.clarity_project_id === p.project_id && projectClarity?.is_connected;
                return (
                  <div key={p.project_id} style={propertyCardStyle} className="clarity-project-row">
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontWeight: 600, fontSize: '13px', color: '#0f172a' }}>
                        {p.name}
                      </div>
                      <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                        Project ID: <span style={{ fontWeight: 500, fontFamily: 'monospace' }}>{p.project_id}</span>
                        {p.website && ` • Website: ${p.website}`}
                      </div>
                    </div>

                    {project && (
                      isCurrentlyLinked ? (
                        <span style={badgeConnectedStyle}>Currently Linked</span>
                      ) : (
                        <button
                          id={`associate-clarity-${p.project_id}-btn`}
                          onClick={() => handleAssociateProject(p)}
                          disabled={isAssociating}
                          style={{
                            ...linkPropertyBtnStyle,
                            opacity: isAssociating ? 0.6 : 1,
                          }}
                          title={`Link ${p.name} to active project ${project.name}`}
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

const associatedCardStyle: React.CSSProperties = {
  marginTop: '12px',
  padding: '12px 14px',
  backgroundColor: '#f0fdf4',
  borderRadius: '6px',
  border: '1px solid #bbf7d0',
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

const manualFormStyle: React.CSSProperties = {
  marginBottom: '14px',
  padding: '10px',
  backgroundColor: '#ffffff',
  borderRadius: '6px',
  border: '1px dashed #cbd5e1',
};

const inputStyle: React.CSSProperties = {
  padding: '6px 10px',
  border: '1px solid #d1d5db',
  borderRadius: '4px',
  fontSize: '13px',
  flex: 1,
  minWidth: '180px',
};
