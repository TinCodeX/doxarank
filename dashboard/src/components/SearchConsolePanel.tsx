import React, { useState, useEffect, useCallback } from 'react';
import type { Project } from '../types/project';
import type {
  SearchConsoleConnection,
  SearchConsolePermission,
  CreateSearchConsoleConnectionPayload,
  UpdateSearchConsoleConnectionPayload,
} from '../types/searchConsole';
import {
  getSearchConsoleConnections,
  createSearchConsoleConnection,
  updateSearchConsoleConnection,
  deleteSearchConsoleConnection,
} from '../api/searchConsole';
import { syncSearchConsole } from '../api/searchConsoleAnalytics';
import { SearchConsoleFormModal } from './SearchConsoleFormModal';

interface SearchConsolePanelProps {
  project: Project;
  onConnectionChange?: (connection: SearchConsoleConnection | null) => void;
}

const PERMISSION_LABELS: Record<SearchConsolePermission, string> = {
  siteOwner: 'Site Owner',
  siteFullUser: 'Full User',
  siteRestrictedUser: 'Restricted User',
  siteUnverifiedUser: 'Unverified User',
};

export const SearchConsolePanel: React.FC<SearchConsolePanelProps> = ({ project, onConnectionChange }) => {
  const [connection, setConnection] = useState<SearchConsoleConnection | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [syncFeedback, setSyncFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Modal states
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isDisconnectModalOpen, setIsDisconnectModalOpen] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const [disconnectError, setDisconnectError] = useState<string | null>(null);

  // Fetch connection when active project changes
  const fetchConnection = useCallback(async (projectId: number) => {
    setIsLoading(true);
    setError(null);
    setConnection(null);
    try {
      const data = await getSearchConsoleConnections(projectId);
      if (data && data.length > 0) {
        setConnection(data[0]);
        onConnectionChange?.(data[0]);
      } else {
        setConnection(null);
        onConnectionChange?.(null);
      }
    } catch (err: any) {
      setError(err?.data?.detail || 'Failed to load Search Console connection for this project.');
      onConnectionChange?.(null);
    } finally {
      setIsLoading(false);
    }
  }, [onConnectionChange]);

  useEffect(() => {
    if (project?.id) {
      fetchConnection(project.id);
    } else {
      setConnection(null);
      onConnectionChange?.(null);
    }
  }, [project?.id, fetchConnection, onConnectionChange]);

  // Handlers
  const handleOpenConnectModal = () => {
    setIsModalOpen(true);
  };

  const handleOpenEditModal = () => {
    setIsModalOpen(true);
  };

  const handleSyncNow = async () => {
    if (!project?.id || isSyncing) return;
    setIsSyncing(true);
    setSyncFeedback(null);
    setError(null);
    try {
      const res = await syncSearchConsole({ project_id: project.id });
      setSyncFeedback(`Sync complete! Created ${res.records_created}, updated ${res.records_updated} records.`);
      await fetchConnection(project.id);
    } catch (err: any) {
      setError(err?.data?.detail || 'Sync failed.');
    } finally {
      setIsSyncing(false);
    }
  };

  const handleSaveConnection = async (
    payload: CreateSearchConsoleConnectionPayload | UpdateSearchConsoleConnectionPayload
  ) => {
    if (connection) {
      const updated = await updateSearchConsoleConnection(
        connection.id,
        payload as UpdateSearchConsoleConnectionPayload
      );
      setConnection(updated);
      onConnectionChange?.(updated);
    } else {
      const created = await createSearchConsoleConnection(
        payload as CreateSearchConsoleConnectionPayload
      );
      setConnection(created);
      onConnectionChange?.(created);
    }
  };

  const handleConfirmDisconnect = async () => {
    if (!connection) return;
    setIsDisconnecting(true);
    setDisconnectError(null);
    try {
      await deleteSearchConsoleConnection(connection.id);
      setConnection(null);
      onConnectionChange?.(null);
      setIsDisconnectModalOpen(false);
    } catch (err: any) {
      setDisconnectError(err?.data?.detail || 'Failed to disconnect Google Search Console.');
    } finally {
      setIsDisconnecting(false);
    }
  };

  return (
    <section style={panelContainerStyle}>
      {/* Panel Header */}
      <div style={panelHeaderStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={gscIconBadgeStyle}>
            <span style={{ fontSize: '18px' }}>📈</span>
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h3 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: '#111827' }}>
                Google Search Console
              </h3>
              {connection && (
                connection.is_connected ? (
                  <span style={connectedBadgeStyle}>● Connected</span>
                ) : (
                  <span style={disconnectedBadgeStyle}>○ Disconnected</span>
                )
              )}
            </div>
            <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#6b7280' }}>
              Search property integration and indexing status for <strong>{project.name}</strong>.
            </p>
          </div>
        </div>

        {connection && (
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button
              id="gsc-header-sync-btn"
              onClick={handleSyncNow}
              disabled={isSyncing || !connection.is_connected}
              style={{ ...primaryAddBtnStyle, backgroundColor: '#2563eb' }}
            >
              {isSyncing ? 'Syncing...' : '⚡ Sync'}
            </button>
            <button
              id="edit-gsc-connection-button"
              onClick={handleOpenEditModal}
              style={secondaryActionBtnStyle}
            >
              Edit Connection
            </button>
            <button
              id="disconnect-gsc-button"
              onClick={() => setIsDisconnectModalOpen(true)}
              style={dangerActionBtnStyle}
            >
              Disconnect
            </button>
          </div>
        )}
      </div>

      {/* Sync Feedback Toast */}
      {syncFeedback && (
        <div style={{ ...errorAlertStyle, backgroundColor: '#ecfdf5', borderColor: '#a7f3d0', color: '#065f46', marginBottom: '16px' }}>
          ✅ {syncFeedback}
        </div>
      )}

      {/* Global Error Banner */}
      {error && (
        <div style={errorAlertStyle}>
          {error}
        </div>
      )}

      {/* Body States */}
      {isLoading ? (
        <div style={loadingStateStyle}>
          <p style={{ color: '#6b7280', fontSize: '14px', margin: 0 }}>
            Checking Google Search Console connection for {project.name}...
          </p>
        </div>
      ) : !connection ? (
        /* Empty State: No connection exists */
        <div style={emptyStateCardStyle}>
          <div style={{ fontSize: '36px', marginBottom: '12px' }}>🌐</div>
          <h4 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 600, color: '#111827' }}>
            Google Search Console is not connected
          </h4>
          <p style={{ margin: '0 0 18px 0', fontSize: '14px', color: '#6b7280', maxWidth: '460px', lineHeight: 1.5 }}>
            Connect Google Search Console to monitor organic impressions, clicks, keyword performance, and indexing status for this project.
          </p>
          <button
            id="connect-gsc-button"
            onClick={handleOpenConnectModal}
            style={primaryAddBtnStyle}
          >
            Connect Search Console
          </button>
        </div>
      ) : (
        /* Connected State: Display connection metadata */
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={detailsGridStyle}>
            {/* Property */}
            <div style={statCardStyle}>
              <span style={statLabelStyle}>Property</span>
              <span style={{ ...statValueStyle, color: '#1d4ed8', wordBreak: 'break-all' }} title={connection.property_url}>
                {connection.property_url}
              </span>
            </div>

            {/* Permission Level */}
            <div style={statCardStyle}>
              <span style={statLabelStyle}>Permission</span>
              <span style={statValueStyle}>
                {PERMISSION_LABELS[connection.permission_level] || connection.permission_level}
              </span>
            </div>

            {/* Connected Date */}
            <div style={statCardStyle}>
              <span style={statLabelStyle}>Connected</span>
              <span style={statValueStyle}>
                {new Date(connection.connected_at).toLocaleDateString(undefined, {
                  year: 'numeric',
                  month: 'short',
                  day: 'numeric',
                })}
              </span>
            </div>

            {/* Last Synced */}
            <div style={statCardStyle}>
              <span style={statLabelStyle}>Last Synced</span>
              <span style={statValueStyle}>
                {connection.last_synced_at
                  ? new Date(connection.last_synced_at).toLocaleString(undefined, {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  : 'Never'}
              </span>
            </div>

            {/* Sync Status */}
            <div style={statCardStyle}>
              <span style={statLabelStyle}>Sync Status</span>
              <div>
                <span
                  style={{
                    display: 'inline-block',
                    padding: '3px 10px',
                    borderRadius: '12px',
                    fontSize: '12px',
                    fontWeight: 700,
                    textTransform: 'capitalize',
                    backgroundColor:
                      connection.sync_status === 'success'
                        ? '#dcfce7'
                        : connection.sync_status === 'syncing'
                        ? '#dbeafe'
                        : connection.sync_status === 'failed'
                        ? '#fee2e2'
                        : '#f1f5f9',
                    color:
                      connection.sync_status === 'success'
                        ? '#15803d'
                        : connection.sync_status === 'syncing'
                        ? '#1d4ed8'
                        : connection.sync_status === 'failed'
                        ? '#b91c1c'
                        : '#475569',
                  }}
                >
                  {connection.sync_status}
                </span>
              </div>
            </div>
          </div>

          {/* Sync / Error details if failed */}
          {connection.error_message && (
            <div style={{ ...errorAlertStyle, margin: 0 }}>
              <strong>Sync Error:</strong> {connection.error_message}
            </div>
          )}
        </div>
      )}

      {/* Connect / Edit Modal */}
      <SearchConsoleFormModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSave={handleSaveConnection}
        projectId={project.id}
        projectName={project.name}
        projectWebsiteUrl={project.website_url}
        connectionToEdit={connection}
      />

      {/* Custom Disconnect Confirmation Modal */}
      {isDisconnectModalOpen && (
        <div style={modalOverlayStyle}>
          <div style={deleteModalBoxStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
              <div style={{ width: '36px', height: '36px', borderRadius: '50%', backgroundColor: '#fee2e2', color: '#dc2626', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '18px', fontWeight: 'bold' }}>
                ⚠️
              </div>
              <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#111827' }}>
                Disconnect Google Search Console?
              </h3>
            </div>

            <p style={{ margin: '0 0 20px 0', fontSize: '14px', color: '#4b5563', lineHeight: 1.5 }}>
              This will remove the Google Search Console property connection (<strong>{connection?.property_url}</strong>) from <strong>{project.name}</strong>.
            </p>

            {disconnectError && (
              <div style={{ ...errorAlertStyle, marginBottom: '16px' }}>
                {disconnectError}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <button
                type="button"
                onClick={() => {
                  setIsDisconnectModalOpen(false);
                  setDisconnectError(null);
                }}
                disabled={isDisconnecting}
                style={cancelDeleteBtnStyle}
              >
                Cancel
              </button>
              <button
                id="confirm-disconnect-gsc-button"
                type="button"
                onClick={handleConfirmDisconnect}
                disabled={isDisconnecting}
                style={{
                  ...confirmDeleteBtnStyle,
                  opacity: isDisconnecting ? 0.7 : 1,
                  cursor: isDisconnecting ? 'not-allowed' : 'pointer',
                }}
              >
                {isDisconnecting ? 'Disconnecting...' : 'Disconnect'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};

// Styles
const panelContainerStyle: React.CSSProperties = {
  marginTop: '40px',
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  border: '1px solid #e2e8f0',
  padding: '24px',
  boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.05)',
};

const panelHeaderStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  flexWrap: 'wrap',
  gap: '16px',
  marginBottom: '20px',
  borderBottom: '1px solid #f1f5f9',
  paddingBottom: '16px',
};

const gscIconBadgeStyle: React.CSSProperties = {
  width: '38px',
  height: '38px',
  borderRadius: '8px',
  backgroundColor: '#eff6ff',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  border: '1px solid #dbeafe',
};

const connectedBadgeStyle: React.CSSProperties = {
  fontSize: '12px',
  fontWeight: 700,
  color: '#16a34a',
  backgroundColor: '#dcfce7',
  padding: '2px 8px',
  borderRadius: '12px',
};

const disconnectedBadgeStyle: React.CSSProperties = {
  fontSize: '12px',
  fontWeight: 600,
  color: '#64748b',
  backgroundColor: '#f1f5f9',
  padding: '2px 8px',
  borderRadius: '12px',
};

const primaryAddBtnStyle: React.CSSProperties = {
  padding: '10px 18px',
  backgroundColor: '#2563eb',
  color: '#ffffff',
  border: 'none',
  borderRadius: '6px',
  fontSize: '14px',
  fontWeight: 600,
  cursor: 'pointer',
};

const secondaryActionBtnStyle: React.CSSProperties = {
  padding: '8px 14px',
  backgroundColor: '#ffffff',
  color: '#374151',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
};

const dangerActionBtnStyle: React.CSSProperties = {
  padding: '8px 14px',
  backgroundColor: '#fef2f2',
  color: '#dc2626',
  border: '1px solid #fecaca',
  borderRadius: '6px',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
};

const errorAlertStyle: React.CSSProperties = {
  backgroundColor: '#fef2f2',
  color: '#b91c1c',
  padding: '12px',
  borderRadius: '8px',
  fontSize: '14px',
  marginBottom: '16px',
  border: '1px solid #fca5a5',
};

const loadingStateStyle: React.CSSProperties = {
  textAlign: 'center',
  padding: '36px 0',
  backgroundColor: '#f8fafc',
  borderRadius: '8px',
  border: '1px solid #e2e8f0',
};

const emptyStateCardStyle: React.CSSProperties = {
  textAlign: 'center',
  padding: '36px 24px',
  backgroundColor: '#f8fafc',
  borderRadius: '12px',
  border: '1px dashed #cbd5e1',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
};

const detailsGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
  gap: '16px',
};

const statCardStyle: React.CSSProperties = {
  backgroundColor: '#f8fafc',
  padding: '14px 16px',
  borderRadius: '8px',
  border: '1px solid #e2e8f0',
  display: 'flex',
  flexDirection: 'column',
  gap: '4px',
};

const statLabelStyle: React.CSSProperties = {
  fontSize: '11px',
  textTransform: 'uppercase',
  fontWeight: 700,
  color: '#64748b',
  letterSpacing: '0.05em',
};

const statValueStyle: React.CSSProperties = {
  fontSize: '14px',
  fontWeight: 600,
  color: '#0f172a',
};

const modalOverlayStyle: React.CSSProperties = {
  position: 'fixed',
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  backgroundColor: 'rgba(0, 0, 0, 0.5)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
  padding: '16px',
};

const deleteModalBoxStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  padding: '24px',
  width: '100%',
  maxWidth: '440px',
  boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
  boxSizing: 'border-box',
};

const cancelDeleteBtnStyle: React.CSSProperties = {
  padding: '8px 16px',
  backgroundColor: '#f3f4f6',
  color: '#374151',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  fontSize: '14px',
  fontWeight: 600,
  cursor: 'pointer',
};

const confirmDeleteBtnStyle: React.CSSProperties = {
  padding: '8px 16px',
  backgroundColor: '#dc2626',
  color: '#ffffff',
  border: 'none',
  borderRadius: '6px',
  fontSize: '14px',
  fontWeight: 600,
};
