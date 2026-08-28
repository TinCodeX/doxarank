import React, { useState, useEffect, useCallback, useMemo } from 'react';
import type { Project } from '../types/project';
import type {
  SEORecommendation,
  RecommendationPriority,
  RecommendationStatus,
  RecommendationType,
  SEORecommendationSummaryCounts
} from '../types/aiRecommendation';
import {
  getSEORecommendations,
  generateSEORecommendations,
  updateSEORecommendationStatus,
  deleteSEORecommendation,
  getSEORecommendationsSummary
} from '../api/aiRecommendations';

interface AIRecommendationsPanelProps {
  project: Project;
  onRefreshInsights?: () => void;
  onGenerateBrief?: (recommendationId: number) => void;
  onCreateAction?: (recommendationId: number) => void;
}

export const AIRecommendationsPanel: React.FC<AIRecommendationsPanelProps> = ({
  project,
  onRefreshInsights,
  onGenerateBrief,
  onCreateAction
}) => {
  const [recommendations, setRecommendations] = useState<SEORecommendation[]>([]);
  const [summaryCounts, setSummaryCounts] = useState<SEORecommendationSummaryCounts | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successToast, setSuccessToast] = useState<string | null>(null);
  const [expandedRecId, setExpandedRecId] = useState<number | null>(null);

  // Filters
  const [selectedPriority, setSelectedPriority] = useState<'all' | RecommendationPriority>('all');
  const [selectedStatus, setSelectedStatus] = useState<RecommendationStatus>('pending_review');
  const [selectedType, setSelectedType] = useState<'all' | RecommendationType>('all');

  // Fetch recommendations and summary counts
  const fetchRecommendationsData = useCallback(async (projectId: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const [recsData, summaryData] = await Promise.all([
        getSEORecommendations({ project_id: projectId }),
        getSEORecommendationsSummary(projectId)
      ]);
      setRecommendations(recsData);
      setSummaryCounts(summaryData);
    } catch (err: any) {
      setError(err?.data?.detail || 'Failed to load AI recommendations.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Project isolation: reload whenever active project changes
  useEffect(() => {
    if (project?.id) {
      setSuccessToast(null);
      setExpandedRecId(null);
      fetchRecommendationsData(project.id);
    } else {
      setRecommendations([]);
      setSummaryCounts(null);
    }
  }, [project?.id, fetchRecommendationsData]);

  // Generate recommendations for all open insights
  const handleGenerateAll = async () => {
    if (!project?.id || isGenerating) return;
    setIsGenerating(true);
    setError(null);
    setSuccessToast(null);
    try {
      const generated = await generateSEORecommendations({ project_id: project.id });
      setSuccessToast(`Successfully generated ${generated.length} AI recommendation(s).`);
      await fetchRecommendationsData(project.id);
      if (onRefreshInsights) onRefreshInsights();
    } catch (err: any) {
      setError(err?.data?.detail || 'Failed to generate AI recommendations.');
    } finally {
      setIsGenerating(false);
    }
  };

  // Status transition handler
  const handleStatusChange = async (id: number, newStatus: RecommendationStatus) => {
    try {
      const updated = await updateSEORecommendationStatus(id, newStatus);
      setRecommendations((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
      if (project?.id) {
        const summary = await getSEORecommendationsSummary(project.id);
        setSummaryCounts(summary);
      }
    } catch (err: any) {
      setError(err?.data?.detail || `Failed to update recommendation status to ${newStatus}.`);
    }
  };

  // Delete handler
  const handleDelete = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this AI recommendation?')) return;
    try {
      await deleteSEORecommendation(id);
      setRecommendations((prev) => prev.filter((r) => r.id !== id));
      if (project?.id) {
        const summary = await getSEORecommendationsSummary(project.id);
        setSummaryCounts(summary);
      }
    } catch (err: any) {
      setError(err?.data?.detail || 'Failed to delete recommendation.');
    }
  };

  // Filtered list
  const filteredRecs = useMemo(() => {
    return recommendations.filter((r) => {
      if (selectedStatus && r.status !== selectedStatus) return false;
      if (selectedPriority !== 'all' && r.priority !== selectedPriority) return false;
      if (selectedType !== 'all' && r.recommendation_type !== selectedType) return false;
      return true;
    });
  }, [recommendations, selectedStatus, selectedPriority, selectedType]);

  // Counts helpers
  const pendingCount = summaryCounts?.pending_review ?? recommendations.filter((r) => r.status === 'pending_review').length;
  const criticalCount = summaryCounts?.critical ?? recommendations.filter((r) => r.priority === 'critical' && r.status === 'pending_review').length;
  const highCount = summaryCounts?.high ?? recommendations.filter((r) => r.priority === 'high' && r.status === 'pending_review').length;
  const mediumCount = summaryCounts?.medium ?? recommendations.filter((r) => r.priority === 'medium' && r.status === 'pending_review').length;
  const lowCount = summaryCounts?.low ?? recommendations.filter((r) => r.priority === 'low' && r.status === 'pending_review').length;

  const getPriorityStyle = (priority: RecommendationPriority) => {
    switch (priority) {
      case 'critical':
        return { bg: '#fef2f2', text: '#991b1b', border: '#fecaca', label: 'Critical Priority', icon: '🚨' };
      case 'high':
        return { bg: '#fffbeb', text: '#92400e', border: '#fde68a', label: 'High Priority', icon: '⚠️' };
      case 'medium':
        return { bg: '#ecfdf5', text: '#065f46', border: '#a7f3d0', label: 'Medium Priority', icon: '💡' };
      case 'low':
      default:
        return { bg: '#eff6ff', text: '#1e40af', border: '#bfdbfe', label: 'Low Priority', icon: 'ℹ️' };
    }
  };

  const formatTypeLabel = (type: RecommendationType) => {
    return type
      .split('_')
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  };

  return (
    <section
      id="ai-recommendations-section"
      style={{
        marginTop: '40px',
        backgroundColor: '#ffffff',
        borderRadius: '16px',
        border: '1px solid #e2e8f0',
        padding: '28px',
        boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: '16px',
          marginBottom: '24px',
          borderBottom: '1px solid #f1f5f9',
          paddingBottom: '20px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px', flexWrap: 'wrap' }}>
            <span
              style={{
                fontSize: '11px',
                textTransform: 'uppercase',
                fontWeight: 800,
                letterSpacing: '0.05em',
                color: '#7c3aed',
                backgroundColor: '#f5f3ff',
                padding: '3px 10px',
                borderRadius: '6px',
                border: '1px solid #ddd6fe',
              }}
            >
              🤖 AI SEO Agent
            </span>
            <span
              style={{
                fontSize: '11px',
                fontWeight: 600,
                color: '#475569',
                backgroundColor: '#f1f5f9',
                padding: '3px 8px',
                borderRadius: '6px',
              }}
            >
              Proposals Require Human Review
            </span>
            <span style={{ fontSize: '13px', color: '#64748b' }}>
              Project: <strong style={{ color: '#0f172a' }}>{project.name}</strong>
            </span>
          </div>
          <h2 style={{ margin: 0, fontSize: '24px', fontWeight: 800, color: '#0f172a', letterSpacing: '-0.02em' }}>
            Automated SEO Recommendations
          </h2>
          <p style={{ margin: '4px 0 0 0', fontSize: '14px', color: '#64748b' }}>
            AI-generated, explainable action plans synthesizing ranking shifts, Search Console metrics, and audit findings.
          </p>
        </div>

        {/* Generate Button */}
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <button
            id="generate-all-recommendations-btn"
            onClick={handleGenerateAll}
            disabled={isGenerating}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              backgroundColor: isGenerating ? '#c4b5fd' : '#7c3aed',
              color: '#ffffff',
              border: 'none',
              padding: '10px 20px',
              borderRadius: '10px',
              fontSize: '14px',
              fontWeight: 700,
              cursor: isGenerating ? 'not-allowed' : 'pointer',
              boxShadow: '0 2px 4px rgba(124, 58, 237, 0.25)',
              transition: 'all 0.2s ease',
            }}
          >
            {isGenerating ? (
              <>
                <span style={{ display: 'inline-block', animation: 'spin 1s linear infinite' }}>🔄</span>
                Synthesizing AI Plans...
              </>
            ) : (
              <>
                <span>✨</span>
                Generate Recommendations
              </>
            )}
          </button>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div
          id="ai-rec-error-alert"
          style={{
            backgroundColor: '#fef2f2',
            color: '#b91c1c',
            border: '1px solid #fecaca',
            borderRadius: '10px',
            padding: '12px 16px',
            fontSize: '14px',
            marginBottom: '20px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>⚠️ {error}</span>
          <button
            onClick={() => setError(null)}
            style={{ background: 'none', border: 'none', color: '#b91c1c', cursor: 'pointer', fontWeight: 700 }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Success Toast */}
      {successToast && (
        <div
          id="ai-rec-success-toast"
          style={{
            backgroundColor: '#f0fdf4',
            color: '#166534',
            border: '1px solid #bbf7d0',
            borderRadius: '10px',
            padding: '14px 18px',
            fontSize: '14px',
            marginBottom: '24px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>✓ {successToast}</span>
          <button
            onClick={() => setSuccessToast(null)}
            style={{ background: 'none', border: 'none', color: '#166534', cursor: 'pointer', fontWeight: 700 }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Metric Counters Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
          gap: '16px',
          marginBottom: '28px',
        }}
      >
        {/* Critical */}
        <div
          id="rec-metric-critical"
          onClick={() => { setSelectedPriority('critical'); setSelectedStatus('pending_review'); }}
          style={{
            backgroundColor: '#ffffff',
            borderRadius: '12px',
            border: selectedPriority === 'critical' && selectedStatus === 'pending_review' ? '2px solid #ef4444' : '1px solid #fecaca',
            padding: '16px',
            cursor: 'pointer',
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#991b1b' }}>🚨 Critical</span>
            <span style={{ fontSize: '11px', color: '#b91c1c', fontWeight: 700, backgroundColor: '#fef2f2', padding: '2px 6px', borderRadius: '4px' }}>Pending</span>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#991b1b', marginTop: '6px' }}>
            {criticalCount}
          </div>
        </div>

        {/* High */}
        <div
          id="rec-metric-high"
          onClick={() => { setSelectedPriority('high'); setSelectedStatus('pending_review'); }}
          style={{
            backgroundColor: '#ffffff',
            borderRadius: '12px',
            border: selectedPriority === 'high' && selectedStatus === 'pending_review' ? '2px solid #f59e0b' : '1px solid #fde68a',
            padding: '16px',
            cursor: 'pointer',
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#92400e' }}>⚠️ High</span>
            <span style={{ fontSize: '11px', color: '#b45309', fontWeight: 700, backgroundColor: '#fffbeb', padding: '2px 6px', borderRadius: '4px' }}>Pending</span>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#92400e', marginTop: '6px' }}>
            {highCount}
          </div>
        </div>

        {/* Medium */}
        <div
          id="rec-metric-medium"
          onClick={() => { setSelectedPriority('medium'); setSelectedStatus('pending_review'); }}
          style={{
            backgroundColor: '#ffffff',
            borderRadius: '12px',
            border: selectedPriority === 'medium' && selectedStatus === 'pending_review' ? '2px solid #10b981' : '1px solid #a7f3d0',
            padding: '16px',
            cursor: 'pointer',
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#065f46' }}>💡 Medium</span>
            <span style={{ fontSize: '11px', color: '#047857', fontWeight: 700, backgroundColor: '#ecfdf5', padding: '2px 6px', borderRadius: '4px' }}>Pending</span>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#065f46', marginTop: '6px' }}>
            {mediumCount}
          </div>
        </div>

        {/* Low */}
        <div
          id="rec-metric-low"
          onClick={() => { setSelectedPriority('low'); setSelectedStatus('pending_review'); }}
          style={{
            backgroundColor: '#ffffff',
            borderRadius: '12px',
            border: selectedPriority === 'low' && selectedStatus === 'pending_review' ? '2px solid #3b82f6' : '1px solid #bfdbfe',
            padding: '16px',
            cursor: 'pointer',
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#1e40af' }}>ℹ️ Low</span>
            <span style={{ fontSize: '11px', color: '#1d4ed8', fontWeight: 700, backgroundColor: '#eff6ff', padding: '2px 6px', borderRadius: '4px' }}>Pending</span>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#1e40af', marginTop: '6px' }}>
            {lowCount}
          </div>
        </div>

        {/* Total Pending */}
        <div
          id="rec-metric-total"
          onClick={() => { setSelectedPriority('all'); setSelectedStatus('pending_review'); }}
          style={{
            backgroundColor: '#f8fafc',
            borderRadius: '12px',
            border: selectedPriority === 'all' && selectedStatus === 'pending_review' ? '2px solid #7c3aed' : '1px solid #e2e8f0',
            padding: '16px',
            cursor: 'pointer',
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#334155' }}>📋 To Review</span>
            <span style={{ fontSize: '11px', color: '#7c3aed', fontWeight: 700, backgroundColor: '#f5f3ff', padding: '2px 6px', borderRadius: '4px' }}>Pending</span>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#0f172a', marginTop: '6px' }}>
            {pendingCount}
          </div>
        </div>
      </div>

      {/* Filter Controls */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '12px',
          backgroundColor: '#f8fafc',
          padding: '12px 16px',
          borderRadius: '12px',
          border: '1px solid #e2e8f0',
          marginBottom: '20px',
        }}
      >
        {/* Priority filter buttons */}
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {(['all', 'critical', 'high', 'medium', 'low'] as const).map((prio) => {
            const isSelected = selectedPriority === prio;
            return (
              <button
                key={prio}
                id={`rec-filter-prio-${prio}`}
                onClick={() => setSelectedPriority(prio)}
                style={{
                  padding: '6px 12px',
                  borderRadius: '8px',
                  fontSize: '13px',
                  fontWeight: isSelected ? 700 : 500,
                  border: isSelected ? '1px solid #7c3aed' : '1px solid #cbd5e1',
                  backgroundColor: isSelected ? '#7c3aed' : '#ffffff',
                  color: isSelected ? '#ffffff' : '#475569',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                {prio === 'all' ? 'All Priorities' : prio.charAt(0).toUpperCase() + prio.slice(1)}
              </button>
            );
          })}
        </div>

        {/* Type and Status toggles */}
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          {/* Type filter select */}
          <select
            id="rec-filter-type-select"
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value as any)}
            style={{
              padding: '6px 10px',
              borderRadius: '8px',
              fontSize: '12px',
              fontWeight: 600,
              border: '1px solid #cbd5e1',
              backgroundColor: '#ffffff',
              color: '#334155',
              cursor: 'pointer',
            }}
          >
            <option value="all">All Types</option>
            <option value="meta_title">Meta Title</option>
            <option value="meta_description">Meta Description</option>
            <option value="content_update">Content Update</option>
            <option value="keyword_optimization">Keyword Optimization</option>
            <option value="internal_linking">Internal Linking</option>
            <option value="technical_seo">Technical SEO</option>
            <option value="ranking_recovery">Ranking Recovery</option>
            <option value="ctr_optimization">CTR Optimization</option>
            <option value="page_two_opportunity">Page Two Opportunity</option>
            <option value="general_seo">General SEO</option>
          </select>

          {/* Status toggles */}
          <div style={{ display: 'flex', gap: '4px', backgroundColor: '#e2e8f0', padding: '3px', borderRadius: '8px' }}>
            {(['pending_review', 'reviewed', 'applied', 'dismissed'] as const).map((stat) => {
              const isSelected = selectedStatus === stat;
              const labelMap = {
                pending_review: 'Pending',
                reviewed: 'Reviewed',
                applied: 'Applied',
                dismissed: 'Dismissed'
              };
              return (
                <button
                  key={stat}
                  id={`rec-filter-status-${stat}`}
                  onClick={() => setSelectedStatus(stat)}
                  style={{
                    padding: '5px 12px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    fontWeight: isSelected ? 700 : 500,
                    border: 'none',
                    backgroundColor: isSelected ? '#ffffff' : 'transparent',
                    color: isSelected ? '#0f172a' : '#64748b',
                    cursor: 'pointer',
                    boxShadow: isSelected ? '0 1px 2px rgba(0,0,0,0.06)' : 'none',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {labelMap[stat]}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Recommendation Cards */}
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: '48px 0', color: '#64748b', fontSize: '14px' }}>
          <p>Loading AI recommendations...</p>
        </div>
      ) : filteredRecs.length === 0 ? (
        <div
          id="ai-recs-empty-state"
          style={{
            textAlign: 'center',
            padding: '48px 24px',
            backgroundColor: '#f8fafc',
            borderRadius: '12px',
            border: '1px dashed #cbd5e1',
          }}
        >
          <div style={{ fontSize: '36px', marginBottom: '10px' }}>✨</div>
          <h4 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 700, color: '#0f172a' }}>
            {recommendations.length === 0 ? 'No AI recommendations generated yet' : 'No recommendations matching filters'}
          </h4>
          <p style={{ margin: '0 0 18px 0', fontSize: '14px', color: '#64748b', maxWidth: '440px', marginLeft: 'auto', marginRight: 'auto' }}>
            {recommendations.length === 0
              ? 'Click "Generate Recommendations" to have the AI SEO Agent analyze your project insights and draft targeted optimization steps.'
              : 'Try selecting a different status or priority filter to view other recommendations.'}
          </p>
          {recommendations.length === 0 ? (
            <button
              id="empty-generate-recs-btn"
              onClick={handleGenerateAll}
              disabled={isGenerating}
              style={{
                backgroundColor: '#7c3aed',
                color: '#ffffff',
                border: 'none',
                padding: '9px 18px',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              Generate First Recommendations
            </button>
          ) : (
            <button
              onClick={() => { setSelectedPriority('all'); setSelectedStatus('pending_review'); }}
              style={{
                backgroundColor: '#ffffff',
                color: '#7c3aed',
                border: '1px solid #ddd6fe',
                padding: '8px 16px',
                borderRadius: '8px',
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Reset Filters
            </button>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {filteredRecs.map((rec) => {
            const prioStyle = getPriorityStyle(rec.priority);
            const isExpanded = expandedRecId === rec.id;
            const isApplied = rec.status === 'applied';
            const isDismissed = rec.status === 'dismissed';

            return (
              <div
                key={rec.id}
                id={`recommendation-card-${rec.id}`}
                style={{
                  backgroundColor: isApplied ? '#f8fafc' : '#ffffff',
                  border: '1px solid #e2e8f0',
                  borderLeft: `4px solid ${
                    rec.priority === 'critical'
                      ? '#ef4444'
                      : rec.priority === 'high'
                      ? '#f59e0b'
                      : rec.priority === 'medium'
                      ? '#10b981'
                      : '#3b82f6'
                  }`,
                  borderRadius: '12px',
                  padding: '22px 24px',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
                  opacity: isDismissed ? 0.65 : 1,
                  transition: 'all 0.2s ease',
                }}
              >
                {/* Header Row */}
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    flexWrap: 'wrap',
                    gap: '10px',
                    marginBottom: '12px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    {/* Priority Badge */}
                    <span
                      style={{
                        fontSize: '12px',
                        fontWeight: 700,
                        padding: '3px 8px',
                        borderRadius: '6px',
                        backgroundColor: prioStyle.bg,
                        color: prioStyle.text,
                        border: `1px solid ${prioStyle.border}`,
                      }}
                    >
                      {prioStyle.icon} {prioStyle.label}
                    </span>

                    {/* Recommendation Type */}
                    <span
                      style={{
                        fontSize: '11px',
                        fontWeight: 600,
                        padding: '3px 8px',
                        borderRadius: '6px',
                        backgroundColor: '#f5f3ff',
                        color: '#6d28d9',
                      }}
                    >
                      {formatTypeLabel(rec.recommendation_type)}
                    </span>

                    {/* Status Badge */}
                    <span
                      style={{
                        fontSize: '11px',
                        fontWeight: 600,
                        padding: '2px 8px',
                        borderRadius: '4px',
                        backgroundColor:
                          rec.status === 'applied'
                            ? '#dcfce7'
                            : rec.status === 'reviewed'
                            ? '#e0e7ff'
                            : rec.status === 'dismissed'
                            ? '#f1f5f9'
                            : '#fef3c7',
                        color:
                          rec.status === 'applied'
                            ? '#15803d'
                            : rec.status === 'reviewed'
                            ? '#3730a3'
                            : rec.status === 'dismissed'
                            ? '#475569'
                            : '#b45309',
                      }}
                    >
                      ● {rec.status.replace('_', ' ').toUpperCase()}
                    </span>
                  </div>

                  {/* Timestamp */}
                  <span style={{ fontSize: '12px', color: '#94a3b8' }}>
                    {new Date(rec.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                  </span>
                </div>

                {/* Title */}
                <h3
                  style={{
                    margin: '0 0 8px 0',
                    fontSize: '18px',
                    fontWeight: 700,
                    color: '#0f172a',
                    textDecoration: isApplied ? 'line-through' : 'none',
                  }}
                >
                  {rec.title}
                </h3>

                {/* Executive Summary */}
                <p style={{ margin: '0 0 14px 0', fontSize: '14px', color: '#334155', lineHeight: '1.5' }}>
                  {rec.summary}
                </p>

                {/* Originating Insight Reference */}
                <div
                  style={{
                    backgroundColor: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                    padding: '10px 14px',
                    marginBottom: '14px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    fontSize: '13px',
                  }}
                >
                  <span style={{ fontSize: '14px' }}>🔍</span>
                  <span style={{ color: '#64748b' }}>Originating Insight:</span>
                  <strong style={{ color: '#1e293b' }}>{rec.insight_title}</strong>
                  <span
                    style={{
                      fontSize: '10px',
                      textTransform: 'uppercase',
                      fontWeight: 700,
                      padding: '1px 5px',
                      borderRadius: '4px',
                      backgroundColor: '#e2e8f0',
                      color: '#475569',
                    }}
                  >
                    {rec.insight_severity}
                  </span>
                </div>

                {/* Recommended Action Box */}
                <div
                  style={{
                    backgroundColor: '#eff6ff',
                    border: '1px solid #bfdbfe',
                    borderRadius: '8px',
                    padding: '14px 16px',
                    marginBottom: '14px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                    <span style={{ fontSize: '16px' }}>🛠️</span>
                    <div>
                      <strong style={{ fontSize: '13px', color: '#1e3a8a', display: 'block', marginBottom: '4px' }}>
                        Action Plan:
                      </strong>
                      <div style={{ fontSize: '13px', color: '#1e40af', lineHeight: '1.6', whiteSpace: 'pre-line' }}>
                        {rec.recommended_action}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Generated Content Box (when present) */}
                {rec.generated_content && (rec.generated_content.proposed_title || rec.generated_content.proposed_meta_description || rec.generated_content.action_checklist) && (
                  <div
                    style={{
                      backgroundColor: '#faf5ff',
                      border: '1px solid #e9d5ff',
                      borderRadius: '8px',
                      padding: '14px 16px',
                      marginBottom: '14px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
                      <span style={{ fontSize: '15px' }}>✨</span>
                      <strong style={{ fontSize: '13px', color: '#6b21a8' }}>AI Generated Copy & Assets:</strong>
                    </div>

                    {rec.generated_content.proposed_title && (
                      <div style={{ marginBottom: '8px' }}>
                        <span style={{ fontSize: '11px', fontWeight: 700, color: '#7c3aed', textTransform: 'uppercase' }}>
                          Suggested Title Tag:
                        </span>
                        <div
                          style={{
                            backgroundColor: '#ffffff',
                            border: '1px solid #ddd6fe',
                            borderRadius: '6px',
                            padding: '6px 10px',
                            fontSize: '13px',
                            color: '#1e1b4b',
                            marginTop: '2px',
                            fontWeight: 600,
                          }}
                        >
                          {rec.generated_content.proposed_title}
                        </div>
                      </div>
                    )}

                    {rec.generated_content.proposed_meta_description && (
                      <div style={{ marginBottom: '8px' }}>
                        <span style={{ fontSize: '11px', fontWeight: 700, color: '#7c3aed', textTransform: 'uppercase' }}>
                          Suggested Meta Description ({rec.generated_content.proposed_meta_description.length} chars):
                        </span>
                        <div
                          style={{
                            backgroundColor: '#ffffff',
                            border: '1px solid #ddd6fe',
                            borderRadius: '6px',
                            padding: '6px 10px',
                            fontSize: '13px',
                            color: '#334155',
                            marginTop: '2px',
                          }}
                        >
                          {rec.generated_content.proposed_meta_description}
                        </div>
                      </div>
                    )}

                    {rec.generated_content.action_checklist && rec.generated_content.action_checklist.length > 0 && (
                      <div style={{ marginTop: '8px' }}>
                        <span style={{ fontSize: '11px', fontWeight: 700, color: '#7c3aed', textTransform: 'uppercase' }}>
                          Step-by-Step Execution Checklist:
                        </span>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '4px' }}>
                          {rec.generated_content.action_checklist.map((step, idx) => (
                            <label
                              key={idx}
                              style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#475569', cursor: 'pointer' }}
                            >
                              <input type="checkbox" style={{ cursor: 'pointer' }} />
                              <span>{step}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Expandable In-Depth Explanation & Expected Impact */}
                {isExpanded && (
                  <div
                    style={{
                      borderTop: '1px dashed #cbd5e1',
                      paddingTop: '12px',
                      marginBottom: '14px',
                    }}
                  >
                    <div style={{ marginBottom: '10px' }}>
                      <strong style={{ fontSize: '12px', color: '#0f172a', textTransform: 'uppercase' }}>In-Depth Rationale:</strong>
                      <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#475569', lineHeight: '1.5' }}>
                        {rec.explanation}
                      </p>
                    </div>

                    <div>
                      <strong style={{ fontSize: '12px', color: '#0f172a', textTransform: 'uppercase' }}>Expected Realistic Impact:</strong>
                      <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#065f46', lineHeight: '1.5' }}>
                        📈 {rec.expected_impact}
                      </p>
                    </div>
                  </div>
                )}

                {/* Footer / Meta & Actions */}
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    gap: '12px',
                    borderTop: '1px solid #f1f5f9',
                    paddingTop: '14px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    {rec.affected_keyword && (
                      <span
                        style={{
                          fontSize: '12px',
                          color: '#475569',
                          backgroundColor: '#f1f5f9',
                          padding: '3px 8px',
                          borderRadius: '6px',
                        }}
                      >
                        🏷️ Keyword: <strong>{rec.affected_keyword}</strong>
                      </span>
                    )}

                    {rec.affected_url && (
                      <a
                        href={rec.affected_url}
                        target="_blank"
                        rel="noreferrer"
                        style={{
                          fontSize: '12px',
                          color: '#2563eb',
                          backgroundColor: '#eff6ff',
                          padding: '3px 8px',
                          borderRadius: '6px',
                          textDecoration: 'none',
                          maxWidth: '240px',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        🔗 {rec.affected_url}
                      </a>
                    )}

                    <button
                      onClick={() => setExpandedRecId(isExpanded ? null : rec.id)}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: '#6366f1',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        padding: 0,
                      }}
                    >
                      {isExpanded ? '▲ Hide Details' : '▼ Read Full Rationale'}
                    </button>
                  </div>

                  {/* Actions */}
                  <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
                    {onGenerateBrief && (
                      <button
                        id={`generate-brief-rec-${rec.id}`}
                        onClick={() => onGenerateBrief(rec.id)}
                        style={{
                          backgroundColor: '#f0f9ff',
                          color: '#0369a1',
                          border: '1px solid #bae6fd',
                          padding: '5px 10px',
                          borderRadius: '6px',
                          fontSize: '12px',
                          fontWeight: 700,
                          cursor: 'pointer',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                      >
                        📋 Brief
                      </button>
                    )}

                    {onCreateAction && (
                      <button
                        id={`create-action-rec-${rec.id}`}
                        onClick={() => onCreateAction(rec.id)}
                        style={{
                          backgroundColor: '#eff6ff',
                          color: '#1d4ed8',
                          border: '1px solid #bfdbfe',
                          padding: '5px 10px',
                          borderRadius: '6px',
                          fontSize: '12px',
                          fontWeight: 700,
                          cursor: 'pointer',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                      >
                        ⚡ Action
                      </button>
                    )}


                    {rec.status === 'pending_review' && (
                      <button
                        id={`review-rec-${rec.id}`}
                        onClick={() => handleStatusChange(rec.id, 'reviewed')}
                        style={{
                          backgroundColor: '#ffffff',
                          color: '#4338ca',
                          border: '1px solid #c7d2fe',
                          padding: '5px 10px',
                          borderRadius: '6px',
                          fontSize: '12px',
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        ✓ Mark Reviewed
                      </button>
                    )}

                    {rec.status !== 'applied' && (
                      <button
                        id={`apply-rec-${rec.id}`}
                        onClick={() => handleStatusChange(rec.id, 'applied')}
                        style={{
                          backgroundColor: '#ffffff',
                          color: '#16a34a',
                          border: '1px solid #86efac',
                          padding: '5px 10px',
                          borderRadius: '6px',
                          fontSize: '12px',
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        🚀 Mark Applied
                      </button>
                    )}

                    {rec.status === 'applied' && (
                      <button
                        id={`reopen-rec-${rec.id}`}
                        onClick={() => handleStatusChange(rec.id, 'pending_review')}
                        style={{
                          backgroundColor: '#ffffff',
                          color: '#6366f1',
                          border: '1px solid #c7d2fe',
                          padding: '5px 10px',
                          borderRadius: '6px',
                          fontSize: '12px',
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        ↺ Reopen
                      </button>
                    )}

                    {rec.status !== 'dismissed' ? (
                      <button
                        id={`dismiss-rec-${rec.id}`}
                        onClick={() => handleStatusChange(rec.id, 'dismissed')}
                        style={{
                          backgroundColor: '#ffffff',
                          color: '#64748b',
                          border: '1px solid #cbd5e1',
                          padding: '5px 8px',
                          borderRadius: '6px',
                          fontSize: '12px',
                          fontWeight: 500,
                          cursor: 'pointer',
                        }}
                      >
                        Dismiss
                      </button>
                    ) : (
                      <button
                        id={`restore-rec-${rec.id}`}
                        onClick={() => handleStatusChange(rec.id, 'pending_review')}
                        style={{
                          backgroundColor: '#ffffff',
                          color: '#6366f1',
                          border: '1px solid #c7d2fe',
                          padding: '5px 8px',
                          borderRadius: '6px',
                          fontSize: '12px',
                          fontWeight: 500,
                          cursor: 'pointer',
                        }}
                      >
                        Restore
                      </button>
                    )}

                    <button
                      id={`delete-rec-${rec.id}`}
                      onClick={() => handleDelete(rec.id)}
                      style={{
                        backgroundColor: '#ffffff',
                        color: '#ef4444',
                        border: '1px solid #fca5a5',
                        padding: '5px 8px',
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: 500,
                        cursor: 'pointer',
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
};
