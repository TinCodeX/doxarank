import React, { useState, useEffect, useCallback } from 'react';
import type { Project } from '../types/project';
import type {
  SiteAudit,
  AuditIssue,
  IssueSeverity,
  CreateSiteAuditPayload,
  UpdateSiteAuditPayload,
  CreateAuditIssuePayload,
  UpdateAuditIssuePayload,
} from '../types/siteAudit';
import {
  getSiteAudits,
  createSiteAudit,
  updateSiteAudit,
  deleteSiteAudit,
  getAuditIssues,
  createAuditIssue,
  updateAuditIssue,
  deleteAuditIssue,
} from '../api/siteAudits';
import { SiteAuditFormModal } from './SiteAuditFormModal';
import { AuditIssueFormModal } from './AuditIssueFormModal';

interface SiteAuditPanelProps {
  project: Project;
}

export const SiteAuditPanel: React.FC<SiteAuditPanelProps> = ({ project }) => {
  // Audits state
  const [audits, setAudits] = useState<SiteAudit[]>([]);
  const [selectedAudit, setSelectedAudit] = useState<SiteAudit | null>(null);
  const [isLoadingAudits, setIsLoadingAudits] = useState<boolean>(true);
  const [auditError, setAuditError] = useState<string | null>(null);

  // Issues state
  const [issues, setIssues] = useState<AuditIssue[]>([]);
  const [isLoadingIssues, setIsLoadingIssues] = useState<boolean>(false);
  const [issueError, setIssueError] = useState<string | null>(null);
  const [selectedSeverityFilter, setSelectedSeverityFilter] = useState<'all' | IssueSeverity>('all');

  // Modals state
  const [isAuditModalOpen, setIsAuditModalOpen] = useState(false);
  const [editingAudit, setEditingAudit] = useState<SiteAudit | null>(null);
  const [deletingAudit, setDeletingAudit] = useState<SiteAudit | null>(null);
  const [isDeletingAudit, setIsDeletingAudit] = useState(false);

  const [isIssueModalOpen, setIsIssueModalOpen] = useState(false);
  const [editingIssue, setEditingIssue] = useState<AuditIssue | null>(null);
  const [deletingIssue, setDeletingIssue] = useState<AuditIssue | null>(null);
  const [isDeletingIssue, setIsDeletingIssue] = useState(false);

  // Fetch audits when project changes
  const fetchAudits = useCallback(async (projectId: number) => {
    setIsLoadingAudits(true);
    setAuditError(null);
    setSelectedAudit(null);
    setIssues([]);
    try {
      const data = await getSiteAudits(projectId);
      setAudits(data);
      if (data.length > 0) {
        setSelectedAudit(data[0]); // Select most recent audit
      } else {
        setSelectedAudit(null);
      }
    } catch (err: any) {
      setAuditError(err?.data?.detail || 'Failed to load site audits for this project.');
    } finally {
      setIsLoadingAudits(false);
    }
  }, []);

  useEffect(() => {
    if (project?.id) {
      fetchAudits(project.id);
    } else {
      setAudits([]);
      setSelectedAudit(null);
      setIssues([]);
    }
  }, [project?.id, fetchAudits]);

  // Fetch issues whenever selectedAudit changes
  const fetchIssues = useCallback(async (auditId: number) => {
    setIsLoadingIssues(true);
    setIssueError(null);
    setIssues([]);
    try {
      const data = await getAuditIssues(auditId);
      setIssues(data);
    } catch (err: any) {
      setIssueError(err?.data?.detail || 'Failed to load issues for this audit.');
    } finally {
      setIsLoadingIssues(false);
    }
  }, []);

  useEffect(() => {
    if (selectedAudit?.id) {
      fetchIssues(selectedAudit.id);
    } else {
      setIssues([]);
    }
  }, [selectedAudit?.id, fetchIssues]);

  // Audit Handlers
  const handleOpenCreateAuditModal = () => {
    setEditingAudit(null);
    setIsAuditModalOpen(true);
  };

  const handleOpenEditAuditModal = (audit: SiteAudit) => {
    setEditingAudit(audit);
    setIsAuditModalOpen(true);
  };

  const handleSaveAudit = async (payload: CreateSiteAuditPayload | UpdateSiteAuditPayload) => {
    if (editingAudit) {
      const updated = await updateSiteAudit(editingAudit.id, payload as UpdateSiteAuditPayload);
      setAudits((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      if (selectedAudit?.id === updated.id) {
        setSelectedAudit(updated);
      }
    } else {
      const created = await createSiteAudit(payload as CreateSiteAuditPayload);
      setAudits((prev) => [created, ...prev]);
      setSelectedAudit(created);
    }
  };

  const handleConfirmDeleteAudit = async () => {
    if (!deletingAudit) return;
    setIsDeletingAudit(true);
    try {
      await deleteSiteAudit(deletingAudit.id);
      const remaining = audits.filter((a) => a.id !== deletingAudit.id);
      setAudits(remaining);
      if (selectedAudit?.id === deletingAudit.id) {
        setSelectedAudit(remaining.length > 0 ? remaining[0] : null);
      }
      setDeletingAudit(null);
    } catch (err: any) {
      alert(err?.data?.detail || 'Failed to delete site audit.');
    } finally {
      setIsDeletingAudit(false);
    }
  };

  // Issue Handlers
  const handleOpenCreateIssueModal = () => {
    setEditingIssue(null);
    setIsIssueModalOpen(true);
  };

  const handleOpenEditIssueModal = (issue: AuditIssue) => {
    setEditingIssue(issue);
    setIsIssueModalOpen(true);
  };

  const handleSaveIssue = async (payload: CreateAuditIssuePayload | UpdateAuditIssuePayload) => {
    if (editingIssue) {
      const updated = await updateAuditIssue(editingIssue.id, payload as UpdateAuditIssuePayload);
      setIssues((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
    } else {
      const created = await createAuditIssue(payload as CreateAuditIssuePayload);
      setIssues((prev) => [created, ...prev]);
    }
  };

  const handleConfirmDeleteIssue = async () => {
    if (!deletingIssue) return;
    setIsDeletingIssue(true);
    try {
      await deleteAuditIssue(deletingIssue.id);
      setIssues((prev) => prev.filter((i) => i.id !== deletingIssue.id));
      setDeletingIssue(null);
    } catch (err: any) {
      alert(err?.data?.detail || 'Failed to delete audit issue.');
    } finally {
      setIsDeletingIssue(false);
    }
  };

  // Issues counts by severity
  const criticalCount = issues.filter((i) => i.severity === 'critical').length;
  const warningCount = issues.filter((i) => i.severity === 'warning').length;
  const noticeCount = issues.filter((i) => i.severity === 'notice').length;

  const filteredIssues = issues.filter((i) => {
    if (selectedSeverityFilter === 'all') return true;
    return i.severity === selectedSeverityFilter;
  });

  // Score color helper
  const getScoreColor = (score: number | null | undefined) => {
    if (score === null || score === undefined) return { bg: '#f1f5f9', text: '#64748b', border: '#cbd5e1', label: 'Unscored' };
    if (score >= 80) return { bg: '#ecfdf5', text: '#059669', border: '#a7f3d0', label: 'Good' };
    if (score >= 50) return { bg: '#fffbeb', text: '#d97706', border: '#fde68a', label: 'Fair' };
    return { bg: '#fef2f2', text: '#dc2626', border: '#fecaca', label: 'Needs Work' };
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <span style={statusCompletedStyle}>● Completed</span>;
      case 'running':
        return <span style={statusRunningStyle}>⏳ Running</span>;
      case 'failed':
        return <span style={statusFailedStyle}>✕ Failed</span>;
      case 'pending':
      default:
        return <span style={statusPendingStyle}>○ Pending</span>;
    }
  };

  return (
    <section style={{ marginTop: '40px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px', marginBottom: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={sectionBadgeStyle}>Site Health</span>
            <span style={{ fontSize: '12px', color: '#6b7280' }}>
              Project: <strong>{project.name}</strong>
            </span>
          </div>
          <h3 style={{ margin: '6px 0 2px 0', fontSize: '20px', fontWeight: 700, color: '#111827' }}>
            Site Audits & On-Page SEO Health
          </h3>
          <p style={{ margin: 0, fontSize: '13px', color: '#6b7280' }}>
            Technical SEO audits and issue records for <strong>{project.website_url}</strong>.
          </p>
        </div>
        <button
          id="run-audit-button"
          onClick={handleOpenCreateAuditModal}
          style={primaryAddBtnStyle}
        >
          + Record Site Audit
        </button>
      </div>

      {auditError && (
        <div style={errorAlertStyle}>
          {auditError}
        </div>
      )}

      {isLoadingAudits ? (
        <div style={loadingStateStyle}>
          <p style={{ color: '#6b7280', fontSize: '14px' }}>Loading site audits for {project.name}...</p>
        </div>
      ) : audits.length === 0 ? (
        <div style={emptyStateCardStyle}>
          <div style={{ fontSize: '36px', marginBottom: '10px' }}>🩺</div>
          <h4 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 600, color: '#111827' }}>
            No site audits recorded yet
          </h4>
          <p style={{ margin: '0 0 16px 0', fontSize: '14px', color: '#6b7280', maxWidth: '440px' }}>
            Record or log your website's SEO health audits to track technical issues, missing metadata, and performance improvements over time.
          </p>
          <button
            id="empty-run-audit-button"
            onClick={handleOpenCreateAuditModal}
            style={primaryAddBtnStyle}
          >
            Record your first site audit
          </button>
        </div>
      ) : (
        <div>
          {/* Audit selector / history pills if multiple audits exist */}
          {audits.length > 1 && (
            <div style={auditHistoryContainerStyle}>
              <span style={{ fontSize: '12px', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Audit History:
              </span>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                {audits.map((audit) => {
                  const isSelected = selectedAudit?.id === audit.id;
                  const dateStr = new Date(audit.created_at).toLocaleDateString(undefined, {
                    month: 'short',
                    day: 'numeric',
                  });
                  return (
                    <button
                      key={audit.id}
                      id={`select-audit-${audit.id}`}
                      onClick={() => setSelectedAudit(audit)}
                      style={{
                        ...auditHistoryPillStyle,
                        backgroundColor: isSelected ? '#eff6ff' : '#ffffff',
                        borderColor: isSelected ? '#3b82f6' : '#e2e8f0',
                        color: isSelected ? '#1d4ed8' : '#475569',
                        fontWeight: isSelected ? 700 : 500,
                      }}
                    >
                      Audit #{audit.id} ({dateStr}) · {audit.score !== null ? `${audit.score}%` : audit.status}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Prominent Active Audit Card */}
          {selectedAudit && (
            <div style={activeAuditCardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '20px' }}>
                {/* Left: Score & Status */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                  {/* Big Score Badge */}
                  <div
                    style={{
                      ...scoreBoxStyle,
                      backgroundColor: getScoreColor(selectedAudit.score).bg,
                      borderColor: getScoreColor(selectedAudit.score).border,
                      color: getScoreColor(selectedAudit.score).text,
                    }}
                  >
                    <div style={{ fontSize: '28px', fontWeight: 800, lineHeight: 1 }}>
                      {selectedAudit.score !== null ? selectedAudit.score : '—'}
                    </div>
                    <div style={{ fontSize: '10px', textTransform: 'uppercase', fontWeight: 700, marginTop: '4px' }}>
                      {getScoreColor(selectedAudit.score).label}
                    </div>
                  </div>

                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                      <h4 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>
                        Audit #{selectedAudit.id}
                      </h4>
                      {getStatusBadge(selectedAudit.status)}
                    </div>
                    <div style={{ fontSize: '13px', color: '#64748b' }}>
                      Created on {new Date(selectedAudit.created_at).toLocaleString(undefined, {
                        dateStyle: 'medium',
                        timeStyle: 'short',
                      })}
                    </div>
                    {selectedAudit.completed_at && (
                      <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '2px' }}>
                        Completed at: {new Date(selectedAudit.completed_at).toLocaleString()}
                      </div>
                    )}
                  </div>
                </div>

                {/* Right: Actions */}
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <button
                    id="add-issue-button"
                    onClick={handleOpenCreateIssueModal}
                    style={primaryAddBtnStyle}
                  >
                    + Add Issue
                  </button>
                  <button
                    id="edit-audit-button"
                    onClick={() => handleOpenEditAuditModal(selectedAudit)}
                    style={secondaryActionBtnStyle}
                  >
                    Edit Audit
                  </button>
                  <button
                    id="delete-audit-button"
                    onClick={() => setDeletingAudit(selectedAudit)}
                    style={{ ...secondaryActionBtnStyle, color: '#ef4444' }}
                  >
                    Delete
                  </button>
                </div>
              </div>

              {/* Error Banner if Audit Failed */}
              {selectedAudit.status === 'failed' && selectedAudit.error_message && (
                <div style={auditErrorBannerStyle}>
                  <strong>Error details:</strong> {selectedAudit.error_message}
                </div>
              )}

              {/* Summary Severity Stats */}
              <div style={severityStatsGridStyle}>
                <div style={{ ...statCardStyle, backgroundColor: '#fef2f2', borderColor: '#fee2e2' }}>
                  <div style={{ fontSize: '12px', fontWeight: 700, color: '#991b1b', textTransform: 'uppercase' }}>
                    Critical Issues
                  </div>
                  <div style={{ fontSize: '22px', fontWeight: 800, color: '#dc2626', marginTop: '4px' }}>
                    {criticalCount}
                  </div>
                </div>

                <div style={{ ...statCardStyle, backgroundColor: '#fffbeb', borderColor: '#fef3c7' }}>
                  <div style={{ fontSize: '12px', fontWeight: 700, color: '#92400e', textTransform: 'uppercase' }}>
                    Warnings
                  </div>
                  <div style={{ fontSize: '22px', fontWeight: 800, color: '#d97706', marginTop: '4px' }}>
                    {warningCount}
                  </div>
                </div>

                <div style={{ ...statCardStyle, backgroundColor: '#eff6ff', borderColor: '#dbeafe' }}>
                  <div style={{ fontSize: '12px', fontWeight: 700, color: '#1e40af', textTransform: 'uppercase' }}>
                    Notices / Info
                  </div>
                  <div style={{ fontSize: '22px', fontWeight: 800, color: '#2563eb', marginTop: '4px' }}>
                    {noticeCount}
                  </div>
                </div>

                <div style={{ ...statCardStyle, backgroundColor: '#f8fafc', borderColor: '#e2e8f0' }}>
                  <div style={{ fontSize: '12px', fontWeight: 700, color: '#475569', textTransform: 'uppercase' }}>
                    Total Identified
                  </div>
                  <div style={{ fontSize: '22px', fontWeight: 800, color: '#0f172a', marginTop: '4px' }}>
                    {issues.length}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Audit Issues Section */}
          {selectedAudit && (
            <div style={{ marginTop: '28px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', marginBottom: '16px' }}>
                <h4 style={{ margin: 0, fontSize: '17px', fontWeight: 700, color: '#111827' }}>
                  Identified Issues ({issues.length})
                </h4>

                {/* Filter Tabs */}
                <div style={{ display: 'flex', gap: '6px' }}>
                  <button
                    onClick={() => setSelectedSeverityFilter('all')}
                    style={{
                      ...filterTabStyle,
                      backgroundColor: selectedSeverityFilter === 'all' ? '#1e293b' : '#f1f5f9',
                      color: selectedSeverityFilter === 'all' ? '#ffffff' : '#475569',
                    }}
                  >
                    All ({issues.length})
                  </button>
                  <button
                    onClick={() => setSelectedSeverityFilter('critical')}
                    style={{
                      ...filterTabStyle,
                      backgroundColor: selectedSeverityFilter === 'critical' ? '#dc2626' : '#fef2f2',
                      color: selectedSeverityFilter === 'critical' ? '#ffffff' : '#991b1b',
                    }}
                  >
                    Critical ({criticalCount})
                  </button>
                  <button
                    onClick={() => setSelectedSeverityFilter('warning')}
                    style={{
                      ...filterTabStyle,
                      backgroundColor: selectedSeverityFilter === 'warning' ? '#d97706' : '#fffbeb',
                      color: selectedSeverityFilter === 'warning' ? '#ffffff' : '#92400e',
                    }}
                  >
                    Warnings ({warningCount})
                  </button>
                  <button
                    onClick={() => setSelectedSeverityFilter('notice')}
                    style={{
                      ...filterTabStyle,
                      backgroundColor: selectedSeverityFilter === 'notice' ? '#2563eb' : '#eff6ff',
                      color: selectedSeverityFilter === 'notice' ? '#ffffff' : '#1e40af',
                    }}
                  >
                    Notices ({noticeCount})
                  </button>
                </div>
              </div>

              {issueError && (
                <div style={errorAlertStyle}>
                  {issueError}
                </div>
              )}

              {isLoadingIssues ? (
                <div style={loadingStateStyle}>
                  <p style={{ color: '#6b7280', fontSize: '14px' }}>Loading audit issues...</p>
                </div>
              ) : issues.length === 0 ? (
                <div style={{ ...emptyStateCardStyle, padding: '32px 20px' }}>
                  <div style={{ fontSize: '30px', marginBottom: '8px' }}>🎉</div>
                  <h5 style={{ margin: '0 0 4px 0', fontSize: '16px', fontWeight: 600, color: '#111827' }}>
                    No issues recorded for this audit
                  </h5>
                  <p style={{ margin: '0 0 14px 0', fontSize: '13px', color: '#6b7280' }}>
                    Click "+ Add Issue" to record any SEO warning, broken link, or metadata notice found during evaluation.
                  </p>
                  <button
                    onClick={handleOpenCreateIssueModal}
                    style={primaryAddBtnStyle}
                  >
                    + Add First Issue
                  </button>
                </div>
              ) : filteredIssues.length === 0 ? (
                <div style={{ ...emptyStateCardStyle, padding: '24px' }}>
                  <p style={{ margin: 0, color: '#6b7280', fontSize: '14px' }}>
                    No issues match the selected severity filter (<strong>{selectedSeverityFilter}</strong>).
                  </p>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  {filteredIssues.map((issue) => {
                    const isCritical = issue.severity === 'critical';
                    const isWarning = issue.severity === 'warning';

                    const borderAccentColor = isCritical ? '#dc2626' : isWarning ? '#f59e0b' : '#3b82f6';
                    const badgeBg = isCritical ? '#fef2f2' : isWarning ? '#fffbeb' : '#eff6ff';
                    const badgeColor = isCritical ? '#991b1b' : isWarning ? '#92400e' : '#1e40af';
                    const badgeBorder = isCritical ? '#fca5a5' : isWarning ? '#fde68a' : '#bfdbfe';

                    return (
                      <div
                        key={issue.id}
                        id={`issue-card-${issue.id}`}
                        style={{
                          ...issueCardStyle,
                          borderLeft: `4px solid ${borderAccentColor}`,
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', marginBottom: '8px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                            <span
                              style={{
                                ...issueSeverityBadgeStyle,
                                backgroundColor: badgeBg,
                                color: badgeColor,
                                border: `1px solid ${badgeBorder}`,
                              }}
                            >
                              {isCritical ? '🔴 Critical' : isWarning ? '🟡 Warning' : '🔵 Notice'}
                            </span>
                            <span style={issueTypeBadgeStyle}>
                              🏷️ {issue.issue_type}
                            </span>
                            {issue.page_url && (
                              <a
                                href={issue.page_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={pageUrlLinkStyle}
                                title={issue.page_url}
                              >
                                🔗 {issue.page_url}
                              </a>
                            )}
                          </div>

                          <div style={{ display: 'flex', gap: '6px' }}>
                            <button
                              id={`edit-issue-${issue.id}`}
                              onClick={() => handleOpenEditIssueModal(issue)}
                              style={actionInlineBtnStyle}
                            >
                              Edit
                            </button>
                            <button
                              id={`delete-issue-${issue.id}`}
                              onClick={() => setDeletingIssue(issue)}
                              style={{ ...actionInlineBtnStyle, color: '#ef4444' }}
                            >
                              Delete
                            </button>
                          </div>
                        </div>

                        {/* Title & Description */}
                        <h5 style={{ margin: '0 0 6px 0', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
                          {issue.title}
                        </h5>
                        <p style={{ margin: '0 0 10px 0', fontSize: '14px', color: '#475569', lineHeight: 1.5 }}>
                          {issue.description}
                        </p>

                        {/* Recommendation Callout if available */}
                        {issue.recommendation && (
                          <div style={recommendationBoxStyle}>
                            <div style={{ fontWeight: 700, fontSize: '12px', color: '#0f766e', marginBottom: '2px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                              💡 Recommendation:
                            </div>
                            <div style={{ fontSize: '13px', color: '#134e4a', lineHeight: 1.4 }}>
                              {issue.recommendation}
                            </div>
                          </div>
                        )}

                        <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '8px' }}>
                          Identified on {new Date(issue.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Site Audit Form Modal */}
      <SiteAuditFormModal
        isOpen={isAuditModalOpen}
        onClose={() => setIsAuditModalOpen(false)}
        onSave={handleSaveAudit}
        projectId={project.id}
        projectName={project.name}
        auditToEdit={editingAudit}
      />

      {/* Audit Issue Form Modal */}
      {selectedAudit && (
        <AuditIssueFormModal
          isOpen={isIssueModalOpen}
          onClose={() => setIsIssueModalOpen(false)}
          onSave={handleSaveIssue}
          auditId={selectedAudit.id}
          issueToEdit={editingIssue}
        />
      )}

      {/* Delete Audit Modal */}
      {deletingAudit && (
        <div style={modalOverlayStyle}>
          <div style={deleteModalBoxStyle}>
            <h3 style={{ margin: '0 0 12px 0', fontSize: '18px', fontWeight: 700, color: '#111827' }}>
              Delete Site Audit #{deletingAudit.id}
            </h3>
            <p style={{ margin: '0 0 20px 0', fontSize: '14px', color: '#4b5563', lineHeight: 1.5 }}>
              Are you sure you want to delete this site audit record? All {issues.length} identified audit issues under this audit will also be deleted.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <button
                type="button"
                onClick={() => setDeletingAudit(null)}
                style={cancelDeleteBtnStyle}
              >
                Cancel
              </button>
              <button
                id="confirm-delete-audit-button"
                type="button"
                onClick={handleConfirmDeleteAudit}
                disabled={isDeletingAudit}
                style={{
                  ...confirmDeleteBtnStyle,
                  opacity: isDeletingAudit ? 0.7 : 1,
                  cursor: isDeletingAudit ? 'not-allowed' : 'pointer',
                }}
              >
                {isDeletingAudit ? 'Deleting...' : 'Confirm Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Issue Modal */}
      {deletingIssue && (
        <div style={modalOverlayStyle}>
          <div style={deleteModalBoxStyle}>
            <h3 style={{ margin: '0 0 12px 0', fontSize: '18px', fontWeight: 700, color: '#111827' }}>
              Delete Audit Issue
            </h3>
            <p style={{ margin: '0 0 20px 0', fontSize: '14px', color: '#4b5563', lineHeight: 1.5 }}>
              Are you sure you want to delete the issue <strong>"{deletingIssue.title}"</strong>?
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <button
                type="button"
                onClick={() => setDeletingIssue(null)}
                style={cancelDeleteBtnStyle}
              >
                Cancel
              </button>
              <button
                id="confirm-delete-issue-button"
                type="button"
                onClick={handleConfirmDeleteIssue}
                disabled={isDeletingIssue}
                style={{
                  ...confirmDeleteBtnStyle,
                  opacity: isDeletingIssue ? 0.7 : 1,
                  cursor: isDeletingIssue ? 'not-allowed' : 'pointer',
                }}
              >
                {isDeletingIssue ? 'Deleting...' : 'Confirm Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};

// Component Styles
const sectionBadgeStyle: React.CSSProperties = {
  fontSize: '11px',
  textTransform: 'uppercase',
  fontWeight: 700,
  color: '#059669',
  backgroundColor: '#ecfdf5',
  padding: '2px 8px',
  borderRadius: '4px',
  border: '1px solid #a7f3d0',
};

const primaryAddBtnStyle: React.CSSProperties = {
  padding: '9px 16px',
  backgroundColor: '#2563eb',
  color: '#ffffff',
  border: 'none',
  borderRadius: '6px',
  fontSize: '13px',
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
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  border: '1px solid #e5e7eb',
};

const emptyStateCardStyle: React.CSSProperties = {
  textAlign: 'center',
  padding: '40px 24px',
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  border: '1px dashed #d1d5db',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
};

const auditHistoryContainerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '12px',
  marginBottom: '16px',
  overflowX: 'auto',
  paddingBottom: '4px',
};

const auditHistoryPillStyle: React.CSSProperties = {
  padding: '6px 12px',
  borderRadius: '20px',
  border: '1px solid #e2e8f0',
  fontSize: '12px',
  cursor: 'pointer',
  whiteSpace: 'nowrap',
  transition: 'all 0.15s ease',
};

const activeAuditCardStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  border: '1px solid #e2e8f0',
  padding: '24px',
  boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.05)',
};

const scoreBoxStyle: React.CSSProperties = {
  width: '76px',
  height: '76px',
  borderRadius: '16px',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  border: '2px solid',
  flexShrink: 0,
};

const statusCompletedStyle: React.CSSProperties = {
  fontSize: '12px',
  fontWeight: 700,
  color: '#16a34a',
  backgroundColor: '#dcfce7',
  padding: '2px 8px',
  borderRadius: '12px',
};

const statusRunningStyle: React.CSSProperties = {
  fontSize: '12px',
  fontWeight: 700,
  color: '#2563eb',
  backgroundColor: '#dbeafe',
  padding: '2px 8px',
  borderRadius: '12px',
};

const statusPendingStyle: React.CSSProperties = {
  fontSize: '12px',
  fontWeight: 600,
  color: '#64748b',
  backgroundColor: '#f1f5f9',
  padding: '2px 8px',
  borderRadius: '12px',
};

const statusFailedStyle: React.CSSProperties = {
  fontSize: '12px',
  fontWeight: 700,
  color: '#dc2626',
  backgroundColor: '#fef2f2',
  padding: '2px 8px',
  borderRadius: '12px',
};

const auditErrorBannerStyle: React.CSSProperties = {
  backgroundColor: '#fef2f2',
  border: '1px solid #fecaca',
  color: '#991b1b',
  padding: '10px 14px',
  borderRadius: '8px',
  fontSize: '13px',
  marginTop: '16px',
};

const severityStatsGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
  gap: '12px',
  marginTop: '20px',
  borderTop: '1px solid #f1f5f9',
  paddingTop: '16px',
};

const statCardStyle: React.CSSProperties = {
  padding: '12px 16px',
  borderRadius: '8px',
  border: '1px solid',
};

const filterTabStyle: React.CSSProperties = {
  padding: '6px 12px',
  borderRadius: '6px',
  border: 'none',
  fontSize: '12px',
  fontWeight: 600,
  cursor: 'pointer',
  transition: 'all 0.15s ease',
};

const issueCardStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '8px',
  border: '1px solid #e2e8f0',
  padding: '16px 20px',
  boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.03)',
};

const issueSeverityBadgeStyle: React.CSSProperties = {
  fontSize: '12px',
  fontWeight: 700,
  padding: '2px 8px',
  borderRadius: '6px',
};

const issueTypeBadgeStyle: React.CSSProperties = {
  fontSize: '12px',
  fontWeight: 600,
  color: '#475569',
  backgroundColor: '#f1f5f9',
  padding: '2px 8px',
  borderRadius: '6px',
};

const pageUrlLinkStyle: React.CSSProperties = {
  fontSize: '12px',
  color: '#2563eb',
  textDecoration: 'none',
  maxWidth: '260px',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

const recommendationBoxStyle: React.CSSProperties = {
  backgroundColor: '#f0fdfa',
  border: '1px solid #ccfbf1',
  borderRadius: '6px',
  padding: '10px 14px',
  marginTop: '8px',
};

const actionInlineBtnStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: '#2563eb',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
  padding: '4px 8px',
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
  maxWidth: '420px',
  boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
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
