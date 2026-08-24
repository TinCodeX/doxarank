import React, { useState, useEffect } from 'react';
import type { AuditIssue, IssueSeverity, CreateAuditIssuePayload, UpdateAuditIssuePayload } from '../types/siteAudit';

interface AuditIssueFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (payload: CreateAuditIssuePayload | UpdateAuditIssuePayload) => Promise<void>;
  auditId: number;
  issueToEdit: AuditIssue | null;
}

const COMMON_ISSUE_TYPES = [
  'missing_h1',
  'missing_title',
  'missing_meta_description',
  'broken_link_404',
  'slow_lcp',
  'duplicate_content',
  'missing_alt_tags',
  'unresponsive_viewport',
  'no_ssl_https',
  'robots_blocking',
];

export const AuditIssueFormModal: React.FC<AuditIssueFormModalProps> = ({
  isOpen,
  onClose,
  onSave,
  auditId,
  issueToEdit,
}) => {
  const [issueType, setIssueType] = useState<string>('missing_h1');
  const [severity, setSeverity] = useState<IssueSeverity>('warning');
  const [title, setTitle] = useState<string>('');
  const [description, setDescription] = useState<string>('');
  const [pageUrl, setPageUrl] = useState<string>('');
  const [recommendation, setRecommendation] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (issueToEdit) {
      setIssueType(issueToEdit.issue_type);
      setSeverity(issueToEdit.severity);
      setTitle(issueToEdit.title);
      setDescription(issueToEdit.description);
      setPageUrl(issueToEdit.page_url || '');
      setRecommendation(issueToEdit.recommendation || '');
    } else {
      setIssueType('missing_h1');
      setSeverity('warning');
      setTitle('');
      setDescription('');
      setPageUrl('');
      setRecommendation('');
    }
    setError(null);
  }, [issueToEdit, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!issueType.trim()) {
      setError('Issue type is required.');
      return;
    }
    if (!title.trim()) {
      setError('Issue title is required.');
      return;
    }
    if (!description.trim()) {
      setError('Issue description is required.');
      return;
    }

    setIsSubmitting(true);
    try {
      if (issueToEdit) {
        const payload: UpdateAuditIssuePayload = {
          issue_type: issueType.trim(),
          severity,
          title: title.trim(),
          description: description.trim(),
          page_url: pageUrl.trim() || null,
          recommendation: recommendation.trim() || null,
        };
        await onSave(payload);
      } else {
        const payload: CreateAuditIssuePayload = {
          audit: auditId,
          issue_type: issueType.trim(),
          severity,
          title: title.trim(),
          description: description.trim(),
          page_url: pageUrl.trim() || null,
          recommendation: recommendation.trim() || null,
        };
        await onSave(payload);
      }
      onClose();
    } catch (err: any) {
      setError(
        err?.data?.title?.[0] ||
        err?.data?.issue_type?.[0] ||
        err?.data?.page_url?.[0] ||
        err?.data?.detail ||
        'Failed to save audit issue.'
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
              {issueToEdit ? 'Edit Audit Issue' : 'Record Audit Issue'}
            </h3>
            <span style={{ fontSize: '12px', color: '#6b7280' }}>
              Audit #{auditId}
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
          {/* Severity & Issue Type in 2 columns */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '14px' }}>
            <div>
              <label style={labelStyle}>
                Severity <span style={{ color: '#ef4444' }}>*</span>
              </label>
              <select
                id="issue-severity-select"
                value={severity}
                onChange={(e) => setSeverity(e.target.value as IssueSeverity)}
                style={inputStyle}
              >
                <option value="critical">🔴 Critical</option>
                <option value="warning">🟡 Warning</option>
                <option value="notice">🔵 Notice / Info</option>
              </select>
            </div>

            <div>
              <label style={labelStyle}>
                Issue Type <span style={{ color: '#ef4444' }}>*</span>
              </label>
              <input
                id="issue-type-input"
                type="text"
                list="issue-type-suggestions"
                value={issueType}
                onChange={(e) => setIssueType(e.target.value)}
                placeholder="e.g. missing_h1"
                style={inputStyle}
                required
              />
              <datalist id="issue-type-suggestions">
                {COMMON_ISSUE_TYPES.map((t) => (
                  <option key={t} value={t} />
                ))}
              </datalist>
            </div>
          </div>

          {/* Title */}
          <div style={{ marginBottom: '14px' }}>
            <label style={labelStyle}>
              Issue Title <span style={{ color: '#ef4444' }}>*</span>
            </label>
            <input
              id="issue-title-input"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Homepage is missing an H1 heading"
              style={inputStyle}
              required
            />
          </div>

          {/* Description */}
          <div style={{ marginBottom: '14px' }}>
            <label style={labelStyle}>
              Description <span style={{ color: '#ef4444' }}>*</span>
            </label>
            <textarea
              id="issue-description-input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Detailed explanation of the issue found during the audit..."
              rows={3}
              style={{ ...inputStyle, resize: 'vertical' }}
              required
            />
          </div>

          {/* Affected Page URL */}
          <div style={{ marginBottom: '14px' }}>
            <label style={labelStyle}>
              Affected Page URL (Optional)
            </label>
            <input
              id="issue-url-input"
              type="url"
              value={pageUrl}
              onChange={(e) => setPageUrl(e.target.value)}
              placeholder="https://example.com/page"
              style={inputStyle}
            />
          </div>

          {/* Recommendation */}
          <div style={{ marginBottom: '16px' }}>
            <label style={labelStyle}>
              Recommended Action (Optional)
            </label>
            <textarea
              id="issue-recommendation-input"
              value={recommendation}
              onChange={(e) => setRecommendation(e.target.value)}
              placeholder="How to resolve this issue (e.g. Add a single <h1> tag at the top of the body)..."
              rows={2}
              style={{ ...inputStyle, resize: 'vertical' }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px' }}>
            <button
              type="button"
              onClick={onClose}
              style={cancelBtnStyle}
            >
              Cancel
            </button>
            <button
              id="save-issue-button"
              type="submit"
              disabled={isSubmitting}
              style={{
                ...submitBtnStyle,
                opacity: isSubmitting ? 0.7 : 1,
                cursor: isSubmitting ? 'not-allowed' : 'pointer',
              }}
            >
              {isSubmitting ? 'Saving...' : issueToEdit ? 'Update Issue' : 'Add Issue'}
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
  maxWidth: '520px',
  boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
  boxSizing: 'border-box',
  maxHeight: '90vh',
  overflowY: 'auto',
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
