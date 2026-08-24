import React, { useState, useEffect } from 'react';
import type {
  SearchConsoleConnection,
  SearchConsolePermission,
  SearchConsoleSyncStatus,
  CreateSearchConsoleConnectionPayload,
  UpdateSearchConsoleConnectionPayload,
} from '../types/searchConsole';

interface SearchConsoleFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (payload: CreateSearchConsoleConnectionPayload | UpdateSearchConsoleConnectionPayload) => Promise<void>;
  projectId: number;
  projectName: string;
  projectWebsiteUrl?: string;
  connectionToEdit: SearchConsoleConnection | null;
}

export const SearchConsoleFormModal: React.FC<SearchConsoleFormModalProps> = ({
  isOpen,
  onClose,
  onSave,
  projectId,
  projectName,
  projectWebsiteUrl,
  connectionToEdit,
}) => {
  const [propertyUrl, setPropertyUrl] = useState<string>('');
  const [permissionLevel, setPermissionLevel] = useState<SearchConsolePermission>('siteOwner');
  const [isConnected, setIsConnected] = useState<boolean>(true);
  const [syncStatus, setSyncStatus] = useState<SearchConsoleSyncStatus>('idle');
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (connectionToEdit) {
      setPropertyUrl(connectionToEdit.property_url);
      setPermissionLevel(connectionToEdit.permission_level);
      setIsConnected(connectionToEdit.is_connected);
      setSyncStatus(connectionToEdit.sync_status);
      setErrorMessage(connectionToEdit.error_message || '');
    } else {
      // Suggest domain property if project website url is available
      let defaultProp = '';
      if (projectWebsiteUrl) {
        try {
          const urlObj = new URL(projectWebsiteUrl.startsWith('http') ? projectWebsiteUrl : `https://${projectWebsiteUrl}`);
          defaultProp = `sc-domain:${urlObj.hostname.replace(/^www\./, '')}`;
        } catch {
          defaultProp = projectWebsiteUrl;
        }
      }
      setPropertyUrl(defaultProp);
      setPermissionLevel('siteOwner');
      setIsConnected(true);
      setSyncStatus('idle');
      setErrorMessage('');
    }
    setError(null);
  }, [connectionToEdit, isOpen, projectWebsiteUrl]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const trimmedPropUrl = propertyUrl.trim();
    if (!trimmedPropUrl) {
      setError('Search Console Property URL is required.');
      return;
    }

    setIsSubmitting(true);
    try {
      if (connectionToEdit) {
        const payload: UpdateSearchConsoleConnectionPayload = {
          property_url: trimmedPropUrl,
          permission_level: permissionLevel,
          is_connected: isConnected,
          sync_status: syncStatus,
          error_message: syncStatus === 'failed' ? (errorMessage.trim() || null) : null,
        };
        await onSave(payload);
      } else {
        const payload: CreateSearchConsoleConnectionPayload = {
          project: projectId,
          property_url: trimmedPropUrl,
          permission_level: permissionLevel,
          is_connected: isConnected,
          sync_status: syncStatus,
          error_message: syncStatus === 'failed' ? (errorMessage.trim() || null) : null,
        };
        await onSave(payload);
      }
      onClose();
    } catch (err: any) {
      setError(
        err?.data?.property_url?.[0] ||
        err?.data?.project?.[0] ||
        err?.data?.permission_level?.[0] ||
        err?.data?.non_field_errors?.[0] ||
        err?.data?.detail ||
        'Failed to save Search Console connection.'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={modalOverlayStyle}>
      <div style={modalBoxStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#111827' }}>
              {connectionToEdit ? 'Edit Search Console Connection' : 'Connect Google Search Console'}
            </h3>
            <span style={{ fontSize: '12px', color: '#6b7280' }}>
              Project: <strong>{projectName}</strong>
            </span>
          </div>
          <button
            onClick={onClose}
            type="button"
            style={closeBtnStyle}
          >
            ✕
          </button>
        </div>

        {error && (
          <div style={errorAlertStyle}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {/* Property URL / Identifier */}
          <div style={{ marginBottom: '16px' }}>
            <label style={labelStyle}>
              Search Console Property <span style={{ color: '#ef4444' }}>*</span>
            </label>
            <input
              id="gsc-property-url-input"
              type="text"
              required
              value={propertyUrl}
              onChange={(e) => setPropertyUrl(e.target.value)}
              placeholder='e.g. "sc-domain:example.et" or "https://example.et/"'
              style={inputStyle}
            />
            <span style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px', display: 'block' }}>
              Enter the exact domain property (sc-domain:domain.com) or URL prefix property registered in Google Search Console.
            </span>
          </div>

          {/* Permission Level */}
          <div style={{ marginBottom: '16px' }}>
            <label style={labelStyle}>
              Search Console Permission Level <span style={{ color: '#ef4444' }}>*</span>
            </label>
            <select
              id="gsc-permission-level-select"
              value={permissionLevel}
              onChange={(e) => setPermissionLevel(e.target.value as SearchConsolePermission)}
              style={inputStyle}
            >
              <option value="siteOwner">Site Owner (Full access)</option>
              <option value="siteFullUser">Full User (View all data, perform some actions)</option>
              <option value="siteRestrictedUser">Restricted User (Simple view capabilities)</option>
              <option value="siteUnverifiedUser">Unverified User</option>
            </select>
          </div>

          {/* Connection Status Toggle */}
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
              <input
                id="gsc-is-connected-toggle"
                type="checkbox"
                checked={isConnected}
                onChange={(e) => setIsConnected(e.target.checked)}
                style={{ width: '16px', height: '16px', cursor: 'pointer' }}
              />
              <span style={{ fontSize: '13px', fontWeight: 600, color: '#374151' }}>
                Active Connection Status (Connected)
              </span>
            </label>
            <span style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px', display: 'block', paddingLeft: '24px' }}>
              Uncheck to pause synchronization without removing the property association.
            </span>
          </div>

          {/* Sync Status (Useful for testing / manual sync simulation) */}
          <div style={{ marginBottom: '16px' }}>
            <label style={labelStyle}>
              Initial Sync Status
            </label>
            <select
              id="gsc-sync-status-select"
              value={syncStatus}
              onChange={(e) => setSyncStatus(e.target.value as SearchConsoleSyncStatus)}
              style={inputStyle}
            >
              <option value="idle">Idle (Ready to sync)</option>
              <option value="syncing">Syncing (In progress)</option>
              <option value="success">Success (Synchronized)</option>
              <option value="failed">Failed (Error state)</option>
            </select>
          </div>

          {/* Error Message if Failed */}
          {syncStatus === 'failed' && (
            <div style={{ marginBottom: '16px' }}>
              <label style={labelStyle}>
                Error Details
              </label>
              <textarea
                id="gsc-error-input"
                value={errorMessage}
                onChange={(e) => setErrorMessage(e.target.value)}
                placeholder="Details on connection or synchronization error"
                rows={2}
                style={{ ...inputStyle, resize: 'vertical' }}
              />
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '24px' }}>
            <button
              type="button"
              onClick={onClose}
              style={cancelBtnStyle}
            >
              Cancel
            </button>
            <button
              id="save-gsc-connection-button"
              type="submit"
              disabled={isSubmitting}
              style={{
                ...submitBtnStyle,
                opacity: isSubmitting ? 0.7 : 1,
                cursor: isSubmitting ? 'not-allowed' : 'pointer',
              }}
            >
              {isSubmitting ? 'Saving...' : connectionToEdit ? 'Update Connection' : 'Save Connection'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
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

const modalBoxStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  padding: '24px',
  width: '100%',
  maxWidth: '480px',
  boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
  boxSizing: 'border-box',
};

const closeBtnStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  fontSize: '16px',
  cursor: 'pointer',
  color: '#9ca3af',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: '13px',
  fontWeight: 600,
  color: '#374151',
  marginBottom: '6px',
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '9px 12px',
  borderRadius: '6px',
  border: '1px solid #d1d5db',
  fontSize: '14px',
  color: '#111827',
  boxSizing: 'border-box',
  outline: 'none',
};

const errorAlertStyle: React.CSSProperties = {
  backgroundColor: '#fef2f2',
  color: '#b91c1c',
  padding: '10px 14px',
  borderRadius: '6px',
  fontSize: '13px',
  marginBottom: '16px',
  border: '1px solid #fca5a5',
};

const cancelBtnStyle: React.CSSProperties = {
  padding: '8px 16px',
  backgroundColor: '#f3f4f6',
  color: '#374151',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  fontSize: '14px',
  fontWeight: 600,
  cursor: 'pointer',
};

const submitBtnStyle: React.CSSProperties = {
  padding: '8px 16px',
  backgroundColor: '#2563eb',
  color: '#ffffff',
  border: 'none',
  borderRadius: '6px',
  fontSize: '14px',
  fontWeight: 600,
};
