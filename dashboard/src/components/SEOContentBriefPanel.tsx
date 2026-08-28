import React, { useState, useEffect, useCallback, useMemo } from 'react';
import type { Project } from '../types/project';
import type {
  SEOContentBrief,
  BriefContentType,
  BriefStatus
} from '../types/seoContentBrief';
import {
  getSEOContentBriefs,
  generateSEOContentBrief,
  updateSEOContentBrief,
  deleteSEOContentBrief,
  downloadSEOContentBrief
} from '../api/seoContentBriefs';

interface SEOContentBriefPanelProps {
  project: Project;
  selectedRecommendationId?: number | null;
  onClearSelectedRecId?: () => void;
  onSelectBriefForDraft?: (briefId: number) => void;
  onCreateAction?: (briefId: number) => void;
}

export const SEOContentBriefPanel: React.FC<SEOContentBriefPanelProps> = ({
  project,
  selectedRecommendationId,
  onClearSelectedRecId,
  onSelectBriefForDraft,
  onCreateAction,
}) => {
  const [briefs, setBriefs] = useState<SEOContentBrief[]>([]);
  const [selectedBriefId, setSelectedBriefId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [isExporting, setIsExporting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Filters
  const [filterType, setFilterType] = useState<'all' | BriefContentType>('all');
  const [filterStatus, setFilterStatus] = useState<'all' | BriefStatus>('all');

  // Load all briefs for the active project
  const fetchBriefs = useCallback(async (projectId: number, autoSelectRecId?: number | null) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getSEOContentBriefs({ project_id: projectId });
      setBriefs(data);

      if (autoSelectRecId) {
        const matched = data.find((b) => b.recommendation === autoSelectRecId);
        if (matched) {
          setSelectedBriefId(matched.id);
        } else if (data.length > 0) {
          setSelectedBriefId(data[0].id);
        } else {
          setSelectedBriefId(null);
        }
      } else if (data.length > 0) {
        // Keep selected if exists, otherwise first
        setSelectedBriefId((prev) => (prev && data.some((b) => b.id === prev) ? prev : data[0].id));
      } else {
        setSelectedBriefId(null);
      }
    } catch (err: any) {
      setError(err?.data?.detail || 'Failed to load SEO content briefs.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Reload when project changes
  useEffect(() => {
    if (project?.id) {
      setToastMessage(null);
      fetchBriefs(project.id, selectedRecommendationId);
    } else {
      setBriefs([]);
      setSelectedBriefId(null);
    }
  }, [project?.id, selectedRecommendationId, fetchBriefs]);

  // Handle generating a new brief or regenerating the current brief
  const handleGenerateBrief = async (recId: number, typeOverride?: BriefContentType) => {
    if (!project?.id || isGenerating) return;
    setIsGenerating(true);
    setError(null);
    setToastMessage(null);
    try {
      const generated = await generateSEOContentBrief({
        project_id: project.id,
        recommendation_id: recId,
        content_type: typeOverride
      });
      setToastMessage(`Content brief generated successfully: "${generated.title}"`);
      await fetchBriefs(project.id);
      setSelectedBriefId(generated.id);
      if (onClearSelectedRecId) onClearSelectedRecId();
    } catch (err: any) {
      setError(err?.data?.detail || err?.data?.recommendation_id || 'Failed to synthesize content brief.');
    } finally {
      setIsGenerating(false);
    }
  };

  // Status transition handler
  const handleStatusChange = async (briefId: number, newStatus: BriefStatus) => {
    try {
      const updated = await updateSEOContentBrief(briefId, { status: newStatus });
      setBriefs((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
      setToastMessage(`Brief status updated to ${newStatus.replace('_', ' ').toUpperCase()}`);
    } catch (err: any) {
      setError(err?.data?.detail || 'Failed to update brief status.');
    }
  };

  // Delete brief
  const handleDeleteBrief = async (briefId: number) => {
    if (!window.confirm('Are you sure you want to delete this content brief?')) return;
    try {
      await deleteSEOContentBrief(briefId);
      const remaining = briefs.filter((b) => b.id !== briefId);
      setBriefs(remaining);
      setSelectedBriefId(remaining.length > 0 ? remaining[0].id : null);
      setToastMessage('Content brief deleted.');
    } catch (err: any) {
      setError(err?.data?.detail || 'Failed to delete content brief.');
    }
  };

  // Direct export download handler
  const handleDownload = async (brief: SEOContentBrief, format: 'markdown' | 'csv' | 'pdf') => {
    setIsExporting(format);
    setError(null);
    try {
      const slugSafe = brief.suggested_slug.replace(/^\/+|\/+$/g, '').replace(/[/\\?%*:|"<>]/g, '-') || `brief_${brief.id}`;
      await downloadSEOContentBrief(brief.id, format, `${slugSafe}_brief`);
      setToastMessage(`Downloaded ${format.toUpperCase()} export for "${brief.title}"`);
    } catch (err: any) {
      setError(err.message || `Failed to download ${format.toUpperCase()} export.`);
    } finally {
      setIsExporting(null);
    }
  };

  // Copy to clipboard helper
  const copyToClipboard = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setToastMessage(`Copied ${label} to clipboard!`);
    } catch {
      // Fallback
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setToastMessage(`Copied ${label} to clipboard!`);
    }
  };

  // Selected brief object
  const activeBrief = useMemo(() => {
    return briefs.find((b) => b.id === selectedBriefId) || (briefs.length > 0 ? briefs[0] : null);
  }, [briefs, selectedBriefId]);

  // Filtered briefs list for selector tabs
  const filteredBriefs = useMemo(() => {
    return briefs.filter((b) => {
      if (filterType !== 'all' && b.content_type !== filterType) return false;
      if (filterStatus !== 'all' && b.status !== filterStatus) return false;
      return true;
    });
  }, [briefs, filterType, filterStatus]);

  // Copy full brief as Markdown
  const copyFullBriefAsMarkdown = (brief: SEOContentBrief) => {
    const lines = [
      `# SEO Content Brief: ${brief.title}`,
      `**Project:** ${brief.project_name}`,
      `**Target Keyword:** ${brief.target_keyword}`,
      `**Content Type:** ${brief.content_type_display} | **Search Intent:** ${brief.search_intent_display}`,
      `**Target URL:** ${brief.target_url || 'N/A'}`,
      `**Recommended Title:** ${brief.recommended_title}`,
      `**Meta Description:** ${brief.meta_description}`,
      `**Audience:** ${brief.audience}`,
      `**Content Angle:** ${brief.content_angle}`,
      '',
      '## Key Points',
      ...(brief.key_points || []).map((kp) => `- ${kp}`),
      '',
      '## Content Outline',
      ...(brief.outline || []).map((sec) => `${sec.level === 'H1' ? '#' : sec.level === 'H2' ? '##' : '###'} ${sec.heading}\n${(sec.key_points || []).map((p) => `  - ${p}`).join('\n')}`),
      '',
      '## Internal Link Suggestions',
      ...(brief.internal_link_suggestions || []).map((l) => `- [${l.anchor_text}](${l.target_url}) — ${l.context}`),
      '',
      '## FAQs',
      ...(brief.faq_questions || []).map((f) => `**Q: ${f.question}**\n*${f.answer_guidance}*`),
    ];
    copyToClipboard(lines.join('\n'), 'full content brief in Markdown');
  };

  const getContentTypeBadge = (type: BriefContentType) => {
    switch (type) {
      case 'landing_page':
        return { icon: '🎯', label: 'Landing Page', bg: '#eff6ff', text: '#1d4ed8', border: '#bfdbfe' };
      case 'page_optimization':
        return { icon: '🔄', label: 'Page Refresh & Optimization', bg: '#fef3c7', text: '#92400e', border: '#fde68a' };
      case 'technical_implementation':
        return { icon: '⚙️', label: 'Technical SEO Implementation', bg: '#fef2f2', text: '#991b1b', border: '#fecaca' };
      case 'blog_post':
      default:
        return { icon: '📝', label: 'In-Depth Article / Blog', bg: '#f5f3ff', text: '#6d28d9', border: '#ddd6fe' };
    }
  };

  return (
    <section
      id="seo-content-briefs-section"
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
                color: '#0369a1',
                backgroundColor: '#f0f9ff',
                padding: '3px 10px',
                borderRadius: '6px',
                border: '1px solid #bae6fd',
              }}
            >
              📋 SEO Content Briefs & Export Engine
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
              Writer & Developer Ready
            </span>
            <span style={{ fontSize: '13px', color: '#64748b' }}>
              Project: <strong style={{ color: '#0f172a' }}>{project.name}</strong>
            </span>
          </div>
          <h2 style={{ margin: 0, fontSize: '24px', fontWeight: 800, color: '#0f172a', letterSpacing: '-0.02em' }}>
            Content Brief Workspace
          </h2>
          <p style={{ margin: '4px 0 0 0', fontSize: '14px', color: '#64748b' }}>
            Synthesize grounded AI recommendations into structured copy briefs, export in Markdown/CSV/PDF, and assign to teams.
          </p>
        </div>

        {/* Global actions */}
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          {activeBrief && (
            <>
              {/* Copy Full Brief */}
              <button
                id="copy-full-brief-btn"
                onClick={() => copyFullBriefAsMarkdown(activeBrief)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  backgroundColor: '#ffffff',
                  color: '#334155',
                  border: '1px solid #cbd5e1',
                  padding: '9px 15px',
                  borderRadius: '8px',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                }}
              >
                📋 Copy All (MD)
              </button>

              {/* Download Markdown */}
              <button
                id="export-markdown-btn"
                onClick={() => handleDownload(activeBrief, 'markdown')}
                disabled={isExporting === 'markdown'}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  backgroundColor: '#ffffff',
                  color: '#0284c7',
                  border: '1px solid #bae6fd',
                  padding: '9px 15px',
                  borderRadius: '8px',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: isExporting ? 'not-allowed' : 'pointer',
                }}
              >
                ⬇️ Markdown
              </button>

              {/* Download CSV */}
              <button
                id="export-csv-btn"
                onClick={() => handleDownload(activeBrief, 'csv')}
                disabled={isExporting === 'csv'}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  backgroundColor: '#ffffff',
                  color: '#059669',
                  border: '1px solid #a7f3d0',
                  padding: '9px 15px',
                  borderRadius: '8px',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: isExporting ? 'not-allowed' : 'pointer',
                }}
              >
                📊 CSV
              </button>

              {/* Download PDF */}
              <button
                id="export-pdf-btn"
                onClick={() => handleDownload(activeBrief, 'pdf')}
                disabled={isExporting === 'pdf'}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  backgroundColor: '#ffffff',
                  color: '#dc2626',
                  border: '1px solid #fecaca',
                  padding: '9px 15px',
                  borderRadius: '8px',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: isExporting ? 'not-allowed' : 'pointer',
                }}
              >
                📄 PDF
              </button>

              {/* Regenerate Brief Button */}
              {activeBrief.recommendation && (
                <button
                  id="regenerate-brief-btn"
                  onClick={() => handleGenerateBrief(activeBrief.recommendation!, activeBrief.content_type)}
                  disabled={isGenerating}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    backgroundColor: isGenerating ? '#93c5fd' : '#2563eb',
                    color: '#ffffff',
                    border: 'none',
                    padding: '9px 16px',
                    borderRadius: '8px',
                    fontSize: '13px',
                    fontWeight: 700,
                    cursor: isGenerating ? 'not-allowed' : 'pointer',
                    boxShadow: '0 2px 4px rgba(37, 99, 235, 0.2)',
                  }}
                >
                  {isGenerating ? '🔄 Regenerating...' : '✨ Regenerate Brief'}
                </button>
              )}

              {/* Generate Draft Button */}
              {onSelectBriefForDraft && (
                <button
                  id={`create-draft-from-brief-${activeBrief.id}-btn`}
                  onClick={() => onSelectBriefForDraft(activeBrief.id)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    backgroundColor: '#10b981',
                    color: '#ffffff',
                    border: 'none',
                    padding: '9px 16px',
                    borderRadius: '8px',
                    fontSize: '13px',
                    fontWeight: 700,
                    cursor: 'pointer',
                    boxShadow: '0 2px 4px rgba(16, 185, 129, 0.2)',
                  }}
                >
                  ✍️ Write SEO Draft
                </button>
              )}

              {/* Create SEO Action Button */}
              {onCreateAction && (
                <button
                  id={`create-action-from-brief-${activeBrief.id}-btn`}
                  onClick={() => onCreateAction(activeBrief.id)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    backgroundColor: '#eff6ff',
                    color: '#1d4ed8',
                    border: '1px solid #bfdbfe',
                    padding: '9px 16px',
                    borderRadius: '8px',
                    fontSize: '13px',
                    fontWeight: 700,
                    cursor: 'pointer',
                  }}
                >
                  ⚡ Create SEO Action
                </button>
              )}

            </>
          )}
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div
          id="brief-error-alert"
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

      {toastMessage && (
        <div
          id="brief-success-toast"
          style={{
            backgroundColor: '#f0fdf4',
            color: '#166534',
            border: '1px solid #bbf7d0',
            borderRadius: '10px',
            padding: '12px 16px',
            fontSize: '14px',
            marginBottom: '20px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>✓ {toastMessage}</span>
          <button
            onClick={() => setToastMessage(null)}
            style={{ background: 'none', border: 'none', color: '#166534', cursor: 'pointer', fontWeight: 700 }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Briefs Selector / Tabs */}
      {briefs.length > 0 && (
        <div
          style={{
            backgroundColor: '#f8fafc',
            border: '1px solid #e2e8f0',
            borderRadius: '12px',
            padding: '14px 18px',
            marginBottom: '24px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
          {/* Brief tabs */}
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', overflowX: 'auto', maxWidth: '100%', paddingBottom: '4px' }}>
            <span style={{ fontSize: '12px', fontWeight: 700, color: '#475569', textTransform: 'uppercase' }}>
              Briefs ({filteredBriefs.length}):
            </span>
            {filteredBriefs.map((brief) => {
              const isSelected = selectedBriefId === brief.id;
              const typeBadge = getContentTypeBadge(brief.content_type);
              return (
                <button
                  key={brief.id}
                  id={`select-brief-tab-${brief.id}`}
                  onClick={() => setSelectedBriefId(brief.id)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '6px 12px',
                    borderRadius: '8px',
                    fontSize: '13px',
                    fontWeight: isSelected ? 700 : 500,
                    border: isSelected ? '1px solid #2563eb' : '1px solid #cbd5e1',
                    backgroundColor: isSelected ? '#eff6ff' : '#ffffff',
                    color: isSelected ? '#1e40af' : '#475569',
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                    boxShadow: isSelected ? '0 1px 3px rgba(37,99,235,0.15)' : 'none',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <span>{typeBadge.icon}</span>
                  <span>{brief.title.length > 32 ? brief.title.slice(0, 32) + '...' : brief.title}</span>
                </button>
              );
            })}
          </div>

          {/* Quick Filters */}
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            <select
              id="brief-type-filter"
              value={filterType}
              onChange={(e) => setFilterType(e.target.value as any)}
              style={{
                padding: '5px 10px',
                borderRadius: '6px',
                fontSize: '12px',
                fontWeight: 600,
                border: '1px solid #cbd5e1',
                backgroundColor: '#ffffff',
                color: '#334155',
                cursor: 'pointer',
              }}
            >
              <option value="all">All Content Types</option>
              <option value="blog_post">Blog / Article</option>
              <option value="landing_page">Landing Page</option>
              <option value="page_optimization">Page Optimization</option>
              <option value="technical_implementation">Technical Implementation</option>
            </select>

            <select
              id="brief-status-filter"
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value as any)}
              style={{
                padding: '5px 10px',
                borderRadius: '6px',
                fontSize: '12px',
                fontWeight: 600,
                border: '1px solid #cbd5e1',
                backgroundColor: '#ffffff',
                color: '#334155',
                cursor: 'pointer',
              }}
            >
              <option value="all">All Statuses</option>
              <option value="draft">Draft</option>
              <option value="in_progress">In Progress</option>
              <option value="completed">Completed</option>
              <option value="archived">Archived</option>
            </select>
          </div>
        </div>
      )}

      {/* Main Workspace Body */}
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: '48px 0', color: '#64748b', fontSize: '14px' }}>
          <p>Loading SEO content briefs...</p>
        </div>
      ) : !activeBrief ? (
        <div
          id="content-briefs-empty-state"
          style={{
            textAlign: 'center',
            padding: '48px 24px',
            backgroundColor: '#f8fafc',
            borderRadius: '12px',
            border: '1px dashed #cbd5e1',
          }}
        >
          <div style={{ fontSize: '36px', marginBottom: '10px' }}>📝</div>
          <h4 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 700, color: '#0f172a' }}>
            No content briefs generated yet for this project
          </h4>
          <p style={{ margin: '0 0 18px 0', fontSize: '14px', color: '#64748b', maxWidth: '460px', marginLeft: 'auto', marginRight: 'auto' }}>
            Generate structured content briefs directly from your AI SEO Recommendations above. Click <strong>"Generate Content Brief"</strong> on any recommendation card to start.
          </p>
        </div>
      ) : (
        <div id={`content-brief-workspace-${activeBrief.id}`} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Status & Overview Bar */}
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid #e2e8f0',
              borderRadius: '12px',
              padding: '20px 24px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '16px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              {/* Content Type Badge */}
              {(() => {
                const typeStyle = getContentTypeBadge(activeBrief.content_type);
                return (
                  <span
                    style={{
                      fontSize: '13px',
                      fontWeight: 700,
                      padding: '4px 10px',
                      borderRadius: '8px',
                      backgroundColor: typeStyle.bg,
                      color: typeStyle.text,
                      border: `1px solid ${typeStyle.border}`,
                    }}
                  >
                    {typeStyle.icon} {typeStyle.label}
                  </span>
                );
              })()}

              {/* Search Intent Badge */}
              <span
                style={{
                  fontSize: '12px',
                  fontWeight: 600,
                  padding: '3px 8px',
                  borderRadius: '6px',
                  backgroundColor: '#f1f5f9',
                  color: '#334155',
                }}
              >
                Intent: <strong>{activeBrief.search_intent_display}</strong>
              </span>

              {/* Word Count Target */}
              {activeBrief.content_length_target && (
                <span
                  style={{
                    fontSize: '12px',
                    fontWeight: 600,
                    padding: '3px 8px',
                    borderRadius: '6px',
                    backgroundColor: '#ecfdf5',
                    color: '#065f46',
                    border: '1px solid #a7f3d0',
                  }}
                >
                  🎯 Target: ~{activeBrief.content_length_target} words
                </span>
              )}
            </div>

            {/* Status Selector */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '12px', color: '#64748b', fontWeight: 600 }}>Status:</span>
              <div style={{ display: 'flex', gap: '4px', backgroundColor: '#f1f5f9', padding: '3px', borderRadius: '8px' }}>
                {(['draft', 'in_progress', 'completed', 'archived'] as const).map((stat) => {
                  const isSelected = activeBrief.status === stat;
                  const statLabels = { draft: 'Draft', in_progress: 'In Progress', completed: 'Completed', archived: 'Archived' };
                  return (
                    <button
                      key={stat}
                      id={`brief-status-btn-${stat}`}
                      onClick={() => handleStatusChange(activeBrief.id, stat)}
                      style={{
                        padding: '4px 10px',
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: isSelected ? 700 : 500,
                        border: 'none',
                        backgroundColor: isSelected ? '#ffffff' : 'transparent',
                        color: isSelected ? '#0f172a' : '#64748b',
                        cursor: 'pointer',
                        boxShadow: isSelected ? '0 1px 2px rgba(0,0,0,0.06)' : 'none',
                      }}
                    >
                      {statLabels[stat]}
                    </button>
                  );
                })}
              </div>

              <button
                id={`delete-brief-btn-${activeBrief.id}`}
                onClick={() => handleDeleteBrief(activeBrief.id)}
                style={{
                  backgroundColor: '#ffffff',
                  color: '#ef4444',
                  border: '1px solid #fca5a5',
                  padding: '5px 10px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  fontWeight: 500,
                  cursor: 'pointer',
                  marginLeft: '6px',
                }}
              >
                Delete
              </button>
            </div>
          </div>

          {/* GRID: 1. Overview & Strategy | 2. Metadata */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
              gap: '20px',
            }}
          >
            {/* Box 1: Strategy & Angle */}
            <div
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid #e2e8f0',
                borderRadius: '12px',
                padding: '20px 22px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                  🎯 Target Strategy & Positioning
                </h4>
                <button
                  onClick={() => copyToClipboard(`Target Keyword: ${activeBrief.target_keyword}\nAudience: ${activeBrief.audience}\nContent Angle: ${activeBrief.content_angle}`, 'Strategy')}
                  style={{ background: 'none', border: 'none', color: '#6366f1', fontSize: '12px', cursor: 'pointer', fontWeight: 600 }}
                >
                  Copy
                </button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '13px' }}>
                <div>
                  <span style={{ color: '#64748b', fontSize: '12px', fontWeight: 600 }}>Primary Target Keyword:</span>
                  <div style={{ marginTop: '2px', fontWeight: 700, color: '#0f172a', fontSize: '15px' }}>
                    🔍 {activeBrief.target_keyword || 'General SEO'}
                  </div>
                </div>

                {activeBrief.secondary_keywords && activeBrief.secondary_keywords.length > 0 && (
                  <div>
                    <span style={{ color: '#64748b', fontSize: '12px', fontWeight: 600 }}>Secondary Keyword Variations:</span>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '4px' }}>
                      {activeBrief.secondary_keywords.map((kw, idx) => (
                        <span
                          key={idx}
                          style={{
                            backgroundColor: '#f1f5f9',
                            color: '#334155',
                            padding: '3px 8px',
                            borderRadius: '6px',
                            fontSize: '12px',
                            fontWeight: 500,
                          }}
                        >
                          {kw}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div>
                  <span style={{ color: '#64748b', fontSize: '12px', fontWeight: 600 }}>Target Audience:</span>
                  <p style={{ margin: '2px 0 0 0', color: '#334155', lineHeight: '1.5' }}>
                    {activeBrief.audience}
                  </p>
                </div>

                <div>
                  <span style={{ color: '#64748b', fontSize: '12px', fontWeight: 600 }}>Editorial Angle & Value Proposition:</span>
                  <p style={{ margin: '2px 0 0 0', color: '#0f172a', lineHeight: '1.5', backgroundColor: '#f8fafc', padding: '8px 12px', borderRadius: '6px', border: '1px solid #f1f5f9' }}>
                    💡 {activeBrief.content_angle}
                  </p>
                </div>
              </div>
            </div>

            {/* Box 2: SEO Metadata Proposals */}
            <div
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid #e2e8f0',
                borderRadius: '12px',
                padding: '20px 22px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                  🏷️ SEO Metadata & Snippet Spec
                </h4>
                <button
                  onClick={() => copyToClipboard(`Title: ${activeBrief.recommended_title}\nDescription: ${activeBrief.meta_description}\nSlug: ${activeBrief.suggested_slug}`, 'Metadata')}
                  style={{ background: 'none', border: 'none', color: '#6366f1', fontSize: '12px', cursor: 'pointer', fontWeight: 600 }}
                >
                  Copy
                </button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', fontSize: '13px' }}>
                {/* Proposed Title Tag */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: '#64748b', fontSize: '12px', fontWeight: 600 }}>Recommended Title Tag (H1):</span>
                    <span style={{ fontSize: '11px', color: '#64748b' }}>{activeBrief.recommended_title.length} chars</span>
                  </div>
                  <div
                    style={{
                      backgroundColor: '#f8fafc',
                      border: '1px solid #cbd5e1',
                      borderRadius: '6px',
                      padding: '8px 12px',
                      marginTop: '4px',
                      fontWeight: 600,
                      color: '#1e3a8a',
                    }}
                  >
                    {activeBrief.recommended_title}
                  </div>
                </div>

                {/* Proposed Meta Description */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: '#64748b', fontSize: '12px', fontWeight: 600 }}>Recommended Meta Description:</span>
                    <span
                      style={{
                        fontSize: '11px',
                        fontWeight: 700,
                        color: activeBrief.meta_description.length >= 120 && activeBrief.meta_description.length <= 160 ? '#16a34a' : '#b45309',
                      }}
                    >
                      {activeBrief.meta_description.length} chars (Optimal: 140-160)
                    </span>
                  </div>
                  <div
                    style={{
                      backgroundColor: '#f8fafc',
                      border: '1px solid #cbd5e1',
                      borderRadius: '6px',
                      padding: '8px 12px',
                      marginTop: '4px',
                      color: '#334155',
                      lineHeight: '1.45',
                    }}
                  >
                    {activeBrief.meta_description}
                  </div>
                </div>

                {/* URL and Slug */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  <div>
                    <span style={{ color: '#64748b', fontSize: '12px', fontWeight: 600 }}>Target URL:</span>
                    <div style={{ marginTop: '2px', color: '#2563eb', wordBreak: 'break-all', fontSize: '12px' }}>
                      {activeBrief.target_url || '—'}
                    </div>
                  </div>
                  <div>
                    <span style={{ color: '#64748b', fontSize: '12px', fontWeight: 600 }}>Suggested Slug:</span>
                    <div style={{ marginTop: '2px', fontFamily: 'monospace', color: '#0f172a', fontSize: '12px' }}>
                      {activeBrief.suggested_slug || '—'}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Section: Content Outline */}
          <div
            id="brief-outline-section"
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid #e2e8f0',
              borderRadius: '12px',
              padding: '22px 24px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '18px' }}>📑</span>
                <h3 style={{ margin: 0, fontSize: '17px', fontWeight: 700, color: '#0f172a' }}>
                  Content Structure & Section Outline
                </h3>
              </div>
              <button
                id="copy-outline-btn"
                onClick={() => {
                  const outlineText = (activeBrief.outline || [])
                    .map((s) => `${s.level}: ${s.heading}\n${(s.key_points || []).map((p) => `  - ${p}`).join('\n')}`)
                    .join('\n\n');
                  copyToClipboard(outlineText, 'Outline');
                }}
                style={{
                  background: 'none',
                  border: '1px solid #cbd5e1',
                  borderRadius: '6px',
                  padding: '4px 10px',
                  color: '#475569',
                  fontSize: '12px',
                  cursor: 'pointer',
                  fontWeight: 600,
                }}
              >
                Copy Outline
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {activeBrief.outline && activeBrief.outline.length > 0 ? (
                activeBrief.outline.map((sec, idx) => (
                  <div
                    key={idx}
                    id={`outline-section-${idx}`}
                    style={{
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                      padding: '14px 18px',
                      backgroundColor: sec.level === 'H1' ? '#faf5ff' : '#ffffff',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span
                          style={{
                            fontSize: '11px',
                            fontWeight: 800,
                            color: sec.level === 'H1' ? '#7c3aed' : sec.level === 'H2' ? '#2563eb' : '#059669',
                            backgroundColor: sec.level === 'H1' ? '#f3e8ff' : sec.level === 'H2' ? '#eff6ff' : '#ecfdf5',
                            padding: '2px 6px',
                            borderRadius: '4px',
                          }}
                        >
                          {sec.level}
                        </span>
                        <strong style={{ fontSize: '15px', color: '#0f172a' }}>{sec.heading}</strong>
                      </div>
                      <button
                        onClick={() => copyToClipboard(`${sec.heading}\n${(sec.key_points || []).map((p) => `- ${p}`).join('\n')}`, `Section "${sec.heading}"`)}
                        style={{ background: 'none', border: 'none', color: '#6366f1', fontSize: '11px', cursor: 'pointer', fontWeight: 600 }}
                      >
                        Copy Section
                      </button>
                    </div>

                    {sec.key_points && sec.key_points.length > 0 && (
                      <ul style={{ margin: '6px 0 0 0', paddingLeft: '20px', color: '#475569', fontSize: '13px', lineHeight: '1.6' }}>
                        {sec.key_points.map((pt, pIdx) => (
                          <li key={pIdx}>{pt}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))
              ) : (
                <p style={{ color: '#64748b', fontSize: '13px', margin: 0 }}>No outline generated.</p>
              )}
            </div>
          </div>

          {/* Section: Optimization Guidance (Internal Links, Citations, FAQs, Entities) */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
              gap: '20px',
            }}
          >
            {/* Internal Links Guidance */}
            <div
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid #e2e8f0',
                borderRadius: '12px',
                padding: '20px 22px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                  🔗 Internal Linking Recommendations
                </h4>
              </div>

              {activeBrief.internal_link_suggestions && activeBrief.internal_link_suggestions.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {activeBrief.internal_link_suggestions.map((link, idx) => (
                    <div
                      key={idx}
                      style={{
                        backgroundColor: '#f8fafc',
                        border: '1px solid #f1f5f9',
                        borderRadius: '8px',
                        padding: '10px 14px',
                        fontSize: '13px',
                      }}
                    >
                      <div style={{ fontWeight: 600, color: '#1d4ed8', marginBottom: '2px' }}>
                        Anchor: "{link.anchor_text}"
                      </div>
                      <div style={{ fontSize: '12px', color: '#64748b' }}>
                        Target: <span style={{ fontFamily: 'monospace' }}>{link.target_url}</span>
                      </div>
                      {link.context && (
                        <div style={{ fontSize: '12px', color: '#475569', marginTop: '4px', fontStyle: 'italic' }}>
                          Placement: {link.context}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{ color: '#64748b', fontSize: '13px', margin: 0 }}>No internal link recommendations.</p>
              )}
            </div>

            {/* FAQs & SERP Schema Questions */}
            <div
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid #e2e8f0',
                borderRadius: '12px',
                padding: '20px 22px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                  ❓ Frequently Asked Questions (Schema Target)
                </h4>
              </div>

              {activeBrief.faq_questions && activeBrief.faq_questions.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {activeBrief.faq_questions.map((faq, idx) => (
                    <div
                      key={idx}
                      style={{
                        backgroundColor: '#fdfbf7',
                        border: '1px solid #fde68a',
                        borderRadius: '8px',
                        padding: '10px 14px',
                        fontSize: '13px',
                      }}
                    >
                      <strong style={{ color: '#92400e', display: 'block', marginBottom: '4px' }}>
                        Q: {faq.question}
                      </strong>
                      <p style={{ margin: 0, color: '#451a03', fontSize: '12px', lineHeight: '1.45' }}>
                        {faq.answer_guidance}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{ color: '#64748b', fontSize: '13px', margin: 0 }}>No FAQs suggested.</p>
              )}
            </div>
          </div>

          {/* Semantic Entities & External Citations */}
          {(activeBrief.entities_topics?.length > 0 || activeBrief.external_link_suggestions?.length > 0) && (
            <div
              style={{
                backgroundColor: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: '12px',
                padding: '18px 22px',
                display: 'flex',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '16px',
              }}
            >
              {/* Entities */}
              {activeBrief.entities_topics && activeBrief.entities_topics.length > 0 && (
                <div>
                  <span style={{ fontSize: '12px', fontWeight: 700, color: '#475569', textTransform: 'uppercase' }}>
                    Semantic Entities & Topical Nodes:
                  </span>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '6px' }}>
                    {activeBrief.entities_topics.map((entity, idx) => (
                      <span
                        key={idx}
                        style={{
                          backgroundColor: '#ffffff',
                          color: '#0f172a',
                          border: '1px solid #cbd5e1',
                          padding: '3px 8px',
                          borderRadius: '6px',
                          fontSize: '12px',
                          fontWeight: 600,
                        }}
                      >
                        🏷️ {entity}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Citations */}
              {activeBrief.external_link_suggestions && activeBrief.external_link_suggestions.length > 0 && (
                <div>
                  <span style={{ fontSize: '12px', fontWeight: 700, color: '#475569', textTransform: 'uppercase' }}>
                    Authoritative External Citations:
                  </span>
                  <ul style={{ margin: '6px 0 0 0', paddingLeft: '18px', fontSize: '12px', color: '#334155' }}>
                    {activeBrief.external_link_suggestions.map((ext, idx) => (
                      <li key={idx}>
                        <strong>{ext.source}</strong> (Anchor: "{ext.anchor_text}") — {ext.context}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
};
