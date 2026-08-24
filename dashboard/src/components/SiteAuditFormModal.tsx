import React, { useState, useEffect } from 'react';
import type { SiteAudit, AuditStatus, CreateSiteAuditPayload, UpdateSiteAuditPayload } from '../types/siteAudit';

interface SiteAuditFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (payload: CreateSiteAuditPayload | UpdateSiteAuditPayload) => Promise<void>;
  projectId: number;
  projectName: string;
  auditToEdit: SiteAudit | null;
}

export const SiteAuditFormModal: React.FC<SiteAuditFormModalProps> = ({
  isOpen,
  onClose,
  onSave,
  projectId,
  projectName,
  auditToEdit,
}) => {
  const [status, setStatus] = useState<AuditStatus>('completed');
  const [score, setScore] = useState<string>('85');
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (auditToEdit) {
      setStatus(auditToEdit.status);
      setScore(auditToEdit.score !== null && auditToEdit.score !== undefined ? String(auditToEdit.score) : '');
      setErrorMessage(auditToEdit.error_message || '');
    } else {
      setStatus('completed');
      setScore('85');
      setErrorMessage('');
    }
    setError(null);
  }, [auditToEdit, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    let parsedScore: number | null = null;
    if (score.trim() !== '') {
      const num = Number(score);
      if (isNaN(num) || num < 0 || num > 100) {
        setError('Score must be a number between 0 and 100.');
        return;
      }
      parsedScore = num;
    }

    setIsSubmitting(true);
    try {
      if (auditToEdit) {
        const payload: UpdateSiteAuditPayload = {
          status,
          score: parsedScore,
          error_message: status === 'failed' ? (errorMessage.trim() || null) : null,
          completed_at: status === 'completed' ? new Date().toISOString() : null,
        };
        await onSave(payload);
      } else {
        const payload: CreateSiteAuditPayload = {
          project: projectId,
          status,
          score: parsedScore,
          started_at: new Date().toISOString(),
          completed_at: status === 'completed' ? new Date().toISOString() : null,
          error_message: status === 'failed' ? (errorMessage.trim() || null) : null,
        };
        await onSave(payload);
      }
      onClose();
    } catch (err: any) {
      setError(
        err?.data?.score?.[0] ||
        err?.data?.status?.[0] ||
        err?.data?.detail ||
        'Failed to save site audit record.'
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
              {auditToEdit ? 'Edit Site Audit Record' : 'Record Site Audit'}
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
          {/* Status Selection */}
          <div style={{ marginBottom: '16px' }}>
            <label style={labelStyle}>
              Audit Status <span style={{ color: '#ef4444' }}>*</span>
            </label>
            <select
              id="audit-status-select"
              value={status}
              onChange={(e) => setStatus(e.target.value as AuditStatus)}
              style={inputStyle}
            >
              <option value="completed">Completed</option>
              <option value="running">Running</option>
              <option value="pending">Pending</option>
              <option value="failed">Failed</option>
            </select>
          </div>

          {/* Health Score (0 - 100) */}
          <div style={{ marginBottom: '16px' }}>
            <label style={labelStyle}>
              SEO Health Score (0 - 100)
            </label>
            <input
              id="audit-score-input"
              type="number"
              min="0"
              max="100"
              value={score}
              onChange={(e) => setScore(e.target.value)}
              placeholder="e.g. 85"
              style={inputStyle}
            />
            <span style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px', display: 'block' }}>
              Overall score representing technical SEO health. Leave empty if audit is pending.
            </span>
          </div>

          {/* Error Message if Failed */}
          {status === 'failed' && (
            <div style={{ marginBottom: '16px' }}>
              <label style={labelStyle}>
                Error Details
              </label>
              <textarea
                id="audit-error-input"
                value={errorMessage}
                onChange={(e) => setErrorMessage(e.target.value)}
                placeholder="Details on why the audit failed (e.g. DNS resolution timeout)"
                rows={3}
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
              id="save-audit-button"
              type="submit"
              disabled={isSubmitting}
              style={{
                ...submitBtnStyle,
                opacity: isSubmitting ? 0.7 : 1,
                cursor: isSubmitting ? 'not-allowed' : 'pointer',
              }}
            >
              {isSubmitting ? 'Saving...' : auditToEdit ? 'Update Audit' : 'Save Audit'}
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
  maxWidth: '460px',
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
