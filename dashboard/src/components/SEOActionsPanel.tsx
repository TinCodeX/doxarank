import React, { useState, useEffect, useCallback, useMemo } from 'react';
import type { Project } from '../types/project';
import type {
  SEOAction,
  SEOActionPlan,
  ActionType,
  ActionStatus,
  ActionPlanStatus,
  ActionPriority,
  ActionRiskLevel,
  VerificationStatus,
  SEOOutcome,
  PlanSEOOutcome,
  HistoricalOutcomeSignals,
  ActionStatusCounts,
  ActionPreviewDiff,
  AdaptiveSEOStrategyResponse
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
  verifySEOAction,
  measureSEOActionOutcome,
  getHistoricalOutcomeSignals,
  getAdaptiveSEOStrategy,
  getSEOActionStatusCounts
} from '../api/seoActions';
import {
  getSEOActionPlans,
  generateSEOActionPlan,
  approveSEOActionPlan,
  rejectSEOActionPlan,
  executeSEOActionPlan,
  verifySEOActionPlan,
  measureSEOActionPlanOutcome,
  deleteSEOActionPlan
} from '../api/seoActionPlans';



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
  // Mode toggle: Actions vs Plans
  const [viewMode, setViewMode] = useState<'plans' | 'actions'>('plans');

  // Actions State
  const [actions, setActions] = useState<SEOAction[]>([]);
  const [selectedActionId, setSelectedActionId] = useState<number | null>(null);
  const [statusCounts, setStatusCounts] = useState<ActionStatusCounts | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [isExecuting, setIsExecuting] = useState<boolean>(false);
  const [isVerifying, setIsVerifying] = useState<boolean>(false);
  const [isMeasuring, setIsMeasuring] = useState<boolean>(false);
  const [historicalSignals, setHistoricalSignals] = useState<HistoricalOutcomeSignals | null>(null);
  const [adaptiveStrategy, setAdaptiveStrategy] = useState<AdaptiveSEOStrategyResponse | null>(null);
  const [isUpdating, setIsUpdating] = useState<boolean>(false);
  const [feedbackMsg, setFeedbackMsg] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);

  // Plans State
  const [plans, setPlans] = useState<SEOActionPlan[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null);
  const [isPlansLoading, setIsPlansLoading] = useState<boolean>(false);
  const [planModalOpen, setPlanModalOpen] = useState<boolean>(false);
  const [planTitleInput, setPlanTitleInput] = useState<string>('');
  const [planMaxActions, setPlanMaxActions] = useState<number>(10);
  const [planRejectModalOpen, setPlanRejectModalOpen] = useState<boolean>(false);
  const [planRejectTargetId, setPlanRejectTargetId] = useState<number | null>(null);
  const [planRejectReason, setPlanRejectReason] = useState<string>('');

  // Filters
  const [filterStatus, setFilterStatus] = useState<ActionStatus | 'all'>('all');
  const [filterType, setFilterType] = useState<ActionType | 'all'>('all');
  const [filterPriority, setFilterPriority] = useState<ActionPriority | 'all'>('all');

  // Active Detail Tab for single action
  const [activeTab, setActiveTab] = useState<'evidence' | 'proposed' | 'instructions' | 'execution' | 'verification' | 'outcome' | 'raw'>('evidence');


  // Reject Modal State for Action
  const [rejectModalOpen, setRejectModalOpen] = useState<boolean>(false);
  const [rejectTargetId, setRejectTargetId] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState<string>('');

  // Preview Modal State
  const [previewModalOpen, setPreviewModalOpen] = useState<boolean>(false);
  const [previewData, setPreviewData] = useState<ActionPreviewDiff | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState<boolean>(false);

  // Verification Inspection Modal State
  const [verificationModalOpen, setVerificationModalOpen] = useState<boolean>(false);
  const [verificationData, setVerificationData] = useState<Record<string, any> | null>(null);

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

  // Fetch plans
  const fetchPlans = useCallback(async () => {
    if (!project) return;
    setIsPlansLoading(true);
    try {
      const data = await getSEOActionPlans({ project_id: project.id });
      setPlans(data);
      if (data.length > 0) {
        if (!selectedPlanId || !data.some((p) => p.id === selectedPlanId)) {
          setSelectedPlanId(data[0].id);
        }
      } else {
        setSelectedPlanId(null);
      }
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to fetch SEO Action Plans.', 'error');
    } finally {
      setIsPlansLoading(false);
    }
  }, [project, selectedPlanId, showFeedback]);

  const fetchHistoricalSignals = useCallback(async () => {
    if (!project) return;
    try {
      const signals = await getHistoricalOutcomeSignals(project.id);
      setHistoricalSignals(signals);
    } catch (err) {
      console.warn('Historical signals fetch skipped', err);
    }
  }, [project]);

  const fetchAdaptiveStrategy = useCallback(async () => {
    if (!project) return;
    try {
      const strat = await getAdaptiveSEOStrategy(project.id);
      setAdaptiveStrategy(strat);
    } catch (err) {
      console.warn('Adaptive strategy fetch skipped', err);
    }
  }, [project]);


  useEffect(() => {
    fetchActions();
    fetchPlans();
    fetchHistoricalSignals();
    fetchAdaptiveStrategy();
  }, [fetchActions, fetchPlans, fetchHistoricalSignals, fetchAdaptiveStrategy]);



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

  // Generate Action Plan handler
  const handleTriggerPlanGeneration = async () => {
    if (!project) return;
    setIsGenerating(true);
    try {
      const newPlan = await generateSEOActionPlan({
        project_id: project.id,
        title: planTitleInput.trim() || undefined,
        max_actions: planMaxActions
      });
      showFeedback(`SEO Action Plan "${newPlan.title}" created with ${newPlan.total_actions_count || newPlan.actions?.length || 0} actions!`, 'success');
      setPlanModalOpen(false);
      setPlanTitleInput('');
      await fetchPlans();
      await fetchActions();
      setSelectedPlanId(newPlan.id);
      setViewMode('plans');
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to generate Action Plan.', 'error');
    } finally {
      setIsGenerating(false);
    }
  };

  // Plan Actions: Approve, Reject, Execute, Verify
  const handleApprovePlan = async (id: number) => {
    setIsUpdating(true);
    try {
      const updated = await approveSEOActionPlan(id);
      setPlans((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      await fetchActions();
      showFeedback('SEO Action Plan approved! Ready for execution.', 'success');
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to approve plan.', 'error');
    } finally {
      setIsUpdating(false);
    }
  };

  const handleOpenPlanRejectModal = (id: number) => {
    setPlanRejectTargetId(id);
    setPlanRejectReason('');
    setPlanRejectModalOpen(true);
  };

  const handleConfirmPlanReject = async () => {
    if (!planRejectTargetId) return;
    if (!planRejectReason.trim()) {
      showFeedback('Please provide a reason for rejecting the action plan.', 'error');
      return;
    }
    setIsUpdating(true);
    try {
      const updated = await rejectSEOActionPlan(planRejectTargetId, planRejectReason.trim());
      setPlans((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      await fetchActions();
      showFeedback('Action Plan rejected.', 'info');
      setPlanRejectModalOpen(false);
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to reject plan.', 'error');
    } finally {
      setIsUpdating(false);
    }
  };

  const handleExecutePlan = async (id: number) => {
    setIsExecuting(true);
    try {
      const executed = await executeSEOActionPlan(id);
      setPlans((prev) => prev.map((p) => (p.id === executed.id ? executed : p)));
      await fetchActions();
      showFeedback(`Action Plan #${id} executed safely! Verification in progress...`, 'success');
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to execute action plan.', 'error');
    } finally {
      setIsExecuting(false);
    }
  };

  const handleVerifyPlan = async (id: number) => {
    setIsVerifying(true);
    try {
      const res = await verifySEOActionPlan(id);
      setPlans((prev) => prev.map((p) => (p.id === res.plan.id ? res.plan : p)));
      await fetchActions();
      setVerificationData(res.verification_summary);
      setVerificationModalOpen(true);
      showFeedback(`Action Plan verified: ${res.plan.verification_status.toUpperCase()}`, 'success');
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to verify action plan.', 'error');
    } finally {
      setIsVerifying(false);
    }
  };

  const handleDeletePlan = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this Action Plan?')) return;
    try {
      await deleteSEOActionPlan(id);
      setPlans((prev) => prev.filter((p) => p.id !== id));
      if (selectedPlanId === id) {
        const remaining = plans.filter((p) => p.id !== id);
        setSelectedPlanId(remaining.length > 0 ? remaining[0].id : null);
      }
      showFeedback('Action Plan deleted.', 'info');
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to delete plan.', 'error');
    }
  };

  // Status transitions for individual actions
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

  const handleVerifyAction = async (id: number) => {
    setIsVerifying(true);
    try {
      const res = await verifySEOAction(id);
      setActions((prev) => prev.map((a) => (a.id === res.action.id ? res.action : a)));
      setVerificationData(res.verification);
      setVerificationModalOpen(true);
      showFeedback(`Action verified: ${res.action.verification_status?.toUpperCase() || 'COMPLETED'}`, 'success');
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to verify action.', 'error');
    } finally {
      setIsVerifying(false);
    }
  };

  const handleMeasureActionOutcome = async (id: number) => {
    setIsMeasuring(true);
    try {
      const res = await measureSEOActionOutcome(id, 14);
      setActions((prev) => prev.map((a) => (a.id === res.action.id ? res.action : a)));
      setActiveTab('outcome');
      showFeedback(`SEO Outcome Measured: ${res.action.seo_outcome_display || res.action.seo_outcome?.toUpperCase() || 'MEASURED'}`, 'success');
      if (project) {
        fetchHistoricalSignals();
      }
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to measure action outcome.', 'error');
    } finally {
      setIsMeasuring(false);
    }
  };

  const handleMeasurePlanOutcome = async (id: number) => {
    setIsMeasuring(true);
    try {
      const res = await measureSEOActionPlanOutcome(id, 14);
      setPlans((prev) => prev.map((p) => (p.id === res.plan.id ? res.plan : p)));
      await fetchActions();
      showFeedback(`Plan Outcome Measured: ${res.plan.seo_outcome_display || res.plan.seo_outcome?.toUpperCase() || 'MEASURED'}`, 'success');
      if (project) {
        fetchHistoricalSignals();
      }
    } catch (err: any) {
      showFeedback(err?.data?.detail || 'Failed to measure plan outcome.', 'error');
    } finally {
      setIsMeasuring(false);
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

  // Badges & Pill Helpers
  const renderStatusBadge = (status: ActionStatus | ActionPlanStatus) => {
    const configs: Record<string, { bg: string; color: string; label: string; icon: string }> = {
      proposed: { bg: '#eff6ff', color: '#1d4ed8', label: 'Proposed', icon: '💡' },
      pending_approval: { bg: '#fffbeb', color: '#b45309', label: 'Pending Approval', icon: '⏳' },
      awaiting_approval: { bg: '#fffbeb', color: '#b45309', label: 'Awaiting Approval', icon: '⏳' },
      reviewed: { bg: '#fef3c7', color: '#b45309', label: 'Reviewed', icon: '🔍' },
      approved: { bg: '#dcfce7', color: '#15803d', label: 'Approved', icon: '✅' },
      ready_to_execute: { bg: '#e0e7ff', color: '#4338ca', label: 'Ready', icon: '🚀' },
      executing: { bg: '#fef9c3', color: '#854d0e', label: 'Executing...', icon: '⚙️' },
      completed: { bg: '#ecfdf5', color: '#047857', label: 'Completed', icon: '✨' },
      partially_completed: { bg: '#fef3c7', color: '#b45309', label: 'Partial', icon: '⚡' },
      rejected: { bg: '#fee2e2', color: '#b91c1c', label: 'Rejected', icon: '❌' },
      failed: { bg: '#fef2f2', color: '#991b1b', label: 'Failed', icon: '⚠️' },
      cancelled: { bg: '#f1f5f9', color: '#64748b', label: 'Cancelled', icon: '🚫' },
      draft: { bg: '#f1f5f9', color: '#475569', label: 'Draft', icon: '📝' },
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

  const renderVerificationBadge = (verifStatus?: VerificationStatus | string) => {
    const s = (verifStatus || 'pending').toLowerCase();
    const configs: Record<string, { bg: string; color: string; label: string; icon: string }> = {
      verified: { bg: '#ecfdf5', color: '#047857', label: 'Verified Live', icon: '🎯' },
      verifying: { bg: '#eff6ff', color: '#1d4ed8', label: 'Verifying...', icon: '🔄' },
      failed: { bg: '#fee2e2', color: '#b91c1c', label: 'Verification Mismatch', icon: '⚠️' },
      partially_verified: { bg: '#fef3c7', color: '#b45309', label: 'Partially Verified', icon: '🟡' },
      pending: { bg: '#f1f5f9', color: '#64748b', label: 'Pending Verification', icon: '⏱️' }
    };
    const c = configs[s] || configs.pending;
    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          padding: '3px 8px',
          borderRadius: '6px',
          fontSize: '11px',
          fontWeight: 700,
          backgroundColor: c.bg,
          color: c.color,
          border: `1px solid ${c.color}30`
        }}
      >
        <span>{c.icon}</span>
        <span>{c.label}</span>
      </span>
    );
  };

  const renderOutcomeBadge = (outcome?: SEOOutcome | PlanSEOOutcome | string, label?: string) => {
    const o = (outcome || 'unknown').toLowerCase();
    const configs: Record<string, { bg: string; color: string; icon: string; text: string }> = {
      improved: { bg: '#ecfdf5', color: '#047857', icon: '📈', text: 'IMPROVED' },
      effective: { bg: '#ecfdf5', color: '#047857', icon: '🏆', text: 'EFFECTIVE' },
      partially_effective: { bg: '#eff6ff', color: '#1d4ed8', icon: '✨', text: 'PARTIAL LIFT' },
      no_change: { bg: '#f8fafc', color: '#64748b', icon: '➖', text: 'NO CHANGE' },
      ineffective: { bg: '#fef3c7', color: '#b45309', icon: '⚠️', text: 'INEFFECTIVE' },
      declined: { bg: '#fef2f2', color: '#b91c1c', icon: '📉', text: 'DECLINED' },
      insufficient_data: { bg: '#faf5ff', color: '#7e22ce', icon: '⏳', text: 'LOW DATA' },
      unknown: { bg: '#f1f5f9', color: '#94a3b8', icon: '❓', text: 'UNMEASURED' },
    };
    const c = configs[o] || configs.unknown;
    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          padding: '2px 8px',
          borderRadius: '6px',
          fontSize: '11px',
          fontWeight: 700,
          backgroundColor: c.bg,
          color: c.color,
          border: `1px solid ${c.color}30`,
          textTransform: 'uppercase',
          letterSpacing: '0.03em'
        }}
      >
        <span>{c.icon}</span>
        <span>{label || c.text}</span>
      </span>
    );
  };

  const renderRiskBadge = (risk: ActionRiskLevel | string) => {

    const r = (risk || 'low').toLowerCase();
    const configs: Record<string, { bg: string; color: string; label: string }> = {
      critical: { bg: '#7f1d1d', color: '#fee2e2', label: 'CRITICAL RISK' },
      high: { bg: '#fee2e2', color: '#dc2626', label: 'HIGH RISK' },
      medium: { bg: '#fef3c7', color: '#d97706', label: 'MEDIUM RISK' },
      low: { bg: '#f0fdf4', color: '#16a34a', label: 'LOW RISK' },
    };
    const c = configs[r] || configs.low;
    return (
      <span
        style={{
          display: 'inline-block',
          padding: '2px 8px',
          borderRadius: '6px',
          fontSize: '10px',
          fontWeight: 800,
          backgroundColor: c.bg,
          color: c.color,
          textTransform: 'uppercase',
          letterSpacing: '0.05em'
        }}
      >
        {c.label}
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

  const activePlan = useMemo(() => {
    return plans.find((p) => p.id === selectedPlanId) || null;
  }, [plans, selectedPlanId]);

  if (!project) {
    return (
      <div style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
        Please select or create a project to view SEO Actions & Plans.
      </div>
    );
  }

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
      {/* Top Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '24px' }}>🛡️</span>
            <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 800, color: '#0f172a' }}>
              Autonomous SEO Action Planning & Verification
            </h2>
          </div>
          <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#64748b' }}>
            Convert multi-source SEO intelligence into structured action plans, enforce human governance, execute mutations, and verify real-world website outcomes.
          </p>
        </div>

        {/* Top View Mode Switcher & Planning CTA */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {statusCounts && (
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              <div style={counterChipStyle}>
                <span style={{ fontSize: '10px', color: '#64748b' }}>Pending</span>
                <strong style={{ color: '#b45309', fontSize: '12px' }}>{statusCounts.pending_approval || statusCounts.proposed}</strong>
              </div>
              <div style={counterChipStyle}>
                <span style={{ fontSize: '10px', color: '#64748b' }}>Approved</span>
                <strong style={{ color: '#15803d', fontSize: '12px' }}>{statusCounts.approved}</strong>
              </div>
              <div style={counterChipStyle}>
                <span style={{ fontSize: '10px', color: '#64748b' }}>Completed</span>
                <strong style={{ color: '#047857', fontSize: '12px' }}>{statusCounts.completed}</strong>
              </div>
            </div>
          )}

          <div style={{ display: 'flex', backgroundColor: '#f1f5f9', borderRadius: '8px', padding: '3px' }}>
            <button
              id="view-mode-plans-btn"
              onClick={() => setViewMode('plans')}
              style={{
                padding: '6px 14px',
                borderRadius: '6px',
                fontSize: '12px',
                fontWeight: 700,
                border: 'none',
                cursor: 'pointer',
                backgroundColor: viewMode === 'plans' ? '#ffffff' : 'transparent',
                color: viewMode === 'plans' ? '#0f172a' : '#64748b',
                boxShadow: viewMode === 'plans' ? '0 1px 2px rgba(0,0,0,0.05)' : 'none',
              }}
            >
              ⚡ Action Plans ({plans.length})
            </button>
            <button
              id="view-mode-actions-btn"
              onClick={() => setViewMode('actions')}
              style={{
                padding: '6px 14px',
                borderRadius: '6px',
                fontSize: '12px',
                fontWeight: 700,
                border: 'none',
                cursor: 'pointer',
                backgroundColor: viewMode === 'actions' ? '#ffffff' : 'transparent',
                color: viewMode === 'actions' ? '#0f172a' : '#64748b',
                boxShadow: viewMode === 'actions' ? '0 1px 2px rgba(0,0,0,0.05)' : 'none',
              }}
            >
              📋 Atomic Actions ({actions.length})
            </button>
          </div>

          <button
            id="plan-actions-modal-btn"
            onClick={() => setPlanModalOpen(true)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: '#4338ca',
              color: '#ffffff',
              border: 'none',
              padding: '8px 14px',
              borderRadius: '8px',
              fontSize: '12px',
              fontWeight: 700,
              cursor: 'pointer',
              transition: 'background-color 0.2s',
            }}
          >
            <span>✨</span>
            <span>Plan SEO Actions</span>
          </button>
        </div>
      </div>

      {/* Adaptive SEO Strategy & Historical Learning Section */}
      {adaptiveStrategy && (
        <div
          id="adaptive-seo-strategy-banner"
          style={{
            padding: '16px 20px',
            borderRadius: '12px',
            backgroundColor: '#f8fafc',
            border: '1px solid #e2e8f0',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '18px' }}>🧠</span>
              <strong style={{ fontSize: '14px', color: '#0f172a' }}>Adaptive SEO Strategy</strong>
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: 700,
                  padding: '2px 8px',
                  borderRadius: '12px',
                  backgroundColor:
                    adaptiveStrategy.strategy_confidence === 'high' ? '#dcfce7' :
                    adaptiveStrategy.strategy_confidence === 'medium' ? '#dbeafe' :
                    adaptiveStrategy.strategy_confidence === 'low' ? '#fef3c7' : '#f1f5f9',
                  color:
                    adaptiveStrategy.strategy_confidence === 'high' ? '#15803d' :
                    adaptiveStrategy.strategy_confidence === 'medium' ? '#1d4ed8' :
                    adaptiveStrategy.strategy_confidence === 'low' ? '#b45309' : '#64748b',
                }}
              >
                {adaptiveStrategy.strategy_confidence === 'none' ? 'INSUFFICIENT DATA' : `${adaptiveStrategy.strategy_confidence.toUpperCase()} CONFIDENCE`}
              </span>
              <span style={{ fontSize: '12px', color: '#64748b' }}>
                ({adaptiveStrategy.historical_sample_size} Measured, {adaptiveStrategy.evaluatable_sample_size} Evaluatable)
              </span>
            </div>

            <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
              <div style={{ fontSize: '12px', color: '#334155' }}>
                Smoothed Win Rate: <strong style={{ color: '#0f172a' }}>{Math.round(adaptiveStrategy.overall_smoothed_rate * 100)}%</strong>
                <span style={{ fontSize: '11px', color: '#64748b', marginLeft: '4px' }}>
                  (Raw: {Math.round(adaptiveStrategy.overall_success_rate * 100)}%)
                </span>
              </div>
            </div>
          </div>

          <p style={{ margin: 0, fontSize: '12px', color: '#475569', lineHeight: '1.4' }}>
            {adaptiveStrategy.reason}
          </p>

          <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', paddingTop: '8px', borderTop: '1px solid #e2e8f0' }}>
            {/* Preferred Actions */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '11px', fontWeight: 700, color: '#15803d' }}>Historically Effective:</span>
              {adaptiveStrategy.preferred_actions.length > 0 ? (
                adaptiveStrategy.preferred_actions.map((actType) => {
                  const pInfo = adaptiveStrategy.action_prioritizations[actType];
                  return (
                    <span
                      key={actType}
                      style={{
                        backgroundColor: '#dcfce7',
                        color: '#166534',
                        padding: '2px 8px',
                        borderRadius: '6px',
                        fontSize: '11px',
                        fontWeight: 600,
                        border: '1px solid #bbf7d0',
                      }}
                    >
                      {actType} {pInfo ? `(+${Math.round(pInfo.historical_adjustment * 100)}%)` : ''}
                    </span>
                  );
                })
              ) : (
                <span style={{ fontSize: '11px', color: '#94a3b8' }}>None classified yet</span>
              )}
            </div>

            {/* Deprioritized Actions */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '11px', fontWeight: 700, color: '#b91c1c' }}>Historically Weak:</span>
              {adaptiveStrategy.deprioritized_actions.length > 0 ? (
                adaptiveStrategy.deprioritized_actions.map((actType) => {
                  const pInfo = adaptiveStrategy.action_prioritizations[actType];
                  return (
                    <span
                      key={actType}
                      style={{
                        backgroundColor: '#fee2e2',
                        color: '#991b1b',
                        padding: '2px 8px',
                        borderRadius: '6px',
                        fontSize: '11px',
                        fontWeight: 600,
                        border: '1px solid #fecaca',
                      }}
                    >
                      {actType} {pInfo ? `(${Math.round(pInfo.historical_adjustment * 100)}%)` : ''}
                    </span>
                  );
                })
              ) : (
                <span style={{ fontSize: '11px', color: '#94a3b8' }}>None suppressed</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Historical Outcome Learning Signals Banner */}
      {historicalSignals && historicalSignals.total_measured > 0 && (
        <div
          id="historical-learning-signals-banner"
          style={{
            padding: '16px 20px',
            borderRadius: '12px',
            backgroundColor: '#f0fdf4',
            border: '1px solid #bbf7d0',
            display: 'flex',
            flexDirection: 'column',
            gap: '10px'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '18px' }}>📊</span>
              <strong style={{ fontSize: '14px', color: '#166534' }}>Empirical Outcome Measurements</strong>
              <span style={{ fontSize: '12px', color: '#15803d' }}>
                ({historicalSignals.total_measured} Actions Measured)
              </span>
            </div>
            <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
              <div style={{ fontSize: '12px', color: '#166534' }}>
                Overall Improvement Rate: <strong style={{ fontSize: '14px', color: '#15803d' }}>{Math.round(historicalSignals.success_rate * 100)}%</strong>
              </div>
              <span style={{ color: '#86efac' }}>|</span>
              <div style={{ display: 'flex', gap: '8px', fontSize: '11px' }}>
                <span style={{ color: '#16a34a', fontWeight: 700 }}>📈 {historicalSignals.improved} Improved</span>
                <span style={{ color: '#64748b', fontWeight: 700 }}>➖ {historicalSignals.no_change} Neutral</span>
                <span style={{ color: '#dc2626', fontWeight: 700 }}>📉 {historicalSignals.declined} Declined</span>
              </div>
            </div>
          </div>

          {/* Action Types Breakdown */}
          {Object.keys(historicalSignals.by_action_type || {}).length > 0 && (
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', paddingTop: '6px', borderTop: '1px solid #dcfce7' }}>
              {Object.entries(historicalSignals.by_action_type).slice(0, 6).map(([typeKey, stats]) => (
                <div
                  key={typeKey}
                  style={{
                    backgroundColor: '#ffffff',
                    padding: '4px 10px',
                    borderRadius: '6px',
                    fontSize: '11px',
                    border: '1px solid #dcfce7',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px'
                  }}
                >
                  <code style={{ color: '#1e293b', fontWeight: 600 }}>{typeKey}</code>
                  <span style={{ color: '#15803d', fontWeight: 800 }}>{Math.round(stats.success_rate * 100)}% win</span>
                  <span style={{ color: '#94a3b8', fontSize: '10px' }}>({stats.total_measured}x)</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}


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

      {/* Loading Indicators */}
      {(isGenerating || isExecuting || isVerifying || isUpdating) && (
        <div
          id="action-processing-toast"
          style={{
            padding: '10px 16px',
            borderRadius: '8px',
            fontSize: '12px',
            fontWeight: 600,
            backgroundColor: '#eff6ff',
            color: '#1e40af',
            border: '1px solid #bfdbfe',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          <span>🔄</span>
          <span>
            {isGenerating && 'Synthesizing evidence & generating action plan...'}
            {isExecuting && 'Executing approved mutations safely in staging environment...'}
            {isVerifying && 'Probing live website HTML & verifying real-world SEO state...'}
            {isUpdating && 'Updating server state...'}
          </span>
        </div>
      )}

      {/* ========================================================================= */}
      {/* VIEW MODE 1: ACTION PLANS */}
      {/* ========================================================================= */}
      {viewMode === 'plans' && (
        <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: '20px', minHeight: '520px' }}>
          {/* Left: Plans List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', borderRight: '1px solid #f1f5f9', paddingRight: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '13px', fontWeight: 700, color: '#334155' }}>Structured Action Plans</span>
              <span style={{ fontSize: '11px', color: '#64748b' }}>{plans.length} available</span>
            </div>

            {isPlansLoading && plans.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: '#94a3b8', fontSize: '13px' }}>Loading plans...</div>
            ) : plans.length === 0 ? (
              <div style={{ padding: '32px 16px', textAlign: 'center', backgroundColor: '#f8fafc', borderRadius: '12px', border: '1px dashed #cbd5e1' }}>
                <span style={{ fontSize: '28px' }}>💡</span>
                <p style={{ margin: '8px 0 4px 0', fontSize: '13px', fontWeight: 700, color: '#1e293b' }}>No Action Plans Yet</p>
                <p style={{ margin: 0, fontSize: '12px', color: '#64748b' }}>Click "Plan SEO Actions" to synthesize audit and GSC opportunities.</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', overflowY: 'auto', maxHeight: '580px' }}>
                {plans.map((p) => {
                  const isSelected = p.id === selectedPlanId;
                  return (
                    <div
                      key={p.id}
                      onClick={() => setSelectedPlanId(p.id)}
                      style={{
                        padding: '14px',
                        borderRadius: '12px',
                        border: isSelected ? '2px solid #4338ca' : '1px solid #e2e8f0',
                        backgroundColor: isSelected ? '#f5f3ff' : '#ffffff',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '6px' }}>
                        <span style={{ fontSize: '12px', fontWeight: 800, color: '#4338ca' }}>Plan #{p.id}</span>
                        {renderStatusBadge(p.status)}
                      </div>
                      <h4 style={{ margin: '0 0 6px 0', fontSize: '13px', fontWeight: 700, color: '#0f172a', lineHeight: '1.4' }}>
                        {p.title}
                      </h4>
                      <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap', marginBottom: '8px' }}>
                        {renderRiskBadge(p.risk_level)}
                        {renderVerificationBadge(p.verification_status)}
                        {renderOutcomeBadge(p.seo_outcome, p.seo_outcome_display)}
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#64748b' }}>
                        <span>⚡ {p.total_actions_count || p.actions?.length || 0} actions</span>
                        <span>Confidence: {Math.round(p.confidence_score * 100)}%</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Right: Plan Detail View */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {activePlan ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {/* Plan Header Card */}
                <div style={{ backgroundColor: '#f8fafc', padding: '18px', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                        <span style={{ fontSize: '14px', fontWeight: 800, color: '#4338ca' }}>PLAN #{activePlan.id}</span>
                        {renderStatusBadge(activePlan.status)}
                        {renderRiskBadge(activePlan.risk_level)}
                        {renderVerificationBadge(activePlan.verification_status)}
                        {renderOutcomeBadge(activePlan.seo_outcome, activePlan.seo_outcome_display)}
                      </div>
                      <h3 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 800, color: '#0f172a' }}>
                        {activePlan.title}
                      </h3>
                      <p style={{ margin: 0, fontSize: '13px', color: '#475569', lineHeight: '1.5' }}>
                        {activePlan.summary}
                      </p>
                    </div>

                    {/* Governance & Control Action Buttons */}
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                      {activePlan.status === 'proposed' && (
                        <>
                          <button
                            id="plan-approve-btn"
                            onClick={() => handleApprovePlan(activePlan.id)}
                            disabled={isUpdating}
                            style={btnSuccessStyle}
                          >
                            ✅ Approve Plan
                          </button>
                          <button
                            id="plan-reject-btn"
                            onClick={() => handleOpenPlanRejectModal(activePlan.id)}
                            disabled={isUpdating}
                            style={btnDangerStyle}
                          >
                            ❌ Reject
                          </button>
                        </>
                      )}

                      {activePlan.status === 'approved' && (
                        <button
                          id="plan-execute-btn"
                          onClick={() => handleExecutePlan(activePlan.id)}
                          disabled={isExecuting}
                          style={btnPrimaryStyle}
                        >
                          🚀 Execute Plan
                        </button>
                      )}

                      {(activePlan.status === 'completed' || activePlan.status === 'partially_completed' || activePlan.status === 'approved') && (
                        <button
                          id="plan-verify-btn"
                          onClick={() => handleVerifyPlan(activePlan.id)}
                          disabled={isVerifying}
                          style={btnVerifyStyle}
                        >
                          🎯 Verify Live State
                        </button>
                      )}

                      {(activePlan.status === 'completed' || activePlan.status === 'partially_completed') && (
                        <button
                          id="plan-measure-outcome-btn"
                          onClick={() => handleMeasurePlanOutcome(activePlan.id)}
                          disabled={isMeasuring}
                          style={btnOutcomeStyle}
                        >
                          📈 {isMeasuring ? 'Measuring...' : 'Measure SEO Outcome'}
                        </button>
                      )}

                      <button
                        onClick={() => handleDeletePlan(activePlan.id)}
                        style={btnGhostDangerStyle}
                        title="Delete Plan"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                </div>

                {/* Plan Outcome Scorecard (if measured) */}
                {activePlan.outcome_summary && (
                  <div
                    id="plan-outcome-scorecard"
                    style={{
                      padding: '16px',
                      borderRadius: '12px',
                      backgroundColor: '#ecfdf5',
                      border: '1px solid #a7f3d0',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '10px'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '18px' }}>📊</span>
                        <strong style={{ fontSize: '14px', color: '#065f46' }}>Aggregate SEO Outcome Scorecard</strong>
                        {renderOutcomeBadge(activePlan.seo_outcome, activePlan.seo_outcome_display)}
                      </div>
                      <span style={{ fontSize: '11px', color: '#047857' }}>
                        Effectiveness Rate: <strong>{Math.round((activePlan.outcome_summary.effectiveness_rate || 0) * 100)}%</strong>
                      </span>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px' }}>
                      <div style={{ backgroundColor: '#ffffff', padding: '10px', borderRadius: '8px', border: '1px solid #d1fae5', textAlign: 'center' }}>
                        <span style={{ fontSize: '10px', color: '#64748b' }}>Total Actions</span>
                        <div style={{ fontSize: '16px', fontWeight: 800, color: '#0f172a' }}>{activePlan.outcome_summary.total_actions || 0}</div>
                      </div>
                      <div style={{ backgroundColor: '#ffffff', padding: '10px', borderRadius: '8px', border: '1px solid #d1fae5', textAlign: 'center' }}>
                        <span style={{ fontSize: '10px', color: '#64748b' }}>Improved</span>
                        <div style={{ fontSize: '16px', fontWeight: 800, color: '#047857' }}>{activePlan.outcome_summary.improved || 0}</div>
                      </div>
                      <div style={{ backgroundColor: '#ffffff', padding: '10px', borderRadius: '8px', border: '1px solid #d1fae5', textAlign: 'center' }}>
                        <span style={{ fontSize: '10px', color: '#64748b' }}>No Change</span>
                        <div style={{ fontSize: '16px', fontWeight: 800, color: '#475569' }}>{activePlan.outcome_summary.no_change || 0}</div>
                      </div>
                      <div style={{ backgroundColor: '#ffffff', padding: '10px', borderRadius: '8px', border: '1px solid #d1fae5', textAlign: 'center' }}>
                        <span style={{ fontSize: '10px', color: '#64748b' }}>Declined</span>
                        <div style={{ fontSize: '16px', fontWeight: 800, color: '#dc2626' }}>{activePlan.outcome_summary.declined || 0}</div>
                      </div>
                    </div>
                  </div>
                )}


                {/* Child Actions in this Plan */}
                <div>
                  <h4 style={{ margin: '0 0 10px 0', fontSize: '14px', fontWeight: 700, color: '#1e293b' }}>
                    Planned Actions ({activePlan.actions?.length || 0})
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {activePlan.actions?.map((act) => (
                      <div
                        key={act.id}
                        style={{
                          padding: '14px',
                          borderRadius: '10px',
                          border: '1px solid #e2e8f0',
                          backgroundColor: '#ffffff',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          gap: '12px',
                        }}
                      >
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontSize: '12px', fontWeight: 800, color: '#334155' }}>#{act.id}</span>
                            <strong style={{ fontSize: '13px', color: '#0f172a' }}>{act.title}</strong>
                            {renderStatusBadge(act.status)}
                            {renderRiskBadge(act.risk_level)}
                            {renderVerificationBadge(act.verification_status)}
                          </div>
                          <div style={{ fontSize: '12px', color: '#64748b' }}>
                            <span>Target: <code>{act.target_url || project.website_url}</code></span>
                          </div>
                          <p style={{ margin: 0, fontSize: '12px', color: '#475569' }}>
                            {act.description}
                          </p>
                        </div>

                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button
                            onClick={() => {
                              setSelectedActionId(act.id);
                              setViewMode('actions');
                            }}
                            style={{
                              padding: '5px 10px',
                              borderRadius: '6px',
                              fontSize: '11px',
                              fontWeight: 700,
                              backgroundColor: '#f1f5f9',
                              color: '#334155',
                              border: '1px solid #cbd5e1',
                              cursor: 'pointer'
                            }}
                          >
                            Inspect Detail →
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ padding: '48px', textAlign: 'center', color: '#94a3b8' }}>
                Select an action plan from the left list to review opportunities, governance state, and verification.
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* VIEW MODE 2: ATOMIC ACTIONS */}
      {/* ========================================================================= */}
      {viewMode === 'actions' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
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
                <option value="all">All Action Types</option>
                <option value="optimize_title">Optimize Title</option>
                <option value="optimize_meta_description">Optimize Meta Description</option>
                <option value="fix_missing_h1">Fix Missing H1</option>
                <option value="fix_canonical">Fix Canonical</option>
                <option value="fix_image_alt">Fix Image Alt</option>
                <option value="fix_broken_internal_link">Fix Broken Internal Link</option>
                <option value="remove_redirect_chain">Remove Redirect Chain</option>
                <option value="add_structured_data">Add Structured Data</option>
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
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: '20px', minHeight: '500px' }}>
            {/* Action List */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', borderRight: '1px solid #f1f5f9', paddingRight: '16px' }}>
              {isLoading && actions.length === 0 ? (
                <div style={{ padding: '24px', textAlign: 'center', color: '#94a3b8' }}>Loading actions...</div>
              ) : actions.length === 0 ? (
                <div style={{ padding: '24px', textAlign: 'center', color: '#94a3b8' }}>No SEO actions matching filter.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', overflowY: 'auto', maxHeight: '560px' }}>
                  {actions.map((act) => {
                    const isSelected = act.id === selectedActionId;
                    return (
                      <div
                        key={act.id}
                        onClick={() => setSelectedActionId(act.id)}
                        style={{
                          padding: '12px',
                          borderRadius: '10px',
                          border: isSelected ? '2px solid #3b82f6' : '1px solid #e2e8f0',
                          backgroundColor: isSelected ? '#eff6ff' : '#ffffff',
                          cursor: 'pointer',
                          transition: 'all 0.15s ease',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '4px' }}>
                          <span style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>#{act.id}</span>
                          {renderStatusBadge(act.status)}
                        </div>
                        <h4 style={{ margin: '0 0 4px 0', fontSize: '13px', fontWeight: 700, color: '#0f172a' }}>{act.title}</h4>
                        <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
                          {renderRiskBadge(act.risk_level)}
                          {renderPriorityBadge(act.priority)}
                          {renderVerificationBadge(act.verification_status)}
                          {renderOutcomeBadge(act.seo_outcome, act.seo_outcome_display)}
                          {act.strategy_reasoning && (
                            <span
                              title={act.strategy_reasoning.reasoning}
                              style={{
                                fontSize: '10px',
                                padding: '2px 6px',
                                borderRadius: '4px',
                                fontWeight: 700,
                                backgroundColor: act.strategy_reasoning.learning_signal === 'positive' ? '#dcfce7' : act.strategy_reasoning.learning_signal === 'negative' ? '#fee2e2' : '#f1f5f9',
                                color: act.strategy_reasoning.learning_signal === 'positive' ? '#166534' : act.strategy_reasoning.learning_signal === 'negative' ? '#991b1b' : '#475569',
                                border: `1px solid ${act.strategy_reasoning.learning_signal === 'positive' ? '#bbf7d0' : act.strategy_reasoning.learning_signal === 'negative' ? '#fecaca' : '#e2e8f0'}`,
                              }}
                            >
                              🧠 {act.strategy_reasoning.learning_signal === 'positive' ? 'Boosted' : act.strategy_reasoning.learning_signal === 'negative' ? 'Deprioritized' : 'Adaptive'} ({act.strategy_reasoning.historical_adjustment > 0 ? '+' : ''}{(act.strategy_reasoning.historical_adjustment * 100).toFixed(0)}%)
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Action Detail */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {activeAction ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {/* Action Header Card */}
                  <div style={{ backgroundColor: '#f8fafc', padding: '16px', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                          <span style={{ fontSize: '12px', fontWeight: 800, color: '#3b82f6' }}>ACTION #{activeAction.id}</span>
                          {renderStatusBadge(activeAction.status)}
                          {renderRiskBadge(activeAction.risk_level)}
                          {renderVerificationBadge(activeAction.verification_status)}
                          {renderOutcomeBadge(activeAction.seo_outcome, activeAction.seo_outcome_display)}
                        </div>
                        <h3 style={{ margin: '0 0 6px 0', fontSize: '16px', fontWeight: 800, color: '#0f172a' }}>
                          {activeAction.title}
                        </h3>
                        <p style={{ margin: 0, fontSize: '13px', color: '#475569' }}>
                          Target: <code>{activeAction.target_url || project.website_url}</code>
                        </p>
                      </div>

                      {/* Action Controls */}
                      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                        <button onClick={() => handlePreviewAction(activeAction.id)} disabled={isPreviewLoading} style={btnSecondaryStyle}>
                          {isPreviewLoading ? 'Loading Preview...' : '🔍 Preview Diff'}
                        </button>

                        {activeAction.status === 'proposed' && (
                          <button onClick={() => handleReviewAction(activeAction.id)} style={btnSecondaryStyle}>
                            🔍 Mark Reviewed
                          </button>
                        )}

                        {(activeAction.status === 'proposed' || activeAction.status === 'pending_approval' || activeAction.status === 'reviewed') && (
                          <>
                            <button onClick={() => handleApproveAction(activeAction.id)} style={btnSuccessStyle}>
                              ✅ Approve
                            </button>
                            <button onClick={() => handleOpenRejectModal(activeAction.id)} style={btnDangerStyle}>
                              ❌ Reject
                            </button>
                          </>
                        )}

                        {activeAction.status === 'approved' && (
                          <button onClick={() => handleExecuteAction(activeAction.id)} style={btnPrimaryStyle}>
                            🚀 Execute
                          </button>
                        )}

                        {(activeAction.status === 'completed' || activeAction.status === 'approved') && (
                          <button onClick={() => handleVerifyAction(activeAction.id)} style={btnVerifyStyle}>
                            🎯 Verify Live State
                          </button>
                        )}

                        {activeAction.status === 'completed' && (
                          <button
                            id="action-measure-outcome-btn"
                            onClick={() => handleMeasureActionOutcome(activeAction.id)}
                            disabled={isMeasuring}
                            style={btnOutcomeStyle}
                          >
                            📈 {isMeasuring ? 'Measuring...' : 'Measure SEO Outcome'}
                          </button>
                        )}

                        {activeAction.status !== 'cancelled' && activeAction.status !== 'completed' && activeAction.status !== 'rejected' && (
                          <button onClick={() => handleCancelAction(activeAction.id)} style={btnSecondaryStyle}>
                            🚫 Cancel
                          </button>
                        )}

                        <button onClick={() => handleDeleteAction(activeAction.id)} style={btnGhostDangerStyle}>
                          🗑️
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Adaptive Planning Prioritization Card */}
                  {activeAction.strategy_reasoning && (
                    <div
                      id="action-strategy-reasoning-card"
                      style={{
                        padding: '14px 16px',
                        borderRadius: '10px',
                        backgroundColor: activeAction.strategy_reasoning.learning_signal === 'positive' ? '#f0fdf4' : activeAction.strategy_reasoning.learning_signal === 'negative' ? '#fef2f2' : '#f8fafc',
                        border: `1px solid ${activeAction.strategy_reasoning.learning_signal === 'positive' ? '#bbf7d0' : activeAction.strategy_reasoning.learning_signal === 'negative' ? '#fecaca' : '#e2e8f0'}`,
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '8px'
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span style={{ fontSize: '15px' }}>🧠</span>
                          <strong style={{ fontSize: '13px', color: '#1e293b' }}>Adaptive Planning Prioritization</strong>
                          <span
                            style={{
                              fontSize: '11px',
                              padding: '2px 8px',
                              borderRadius: '12px',
                              fontWeight: 700,
                              backgroundColor: activeAction.strategy_reasoning.learning_signal === 'positive' ? '#dcfce7' : activeAction.strategy_reasoning.learning_signal === 'negative' ? '#fee2e2' : '#e2e8f0',
                              color: activeAction.strategy_reasoning.learning_signal === 'positive' ? '#15803d' : activeAction.strategy_reasoning.learning_signal === 'negative' ? '#991b1b' : '#475569',
                            }}
                          >
                            {activeAction.strategy_reasoning.learning_signal.toUpperCase()} SIGNAL
                          </span>
                        </div>
                        <div style={{ fontSize: '12px', color: '#334155' }}>
                          Base: <strong>{Math.round((activeAction.strategy_reasoning.base_priority ?? 0.5) * 100)}%</strong>
                          {' '}+ Hist Adj: <strong style={{ color: activeAction.strategy_reasoning.historical_adjustment >= 0 ? '#15803d' : '#dc2626' }}>
                            {activeAction.strategy_reasoning.historical_adjustment >= 0 ? '+' : ''}{Math.round(activeAction.strategy_reasoning.historical_adjustment * 100)}%
                          </strong>
                          {' '}={' '}Final Priority: <strong>{Math.round((activeAction.strategy_reasoning.final_priority ?? 0.5) * 100)}%</strong>
                        </div>
                      </div>
                      <p style={{ margin: 0, fontSize: '12px', color: '#475569', lineHeight: '1.4' }}>
                        {activeAction.strategy_reasoning.reasoning}
                      </p>
                      <div style={{ display: 'flex', gap: '14px', fontSize: '11px', color: '#64748b', flexWrap: 'wrap' }}>
                        <span>Historical Sample: <strong>{activeAction.strategy_reasoning.historical_sample_size} measured</strong></span>
                        <span>Smoothed Success Rate: <strong>{Math.round(activeAction.strategy_reasoning.historical_smoothed_rate * 100)}%</strong></span>
                        <span>Confidence: <strong>{activeAction.strategy_reasoning.confidence_level.toUpperCase()}</strong></span>
                      </div>
                    </div>
                  )}

                  {/* Tabs */}
                  <div style={{ display: 'flex', gap: '6px', borderBottom: '1px solid #e2e8f0', paddingBottom: '8px' }}>
                    <button onClick={() => setActiveTab('evidence')} style={activeTab === 'evidence' ? activeTabStyle : tabStyle}>
                      Evidence Snapshot
                    </button>
                    <button onClick={() => setActiveTab('proposed')} style={activeTab === 'proposed' ? activeTabStyle : tabStyle}>
                      Proposed Change
                    </button>
                    <button onClick={() => setActiveTab('instructions')} style={activeTab === 'instructions' ? activeTabStyle : tabStyle}>
                      Instructions
                    </button>
                    <button onClick={() => setActiveTab('verification')} style={activeTab === 'verification' ? activeTabStyle : tabStyle}>
                      Verification Proof
                    </button>
                    <button onClick={() => setActiveTab('outcome')} style={activeTab === 'outcome' ? activeTabStyle : tabStyle}>
                      📈 SEO Outcome & Lift
                    </button>
                    <button onClick={() => setActiveTab('execution')} style={activeTab === 'execution' ? activeTabStyle : tabStyle}>
                      Execution Logs
                    </button>
                  </div>

                  {/* Tab Contents */}
                  {activeTab === 'evidence' && (
                    <div style={{ padding: '16px', backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0' }}>
                      <h4 style={{ margin: '0 0 8px 0', fontSize: '13px', fontWeight: 700 }}>Causal Rationale</h4>
                      <p style={{ fontSize: '13px', color: '#334155', lineHeight: '1.5' }}>{activeAction.rationale || activeAction.description}</p>
                      <h4 style={{ margin: '14px 0 8px 0', fontSize: '13px', fontWeight: 700 }}>Supporting Evidence Data</h4>
                      <pre style={codeBlockStyle}>{JSON.stringify(activeAction.evidence_snapshot || {}, null, 2)}</pre>
                    </div>
                  )}

                  {activeTab === 'proposed' && (
                    <div style={{ padding: '16px', backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0' }}>
                      <h4 style={{ margin: '0 0 8px 0', fontSize: '13px', fontWeight: 700 }}>Structured Proposed Changes</h4>
                      <pre style={codeBlockStyle}>{JSON.stringify(activeAction.proposed_change || {}, null, 2)}</pre>
                    </div>
                  )}

                  {activeTab === 'instructions' && (
                    <div style={{ padding: '16px', backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0' }}>
                      <pre style={{ margin: 0, fontFamily: 'monospace', fontSize: '13px', whiteSpace: 'pre-wrap', lineHeight: '1.6' }}>
                        {activeAction.implementation_instructions}
                      </pre>
                    </div>
                  )}

                  {activeTab === 'verification' && (
                    <div style={{ padding: '16px', backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                        <h4 style={{ margin: 0, fontSize: '13px', fontWeight: 700 }}>Real-World Verification State</h4>
                        {renderVerificationBadge(activeAction.verification_status)}
                      </div>
                      <pre style={codeBlockStyle}>
                        {JSON.stringify(activeAction.verification_result || {"status": "Pending verification"}, null, 2)}
                      </pre>
                    </div>
                  )}

                  {activeTab === 'outcome' && (
                    <div style={{ padding: '16px', backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontSize: '18px' }}>📈</span>
                          <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 700 }}>Empirical SEO Outcome Measurement</h4>
                          {renderOutcomeBadge(activeAction.seo_outcome, activeAction.seo_outcome_display)}
                        </div>
                        {activeAction.outcome_confidence !== undefined && (
                          <span style={{ fontSize: '12px', fontWeight: 700, color: '#475569' }}>
                            Confidence: <strong>{Math.round((activeAction.outcome_confidence || 0) * 100)}%</strong>
                          </span>
                        )}
                      </div>

                      {activeAction.outcome_evidence ? (
                        <>
                          {/* Deltas Grid */}
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px' }}>
                            <div style={{ backgroundColor: '#f8fafc', padding: '10px', borderRadius: '8px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                              <span style={{ fontSize: '10px', color: '#64748b' }}>Position Delta</span>
                              <div style={{ fontSize: '16px', fontWeight: 800, color: (activeAction.outcome_evidence.deltas?.position_delta || 0) > 0 ? '#16a34a' : (activeAction.outcome_evidence.deltas?.position_delta || 0) < 0 ? '#dc2626' : '#0f172a' }}>
                                {(activeAction.outcome_evidence.deltas?.position_delta || 0) > 0 ? `+${activeAction.outcome_evidence.deltas.position_delta.toFixed(1)} spots` : `${(activeAction.outcome_evidence.deltas?.position_delta || 0).toFixed(1)} spots`}
                              </div>
                            </div>
                            <div style={{ backgroundColor: '#f8fafc', padding: '10px', borderRadius: '8px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                              <span style={{ fontSize: '10px', color: '#64748b' }}>CTR Delta</span>
                              <div style={{ fontSize: '16px', fontWeight: 800, color: (activeAction.outcome_evidence.deltas?.ctr_delta || 0) > 0 ? '#16a34a' : (activeAction.outcome_evidence.deltas?.ctr_delta || 0) < 0 ? '#dc2626' : '#0f172a' }}>
                                {((activeAction.outcome_evidence.deltas?.ctr_delta || 0) * 100).toFixed(2)}%
                              </div>
                            </div>
                            <div style={{ backgroundColor: '#f8fafc', padding: '10px', borderRadius: '8px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                              <span style={{ fontSize: '10px', color: '#64748b' }}>Clicks Delta</span>
                              <div style={{ fontSize: '16px', fontWeight: 800, color: (activeAction.outcome_evidence.deltas?.clicks_delta || 0) > 0 ? '#16a34a' : (activeAction.outcome_evidence.deltas?.clicks_delta || 0) < 0 ? '#dc2626' : '#0f172a' }}>
                                {(activeAction.outcome_evidence.deltas?.clicks_delta || 0) > 0 ? `+${activeAction.outcome_evidence.deltas.clicks_delta}` : (activeAction.outcome_evidence.deltas?.clicks_delta || 0)}
                              </div>
                            </div>
                            <div style={{ backgroundColor: '#f8fafc', padding: '10px', borderRadius: '8px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                              <span style={{ fontSize: '10px', color: '#64748b' }}>Impressions Delta</span>
                              <div style={{ fontSize: '16px', fontWeight: 800, color: '#0f172a' }}>
                                {(activeAction.outcome_evidence.deltas?.impressions_delta || 0) > 0 ? `+${activeAction.outcome_evidence.deltas.impressions_delta}` : (activeAction.outcome_evidence.deltas?.impressions_delta || 0)}
                              </div>
                            </div>
                          </div>

                          {/* Pre vs Post Comparison Table */}
                          <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse', border: '1px solid #e2e8f0' }}>
                            <thead>
                              <tr style={{ backgroundColor: '#f1f5f9', textAlign: 'left' }}>
                                <th style={{ padding: '8px 12px', borderBottom: '1px solid #e2e8f0' }}>Metric</th>
                                <th style={{ padding: '8px 12px', borderBottom: '1px solid #e2e8f0' }}>Before Execution</th>
                                <th style={{ padding: '8px 12px', borderBottom: '1px solid #e2e8f0' }}>After Execution</th>
                                <th style={{ padding: '8px 12px', borderBottom: '1px solid #e2e8f0' }}>Net Change</th>
                              </tr>
                            </thead>
                            <tbody>
                              <tr>
                                <td style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9', fontWeight: 600 }}>Average Position</td>
                                <td style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9' }}>#{activeAction.outcome_evidence.before_metrics?.position?.toFixed(1) || 'N/A'}</td>
                                <td style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9' }}>#{activeAction.outcome_evidence.after_metrics?.position?.toFixed(1) || 'N/A'}</td>
                                <td style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9', fontWeight: 700, color: (activeAction.outcome_evidence.deltas?.position_delta || 0) > 0 ? '#16a34a' : '#475569' }}>
                                  {(activeAction.outcome_evidence.deltas?.position_delta || 0) > 0 ? `+${activeAction.outcome_evidence.deltas.position_delta.toFixed(1)} spots` : `${(activeAction.outcome_evidence.deltas?.position_delta || 0).toFixed(1)} spots`}
                                </td>
                              </tr>
                              <tr>
                                <td style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9', fontWeight: 600 }}>Click-Through Rate (CTR)</td>
                                <td style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9' }}>{((activeAction.outcome_evidence.before_metrics?.ctr || 0) * 100).toFixed(2)}%</td>
                                <td style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9' }}>{((activeAction.outcome_evidence.after_metrics?.ctr || 0) * 100).toFixed(2)}%</td>
                                <td style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9', fontWeight: 700, color: (activeAction.outcome_evidence.deltas?.ctr_delta || 0) > 0 ? '#16a34a' : '#475569' }}>
                                  {((activeAction.outcome_evidence.deltas?.ctr_delta || 0) * 100).toFixed(2)}%
                                </td>
                              </tr>
                              <tr>
                                <td style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9', fontWeight: 600 }}>Clicks</td>
                                <td style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9' }}>{activeAction.outcome_evidence.before_metrics?.clicks || 0}</td>
                                <td style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9' }}>{activeAction.outcome_evidence.after_metrics?.clicks || 0}</td>
                                <td style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9', fontWeight: 700, color: (activeAction.outcome_evidence.deltas?.clicks_delta || 0) > 0 ? '#16a34a' : '#475569' }}>
                                  {(activeAction.outcome_evidence.deltas?.clicks_delta || 0) > 0 ? `+${activeAction.outcome_evidence.deltas.clicks_delta}` : activeAction.outcome_evidence.deltas?.clicks_delta || 0}
                                </td>
                              </tr>
                              <tr>
                                <td style={{ padding: '8px 12px', fontWeight: 600 }}>Impressions</td>
                                <td style={{ padding: '8px 12px' }}>{activeAction.outcome_evidence.before_metrics?.impressions || 0}</td>
                                <td style={{ padding: '8px 12px' }}>{activeAction.outcome_evidence.after_metrics?.impressions || 0}</td>
                                <td style={{ padding: '8px 12px', fontWeight: 700 }}>
                                  {(activeAction.outcome_evidence.deltas?.impressions_delta || 0) > 0 ? `+${activeAction.outcome_evidence.deltas.impressions_delta}` : activeAction.outcome_evidence.deltas?.impressions_delta || 0}
                                </td>
                              </tr>
                            </tbody>
                          </table>

                          <div style={{ fontSize: '11px', color: '#64748b' }}>
                            Measured at: <strong>{activeAction.outcome_measured_at ? new Date(activeAction.outcome_measured_at).toLocaleString() : 'Recently'}</strong> |
                            Window: <strong>{activeAction.outcome_evidence.window_days || 14} days symmetric</strong> |
                            Significance: <strong>{activeAction.outcome_evidence.is_statistically_significant ? 'Statistically Significant' : 'Directional Signal'}</strong>
                          </div>
                        </>
                      ) : (
                        <div style={{ padding: '32px 16px', textAlign: 'center', backgroundColor: '#f8fafc', borderRadius: '8px', border: '1px dashed #cbd5e1' }}>
                          <span style={{ fontSize: '28px' }}>⏳</span>
                          <p style={{ margin: '8px 0 4px 0', fontSize: '13px', fontWeight: 700, color: '#1e293b' }}>Outcome Not Measured Yet</p>
                          <p style={{ margin: '0 0 12px 0', fontSize: '12px', color: '#64748b' }}>
                            Click "Measure SEO Outcome" to compare pre- and post-execution Search Console performance.
                          </p>
                          {activeAction.status === 'completed' && (
                            <button
                              onClick={() => handleMeasureActionOutcome(activeAction.id)}
                              disabled={isMeasuring}
                              style={btnOutcomeStyle}
                            >
                              📈 {isMeasuring ? 'Measuring...' : 'Measure Outcome Now'}
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {activeTab === 'execution' && (
                    <div style={{ padding: '16px', backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0' }}>
                      <h4 style={{ margin: '0 0 8px 0', fontSize: '13px', fontWeight: 700 }}>Connector Execution Metadata</h4>
                      <pre style={codeBlockStyle}>{JSON.stringify(activeAction.execution_metadata || {}, null, 2)}</pre>
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ padding: '48px', textAlign: 'center', color: '#94a3b8' }}>
                  Select an action to inspect its evidence and approval state.
                </div>
              )}
            </div>
          </div>
        </div>
      )}


      {/* ========================================================================= */}
      {/* MODAL 1: PLAN GENERATOR */}
      {/* ========================================================================= */}
      {planModalOpen && (
        <div style={modalBackdropStyle}>
          <div style={modalDialogStyle}>
            <h3 style={{ margin: '0 0 12px 0', fontSize: '18px', fontWeight: 800 }}>Plan Autonomous SEO Actions</h3>
            <p style={{ margin: '0 0 16px 0', fontSize: '13px', color: '#64748b' }}>
              The agent will synthesize SiteAudit crawl defects, GSC search momentum anomalies, and active opportunity signals into a prioritized, cohesive plan.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div>
                <label style={{ fontSize: '12px', fontWeight: 700, color: '#334155', display: 'block', marginBottom: '4px' }}>
                  Plan Title (Optional):
                </label>
                <input
                  type="text"
                  placeholder="e.g. Q3 Organic CTR & Technical Remediation Plan"
                  value={planTitleInput}
                  onChange={(e) => setPlanTitleInput(e.target.value)}
                  style={textInputStyle}
                />
              </div>

              <div>
                <label style={{ fontSize: '12px', fontWeight: 700, color: '#334155', display: 'block', marginBottom: '4px' }}>
                  Maximum Actions:
                </label>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={planMaxActions}
                  onChange={(e) => setPlanMaxActions(parseInt(e.target.value) || 10)}
                  style={textInputStyle}
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px' }}>
              <button onClick={() => setPlanModalOpen(false)} style={btnSecondaryStyle}>
                Cancel
              </button>
              <button onClick={handleTriggerPlanGeneration} disabled={isGenerating} style={btnPrimaryStyle}>
                {isGenerating ? 'Planning...' : 'Generate Plan'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL 2: PLAN REJECTION */}
      {/* ========================================================================= */}
      {planRejectModalOpen && (
        <div style={modalBackdropStyle}>
          <div style={modalDialogStyle}>
            <h3 style={{ margin: '0 0 12px 0', fontSize: '18px', fontWeight: 800, color: '#991b1b' }}>Reject Action Plan</h3>
            <p style={{ margin: '0 0 16px 0', fontSize: '13px', color: '#64748b' }}>
              Provide a clear, auditable explanation for rejecting this action plan.
            </p>
            <textarea
              rows={3}
              placeholder="e.g. Action plan contains high risk canonical modifications that require engineering review."
              value={planRejectReason}
              onChange={(e) => setPlanRejectReason(e.target.value)}
              style={textareaStyle}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
              <button onClick={() => setPlanRejectModalOpen(false)} style={btnSecondaryStyle}>Cancel</button>
              <button onClick={handleConfirmPlanReject} style={btnDangerStyle}>Confirm Rejection</button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL 3: ACTION REJECTION */}
      {/* ========================================================================= */}
      {rejectModalOpen && (
        <div style={modalBackdropStyle}>
          <div style={modalDialogStyle}>
            <h3 style={{ margin: '0 0 12px 0', fontSize: '18px', fontWeight: 800, color: '#991b1b' }}>Reject SEO Action</h3>
            <p style={{ margin: '0 0 16px 0', fontSize: '13px', color: '#64748b' }}>
              Provide a clear reason for rejecting this proposed action.
            </p>
            <textarea
              rows={3}
              placeholder="e.g. Target landing page is currently undergoing brand redesign."
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              style={textareaStyle}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
              <button onClick={() => setRejectModalOpen(false)} style={btnSecondaryStyle}>Cancel</button>
              <button onClick={handleConfirmReject} style={btnDangerStyle}>Confirm Rejection</button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL 4: VISUAL DIFF PREVIEW */}
      {/* ========================================================================= */}
      {previewModalOpen && previewData && (
        <div style={modalBackdropStyle}>
          <div style={{ ...modalDialogStyle, maxWidth: '700px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <h3 style={{ margin: 0, fontSize: '17px', fontWeight: 800 }}>Non-Destructive Visual Diff Preview</h3>
              <button onClick={() => setPreviewModalOpen(false)} style={{ border: 'none', background: 'none', fontSize: '18px', cursor: 'pointer' }}>✖</button>
            </div>
            <p style={{ fontSize: '13px', color: '#475569', marginBottom: '14px' }}>{previewData.summary}</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div>
                <strong style={{ fontSize: '12px', color: '#64748b' }}>Before State:</strong>
                <pre style={codeBlockStyle}>{JSON.stringify(previewData.before_state || {}, null, 2)}</pre>
              </div>
              <div>
                <strong style={{ fontSize: '12px', color: '#16a34a' }}>After State (Proposed):</strong>
                <pre style={codeBlockStyle}>{JSON.stringify(previewData.after_state || {}, null, 2)}</pre>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL 5: VERIFICATION INSPECTION */}
      {/* ========================================================================= */}
      {verificationModalOpen && verificationData && (
        <div style={modalBackdropStyle}>
          <div style={{ ...modalDialogStyle, maxWidth: '700px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <h3 style={{ margin: 0, fontSize: '17px', fontWeight: 800 }}>🎯 Real-World Verification Result</h3>
              <button onClick={() => setVerificationModalOpen(false)} style={{ border: 'none', background: 'none', fontSize: '18px', cursor: 'pointer' }}>✖</button>
            </div>
            <div style={{ marginBottom: '14px' }}>
              <p style={{ margin: '0 0 6px 0', fontSize: '14px', fontWeight: 700, color: verificationData.verified ? '#065f46' : '#991b1b' }}>
                {verificationData.verified ? '✅ Verified in Live DOM' : '⚠️ Verification Mismatch / Incomplete'}
              </p>
              <p style={{ margin: 0, fontSize: '13px', color: '#475569' }}>
                {verificationData.explanation || 'Verified using empirical crawler inspection.'}
              </p>
            </div>
            <pre style={codeBlockStyle}>{JSON.stringify(verificationData, null, 2)}</pre>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px' }}>
              <button onClick={() => setVerificationModalOpen(false)} style={btnPrimaryStyle}>Close</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};

// Styles
const counterChipStyle: React.CSSProperties = {
  backgroundColor: '#f8fafc',
  padding: '6px 12px',
  borderRadius: '8px',
  border: '1px solid #e2e8f0',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  minWidth: '60px',
};

const selectInputStyle: React.CSSProperties = {
  padding: '6px 10px',
  borderRadius: '6px',
  border: '1px solid #cbd5e1',
  fontSize: '12px',
  backgroundColor: '#ffffff',
  color: '#1e293b',
  outline: 'none',
};

const textInputStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 12px',
  borderRadius: '6px',
  border: '1px solid #cbd5e1',
  fontSize: '13px',
  boxSizing: 'border-box',
};

const textareaStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 12px',
  borderRadius: '6px',
  border: '1px solid #cbd5e1',
  fontSize: '13px',
  fontFamily: 'inherit',
  boxSizing: 'border-box',
};

const btnPrimaryStyle: React.CSSProperties = {
  padding: '7px 14px',
  borderRadius: '7px',
  backgroundColor: '#4338ca',
  color: '#ffffff',
  border: 'none',
  fontSize: '12px',
  fontWeight: 700,
  cursor: 'pointer',
};

const btnSecondaryStyle: React.CSSProperties = {
  padding: '7px 14px',
  borderRadius: '7px',
  backgroundColor: '#ffffff',
  color: '#334155',
  border: '1px solid #cbd5e1',
  fontSize: '12px',
  fontWeight: 600,
  cursor: 'pointer',
};

const btnSuccessStyle: React.CSSProperties = {
  padding: '7px 14px',
  borderRadius: '7px',
  backgroundColor: '#15803d',
  color: '#ffffff',
  border: 'none',
  fontSize: '12px',
  fontWeight: 700,
  cursor: 'pointer',
};

const btnDangerStyle: React.CSSProperties = {
  padding: '7px 14px',
  borderRadius: '7px',
  backgroundColor: '#dc2626',
  color: '#ffffff',
  border: 'none',
  fontSize: '12px',
  fontWeight: 700,
  cursor: 'pointer',
};

const btnVerifyStyle: React.CSSProperties = {
  padding: '7px 14px',
  borderRadius: '7px',
  backgroundColor: '#059669',
  color: '#ffffff',
  border: 'none',
  fontSize: '12px',
  fontWeight: 700,
  cursor: 'pointer',
};

const btnOutcomeStyle: React.CSSProperties = {
  padding: '7px 14px',
  borderRadius: '7px',
  backgroundColor: '#047857',
  color: '#ffffff',
  border: 'none',
  fontSize: '12px',
  fontWeight: 700,
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  gap: '4px',
  boxShadow: '0 1px 2px rgba(0,0,0,0.05)'
};


const btnGhostDangerStyle: React.CSSProperties = {
  padding: '7px 10px',
  borderRadius: '7px',
  backgroundColor: 'transparent',
  border: '1px solid #fecaca',
  color: '#dc2626',
  cursor: 'pointer',
};

const tabStyle: React.CSSProperties = {
  padding: '6px 12px',
  borderRadius: '6px',
  border: 'none',
  background: 'none',
  fontSize: '12px',
  fontWeight: 600,
  color: '#64748b',
  cursor: 'pointer',
};

const activeTabStyle: React.CSSProperties = {
  ...tabStyle,
  backgroundColor: '#eff6ff',
  color: '#1d4ed8',
  fontWeight: 700,
};

const codeBlockStyle: React.CSSProperties = {
  margin: 0,
  padding: '12px',
  backgroundColor: '#0f172a',
  color: '#f8fafc',
  borderRadius: '8px',
  fontSize: '12px',
  fontFamily: 'monospace',
  overflowX: 'auto',
  maxHeight: '260px',
};

const modalBackdropStyle: React.CSSProperties = {
  position: 'fixed',
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  backgroundColor: 'rgba(15, 23, 42, 0.6)',
  display: 'flex',
  justifyContent: 'center',
  alignItems: 'center',
  zIndex: 1000,
  padding: '20px',
};

const modalDialogStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '16px',
  padding: '24px',
  maxWidth: '520px',
  width: '100%',
  boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
};
