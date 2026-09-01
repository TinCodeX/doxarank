import React, { useState, useEffect, useCallback, useMemo } from 'react';
import type { Project } from '../types/project';
import type {
  SEOAction,
  ActionType,
  ActionStatus,
  ActionPriority,
  ActionStatusCounts,
  ActionPreviewDiff
} from '../types/seoAction';
import {
  getSEOActions,
  generateSEOAction,
  reviewSEOAction,
  approveSEOAction,
  rejectSEOAction,
  cancelSEOAction,
  executeSEOAction,
  deleteSEOAction,
  previewSEOAction,
  getSEOActionStatusCounts
} from '../api/seoActions';


interface SEOActionsPanelProps {
  project: Project | null;
  targetRecommendationId?: number | null;
  targetDraftId?: number | null;
  targetBriefId?: number | null;
  onClearTargets?: () => void;
}

export const SEOActionsPanel: React.FC<SEOActionsPanelProps> = ({
  project,
  targetRecommendationId,
  targetDraftId,
  targetBriefId,
  onClearTargets,
}) => {
  const [actions, setActions] = useState<SEOAction[]>([]);
  const [selectedActionId, setSelectedActionId] = useState<number | null>(null);
  const [statusCounts, setStatusCounts] = useState<ActionStatusCounts | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [isExecuting, setIsExecuting] = useState<boolean>(false);
  const [isUpdating, setIsUpdating] = useState<boolean>(false);
  const [feedbackMsg, setFeedbackMsg] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);

  // Filters
  const [filterStatus, setFilterStatus] = useState<ActionStatus | 'all'>('all');
  const [filterType, setFilterType] = useState<ActionType | 'all'>('all');
  const [filterPriority, setFilterPriority] = useState<ActionPriority | 'all'>('all');

  // Active Detail Tab
  const [activeTab, setActiveTab] = useState<'evidence' | 'proposed' | 'instructions' | 'execution' | 'raw'>('evidence');

  // Reject Modal State
  const [rejectModalOpen, setRejectModalOpen] = useState<boolean>(false);
  const [rejectTargetId, setRejectTargetId] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState<string>('');

  // Preview Modal State
  const [previewModalOpen, setPreviewModalOpen] = useState<boolean>(false);
  const [previewData, setPreviewData] = useState<ActionPreviewDiff | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState<boolean>(false);

  // Show feedback alert helper
  const showFeedback = useCallback((text: string, type: 'success' | 'error' | 'info' = 'info') => {
    setFeedbackMsg({ text, type });
    setTimeout(() => setFeedbackMsg(null), 5000);
  }, []);

  // Fetch actions
  const fetchActions = useCallback(async () => {
    if (!project) return;
    setIsLoading(true);
    try {
      const data = await getSEOActions({
        project_id: project.id,
        status: filterStatus !== 'all' ? filterStatus : undefined,
        action_type: filterType !== 'all' ? filterType : undefined,
        priority: filterPriority !== 'all' ? filterPriority : undefined,
      });
      setActions(data);

      if (data.length > 0) {
        if (!selectedActionId || !data.some((a) => a.id === selectedActionId)) {
          setSelectedActionId(data[0].id);
        }
      } else {
        setSelectedActionId(null);
      }

      // Fetch summary counts
      try {
        const counts = await getSEOActionStatusCounts(project.id);
        setStatusCounts(counts);
      } catch (err) {
        console.warn('Status counts fetch skipped', err);
      }
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to fetch SEO Actions.', 'error');
    } finally {
      setIsLoading(false);
    }
  }, [project, filterStatus, filterType, filterPriority, selectedActionId, showFeedback]);

  useEffect(() => {
    fetchActions();
  }, [fetchActions]);

  // Handle incoming target generator trigger from other panels
  useEffect(() => {
    if (!project) return;

    if (targetDraftId) {
      handleGenerateAction({ project_id: project.id, content_draft_id: targetDraftId });
      if (onClearTargets) onClearTargets();
    } else if (targetRecommendationId) {
      handleGenerateAction({ project_id: project.id, recommendation_id: targetRecommendationId });
      if (onClearTargets) onClearTargets();
    } else if (targetBriefId) {
      handleGenerateAction({ project_id: project.id, content_brief_id: targetBriefId });
      if (onClearTargets) onClearTargets();
    }
  }, [targetDraftId, targetRecommendationId, targetBriefId, project]);

  // Generate action handler
  const handleGenerateAction = async (payload: { project_id: number; recommendation_id?: number; content_draft_id?: number; content_brief_id?: number; action_type?: string }) => {
    setIsGenerating(true);
    try {
      const newAction = await generateSEOAction(payload);
      showFeedback(`SEO Action "${newAction.title}" generated successfully!`, 'success');
      await fetchActions();
      setSelectedActionId(newAction.id);
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to generate SEO Action.', 'error');
    } finally {
      setIsGenerating(false);
    }
  };

  // Status transitions
  const handleReviewAction = async (id: number) => {
    setIsUpdating(true);
    try {
      const updated = await reviewSEOAction(id);
      setActions((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      showFeedback('Action marked as Reviewed.', 'success');
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to review action.', 'error');
    } finally {
      setIsUpdating(false);
    }
  };

  const handleApproveAction = async (id: number) => {
    setIsUpdating(true);
    try {
      const updated = await approveSEOAction(id);
      setActions((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      showFeedback('Action Approved! Ready for execution.', 'success');
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to approve action.', 'error');
    } finally {
      setIsUpdating(false);
    }
  };

  const handleOpenRejectModal = (id: number) => {
    setRejectTargetId(id);
    setRejectReason('');
    setRejectModalOpen(true);
  };

  const handleConfirmReject = async () => {
    if (!rejectTargetId) return;
    if (!rejectReason.trim()) {
      showFeedback('Please provide a reason for rejecting the action.', 'error');
      return;
    }

    setIsUpdating(true);
    try {
      const updated = await rejectSEOAction(rejectTargetId, rejectReason.trim());
      setActions((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      showFeedback('Action rejected.', 'info');
      setRejectModalOpen(false);
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to reject action.', 'error');
    } finally {
      setIsUpdating(false);
    }
  };

  const handlePreviewAction = async (id: number) => {
    setIsPreviewLoading(true);
    try {
      const res = await previewSEOAction(id);
      setPreviewData(res.preview);
      setPreviewModalOpen(true);
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to generate visual diff preview.', 'error');
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const handleCancelAction = async (id: number) => {
    setIsUpdating(true);
    try {
      const updated = await cancelSEOAction(id);
      setActions((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      showFeedback('Action cancelled.', 'info');
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to cancel action.', 'error');
    } finally {
      setIsUpdating(false);
    }
  };

  const handleExecuteAction = async (id: number) => {
    setIsExecuting(true);
    try {
      const executed = await executeSEOAction(id);
      setActions((prev) => prev.map((a) => (a.id === executed.id ? executed : a)));
      showFeedback(`SEO Action "${executed.title}" executed safely in staging mode!`, 'success');
      setActiveTab('execution');
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to execute action.', 'error');
    } finally {
      setIsExecuting(false);
    }
  };

  const handleDeleteAction = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this SEO Action?')) return;
    try {
      await deleteSEOAction(id);
      setActions((prev) => prev.filter((a) => a.id !== id));
      if (selectedActionId === id) {
        const remaining = actions.filter((a) => a.id !== id);
        setSelectedActionId(remaining.length > 0 ? remaining[0].id : null);
      }
      showFeedback('Action deleted.', 'info');
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to delete action.', 'error');
    }
  };

  // Helper formatting badges
  const renderStatusBadge = (status: ActionStatus) => {
    const configs: Record<string, { bg: string; color: string; label: string; icon: string }> = {
      proposed: { bg: '#eff6ff', color: '#1d4ed8', label: 'Proposed', icon: '💡' },
      pending_approval: { bg: '#fffbeb', color: '#b45309', label: 'Pending Approval', icon: '⏳' },
      reviewed: { bg: '#fef3c7', color: '#b45309', label: 'Reviewed', icon: '🔍' },
      approved: { bg: '#dcfce7', color: '#15803d', label: 'Approved', icon: '✅' },
      ready_to_execute: { bg: '#e0e7ff', color: '#4338ca', label: 'Ready', icon: '🚀' },
      executing: { bg: '#fef9c3', color: '#854d0e', label: 'Executing...', icon: '⚙️' },
      completed: { bg: '#ecfdf5', color: '#047857', label: 'Completed', icon: '✨' },
      rejected: { bg: '#fee2e2', color: '#b91c1c', label: 'Rejected', icon: '❌' },
      failed: { bg: '#fef2f2', color: '#991b1b', label: 'Failed', icon: '⚠️' },
      cancelled: { bg: '#f1f5f9', color: '#64748b', label: 'Cancelled', icon: '🚫' },
    };
    const c = configs[status] || configs.proposed;
    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          padding: '3px 9px',
          borderRadius: '12px',
          fontSize: '11px',
          fontWeight: 700,
          backgroundColor: c.bg,
          color: c.color,
          border: `1px solid ${c.color}30`,
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
        }}
      >
        <span>{c.icon}</span>
        <span>{c.label}</span>
      </span>
    );
  };

  const renderPriorityBadge = (priority: ActionPriority) => {
    const colors: Record<ActionPriority, { bg: string; color: string }> = {
      critical: { bg: '#fee2e2', color: '#dc2626' },
      high: { bg: '#ffedd5', color: '#ea580c' },
      medium: { bg: '#fef3c7', color: '#d97706' },
      low: { bg: '#f1f5f9', color: '#64748b' },
    };
    const c = colors[priority] || colors.high;
    return (
      <span
        style={{
          display: 'inline-block',
          padding: '2px 8px',
          borderRadius: '6px',
          fontSize: '11px',
          fontWeight: 700,
          backgroundColor: c.bg,
          color: c.color,
          textTransform: 'capitalize',
        }}
      >
        {priority}
      </span>
    );
  };

  const activeAction = useMemo(() => {
    return actions.find((a) => a.id === selectedActionId) || null;
  }, [actions, selectedActionId]);

  if (!project) {
    return (
      <div style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
        Please select or create a project to view SEO Actions.
      </div>
    );
  }

  const isPendingApproval = activeAction && (
    activeAction.status === 'pending_approval' ||
    (activeAction.requires_human_approval && !activeAction.approved_at && activeAction.status !== 'approved' && activeAction.status !== 'completed' && activeAction.status !== 'rejected')
  );

  return (
    <section
      id="seo-actions-panel"
      style={{
        backgroundColor: '#ffffff',
        borderRadius: '16px',
        border: '1px solid #e2e8f0',
        padding: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
      }}
    >
      {/* Header & Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '24px' }}>🛡️</span>
            <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 800, color: '#0f172a' }}>
              SEO Actions & Human Approval Gate
            </h2>
          </div>
          <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#64748b' }}>
            Actionable SEO mutation tasks with strict server-side human approval governance before any execution.
          </p>
        </div>

        {/* Status Counters */}
        {statusCounts && (
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <div style={counterChipStyle}>
              <span style={{ fontSize: '11px', color: '#64748b' }}>Pending</span>
              <strong style={{ color: '#b45309' }}>{statusCounts.pending_approval || statusCounts.proposed}</strong>
            </div>
            <div style={counterChipStyle}>
              <span style={{ fontSize: '11px', color: '#64748b' }}>Approved</span>
              <strong style={{ color: '#15803d' }}>{statusCounts.approved}</strong>
            </div>
            <div style={counterChipStyle}>
              <span style={{ fontSize: '11px', color: '#64748b' }}>Completed</span>
              <strong style={{ color: '#047857' }}>{statusCounts.completed}</strong>
            </div>
            <div style={counterChipStyle}>
              <span style={{ fontSize: '11px', color: '#64748b' }}>Total</span>
              <strong>{statusCounts.total}</strong>
            </div>
          </div>
        )}
      </div>

      {/* Feedback Toast */}
      {feedbackMsg && (
        <div
          id="action-feedback-toast"
          style={{
            padding: '12px 16px',
            borderRadius: '8px',
            fontSize: '13px',
            fontWeight: 600,
            backgroundColor: feedbackMsg.type === 'success' ? '#ecfdf5' : feedbackMsg.type === 'error' ? '#fef2f2' : '#eff6ff',
            color: feedbackMsg.type === 'success' ? '#065f46' : feedbackMsg.type === 'error' ? '#991b1b' : '#1e40af',
            border: `1px solid ${feedbackMsg.type === 'success' ? '#a7f3d0' : feedbackMsg.type === 'error' ? '#fca5a5' : '#bfdbfe'}`,
          }}
        >
          {feedbackMsg.text}
        </div>
      )}

      {/* Generating Indicator */}
      {isGenerating && (
        <div
          id="action-generating-toast"
          style={{
            padding: '12px 16px',
            borderRadius: '8px',
            fontSize: '13px',
            fontWeight: 600,
            backgroundColor: '#eff6ff',
            color: '#1e40af',
            border: '1px solid #bfdbfe',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          <span>⚡</span>
          <span>Synthesizing new SEO Action proposal...</span>
        </div>
      )}

      {/* Filter Bar */}
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center', backgroundColor: '#f8fafc', padding: '12px 16px', borderRadius: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>Status:</label>
          <select
            id="filter-action-status"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value as any)}
            style={selectInputStyle}
          >
            <option value="all">All Statuses</option>
            <option value="pending_approval">Pending Approval</option>
            <option value="proposed">Proposed</option>
            <option value="reviewed">Reviewed</option>
            <option value="approved">Approved</option>
            <option value="ready_to_execute">Ready to Execute</option>
            <option value="executing">Executing</option>
            <option value="completed">Completed</option>
            <option value="rejected">Rejected</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>Action Type:</label>
          <select
            id="filter-action-type"
            value={filterType}
            onChange={(e) => setFilterType(e.target.value as any)}
            style={selectInputStyle}
          >
            <option value="all">All Types</option>
            <option value="optimize_title">Optimize Title</option>
            <option value="optimize_meta_description">Optimize Meta Description</option>
            <option value="fix_missing_h1">Fix Missing H1</option>
            <option value="fix_canonical">Fix Canonical Tag</option>
            <option value="fix_image_alt">Fix Image Alt</option>
            <option value="fix_broken_link">Fix Broken Links</option>
            <option value="publish_new_content">Publish New Content</option>
            <option value="optimize_existing_content">Optimize Content</option>
            <option value="technical_seo_fix">Technical SEO</option>
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>Priority:</label>
          <select
            id="filter-action-priority"
            value={filterPriority}
            onChange={(e) => setFilterPriority(e.target.value as any)}
            style={selectInputStyle}
          >
            <option value="all">All Priorities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>

        {(filterStatus !== 'all' || filterType !== 'all' || filterPriority !== 'all') && (
          <button
            onClick={() => {
              setFilterStatus('all');
              setFilterType('all');
              setFilterPriority('all');
            }}
            style={{
              background: 'none',
              border: 'none',
              color: '#2563eb',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Reset Filters
          </button>
        )}
      </div>

      {/* Main Workspace Grid */}
      {isLoading ? (
        <div style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>
          Loading SEO Actions...
        </div>
      ) : actions.length === 0 ? (
        <div
          style={{
            padding: '48px 24px',
            textAlign: 'center',
            backgroundColor: '#f8fafc',
            borderRadius: '12px',
            border: '2px dashed #e2e8f0',
          }}
        >
          <div style={{ fontSize: '40px', marginBottom: '12px' }}>🛡️</div>
          <h3 style={{ margin: '0 0 6px 0', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
            No SEO Actions Proposed Yet
          </h3>
          <p style={{ margin: '0 0 16px 0', fontSize: '13px', color: '#64748b', maxWidth: '480px', marginInline: 'auto' }}>
            Autonomous investigations and AI suggestions will propose formal action tasks requiring your approval before execution.
          </p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: '20px', alignItems: 'start' }}>
          {/* Action List Sidebar */}
          <div
            style={{
              border: '1px solid #e2e8f0',
              borderRadius: '12px',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
              maxHeight: '650px',
            }}
          >
            <div style={{ padding: '12px 14px', backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', fontSize: '12px', fontWeight: 700, color: '#475569' }}>
              Action Tasks ({actions.length})
            </div>
            <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
              {actions.map((act) => {
                const isSelected = activeAction?.id === act.id;
                return (
                  <div
                    key={act.id}
                    id={`action-item-${act.id}`}
                    onClick={() => setSelectedActionId(act.id)}
                    style={{
                      padding: '12px 14px',
                      borderBottom: '1px solid #f1f5f9',
                      backgroundColor: isSelected ? '#eff6ff' : '#ffffff',
                      borderLeft: isSelected ? '4px solid #2563eb' : '4px solid transparent',
                      cursor: 'pointer',
                      transition: 'background 0.15s ease',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                      {renderPriorityBadge(act.priority)}
                      {renderStatusBadge(act.status)}
                    </div>
                    <div style={{ fontWeight: 700, fontSize: '13px', color: isSelected ? '#1e40af' : '#0f172a', marginBottom: '4px', lineHeight: 1.3 }}>
                      {act.title}
                    </div>
                    {act.target_url && (
                      <div style={{ fontSize: '11px', color: '#64748b', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        🔗 <code>{act.target_url}</code>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Action Detail Workspace */}
          {activeAction ? (
            <div
              style={{
                border: '1px solid #e2e8f0',
                borderRadius: '12px',
                backgroundColor: '#ffffff',
                padding: '24px',
                display: 'flex',
                flexDirection: 'column',
                gap: '20px',
              }}
            >
              {/* Prominent Human Approval Governance Banner */}
              {isPendingApproval && (
                <div
                  id="pending-approval-banner"
                  style={{
                    padding: '16px 20px',
                    backgroundColor: '#fffbeb',
                    border: '1px solid #fde68a',
                    borderRadius: '10px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: '14px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span style={{ fontSize: '28px' }}>🛡️</span>
                    <div>
                      <div style={{ fontWeight: 800, fontSize: '14px', color: '#92400e' }}>
                        WAITING FOR YOUR APPROVAL
                      </div>
                      <div style={{ fontSize: '12px', color: '#b45309', marginTop: '2px' }}>
                        The autonomous agent proposed this website mutation. Direct execution is strictly blocked until you review and approve.
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <button
                      id="preview-action-banner-btn"
                      onClick={() => handlePreviewAction(activeAction.id)}
                      disabled={isPreviewLoading}
                      style={{ ...actionBtnStyleSecondary, borderColor: '#f59e0b', color: '#b45309', fontWeight: 700 }}
                    >
                      {isPreviewLoading ? 'Loading Diff...' : '🔍 Preview Diff'}
                    </button>
                    <button
                      id="approve-action-banner-btn"
                      onClick={() => handleApproveAction(activeAction.id)}
                      disabled={isUpdating}
                      style={{ ...actionBtnStylePrimary, backgroundColor: '#10b981' }}
                    >
                      ✅ Approve Action
                    </button>
                    <button
                      id="reject-action-banner-btn"
                      onClick={() => handleOpenRejectModal(activeAction.id)}
                      disabled={isUpdating}
                      style={actionBtnStyleDanger}
                    >
                      Reject...
                    </button>
                  </div>
                </div>
              )}

              {/* Header Details */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px', borderBottom: '1px solid #f1f5f9', paddingBottom: '16px' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                    {renderPriorityBadge(activeAction.priority)}
                    {renderStatusBadge(activeAction.status)}
                    <span style={{ fontSize: '12px', color: '#64748b' }}>
                      Type: <strong>{activeAction.action_type_display}</strong>
                    </span>
                    {activeAction.risk_level && (
                      <span style={{ fontSize: '11px', padding: '2px 6px', backgroundColor: '#f1f5f9', borderRadius: '4px', color: '#475569' }}>
                        Risk: <strong>{activeAction.risk_level.toUpperCase()}</strong>
                      </span>
                    )}
                  </div>
                  <h3 style={{ margin: '0 0 6px 0', fontSize: '18px', fontWeight: 800, color: '#0f172a' }}>
                    {activeAction.title}
                  </h3>
                  <p style={{ margin: 0, fontSize: '13px', color: '#475569', lineHeight: 1.5 }}>
                    {activeAction.description}
                  </p>
                </div>

                {/* Primary Action Controls */}
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                  <button
                    id="preview-action-btn"
                    onClick={() => handlePreviewAction(activeAction.id)}
                    disabled={isPreviewLoading}
                    style={actionBtnStyleSecondary}
                  >
                    🔍 Preview Diff
                  </button>

                  {activeAction.status === 'proposed' && (
                    <button
                      id="review-action-btn"
                      onClick={() => handleReviewAction(activeAction.id)}
                      disabled={isUpdating}
                      style={actionBtnStyleSecondary}
                    >
                      🔍 Mark Reviewed
                    </button>
                  )}

                  {(activeAction.status === 'proposed' || activeAction.status === 'pending_approval' || activeAction.status === 'reviewed') && (
                    <button
                      id="approve-action-btn"
                      onClick={() => handleApproveAction(activeAction.id)}
                      disabled={isUpdating}
                      style={{ ...actionBtnStylePrimary, backgroundColor: '#10b981' }}
                    >
                      ✅ Approve
                    </button>
                  )}

                  {/* Execute Button - strictly available only when approved/ready */}
                  {(activeAction.status === 'approved' || activeAction.status === 'ready_to_execute') && (
                    <button
                      id="execute-action-btn"
                      onClick={() => handleExecuteAction(activeAction.id)}
                      disabled={isExecuting}
                      style={{
                        ...actionBtnStylePrimary,
                        backgroundColor: '#2563eb',
                        boxShadow: '0 4px 10px rgba(37,99,235,0.25)',
                      }}
                    >
                      {isExecuting ? '⚙️ Executing...' : '⚡ Execute (Safe Staging)'}
                    </button>
                  )}

                  {(activeAction.status === 'proposed' || activeAction.status === 'pending_approval' || activeAction.status === 'reviewed') && (
                    <button
                      id="reject-action-btn"
                      onClick={() => handleOpenRejectModal(activeAction.id)}
                      disabled={isUpdating}
                      style={actionBtnStyleDanger}
                    >
                      Reject...
                    </button>
                  )}

                  {activeAction.status !== 'completed' && activeAction.status !== 'cancelled' && activeAction.status !== 'rejected' && (
                    <button
                      id="cancel-action-btn"
                      onClick={() => handleCancelAction(activeAction.id)}
                      disabled={isUpdating}
                      style={actionBtnStyleSecondary}
                    >
                      Cancel
                    </button>
                  )}

                  <button
                    id="delete-action-btn"
                    onClick={() => handleDeleteAction(activeAction.id)}
                    style={{ background: 'none', border: 'none', color: '#94a3b8', fontSize: '12px', cursor: 'pointer' }}
                  >
                    🗑️ Delete
                  </button>
                </div>
              </div>

              {/* Target Details Grid */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', padding: '14px', backgroundColor: '#f8fafc', borderRadius: '10px' }}>
                <div>
                  <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>Target URL</span>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: '#0f172a', wordBreak: 'break-all' }}>
                    {activeAction.target_url || 'Project Base Domain'}
                  </div>
                </div>
                <div>
                  <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>Target Query</span>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: '#0f172a' }}>
                    <code>{activeAction.target_keyword || 'N/A'}</code>
                  </div>
                </div>
                <div>
                  <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>Approval State</span>
                  <div style={{ fontSize: '13px', color: '#0f172a' }}>
                    {activeAction.approved_at ? (
                      <span style={{ color: '#15803d', fontWeight: 600 }}>Approved ({activeAction.approved_by_email || 'Owner'})</span>
                    ) : activeAction.rejected_at ? (
                      <span style={{ color: '#b91c1c', fontWeight: 600 }}>Rejected: {activeAction.rejection_reason}</span>
                    ) : (
                      <span style={{ color: '#b45309', fontWeight: 600 }}>Requires Human Sign-off</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Detail Navigation Tabs */}
              <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid #e2e8f0', paddingBottom: '8px', flexWrap: 'wrap' }}>
                <button
                  id="tab-evidence"
                  onClick={() => setActiveTab('evidence')}
                  style={getTabStyle(activeTab === 'evidence')}
                >
                  🔬 Evidence & Root Cause
                </button>
                <button
                  id="tab-proposed-changes"
                  onClick={() => setActiveTab('proposed')}
                  style={getTabStyle(activeTab === 'proposed')}
                >
                  📝 Proposed Changes
                </button>
                <button
                  id="tab-instructions"
                  onClick={() => setActiveTab('instructions')}
                  style={getTabStyle(activeTab === 'instructions')}
                >
                  📋 Implementation Instructions
                </button>
                {activeAction.execution_metadata && Object.keys(activeAction.execution_metadata).length > 0 && (
                  <button
                    id="tab-execution-history"
                    onClick={() => setActiveTab('execution')}
                    style={getTabStyle(activeTab === 'execution')}
                  >
                    🚀 Execution & Monitoring
                  </button>
                )}
                <button
                  id="tab-raw-payload"
                  onClick={() => setActiveTab('raw')}
                  style={getTabStyle(activeTab === 'raw')}
                >
                  🔧 Raw Data
                </button>
              </div>

              {/* Tab 0: Evidence & Root Cause */}
              {activeTab === 'evidence' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {activeAction.rationale && (
                    <div style={{ padding: '14px', backgroundColor: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                      <span style={propLabelStyle}>Causal Root Cause Rationale</span>
                      <p style={{ margin: '6px 0 0 0', fontSize: '13px', color: '#1e293b', lineHeight: 1.5 }}>
                        {activeAction.rationale}
                      </p>
                    </div>
                  )}

                  {activeAction.evidence_snapshot && (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
                      {/* Observed Facts */}
                      <div style={{ padding: '14px', backgroundColor: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                        <span style={propLabelStyle}>Observed Facts</span>
                        <ul style={{ margin: '8px 0 0 0', paddingLeft: '18px', fontSize: '12px', color: '#334155', lineHeight: 1.5 }}>
                          {(activeAction.evidence_snapshot.observed_facts || ['Empirical signals recorded from GSC and SiteAudit']).map((f: string, i: number) => (
                            <li key={i}>{f}</li>
                          ))}
                        </ul>
                      </div>

                      {/* Inferences */}
                      <div style={{ padding: '14px', backgroundColor: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                        <span style={propLabelStyle}>Inferences & Deductions</span>
                        <ul style={{ margin: '8px 0 0 0', paddingLeft: '18px', fontSize: '12px', color: '#334155', lineHeight: 1.5 }}>
                          {(activeAction.evidence_snapshot.inferences || ['Grounded deductions from observed ranking & crawl behavior']).map((inf: string, i: number) => (
                            <li key={i}>{inf}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Tab 1: Proposed Changes */}
              {activeTab === 'proposed' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {activeAction.proposed_change?.title && (
                    <div style={propFieldStyle}>
                      <span style={propLabelStyle}>Proposed Title / H1:</span>
                      <div style={{ fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
                        {activeAction.proposed_change.title}
                      </div>
                    </div>
                  )}

                  {activeAction.proposed_change?.meta_description && (
                    <div style={propFieldStyle}>
                      <span style={propLabelStyle}>Proposed Meta Description ({String(activeAction.proposed_change.meta_description).length} chars):</span>
                      <div style={{ fontSize: '13px', color: '#334155', lineHeight: 1.4 }}>
                        {activeAction.proposed_change.meta_description}
                      </div>
                    </div>
                  )}

                  {activeAction.proposed_change?.canonical_url && (
                    <div style={propFieldStyle}>
                      <span style={propLabelStyle}>Canonical URL:</span>
                      <div style={{ fontSize: '13px', color: '#2563eb' }}>
                        <code>{activeAction.proposed_change.canonical_url}</code>
                      </div>
                    </div>
                  )}

                  {activeAction.proposed_change?.content && (
                    <div style={propFieldStyle}>
                      <span style={propLabelStyle}>Publishing Content Body Preview:</span>
                      <div style={{ fontSize: '13px', color: '#1e293b', maxHeight: '200px', overflowY: 'auto', whiteSpace: 'pre-wrap', backgroundColor: '#f8fafc', padding: '12px', borderRadius: '8px' }}>
                        {typeof activeAction.proposed_change.content === 'string'
                          ? activeAction.proposed_change.content.slice(0, 1000) + '...'
                          : JSON.stringify(activeAction.proposed_change.content, null, 2)}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Tab 2: Implementation Instructions */}
              {activeTab === 'instructions' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div
                    style={{
                      padding: '16px',
                      backgroundColor: '#f8fafc',
                      borderRadius: '10px',
                      border: '1px solid #e2e8f0',
                      fontSize: '13px',
                      color: '#1e293b',
                      lineHeight: 1.6,
                      whiteSpace: 'pre-wrap',
                    }}
                  >
                    {activeAction.implementation_instructions}
                  </div>
                </div>
              )}

              {/* Tab 3: Execution History & Monitoring */}
              {activeTab === 'execution' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div style={{ padding: '16px', backgroundColor: '#ecfdf5', borderRadius: '10px', border: '1px solid #a7f3d0' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                      <span style={{ fontSize: '18px' }}>✅</span>
                      <strong style={{ color: '#065f46', fontSize: '14px' }}>Safe Staging Execution Record</strong>
                    </div>
                    <p style={{ margin: '0 0 8px 0', fontSize: '13px', color: '#047857' }}>
                      {activeAction.execution_metadata?.summary || 'Action deployed safely in staging mode. Zero destructive mutations applied.'}
                    </p>
                    <div style={{ fontSize: '12px', color: '#047857', display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                      <span><strong>Executor:</strong> {activeAction.execution_metadata?.executor}</span>
                      <span><strong>Executed:</strong> {activeAction.execution_metadata?.executed_at ? new Date(activeAction.execution_metadata.executed_at).toLocaleString() : 'N/A'}</span>
                      <span><strong>Duration:</strong> {activeAction.execution_metadata?.duration_ms}ms</span>
                    </div>
                  </div>

                  {/* Monitoring Hook Baseline */}
                  {activeAction.execution_metadata?.monitoring_baseline && (
                    <div style={{ padding: '16px', backgroundColor: '#eff6ff', borderRadius: '10px', border: '1px solid #bfdbfe' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                        <span style={{ fontSize: '18px' }}>📡</span>
                        <strong style={{ color: '#1e40af', fontSize: '14px' }}>SEO Monitoring Hook Baseline</strong>
                      </div>
                      <p style={{ margin: '0 0 12px 0', fontSize: '12px', color: '#1e3a8a' }}>
                        Baseline captured at execution time to verify future SEO ranking, impressions, and CTR changes.
                      </p>
                      <pre style={{ margin: 0, fontSize: '11px', backgroundColor: '#ffffff', color: '#0f172a', padding: '12px', borderRadius: '8px', border: '1px solid #dbeafe', overflowX: 'auto' }}>
                        {JSON.stringify(activeAction.execution_metadata.monitoring_baseline, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}

              {/* Tab 4: Raw Data */}
              {activeTab === 'raw' && (
                <pre style={{ margin: 0, fontSize: '11px', backgroundColor: '#0f172a', color: '#38bdf8', padding: '14px', borderRadius: '8px', maxHeight: '350px', overflowY: 'auto' }}>
                  {JSON.stringify(activeAction, null, 2)}
                </pre>
              )}
            </div>
          ) : (
            <div style={{ padding: '40px', textAlign: 'center', color: '#94a3b8' }}>
              Select an action on the left to inspect details.
            </div>
          )}
        </div>
      )}

      {/* Reject Modal */}
      {rejectModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            backdropFilter: 'blur(2px)',
          }}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              padding: '24px',
              maxWidth: '480px',
              width: '90%',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '20px' }}>❌</span>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 800, color: '#0f172a' }}>
                Reject SEO Action Proposal
              </h3>
            </div>
            <p style={{ margin: 0, fontSize: '13px', color: '#475569' }}>
              Please provide a clear reason for rejecting this action. This helps the AI agent calibrate future recommendations.
            </p>
            <textarea
              id="reject-reason-input"
              rows={4}
              placeholder="e.g. Meta description copy does not align with brand voice guidelines..."
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: '8px',
                border: '1px solid #cbd5e1',
                fontSize: '13px',
                fontFamily: 'inherit',
                resize: 'vertical',
                boxSizing: 'border-box',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                onClick={() => setRejectModalOpen(false)}
                style={actionBtnStyleSecondary}
              >
                Cancel
              </button>
              <button
                id="confirm-reject-btn"
                onClick={handleConfirmReject}
                disabled={isUpdating || !rejectReason.trim()}
                style={{ ...actionBtnStyleDanger, opacity: !rejectReason.trim() ? 0.6 : 1 }}
              >
                {isUpdating ? 'Rejecting...' : 'Confirm Rejection'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Preview Diff Modal */}
      {previewModalOpen && previewData && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            backdropFilter: 'blur(2px)',
          }}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              padding: '24px',
              maxWidth: '680px',
              width: '90%',
              maxHeight: '85vh',
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '20px' }}>🔍</span>
                <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 800, color: '#0f172a' }}>
                  Visual Diff & Impact Preview
                </h3>
              </div>
              <button
                onClick={() => setPreviewModalOpen(false)}
                style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer', color: '#94a3b8' }}
              >
                ✕
              </button>
            </div>

            <p style={{ margin: 0, fontSize: '13px', color: '#475569' }}>
              {previewData.summary || 'Simulated diff showing proposed changes against current state.'}
            </p>

            {/* Target info */}
            <div style={{ padding: '10px 14px', backgroundColor: '#f8fafc', borderRadius: '8px', fontSize: '12px', display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
              <span><strong>Target URL:</strong> <code>{previewData.target_url}</code></span>
              <span><strong>Risk Level:</strong> {previewData.risk_level?.toUpperCase()}</span>
            </div>

            {/* Diff details */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <span style={propLabelStyle}>Structured Diff</span>
              <pre style={{ margin: 0, fontSize: '12px', backgroundColor: '#0f172a', color: '#38bdf8', padding: '14px', borderRadius: '8px', overflowX: 'auto' }}>
                {JSON.stringify(previewData.diff || previewData.after_state, null, 2)}
              </pre>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '8px' }}>
              <button
                onClick={() => setPreviewModalOpen(false)}
                style={actionBtnStylePrimary}
              >
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};

// Internal styles
const counterChipStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  padding: '4px 12px',
  backgroundColor: '#f8fafc',
  borderRadius: '8px',
  border: '1px solid #e2e8f0',
};

const selectInputStyle: React.CSSProperties = {
  padding: '6px 10px',
  borderRadius: '6px',
  border: '1px solid #cbd5e1',
  fontSize: '12px',
  fontWeight: 500,
  backgroundColor: '#ffffff',
  color: '#0f172a',
};

const actionBtnStylePrimary: React.CSSProperties = {
  backgroundColor: '#2563eb',
  color: '#ffffff',
  border: 'none',
  borderRadius: '8px',
  padding: '7px 14px',
  fontSize: '12px',
  fontWeight: 700,
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  gap: '6px',
};

const actionBtnStyleSecondary: React.CSSProperties = {
  backgroundColor: '#ffffff',
  color: '#334155',
  border: '1px solid #cbd5e1',
  borderRadius: '8px',
  padding: '7px 12px',
  fontSize: '12px',
  fontWeight: 600,
  cursor: 'pointer',
};

const actionBtnStyleDanger: React.CSSProperties = {
  backgroundColor: '#fee2e2',
  color: '#991b1b',
  border: '1px solid #fca5a5',
  borderRadius: '8px',
  padding: '7px 12px',
  fontSize: '12px',
  fontWeight: 600,
  cursor: 'pointer',
};

const propFieldStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '4px',
  padding: '12px',
  backgroundColor: '#f8fafc',
  borderRadius: '8px',
  border: '1px solid #f1f5f9',
};

const propLabelStyle: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 700,
  color: '#64748b',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};

const getTabStyle = (isActive: boolean): React.CSSProperties => ({
  background: 'none',
  border: 'none',
  borderBottom: isActive ? '2px solid #2563eb' : '2px solid transparent',
  color: isActive ? '#2563eb' : '#64748b',
  fontWeight: isActive ? 700 : 500,
  fontSize: '13px',
  padding: '6px 12px',
  cursor: 'pointer',
});
