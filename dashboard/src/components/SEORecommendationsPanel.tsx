import React, { useState, useEffect, useCallback } from 'react';
import type { Project } from '../types/project';
import type { Recommendation } from '../types/recommendation';
import {
  getRecommendations,
  updateRecommendationStatus,
  acknowledgeRecommendation,
  resolveRecommendation,
  dismissRecommendation,
  generateRecommendations,
} from '../api/recommendations';

interface SEORecommendationsPanelProps {
  project: Project;
}

type TabFilter = 'all' | 'critical_high' | 'technical' | 'rankings' | 'competitors' | 'resolved';

export const SEORecommendationsPanel: React.FC<SEORecommendationsPanelProps> = ({ project }) => {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [generating, setGenerating] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabFilter>('all');
  const [expandedRecId, setExpandedRecId] = useState<number | null>(null);

  const fetchRecommendations = useCallback(async () => {
    if (!project?.id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getRecommendations({ project_id: project.id });
      setRecommendations(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to load recommendations.');
    } finally {
      setLoading(false);
    }
  }, [project?.id]);

  useEffect(() => {
    fetchRecommendations();
  }, [fetchRecommendations]);

  const handleGenerate = async () => {
    if (!project?.id) return;
    setGenerating(true);
    setNotice(null);
    setError(null);
    try {
      const result = await generateRecommendations({ project_id: project.id });
      setRecommendations(result);
      setNotice(`Generated and prioritized ${result.length} actionable recommendations.`);
      setTimeout(() => setNotice(null), 5000);
    } catch (err: any) {
      setError(err?.message || 'Failed to generate recommendations.');
    } finally {
      setGenerating(false);
    }
  };

  const handleStatusChange = async (recId: number, action: 'acknowledge' | 'resolve' | 'dismiss' | 'reopen') => {
    try {
      let updated: Recommendation;
      if (action === 'acknowledge') {
        updated = await acknowledgeRecommendation(recId);
      } else if (action === 'resolve') {
        updated = await resolveRecommendation(recId);
      } else if (action === 'dismiss') {
        updated = await dismissRecommendation(recId);
      } else {
        updated = await updateRecommendationStatus(recId, 'open');
      }

      setRecommendations((prev) =>
        prev.map((r) => (r.id === recId ? updated : r))
      );
    } catch (err: any) {
      setError(err?.message || `Failed to update recommendation status to ${action}.`);
    }
  };

  // KPIs
  const openRecs = recommendations.filter((r) => r.status === 'open' || r.status === 'acknowledged');
  const criticalCount = openRecs.filter((r) => r.severity === 'critical').length;
  const highCount = openRecs.filter((r) => r.severity === 'high').length;
  const mediumCount = openRecs.filter((r) => r.severity === 'medium').length;
  const resolvedCount = recommendations.filter((r) => r.status === 'resolved').length;

  // Filtered list
  const filteredRecs = recommendations.filter((r) => {
    if (activeTab === 'all') {
      return r.status === 'open' || r.status === 'acknowledged';
    }
    if (activeTab === 'critical_high') {
      return (r.status === 'open' || r.status === 'acknowledged') && (r.severity === 'critical' || r.severity === 'high');
    }
    if (activeTab === 'technical') {
      return (r.status === 'open' || r.status === 'acknowledged') &&
        (r.category === 'technical_seo' || r.category === 'indexing' || r.category === 'performance' || r.category === 'on_page_seo');
    }
    if (activeTab === 'rankings') {
      return (r.status === 'open' || r.status === 'acknowledged') && r.category === 'rankings';
    }
    if (activeTab === 'competitors') {
      return (r.status === 'open' || r.status === 'acknowledged') && r.category === 'competitors';
    }
    if (activeTab === 'resolved') {
      return r.status === 'resolved' || r.status === 'dismissed';
    }
    return true;
  });

  const getSeverityBadge = (sev: string) => {
    const map: Record<string, { bg: string; color: string; border: string }> = {
      critical: { bg: '#fef2f2', color: '#b91c1c', border: '#fca5a5' },
      high: { bg: '#fff7ed', color: '#c2410c', border: '#fdba74' },
      medium: { bg: '#fefce8', color: '#a16207', border: '#fde047' },
      low: { bg: '#eff6ff', color: '#1d4ed8', border: '#93c5fd' },
      info: { bg: '#f9fafb', color: '#4b5563', border: '#d1d5db' },
    };
    const s = map[sev] || map.info;
    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          padding: '2px 8px',
          borderRadius: '9999px',
          fontSize: '11px',
          fontWeight: 700,
          textTransform: 'uppercase',
          backgroundColor: s.bg,
          color: s.color,
          border: `1px solid ${s.border}`,
        }}
      >
        {sev}
      </span>
    );
  };

  const getSourceBadge = (source: string) => {
    const labels: Record<string, string> = {
      crawler: 'Crawler',
      rank_tracker: 'Rank Tracker',
      competitor_snapshot: 'Competitors',
      seo_tool: 'SEO Tool',
      system: 'System',
    };
    return (
      <span
        style={{
          fontSize: '11px',
          color: '#6b7280',
          backgroundColor: '#f3f4f6',
          padding: '2px 6px',
          borderRadius: '4px',
          fontWeight: 500,
        }}
      >
        {labels[source] || source}
      </span>
    );
  };

  return (
    <section
      id="seo-recommendations-panel"
      style={{
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        border: '1px solid #e5e7eb',
        padding: '24px',
        marginBottom: '32px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
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
          marginBottom: '20px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: '#111827' }}>
              Actionable SEO Recommendations
            </h2>
            <span
              style={{
                backgroundColor: '#eff6ff',
                color: '#1d4ed8',
                fontSize: '12px',
                fontWeight: 600,
                padding: '2px 8px',
                borderRadius: '9999px',
              }}
            >
              Rule-Based
            </span>
          </div>
          <p style={{ margin: '4px 0 0 0', fontSize: '14px', color: '#6b7280' }}>
            Prioritized issues and growth opportunities synthesized from Crawler, Rank Tracker, and Competitor visibility data for {project.name}.
          </p>
        </div>

        <button
          id="btn-generate-recommendations"
          type="button"
          onClick={handleGenerate}
          disabled={generating || loading}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            padding: '10px 18px',
            backgroundColor: '#2563eb',
            color: '#ffffff',
            border: 'none',
            borderRadius: '8px',
            fontSize: '14px',
            fontWeight: 600,
            cursor: generating ? 'not-allowed' : 'pointer',
            opacity: generating ? 0.7 : 1,
            boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
          }}
        >
          {generating ? 'Evaluating Findings...' : '⚡ Generate Recommendations'}
        </button>
      </div>

      {/* KPI Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: '12px',
          marginBottom: '20px',
        }}
      >
        <div style={{ padding: '12px 16px', backgroundColor: '#f9fafb', borderRadius: '8px', border: '1px solid #f3f4f6' }}>
          <div style={{ fontSize: '11px', fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Open Actions</div>
          <div style={{ fontSize: '22px', fontWeight: 700, color: '#111827', marginTop: '4px' }}>{openRecs.length}</div>
        </div>
        <div style={{ padding: '12px 16px', backgroundColor: '#fef2f2', borderRadius: '8px', border: '1px solid #fee2e2' }}>
          <div style={{ fontSize: '11px', fontWeight: 600, color: '#b91c1c', textTransform: 'uppercase' }}>Critical</div>
          <div style={{ fontSize: '22px', fontWeight: 700, color: '#b91c1c', marginTop: '4px' }}>{criticalCount}</div>
        </div>
        <div style={{ padding: '12px 16px', backgroundColor: '#fff7ed', borderRadius: '8px', border: '1px solid #ffedd5' }}>
          <div style={{ fontSize: '11px', fontWeight: 600, color: '#c2410c', textTransform: 'uppercase' }}>High Priority</div>
          <div style={{ fontSize: '22px', fontWeight: 700, color: '#c2410c', marginTop: '4px' }}>{highCount}</div>
        </div>
        <div style={{ padding: '12px 16px', backgroundColor: '#fefce8', borderRadius: '8px', border: '1px solid #fef9c3' }}>
          <div style={{ fontSize: '11px', fontWeight: 600, color: '#a16207', textTransform: 'uppercase' }}>Medium Priority</div>
          <div style={{ fontSize: '22px', fontWeight: 700, color: '#a16207', marginTop: '4px' }}>{mediumCount}</div>
        </div>
        <div style={{ padding: '12px 16px', backgroundColor: '#f0fdf4', borderRadius: '8px', border: '1px solid #dcfce7' }}>
          <div style={{ fontSize: '11px', fontWeight: 600, color: '#15803d', textTransform: 'uppercase' }}>Resolved</div>
          <div style={{ fontSize: '22px', fontWeight: 700, color: '#15803d', marginTop: '4px' }}>{resolvedCount}</div>
        </div>
      </div>

      {/* Notices & Errors */}
      {notice && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: '#f0fdf4',
            border: '1px solid #bbf7d0',
            color: '#166534',
            borderRadius: '8px',
            fontSize: '14px',
            marginBottom: '16px',
          }}
        >
          {notice}
        </div>
      )}
      {error && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#991b1b',
            borderRadius: '8px',
            fontSize: '14px',
            marginBottom: '16px',
          }}
        >
          {error}
        </div>
      )}

      {/* Tabs Filter */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          borderBottom: '1px solid #e5e7eb',
          marginBottom: '16px',
          overflowX: 'auto',
          paddingBottom: '2px',
        }}
      >
        {[
          { key: 'all', label: `All Active (${openRecs.length})` },
          { key: 'critical_high', label: `Critical & High (${criticalCount + highCount})` },
          { key: 'technical', label: 'Technical SEO' },
          { key: 'rankings', label: 'Rankings' },
          { key: 'competitors', label: 'Competitors' },
          { key: 'resolved', label: `Resolved (${resolvedCount})` },
        ].map((tab) => {
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key as TabFilter)}
              style={{
                padding: '8px 14px',
                border: 'none',
                background: 'none',
                cursor: 'pointer',
                fontSize: '13px',
                fontWeight: isActive ? 700 : 500,
                color: isActive ? '#2563eb' : '#6b7280',
                borderBottom: isActive ? '2px solid #2563eb' : '2px solid transparent',
                whiteSpace: 'nowrap',
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Content list */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: '#6b7280', fontSize: '14px' }}>
          Loading recommendations...
        </div>
      ) : filteredRecs.length === 0 ? (
        <div
          style={{
            textAlign: 'center',
            padding: '48px 20px',
            backgroundColor: '#f9fafb',
            borderRadius: '8px',
            border: '1px dashed #e5e7eb',
          }}
        >
          <div style={{ fontSize: '32px', marginBottom: '8px' }}>🎉</div>
          <div style={{ fontSize: '15px', fontWeight: 600, color: '#374151' }}>
            No recommendations in this view
          </div>
          <p style={{ fontSize: '13px', color: '#6b7280', marginTop: '4px', maxWidth: '420px', margin: '4px auto 16px auto' }}>
            {activeTab === 'resolved'
              ? 'No resolved recommendations yet. When you complete action items, mark them as resolved.'
              : 'Run a technical crawl, track search keywords, or click "Generate Recommendations" above to refresh.'}
          </p>
          {activeTab !== 'resolved' && (
            <button
              type="button"
              onClick={handleGenerate}
              disabled={generating}
              style={{
                padding: '8px 16px',
                backgroundColor: '#ffffff',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                fontSize: '13px',
                fontWeight: 600,
                color: '#374151',
                cursor: 'pointer',
              }}
            >
              Run Audit &amp; Refresh
            </button>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {filteredRecs.map((rec) => {
            const isExpanded = expandedRecId === rec.id;
            return (
              <div
                key={rec.id}
                style={{
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  backgroundColor: rec.status === 'resolved' ? '#fafafa' : '#ffffff',
                  padding: '16px',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
                  opacity: rec.status === 'resolved' || rec.status === 'dismissed' ? 0.85 : 1,
                }}
              >
                {/* Header Row */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    justifyContent: 'space-between',
                    gap: '12px',
                    flexWrap: 'wrap',
                  }}
                >
                  <div style={{ flex: 1, minWidth: '240px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                      {getSeverityBadge(rec.severity)}
                      {getSourceBadge(rec.source_type)}
                      <span
                        style={{
                          fontSize: '11px',
                          color: '#6b7280',
                          backgroundColor: '#f3f4f6',
                          padding: '2px 6px',
                          borderRadius: '4px',
                        }}
                      >
                        Priority {rec.priority}/100
                      </span>
                      {rec.status === 'acknowledged' && (
                        <span style={{ fontSize: '11px', color: '#b45309', fontWeight: 600 }}>● Acknowledged</span>
                      )}
                      {rec.status === 'resolved' && (
                        <span style={{ fontSize: '11px', color: '#15803d', fontWeight: 600 }}>✓ Resolved</span>
                      )}
                      {rec.status === 'dismissed' && (
                        <span style={{ fontSize: '11px', color: '#9ca3af', fontWeight: 600 }}>✕ Dismissed</span>
                      )}
                    </div>

                    <h4
                      onClick={() => setExpandedRecId(isExpanded ? null : rec.id)}
                      style={{
                        margin: '0 0 6px 0',
                        fontSize: '15px',
                        fontWeight: 700,
                        color: '#111827',
                        cursor: 'pointer',
                        lineHeight: 1.4,
                      }}
                    >
                      {rec.title}
                    </h4>

                    {(rec.affected_url || rec.affected_keyword) && (
                      <div style={{ fontSize: '12px', color: '#4b5563', display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                        {rec.affected_url && (
                          <span style={{ wordBreak: 'break-all' }}>
                            <strong>URL:</strong> {rec.affected_url}
                          </span>
                        )}
                        {rec.affected_keyword && (
                          <span>
                            <strong>Keyword:</strong> "{rec.affected_keyword}"
                          </span>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Actions */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {rec.status === 'open' && (
                      <button
                        type="button"
                        onClick={() => handleStatusChange(rec.id, 'acknowledge')}
                        style={{
                          padding: '6px 10px',
                          fontSize: '12px',
                          fontWeight: 600,
                          backgroundColor: '#fefce8',
                          color: '#a16207',
                          border: '1px solid #fde047',
                          borderRadius: '6px',
                          cursor: 'pointer',
                        }}
                      >
                        Acknowledge
                      </button>
                    )}
                    {rec.status !== 'resolved' ? (
                      <button
                        type="button"
                        onClick={() => handleStatusChange(rec.id, 'resolve')}
                        style={{
                          padding: '6px 10px',
                          fontSize: '12px',
                          fontWeight: 600,
                          backgroundColor: '#f0fdf4',
                          color: '#15803d',
                          border: '1px solid #bbf7d0',
                          borderRadius: '6px',
                          cursor: 'pointer',
                        }}
                      >
                        ✓ Mark Resolved
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleStatusChange(rec.id, 'reopen')}
                        style={{
                          padding: '6px 10px',
                          fontSize: '12px',
                          fontWeight: 600,
                          backgroundColor: '#ffffff',
                          color: '#374151',
                          border: '1px solid #d1d5db',
                          borderRadius: '6px',
                          cursor: 'pointer',
                        }}
                      >
                        Re-open
                      </button>
                    )}
                    {rec.status !== 'dismissed' && rec.status !== 'resolved' && (
                      <button
                        type="button"
                        onClick={() => handleStatusChange(rec.id, 'dismiss')}
                        style={{
                          padding: '6px 10px',
                          fontSize: '12px',
                          color: '#9ca3af',
                          backgroundColor: 'transparent',
                          border: 'none',
                          cursor: 'pointer',
                        }}
                      >
                        Dismiss
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => setExpandedRecId(isExpanded ? null : rec.id)}
                      style={{
                        padding: '6px 10px',
                        fontSize: '12px',
                        fontWeight: 600,
                        color: '#4b5563',
                        backgroundColor: '#f3f4f6',
                        border: 'none',
                        borderRadius: '6px',
                        cursor: 'pointer',
                      }}
                    >
                      {isExpanded ? 'Less ▲' : 'Details ▼'}
                    </button>
                  </div>
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div
                    style={{
                      marginTop: '16px',
                      paddingTop: '16px',
                      borderTop: '1px solid #f3f4f6',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '12px',
                    }}
                  >
                    <div>
                      <div style={{ fontSize: '11px', fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', marginBottom: '4px' }}>
                        Explanation
                      </div>
                      <div
                        style={{
                          fontSize: '13px',
                          color: '#374151',
                          lineHeight: 1.6,
                          whiteSpace: 'pre-line',
                        }}
                      >
                        {rec.description}
                      </div>
                    </div>

                    <div
                      style={{
                        backgroundColor: '#eff6ff',
                        padding: '12px',
                        borderRadius: '6px',
                        border: '1px solid #dbeafe',
                      }}
                    >
                      <div style={{ fontSize: '11px', fontWeight: 700, color: '#1d4ed8', textTransform: 'uppercase', marginBottom: '4px' }}>
                        Recommended Action
                      </div>
                      <div style={{ fontSize: '13px', color: '#1e3a8a', lineHeight: 1.5 }}>
                        {rec.recommended_action}
                      </div>
                    </div>

                    <div style={{ fontSize: '11px', color: '#9ca3af', display: 'flex', justifyContent: 'space-between' }}>
                      <span>Created: {new Date(rec.created_at).toLocaleDateString()}</span>
                      {rec.resolved_at && <span>Resolved: {new Date(rec.resolved_at).toLocaleDateString()}</span>}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
};
