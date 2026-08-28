import React, { useState, useEffect, useCallback, useMemo } from 'react';
import type { Project } from '../types/project';
import type {
  SEOAction,
  ActionType,
  ActionStatus,
  ActionPriority,
  ActionStatusCounts
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

  // Active view tab inside Action Workspace
  const [activeTab, setActiveTab] = useState<'proposed' | 'instructions' | 'execution' | 'raw'>('proposed');

  // Selected Action object
  const activeAction = useMemo(() => {
    return actions.find((a) => a.id === selectedActionId) || actions[0] || null;
  }, [actions, selectedActionId]);

  const showFeedback = useCallback((text: string, type: 'success' | 'error' | 'info' = 'success') => {
    setFeedbackMsg({ text, type });
    setTimeout(() => setFeedbackMsg(null), 5000);
  }, []);

  // Fetch actions & status counts
  const fetchActions = useCallback(async () => {
    if (!project) {
      setActions([]);
      setStatusCounts(null);
      return;
    }

    setIsLoading(true);
    try {
      const [actionsData, countsData] = await Promise.all([
        getSEOActions({
          project_id: project.id,
          status: filterStatus !== 'all' ? filterStatus : undefined,
          action_type: filterType !== 'all' ? filterType : undefined,
          priority: filterPriority !== 'all' ? filterPriority : undefined,
        }),
        getSEOActionStatusCounts(project.id).catch(() => null)
      ]);

      setActions(actionsData);
      if (countsData) setStatusCounts(countsData);

      if (actionsData.length > 0) {
        if (!selectedActionId || !actionsData.some((a) => a.id === selectedActionId)) {
          setSelectedActionId(actionsData[0].id);
        }
      } else {
        setSelectedActionId(null);
      }
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to load SEO actions.', 'error');
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

  const handleRejectAction = async (id: number) => {
    setIsUpdating(true);
    try {
      const updated = await rejectSEOAction(id);
      setActions((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      showFeedback('Action rejected.', 'info');
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to reject action.', 'error');
    } finally {
      setIsUpdating(false);
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
    const configs: Record<ActionStatus, { bg: string; color: string; label: string; icon: string }> = {
      proposed: { bg: '#eff6ff', color: '#1d4ed8', label: 'Proposed', icon: '💡' },
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
          textTransform: 'uppercase',
        }}
      >
        {priority}
      </span>
    );
  };

  return (
    <section
      id="seo-actions-section"
      style={{
        backgroundColor: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: '16px',
        padding: '24px 28px',
        marginTop: '28px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.03)',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
      }}
    >
      {/* Panel Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '26px' }}>⚡</span>
            <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 800, color: '#0f172a' }}>
              SEO Action & Publishing Engine
            </h2>
            <span
              style={{
                fontSize: '11px',
                fontWeight: 700,
                padding: '3px 8px',
                borderRadius: '12px',
                backgroundColor: '#eff6ff',
                color: '#2563eb',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
              }}
            >
              Step 5: Human Review & Safe Execution
            </span>
            {isGenerating && (
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: 700,
                  padding: '3px 8px',
                  borderRadius: '12px',
                  backgroundColor: '#fef3c7',
                  color: '#b45309',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                ⚙️ Synthesizing Action Proposal...
              </span>
            )}
          </div>
          <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#64748b' }}>

            Convert AI recommendations and approved drafts into executable tasks with human approval controls and safe staging deployment.
          </p>
        </div>

        {/* Status Counter Bar */}
        {statusCounts && (
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <div style={counterChipStyle}>
              <span style={{ color: '#64748b', fontSize: '11px' }}>Proposed</span>
              <strong style={{ color: '#1d4ed8', fontSize: '14px' }}>{statusCounts.proposed}</strong>
            </div>
            <div style={counterChipStyle}>
              <span style={{ color: '#64748b', fontSize: '11px' }}>Approved</span>
              <strong style={{ color: '#15803d', fontSize: '14px' }}>{statusCounts.approved}</strong>
            </div>
            <div style={counterChipStyle}>
              <span style={{ color: '#64748b', fontSize: '11px' }}>Completed</span>
              <strong style={{ color: '#047857', fontSize: '14px' }}>{statusCounts.completed}</strong>
            </div>
            <div style={counterChipStyle}>
              <span style={{ color: '#64748b', fontSize: '11px' }}>Total</span>
              <strong style={{ color: '#0f172a', fontSize: '14px' }}>{statusCounts.total}</strong>
            </div>
          </div>
        )}
      </div>

      {/* Feedback Alert */}
      {feedbackMsg && (
        <div
          style={{
            padding: '10px 16px',
            borderRadius: '8px',
            fontSize: '13px',
            fontWeight: 500,
            backgroundColor: feedbackMsg.type === 'success' ? '#f0fdf4' : feedbackMsg.type === 'error' ? '#fef2f2' : '#f0f9ff',
            color: feedbackMsg.type === 'success' ? '#166534' : feedbackMsg.type === 'error' ? '#991b1b' : '#0369a1',
            border: `1px solid ${feedbackMsg.type === 'success' ? '#bbf7d0' : feedbackMsg.type === 'error' ? '#fecaca' : '#bae6fd'}`,
          }}
        >
          {feedbackMsg.text}
        </div>
      )}

      {/* Filters Bar */}
      <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap', padding: '12px 16px', backgroundColor: '#f8fafc', borderRadius: '10px', border: '1px solid #edf2f7' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>Status:</label>
          <select
            id="filter-action-status"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value as any)}
            style={selectInputStyle}
          >
            <option value="all">All Statuses</option>
            <option value="proposed">Proposed</option>
            <option value="reviewed">Reviewed</option>
            <option value="approved">Approved</option>
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
            <option value="publish_new_content">Publish New Content</option>
            <option value="update_meta_description">Update Meta Description</option>
            <option value="update_title">Update Title Tag</option>
            <option value="optimize_existing_content">Optimize Content</option>
            <option value="content_refresh">Content Refresh</option>
            <option value="add_internal_links">Add Internal Links</option>
            <option value="add_structured_data">Structured Data</option>
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
          <div style={{ fontSize: '40px', marginBottom: '12px' }}>⚡</div>
          <h3 style={{ margin: '0 0 6px 0', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
            No SEO Actions Created Yet
          </h3>
          <p style={{ margin: '0 0 16px 0', fontSize: '13px', color: '#64748b', maxWidth: '480px', marginInline: 'auto' }}>
            Click <strong>"⚡ Create Action"</strong> on any AI Recommendation, Content Brief, or Approved Draft above to generate an actionable SEO task.
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
                    {act.target_keyword && (
                      <div style={{ fontSize: '11px', color: '#64748b', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        🎯 <code>{act.target_keyword}</code>
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
              {/* Header Details */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px', borderBottom: '1px solid #f1f5f9', paddingBottom: '16px' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                    {renderPriorityBadge(activeAction.priority)}
                    {renderStatusBadge(activeAction.status)}
                    <span style={{ fontSize: '12px', color: '#64748b' }}>
                      Type: <strong>{activeAction.action_type_display}</strong>
                    </span>
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
                  {/* Status buttons */}
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

                  {(activeAction.status === 'proposed' || activeAction.status === 'reviewed') && (
                    <button
                      id="approve-action-btn"
                      onClick={() => handleApproveAction(activeAction.id)}
                      disabled={isUpdating}
                      style={{ ...actionBtnStylePrimary, backgroundColor: '#10b981' }}
                    >
                      ✅ Approve Action
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

                  {(activeAction.status === 'proposed' || activeAction.status === 'reviewed') && (
                    <button
                      id="reject-action-btn"
                      onClick={() => handleRejectAction(activeAction.id)}
                      disabled={isUpdating}
                      style={actionBtnStyleDanger}
                    >
                      Reject
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
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px', padding: '14px', backgroundColor: '#f8fafc', borderRadius: '10px' }}>
                <div>
                  <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>Target URL</span>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: '#0f172a', wordBreak: 'break-all' }}>
                    {activeAction.target_url || 'Project Base Domain'}
                  </div>
                </div>
                <div>
                  <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>Target Keyword</span>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: '#0f172a' }}>
                    <code>{activeAction.target_keyword || 'N/A'}</code>
                  </div>
                </div>
                <div>
                  <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>Originating Source</span>
                  <div style={{ fontSize: '13px', color: '#0f172a' }}>
                    {activeAction.draft ? (
                      <span>📄 Content Draft #{activeAction.draft}</span>
                    ) : activeAction.brief ? (
                      <span>📋 Content Brief #{activeAction.brief}</span>
                    ) : activeAction.recommendation ? (
                      <span>💡 Recommendation #{activeAction.recommendation}</span>
                    ) : (
                      <span>Direct AI Generation</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Detail Navigation Tabs */}
              <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid #e2e8f0', paddingBottom: '8px' }}>
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
                    🚀 Execution History & Monitoring
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

                  {activeAction.proposed_change?.slug && (
                    <div style={propFieldStyle}>
                      <span style={propLabelStyle}>URL Slug:</span>
                      <div style={{ fontSize: '13px', color: '#2563eb' }}>
                        <code>{activeAction.proposed_change.slug}</code>
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

                  {activeAction.proposed_change?.faq && Array.isArray(activeAction.proposed_change.faq) && activeAction.proposed_change.faq.length > 0 && (
                    <div style={propFieldStyle}>
                      <span style={propLabelStyle}>FAQ Schema Items ({activeAction.proposed_change.faq.length}):</span>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {activeAction.proposed_change.faq.map((faq: any, i: number) => (
                          <div key={i} style={{ padding: '8px 12px', backgroundColor: '#f8fafc', borderRadius: '6px', fontSize: '12px' }}>
                            <strong>Q: {faq.question}</strong>
                            <p style={{ margin: '4px 0 0 0', color: '#475569' }}>A: {faq.answer}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {activeAction.proposed_change?.schema_json_ld && Object.keys(activeAction.proposed_change.schema_json_ld).length > 0 && (
                    <div style={propFieldStyle}>
                      <span style={propLabelStyle}>Schema JSON-LD Markup:</span>
                      <pre style={{ margin: 0, fontSize: '11px', backgroundColor: '#1e293b', color: '#f8fafc', padding: '12px', borderRadius: '8px', overflowX: 'auto' }}>
                        {JSON.stringify(activeAction.proposed_change.schema_json_ld, null, 2)}
                      </pre>
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
                      <strong style={{ color: '#065f46', fontSize: '14px' }}>Safe Execution Record</strong>
                    </div>
                    <p style={{ margin: '0 0 8px 0', fontSize: '13px', color: '#047857' }}>
                      {activeAction.execution_metadata?.deployment_summary || 'Action deployed in safe simulation mode.'}
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
