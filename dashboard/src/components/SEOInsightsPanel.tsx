import React, { useState, useEffect, useCallback, useMemo } from 'react';
import type { Project } from '../types/project';
import type {
  SEOInsight,
  InsightSeverity,
  InsightStatus,
  InsightSource,
  SEOInsightAnalyzeSummary,
  SEOInsightSummaryCounts
} from '../types/seoInsight';
import {
  getSEOInsights,
  analyzeSEO,
  updateSEOInsightStatus,
  deleteSEOInsight,
  getSEOInsightsSummary
} from '../api/seoInsights';
import { generateSEORecommendations } from '../api/aiRecommendations';

interface SEOInsightsPanelProps {
  project: Project;
  onRecommendationGenerated?: () => void;
}

export const SEOInsightsPanel: React.FC<SEOInsightsPanelProps> = ({ project, onRecommendationGenerated }) => {
  const [insights, setInsights] = useState<SEOInsight[]>([]);
  const [summaryCounts, setSummaryCounts] = useState<SEOInsightSummaryCounts | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [generatingInsightId, setGeneratingInsightId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [analyzeResult, setAnalyzeResult] = useState<SEOInsightAnalyzeSummary | null>(null);


  // Filters
  const [selectedSeverity, setSelectedSeverity] = useState<'all' | InsightSeverity>('all');
  const [selectedStatus, setSelectedStatus] = useState<InsightStatus>('open');
  const [selectedSource, setSelectedSource] = useState<'all' | InsightSource>('all');

  // Fetch insights and summary
  const fetchInsightsData = useCallback(async (projectId: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const [insightsData, summaryData] = await Promise.all([
        getSEOInsights({ project_id: projectId }),
        getSEOInsightsSummary(projectId)
      ]);
      setInsights(insightsData);
      setSummaryCounts(summaryData);
    } catch (err: any) {
      setError(err?.data?.detail || 'Failed to load SEO insights for this project.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Project isolation: reload whenever active project changes
  useEffect(() => {
    if (project?.id) {
      setAnalyzeResult(null);
      fetchInsightsData(project.id);
    } else {
      setInsights([]);
      setSummaryCounts(null);
    }
  }, [project?.id, fetchInsightsData]);

  // Run SEO intelligence analysis
  const handleAnalyze = async () => {
    if (!project?.id || isAnalyzing) return;
    setIsAnalyzing(true);
    setError(null);
    setAnalyzeResult(null);
    try {
      const result = await analyzeSEO(project.id);
      setAnalyzeResult(result);
      // Refresh insights list and counts
      await fetchInsightsData(project.id);
    } catch (err: any) {
      setError(err?.data?.detail || 'Failed to execute SEO intelligence analysis.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Status transition handlers
  const handleGenerateRecommendationForInsight = async (insightId: number) => {
    if (!project?.id || generatingInsightId) return;
    setGeneratingInsightId(insightId);
    setError(null);
    try {
      await generateSEORecommendations({ project_id: project.id, insight_ids: [insightId] });
      if (onRecommendationGenerated) {
        onRecommendationGenerated();
      }
    } catch (err: any) {
      setError(err?.data?.detail || 'Failed to generate AI recommendation for this insight.');
    } finally {
      setGeneratingInsightId(null);
    }
  };

  const handleStatusChange = async (id: number, newStatus: InsightStatus) => {
    try {
      const updated = await updateSEOInsightStatus(id, newStatus);
      setInsights((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      if (project?.id) {
        const summary = await getSEOInsightsSummary(project.id);
        setSummaryCounts(summary);
      }
    } catch (err: any) {
      setError(err?.data?.detail || `Failed to update insight status to ${newStatus}.`);
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this SEO insight?')) return;
    try {
      await deleteSEOInsight(id);
      setInsights((prev) => prev.filter((item) => item.id !== id));
      if (project?.id) {
        const summary = await getSEOInsightsSummary(project.id);
        setSummaryCounts(summary);
      }
    } catch (err: any) {
      setError(err?.data?.detail || 'Failed to delete insight.');
    }
  };

  // Filtered insights
  const filteredInsights = useMemo(() => {
    return insights.filter((item) => {
      if (selectedStatus && item.status !== selectedStatus) return false;
      if (selectedSeverity !== 'all' && item.severity !== selectedSeverity) return false;
      if (selectedSource !== 'all' && item.source !== selectedSource) return false;
      return true;
    });
  }, [insights, selectedStatus, selectedSeverity, selectedSource]);

  // Calculated count helpers
  const openCount = summaryCounts?.open_total ?? insights.filter((i) => i.status === 'open').length;
  const criticalCount = summaryCounts?.critical ?? insights.filter((i) => i.severity === 'critical' && i.status === 'open').length;
  const warningCount = summaryCounts?.warning ?? insights.filter((i) => i.severity === 'warning' && i.status === 'open').length;
  const opportunityCount = summaryCounts?.opportunity ?? insights.filter((i) => i.severity === 'opportunity' && i.status === 'open').length;
  const infoCount = summaryCounts?.info ?? insights.filter((i) => i.severity === 'info' && i.status === 'open').length;

  // Severity styling helper
  const getSeverityBadgeStyle = (severity: InsightSeverity) => {
    switch (severity) {
      case 'critical':
        return {
          backgroundColor: '#fef2f2',
          color: '#991b1b',
          border: '1px solid #fecaca',
          label: 'Critical',
          icon: '🚨'
        };
      case 'warning':
        return {
          backgroundColor: '#fffbeb',
          color: '#92400e',
          border: '1px solid #fde68a',
          label: 'Warning',
          icon: '⚠️'
        };
      case 'opportunity':
        return {
          backgroundColor: '#ecfdf5',
          color: '#065f46',
          border: '1px solid #a7f3d0',
          label: 'Opportunity',
          icon: '💡'
        };
      case 'info':
      default:
        return {
          backgroundColor: '#eff6ff',
          color: '#1e40af',
          border: '1px solid #bfdbfe',
          label: 'Info',
          icon: 'ℹ️'
        };
    }
  };

  const getSourceBadgeStyle = (source: InsightSource) => {
    switch (source) {
      case 'ranking':
        return { backgroundColor: '#f3e8ff', color: '#6b21a8', label: 'Rankings' };
      case 'search_console':
        return { backgroundColor: '#e0f2fe', color: '#0369a1', label: 'Search Console' };
      case 'site_audit':
        return { backgroundColor: '#fef3c7', color: '#b45309', label: 'Site Audit' };
      case 'combined':
      default:
        return { backgroundColor: '#f1f5f9', color: '#475569', label: 'Combined' };
    }
  };

  return (
    <section
      id="seo-intelligence-section"
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
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
            <span
              style={{
                fontSize: '11px',
                textTransform: 'uppercase',
                fontWeight: 800,
                letterSpacing: '0.05em',
                color: '#4338ca',
                backgroundColor: '#e0e7ff',
                padding: '3px 10px',
                borderRadius: '6px',
              }}
            >
              SEO Intelligence Engine
            </span>
            <span style={{ fontSize: '13px', color: '#64748b' }}>
              Project: <strong style={{ color: '#0f172a' }}>{project.name}</strong>
            </span>
          </div>
          <h2 style={{ margin: 0, fontSize: '24px', fontWeight: 800, color: '#0f172a', letterSpacing: '-0.02em' }}>
            Actionable SEO Insights
          </h2>
          <p style={{ margin: '4px 0 0 0', fontSize: '14px', color: '#64748b' }}>
            Automated intelligence rules analyzing keyword fluctuations, Search Console queries, and technical site audit issues.
          </p>
        </div>

        {/* Action button */}
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <button
            id="analyze-seo-button"
            onClick={handleAnalyze}
            disabled={isAnalyzing}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              backgroundColor: isAnalyzing ? '#93c5fd' : '#2563eb',
              color: '#ffffff',
              border: 'none',
              padding: '10px 20px',
              borderRadius: '10px',
              fontSize: '14px',
              fontWeight: 700,
              cursor: isAnalyzing ? 'not-allowed' : 'pointer',
              boxShadow: '0 2px 4px rgba(37, 99, 235, 0.2)',
              transition: 'all 0.2s ease',
            }}
          >
            {isAnalyzing ? (
              <>
                <span style={{ display: 'inline-block', animation: 'spin 1s linear infinite' }}>🔄</span>
                Analyzing SEO Data...
              </>
            ) : (
              <>
                <span>⚡</span>
                Analyze SEO
              </>
            )}
          </button>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div
          id="seo-insight-error-alert"
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

      {/* Analyze Result Banner */}
      {analyzeResult && (
        <div
          id="analyze-summary-toast"
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
          <div>
            <strong>✓ Analysis Complete:</strong> Found{' '}
            <strong>{analyzeResult.created} new</strong> and{' '}
            <strong>{analyzeResult.updated} updated</strong> insights. Total open actionable items:{' '}
            <strong>{analyzeResult.total_open}</strong>.
          </div>
          <button
            onClick={() => setAnalyzeResult(null)}
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
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '16px',
          marginBottom: '28px',
        }}
      >
        {/* Critical */}
        <div
          id="metric-critical-card"
          onClick={() => { setSelectedSeverity('critical'); setSelectedStatus('open'); }}
          style={{
            backgroundColor: '#ffffff',
            borderRadius: '12px',
            border: selectedSeverity === 'critical' && selectedStatus === 'open' ? '2px solid #ef4444' : '1px solid #fecaca',
            padding: '16px',
            cursor: 'pointer',
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            transition: 'all 0.15s ease',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#991b1b' }}>🚨 Critical</span>
            <span style={{ fontSize: '11px', color: '#b91c1c', fontWeight: 700, backgroundColor: '#fef2f2', padding: '2px 6px', borderRadius: '4px' }}>Open</span>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#991b1b', marginTop: '6px' }}>
            {criticalCount}
          </div>
        </div>

        {/* Warning */}
        <div
          id="metric-warning-card"
          onClick={() => { setSelectedSeverity('warning'); setSelectedStatus('open'); }}
          style={{
            backgroundColor: '#ffffff',
            borderRadius: '12px',
            border: selectedSeverity === 'warning' && selectedStatus === 'open' ? '2px solid #f59e0b' : '1px solid #fde68a',
            padding: '16px',
            cursor: 'pointer',
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            transition: 'all 0.15s ease',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#92400e' }}>⚠️ Warnings</span>
            <span style={{ fontSize: '11px', color: '#b45309', fontWeight: 700, backgroundColor: '#fffbeb', padding: '2px 6px', borderRadius: '4px' }}>Open</span>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#92400e', marginTop: '6px' }}>
            {warningCount}
          </div>
        </div>

        {/* Opportunity */}
        <div
          id="metric-opportunity-card"
          onClick={() => { setSelectedSeverity('opportunity'); setSelectedStatus('open'); }}
          style={{
            backgroundColor: '#ffffff',
            borderRadius: '12px',
            border: selectedSeverity === 'opportunity' && selectedStatus === 'open' ? '2px solid #10b981' : '1px solid #a7f3d0',
            padding: '16px',
            cursor: 'pointer',
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            transition: 'all 0.15s ease',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#065f46' }}>💡 Opportunities</span>
            <span style={{ fontSize: '11px', color: '#047857', fontWeight: 700, backgroundColor: '#ecfdf5', padding: '2px 6px', borderRadius: '4px' }}>Open</span>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#065f46', marginTop: '6px' }}>
            {opportunityCount}
          </div>
        </div>

        {/* Info */}
        <div
          id="metric-info-card"
          onClick={() => { setSelectedSeverity('info'); setSelectedStatus('open'); }}
          style={{
            backgroundColor: '#ffffff',
            borderRadius: '12px',
            border: selectedSeverity === 'info' && selectedStatus === 'open' ? '2px solid #3b82f6' : '1px solid #bfdbfe',
            padding: '16px',
            cursor: 'pointer',
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            transition: 'all 0.15s ease',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#1e40af' }}>ℹ️ Info</span>
            <span style={{ fontSize: '11px', color: '#1d4ed8', fontWeight: 700, backgroundColor: '#eff6ff', padding: '2px 6px', borderRadius: '4px' }}>Open</span>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#1e40af', marginTop: '6px' }}>
            {infoCount}
          </div>
        </div>

        {/* Total Open */}
        <div
          id="metric-total-open-card"
          onClick={() => { setSelectedSeverity('all'); setSelectedStatus('open'); }}
          style={{
            backgroundColor: '#f8fafc',
            borderRadius: '12px',
            border: selectedSeverity === 'all' && selectedStatus === 'open' ? '2px solid #6366f1' : '1px solid #e2e8f0',
            padding: '16px',
            cursor: 'pointer',
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            transition: 'all 0.15s ease',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#334155' }}>📊 All Open</span>
            <span style={{ fontSize: '11px', color: '#4338ca', fontWeight: 700, backgroundColor: '#e0e7ff', padding: '2px 6px', borderRadius: '4px' }}>Total</span>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#0f172a', marginTop: '6px' }}>
            {openCount}
          </div>
        </div>
      </div>

      {/* Filter Tabs and Controls */}
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
        {/* Severity filter buttons */}
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {(['all', 'critical', 'warning', 'opportunity', 'info'] as const).map((sev) => {
            const isSelected = selectedSeverity === sev;
            return (
              <button
                key={sev}
                id={`filter-severity-${sev}`}
                onClick={() => setSelectedSeverity(sev)}
                style={{
                  padding: '6px 12px',
                  borderRadius: '8px',
                  fontSize: '13px',
                  fontWeight: isSelected ? 700 : 500,
                  border: isSelected ? '1px solid #2563eb' : '1px solid #cbd5e1',
                  backgroundColor: isSelected ? '#2563eb' : '#ffffff',
                  color: isSelected ? '#ffffff' : '#475569',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                {sev === 'all' ? 'All Severities' : sev.charAt(0).toUpperCase() + sev.slice(1)}
              </button>
            );
          })}
        </div>

        {/* Source and Status filters */}
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          {/* Source dropdown / pills */}
          <div style={{ display: 'flex', gap: '4px', backgroundColor: '#e2e8f0', padding: '3px', borderRadius: '8px' }}>
            {([
              { id: 'all', label: 'All Sources' },
              { id: 'ranking', label: 'Rankings' },
              { id: 'search_console', label: 'GSC' },
              { id: 'site_audit', label: 'Audit' },
            ] as const).map((src) => {
              const isSelected = selectedSource === src.id;
              return (
                <button
                  key={src.id}
                  id={`filter-source-${src.id}`}
                  onClick={() => setSelectedSource(src.id as any)}
                  style={{
                    padding: '5px 10px',
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
                  {src.label}
                </button>
              );
            })}
          </div>

          {/* Status toggles */}
          <div style={{ display: 'flex', gap: '4px', backgroundColor: '#e2e8f0', padding: '3px', borderRadius: '8px' }}>
            {(['open', 'resolved', 'dismissed'] as const).map((stat) => {
              const isSelected = selectedStatus === stat;
              return (
                <button
                  key={stat}
                  id={`filter-status-${stat}`}
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
                  {stat.charAt(0).toUpperCase() + stat.slice(1)}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Insight Content / Cards */}
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: '48px 0', color: '#64748b', fontSize: '14px' }}>
          <p>Loading SEO insights from intelligence engine...</p>
        </div>
      ) : filteredInsights.length === 0 ? (
        <div
          id="seo-insights-empty-state"
          style={{
            textAlign: 'center',
            padding: '48px 24px',
            backgroundColor: '#f8fafc',
            borderRadius: '12px',
            border: '1px dashed #cbd5e1',
          }}
        >
          <div style={{ fontSize: '36px', marginBottom: '10px' }}>🧠</div>
          <h4 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 700, color: '#0f172a' }}>
            {insights.length === 0 ? 'No insights detected yet' : 'No insights matching filters'}
          </h4>
          <p style={{ margin: '0 0 18px 0', fontSize: '14px', color: '#64748b', maxWidth: '440px', marginLeft: 'auto', marginRight: 'auto' }}>
            {insights.length === 0
              ? 'Click "Analyze SEO" to scan your ranking trends, Search Console analytics, and site audit issues.'
              : 'Try clearing the active severity or status filters to view other insights.'}
          </p>
          {insights.length === 0 ? (
            <button
              id="empty-analyze-seo-button"
              onClick={handleAnalyze}
              disabled={isAnalyzing}
              style={{
                backgroundColor: '#2563eb',
                color: '#ffffff',
                border: 'none',
                padding: '9px 18px',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              Run First Analysis
            </button>
          ) : (
            <button
              onClick={() => { setSelectedSeverity('all'); setSelectedStatus('open'); }}
              style={{
                backgroundColor: '#ffffff',
                color: '#2563eb',
                border: '1px solid #bfdbfe',
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
          {filteredInsights.map((insight) => {
            const sevBadge = getSeverityBadgeStyle(insight.severity);
            const srcBadge = getSourceBadgeStyle(insight.source);
            const isResolved = insight.status === 'resolved';
            const isDismissed = insight.status === 'dismissed';

            return (
              <div
                key={insight.id}
                id={`insight-card-${insight.id}`}
                style={{
                  backgroundColor: isResolved ? '#f8fafc' : '#ffffff',
                  border: isResolved ? '1px solid #e2e8f0' : '1px solid #e2e8f0',
                  borderLeft: `4px solid ${
                    insight.severity === 'critical'
                      ? '#ef4444'
                      : insight.severity === 'warning'
                      ? '#f59e0b'
                      : insight.severity === 'opportunity'
                      ? '#10b981'
                      : '#3b82f6'
                  }`,
                  borderRadius: '12px',
                  padding: '20px 24px',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
                  transition: 'all 0.2s ease',
                  opacity: isDismissed ? 0.7 : 1,
                }}
              >
                {/* Card Header */}
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
                    {/* Severity Badge */}
                    <span
                      style={{
                        fontSize: '12px',
                        fontWeight: 700,
                        padding: '3px 8px',
                        borderRadius: '6px',
                        backgroundColor: sevBadge.backgroundColor,
                        color: sevBadge.color,
                        border: sevBadge.border,
                      }}
                    >
                      {sevBadge.icon} {sevBadge.label}
                    </span>

                    {/* Source Badge */}
                    <span
                      style={{
                        fontSize: '11px',
                        fontWeight: 600,
                        padding: '3px 8px',
                        borderRadius: '6px',
                        backgroundColor: srcBadge.backgroundColor,
                        color: srcBadge.color,
                      }}
                    >
                      {srcBadge.label}
                    </span>

                    {/* Status Badge */}
                    <span
                      style={{
                        fontSize: '11px',
                        fontWeight: 600,
                        padding: '2px 8px',
                        borderRadius: '4px',
                        backgroundColor: isResolved ? '#dcfce7' : isDismissed ? '#f1f5f9' : '#e0f2fe',
                        color: isResolved ? '#15803d' : isDismissed ? '#475569' : '#0369a1',
                      }}
                    >
                      ● {insight.status.toUpperCase()}
                    </span>
                  </div>

                  {/* Detected date */}
                  <span style={{ fontSize: '12px', color: '#94a3b8' }}>
                    Detected: {new Date(insight.detected_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                  </span>
                </div>

                {/* Title */}
                <h3
                  style={{
                    margin: '0 0 8px 0',
                    fontSize: '17px',
                    fontWeight: 700,
                    color: isResolved ? '#475569' : '#0f172a',
                    textDecoration: isResolved ? 'line-through' : 'none',
                  }}
                >
                  {insight.title}
                </h3>

                {/* Description */}
                <p style={{ margin: '0 0 14px 0', fontSize: '14px', color: '#475569', lineHeight: '1.5' }}>
                  {insight.description}
                </p>

                {/* Recommendation Box */}
                {insight.recommendation && (
                  <div
                    style={{
                      backgroundColor: '#f8fafc',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                      padding: '12px 16px',
                      marginBottom: '14px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                      <span style={{ fontSize: '15px' }}>💡</span>
                      <div>
                        <strong style={{ fontSize: '13px', color: '#1e293b' }}>Recommendation: </strong>
                        <span style={{ fontSize: '13px', color: '#334155' }}>{insight.recommendation}</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Tags and Meta Details */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: '12px',
                    borderTop: '1px solid #f1f5f9',
                    paddingTop: '14px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    {insight.related_keyword_name && (
                      <span
                        style={{
                          fontSize: '12px',
                          color: '#475569',
                          backgroundColor: '#f1f5f9',
                          padding: '3px 8px',
                          borderRadius: '6px',
                        }}
                      >
                        🏷️ Keyword: <strong>{insight.related_keyword_name}</strong>
                      </span>
                    )}

                    {insight.related_url && (
                      <a
                        href={insight.related_url}
                        target="_blank"
                        rel="noreferrer"
                        style={{
                          fontSize: '12px',
                          color: '#2563eb',
                          backgroundColor: '#eff6ff',
                          padding: '3px 8px',
                          borderRadius: '6px',
                          textDecoration: 'none',
                          maxWidth: '280px',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          display: 'inline-block',
                        }}
                      >
                        🔗 {insight.related_url}
                      </a>
                    )}
                  </div>

                  {/* Actions */}
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                    {/* Generate AI Recommendation Button */}
                    <button
                      id={`generate-rec-insight-${insight.id}`}
                      onClick={() => handleGenerateRecommendationForInsight(insight.id)}
                      disabled={generatingInsightId === insight.id}
                      style={{
                        backgroundColor: '#f5f3ff',
                        color: '#7c3aed',
                        border: '1px solid #ddd6fe',
                        padding: '5px 12px',
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: 700,
                        cursor: generatingInsightId === insight.id ? 'not-allowed' : 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      {generatingInsightId === insight.id ? '✨ Synthesizing...' : '✨ AI Recommendation'}
                    </button>

                    {insight.status !== 'resolved' ? (
                      <button
                        id={`resolve-insight-${insight.id}`}
                        onClick={() => handleStatusChange(insight.id, 'resolved')}
                        style={{
                          backgroundColor: '#ffffff',
                          color: '#16a34a',
                          border: '1px solid #86efac',
                          padding: '5px 12px',
                          borderRadius: '6px',
                          fontSize: '12px',
                          fontWeight: 600,
                          cursor: 'pointer',
                          transition: 'all 0.15s ease',
                        }}
                      >
                        ✓ Mark Resolved
                      </button>
                    ) : (
                      <button
                        id={`reopen-insight-${insight.id}`}
                        onClick={() => handleStatusChange(insight.id, 'open')}
                        style={{
                          backgroundColor: '#ffffff',
                          color: '#2563eb',
                          border: '1px solid #93c5fd',
                          padding: '5px 12px',
                          borderRadius: '6px',
                          fontSize: '12px',
                          fontWeight: 600,
                          cursor: 'pointer',
                          transition: 'all 0.15s ease',
                        }}
                      >
                        ↺ Reopen
                      </button>
                    )}

                    {insight.status !== 'dismissed' ? (
                      <button
                        id={`dismiss-insight-${insight.id}`}
                        onClick={() => handleStatusChange(insight.id, 'dismissed')}
                        style={{
                          backgroundColor: '#ffffff',
                          color: '#64748b',
                          border: '1px solid #cbd5e1',
                          padding: '5px 10px',
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
                        id={`reopen-dismissed-insight-${insight.id}`}
                        onClick={() => handleStatusChange(insight.id, 'open')}
                        style={{
                          backgroundColor: '#ffffff',
                          color: '#2563eb',
                          border: '1px solid #93c5fd',
                          padding: '5px 10px',
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
                      id={`delete-insight-${insight.id}`}
                      onClick={() => handleDelete(insight.id)}
                      style={{
                        backgroundColor: '#ffffff',
                        color: '#ef4444',
                        border: '1px solid #fca5a5',
                        padding: '5px 10px',
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
