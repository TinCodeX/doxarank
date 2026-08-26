import React, { useState, useEffect, useCallback, useMemo } from 'react';
import type { Project } from '../types/project';
import type {
  SEOContentDraft,
  DraftStatus,
  DraftSection,
  DraftFAQItem
} from '../types/seoContentDraft';
import type { BriefContentType } from '../types/seoContentBrief';
import {
  getSEOContentDrafts,
  generateSEOContentDraft,
  updateSEOContentDraft,
  deleteSEOContentDraft,
  downloadSEOContentDraft
} from '../api/seoContentDrafts';

interface SEOContentDraftPanelProps {
  currentProject: Project | null;
  targetBriefId?: number | null;
  onClearTargetBrief?: () => void;
}

export const SEOContentDraftPanel: React.FC<SEOContentDraftPanelProps> = ({
  currentProject,
  targetBriefId,
  onClearTargetBrief,
}) => {
  const [drafts, setDrafts] = useState<SEOContentDraft[]>([]);
  const [selectedDraftId, setSelectedDraftId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [feedbackMsg, setFeedbackMsg] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);
  const [filterType, setFilterType] = useState<BriefContentType | 'all'>('all');
  const [filterStatus, setFilterStatus] = useState<DraftStatus | 'all'>('all');
  const [activeTab, setActiveTab] = useState<'editor' | 'optimization' | 'schema'>('editor');

  // Editable local state for active draft
  const [editTitle, setEditTitle] = useState<string>('');
  const [editMetaTitle, setEditMetaTitle] = useState<string>('');
  const [editMetaDesc, setEditMetaDesc] = useState<string>('');
  const [editSlug, setEditSlug] = useState<string>('');
  const [editIntro, setEditIntro] = useState<string>('');
  const [editSections, setEditSections] = useState<DraftSection[]>([]);
  const [editFAQs, setEditFAQs] = useState<DraftFAQItem[]>([]);
  const [isDirty, setIsDirty] = useState<boolean>(false);

  const activeDraft = useMemo(() => {
    return drafts.find((d) => d.id === selectedDraftId) || drafts[0] || null;
  }, [drafts, selectedDraftId]);

  // Sync local edit state when activeDraft changes
  useEffect(() => {
    if (activeDraft) {
      setEditTitle(activeDraft.title || '');
      setEditMetaTitle(activeDraft.meta_title || '');
      setEditMetaDesc(activeDraft.meta_description || '');
      setEditSlug(activeDraft.suggested_slug || '');
      setEditIntro(activeDraft.introduction || '');
      setEditSections(activeDraft.outline_structure || []);
      setEditFAQs(activeDraft.faq_section || []);
      setIsDirty(false);
    }
  }, [activeDraft]);

  const showFeedback = useCallback((text: string, type: 'success' | 'error' | 'info' = 'success') => {
    setFeedbackMsg({ text, type });
    setTimeout(() => setFeedbackMsg(null), 5000);
  }, []);

  const loadDrafts = useCallback(
    async (preferredDraftId?: number | null) => {
      if (!currentProject) {
        setDrafts([]);
        setSelectedDraftId(null);
        return;
      }

      setIsLoading(true);
      try {
        const data = await getSEOContentDrafts({ project_id: currentProject.id });
        setDrafts(data);

        if (data.length > 0) {
          if (preferredDraftId && data.some((d) => d.id === preferredDraftId)) {
            setSelectedDraftId(preferredDraftId);
          } else if (targetBriefId) {
            const match = data.find((d) => d.brief === targetBriefId);
            if (match) setSelectedDraftId(match.id);
            else setSelectedDraftId(data[0].id);
          } else if (!selectedDraftId || !data.some((d) => d.id === selectedDraftId)) {
            setSelectedDraftId(data[0].id);
          }
        } else {
          setSelectedDraftId(null);
        }
      } catch (err: any) {
        showFeedback(err?.message || 'Failed to load SEO content drafts.', 'error');
      } finally {
        setIsLoading(false);
      }
    },
    [currentProject, targetBriefId, selectedDraftId, showFeedback]
  );

  useEffect(() => {
    loadDrafts();
  }, [currentProject?.id]);

  // Handle incoming targetBriefId to auto-generate or switch
  useEffect(() => {
    if (targetBriefId && currentProject) {
      const existing = drafts.find((d) => d.brief === targetBriefId);
      if (existing) {
        setSelectedDraftId(existing.id);
      }
    }
  }, [targetBriefId, drafts, currentProject]);

  const handleGenerateDraft = async (briefId: number, isRegen: boolean = false) => {
    if (!currentProject) return;

    setIsGenerating(true);
    try {
      const newDraft = await generateSEOContentDraft({
        project_id: currentProject.id,
        content_brief_id: briefId,
        regenerate: isRegen,
      });

      showFeedback(
        isRegen
          ? `Draft for "${newDraft.title}" successfully regenerated!`
          : `SEO Content Draft for "${newDraft.title}" successfully generated!`,
        'success'
      );

      await loadDrafts(newDraft.id);
      if (onClearTargetBrief) onClearTargetBrief();
    } catch (err: any) {
      showFeedback(err?.message || 'Draft generation failed.', 'error');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSaveDraft = async () => {
    if (!activeDraft) return;

    setIsSaving(true);
    try {
      // Rebuild markdown body
      const bodyLines: string[] = [fHeading(1, editTitle), ''];
      if (editIntro) {
        bodyLines.push(editIntro, '');
      }
      for (const sec of editSections) {
        bodyLines.push(fHeading(sec.level === 'H3' ? 3 : 2, sec.heading), '');
        if (sec.content) bodyLines.push(sec.content, '');
      }
      if (editFAQs.length > 0) {
        bodyLines.push('## Frequently Asked Questions', '');
        for (const f of editFAQs) {
          bodyLines.push(`**Q: ${f.question}**`, f.answer, '');
        }
      }
      const fullBody = bodyLines.join('\n');

      const updated = await updateSEOContentDraft(activeDraft.id, {
        title: editTitle,
        meta_title: editMetaTitle,
        meta_description: editMetaDesc,
        suggested_slug: editSlug,
        introduction: editIntro,
        content_body: fullBody,
        outline_structure: editSections,
        faq_section: editFAQs,
      });

      setDrafts((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
      setIsDirty(false);
      showFeedback('All draft changes and SEO metrics saved successfully!', 'success');
    } catch (err: any) {
      showFeedback(err?.message || 'Failed to save draft changes.', 'error');
    } finally {
      setIsSaving(false);
    }
  };

  const handleStatusChange = async (draftId: number, status: DraftStatus) => {
    try {
      const updated = await updateSEOContentDraft(draftId, { status });
      setDrafts((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
      showFeedback(`Draft status changed to "${updated.status_display}"`, 'success');
    } catch (err: any) {
      showFeedback(err?.message || 'Failed to update draft status.', 'error');
    }
  };

  const handleDeleteDraft = async (draftId: number) => {
    if (!window.confirm('Are you sure you want to delete this SEO content draft?')) return;

    try {
      await deleteSEOContentDraft(draftId);
      showFeedback('SEO Content Draft deleted.', 'info');
      await loadDrafts();
    } catch (err: any) {
      showFeedback(err?.message || 'Failed to delete draft.', 'error');
    }
  };

  const handleExport = async (format: 'markdown' | 'html' | 'pdf') => {
    if (!activeDraft) return;

    try {
      await downloadSEOContentDraft(activeDraft.id, format, activeDraft.suggested_slug || 'seo_draft');
      showFeedback(`Downloaded ${format.toUpperCase()} export!`, 'success');
    } catch (err: any) {
      showFeedback(err?.message || `Failed to export as ${format}.`, 'error');
    }
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    showFeedback(`Copied ${label} to clipboard!`, 'info');
  };

  const fHeading = (level: number, text: string) => `${'#'.repeat(level)} ${text}`;

  const filteredDrafts = useMemo(() => {
    return drafts.filter((d) => {
      if (filterType !== 'all' && d.content_type !== filterType) return false;
      if (filterStatus !== 'all' && d.status !== filterStatus) return false;
      return true;
    });
  }, [drafts, filterType, filterStatus]);

  const getContentTypeBadge = (type: BriefContentType) => {
    switch (type) {
      case 'landing_page':
        return { icon: '🚀', label: 'Landing Page Draft', bg: '#eff6ff', text: '#1e40af', border: '#bfdbfe' };
      case 'page_optimization':
        return { icon: '🔄', label: 'Page Optimization Draft', bg: '#ecfdf5', text: '#065f46', border: '#a7f3d0' };
      case 'technical_implementation':
        return { icon: '⚙️', label: 'Technical SEO Spec', bg: '#fef2f2', text: '#991b1b', border: '#fecaca' };
      case 'blog_post':
      default:
        return { icon: '✍️', label: 'Article / Blog Draft', bg: '#f5f3ff', text: '#6d28d9', border: '#ddd6fe' };
    }
  };

  return (
    <section
      id="seo-content-drafts-section"
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
            <span style={{ fontSize: '26px' }}>✍️</span>
            <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 800, color: '#0f172a' }}>
              AI SEO Content Draft Writer
            </h2>
            <span
              style={{
                fontSize: '11px',
                fontWeight: 700,
                padding: '3px 8px',
                borderRadius: '12px',
                backgroundColor: '#f1f5f9',
                color: '#475569',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
              }}
            >
              Step 4: Draft & Review
            </span>
          </div>
          <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#64748b' }}>
            Transform structured content briefs into full, publish-ready SEO drafts with in-place human editing, live keyword density tracking, and multi-format exports.
          </p>
        </div>

        {/* Quick action buttons */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          {activeDraft && (
            <>
              {isDirty && (
                <button
                  id="save-draft-btn"
                  onClick={handleSaveDraft}
                  disabled={isSaving}
                  style={{
                    backgroundColor: '#10b981',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: '8px',
                    padding: '8px 16px',
                    fontSize: '13px',
                    fontWeight: 700,
                    cursor: 'pointer',
                    boxShadow: '0 2px 4px rgba(16,185,129,0.2)',
                  }}
                >
                  {isSaving ? 'Saving...' : '💾 Save Changes'}
                </button>
              )}

              <button
                id="regenerate-draft-btn"
                onClick={() => handleGenerateDraft(activeDraft.brief, true)}
                disabled={isGenerating}
                style={{
                  backgroundColor: '#ffffff',
                  color: '#475569',
                  border: '1px solid #cbd5e1',
                  borderRadius: '8px',
                  padding: '7px 14px',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {isGenerating ? 'Regenerating...' : '🔄 Regenerate'}
              </button>

              {/* Exports */}
              <div style={{ display: 'inline-flex', borderRadius: '8px', overflow: 'hidden', border: '1px solid #cbd5e1' }}>
                <button
                  id="export-draft-md-btn"
                  onClick={() => handleExport('markdown')}
                  style={{
                    backgroundColor: '#ffffff',
                    border: 'none',
                    borderRight: '1px solid #e2e8f0',
                    padding: '7px 12px',
                    fontSize: '12px',
                    fontWeight: 600,
                    color: '#1e293b',
                    cursor: 'pointer',
                  }}
                >
                  ⬇️ MD
                </button>
                <button
                  id="export-draft-html-btn"
                  onClick={() => handleExport('html')}
                  style={{
                    backgroundColor: '#ffffff',
                    border: 'none',
                    borderRight: '1px solid #e2e8f0',
                    padding: '7px 12px',
                    fontSize: '12px',
                    fontWeight: 600,
                    color: '#1e293b',
                    cursor: 'pointer',
                  }}
                >
                  🌐 HTML
                </button>
                <button
                  id="export-draft-pdf-btn"
                  onClick={() => handleExport('pdf')}
                  style={{
                    backgroundColor: '#ffffff',
                    border: 'none',
                    padding: '7px 12px',
                    fontSize: '12px',
                    fontWeight: 600,
                    color: '#1e293b',
                    cursor: 'pointer',
                  }}
                >
                  📄 PDF
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Toast Feedback */}
      {feedbackMsg && (
        <div
          id="draft-feedback-toast"
          style={{
            padding: '10px 16px',
            borderRadius: '8px',
            fontSize: '13px',
            fontWeight: 600,
            backgroundColor:
              feedbackMsg.type === 'error'
                ? '#fef2f2'
                : feedbackMsg.type === 'info'
                ? '#eff6ff'
                : '#ecfdf5',
            color:
              feedbackMsg.type === 'error'
                ? '#991b1b'
                : feedbackMsg.type === 'info'
                ? '#1e40af'
                : '#065f46',
            border: `1px solid ${
              feedbackMsg.type === 'error'
                ? '#fecaca'
                : feedbackMsg.type === 'info'
                ? '#bfdbfe'
                : '#a7f3d0'
            }`,
          }}
        >
          {feedbackMsg.text}
        </div>
      )}

      {/* Filter and Draft Tab Switcher */}
      {drafts.length > 0 && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '12px',
            borderBottom: '1px solid #e2e8f0',
            paddingBottom: '14px',
          }}
        >
          {/* Draft tabs */}
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', overflowX: 'auto', maxWidth: '100%', paddingBottom: '4px' }}>
            <span style={{ fontSize: '12px', fontWeight: 700, color: '#475569', textTransform: 'uppercase' }}>
              Drafts ({filteredDrafts.length}):
            </span>
            {filteredDrafts.map((d) => {
              const isSelected = selectedDraftId === d.id;
              const typeBadge = getContentTypeBadge(d.content_type);
              return (
                <button
                  key={d.id}
                  id={`select-draft-tab-${d.id}`}
                  onClick={() => setSelectedDraftId(d.id)}
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
                  <span>{d.title.length > 32 ? d.title.slice(0, 32) + '...' : d.title}</span>
                </button>
              );
            })}
          </div>

          {/* Quick Filters */}
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            <select
              id="draft-type-filter"
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
              id="draft-status-filter"
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
              <option value="generating">Generating</option>
              <option value="generated">Generated</option>
              <option value="reviewed">Reviewed</option>
              <option value="approved">Approved</option>
              <option value="published">Published</option>
              <option value="archived">Archived</option>
            </select>
          </div>
        </div>
      )}

      {/* Main Workspace Body */}
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: '48px 0', color: '#64748b', fontSize: '14px' }}>
          <p>Loading SEO content drafts...</p>
        </div>
      ) : !activeDraft ? (
        <div
          id="content-drafts-empty-state"
          style={{
            textAlign: 'center',
            padding: '48px 24px',
            backgroundColor: '#f8fafc',
            borderRadius: '12px',
            border: '1px dashed #cbd5e1',
          }}
        >
          <div style={{ fontSize: '36px', marginBottom: '10px' }}>📄</div>
          <h4 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 700, color: '#0f172a' }}>
            No content drafts generated yet for this project
          </h4>
          <p style={{ margin: '0 0 18px 0', fontSize: '14px', color: '#64748b', maxWidth: '460px', marginLeft: 'auto', marginRight: 'auto' }}>
            Generate structured content drafts directly from your SEO Content Briefs above. Click <strong>"✍️ Generate Draft"</strong> on any brief to start.
          </p>
        </div>
      ) : (
        <div id={`content-draft-workspace-${activeDraft.id}`} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Status & Overview Bar */}
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid #e2e8f0',
              borderRadius: '12px',
              padding: '16px 20px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '16px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              {/* Type Badge */}
              {(() => {
                const typeStyle = getContentTypeBadge(activeDraft.content_type);
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

              {/* Word Count */}
              <span
                style={{
                  fontSize: '12px',
                  fontWeight: 700,
                  padding: '3px 8px',
                  borderRadius: '6px',
                  backgroundColor: '#ecfdf5',
                  color: '#065f46',
                  border: '1px solid #a7f3d0',
                }}
              >
                📊 {activeDraft.word_count} words
              </span>

              {/* Target Keyword */}
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
                Keyword: <strong>{activeDraft.target_keyword || 'N/A'}</strong>
              </span>
            </div>

            {/* Workflow status pills */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '12px', color: '#64748b', fontWeight: 600 }}>Status:</span>
              <div style={{ display: 'flex', gap: '4px', backgroundColor: '#f1f5f9', padding: '3px', borderRadius: '8px' }}>
                {(['draft', 'reviewed', 'approved', 'published', 'archived'] as const).map((st) => {
                  const isSel = activeDraft.status === st;
                  const labels = { draft: 'Draft', reviewed: 'Reviewed', approved: 'Approved', published: 'Published', archived: 'Archived' };
                  return (
                    <button
                      key={st}
                      id={`draft-status-btn-${st}`}
                      onClick={() => handleStatusChange(activeDraft.id, st)}
                      style={{
                        padding: '4px 10px',
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: isSel ? 700 : 500,
                        border: 'none',
                        backgroundColor: isSel ? (st === 'approved' ? '#10b981' : '#ffffff') : 'transparent',
                        color: isSel ? (st === 'approved' ? '#ffffff' : '#0f172a') : '#64748b',
                        cursor: 'pointer',
                        boxShadow: isSel ? '0 1px 2px rgba(0,0,0,0.06)' : 'none',
                      }}
                    >
                      {labels[st]}
                    </button>
                  );
                })}
              </div>

              <button
                id={`delete-draft-btn-${activeDraft.id}`}
                onClick={() => handleDeleteDraft(activeDraft.id)}
                style={{
                  backgroundColor: '#ffffff',
                  color: '#ef4444',
                  border: '1px solid #fca5a5',
                  padding: '5px 10px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  fontWeight: 500,
                  cursor: 'pointer',
                  marginLeft: '4px',
                }}
              >
                Delete
              </button>
            </div>
          </div>

          {/* Sub-tab Switcher: Editor | SEO Optimization | Schema JSON-LD */}
          <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid #e2e8f0', paddingBottom: '8px' }}>
            <button
              id="draft-subtab-editor"
              onClick={() => setActiveTab('editor')}
              style={{
                padding: '8px 16px',
                borderRadius: '8px',
                fontSize: '13px',
                fontWeight: activeTab === 'editor' ? 700 : 500,
                border: activeTab === 'editor' ? '1px solid #2563eb' : '1px solid transparent',
                backgroundColor: activeTab === 'editor' ? '#eff6ff' : 'transparent',
                color: activeTab === 'editor' ? '#1e40af' : '#64748b',
                cursor: 'pointer',
              }}
            >
              📝 Draft Content Editor
            </button>
            <button
              id="draft-subtab-optimization"
              onClick={() => setActiveTab('optimization')}
              style={{
                padding: '8px 16px',
                borderRadius: '8px',
                fontSize: '13px',
                fontWeight: activeTab === 'optimization' ? 700 : 500,
                border: activeTab === 'optimization' ? '1px solid #2563eb' : '1px solid transparent',
                backgroundColor: activeTab === 'optimization' ? '#eff6ff' : 'transparent',
                color: activeTab === 'optimization' ? '#1e40af' : '#64748b',
                cursor: 'pointer',
              }}
            >
              🎯 SEO Optimization & Keyword Audit
            </button>
            <button
              id="draft-subtab-schema"
              onClick={() => setActiveTab('schema')}
              style={{
                padding: '8px 16px',
                borderRadius: '8px',
                fontSize: '13px',
                fontWeight: activeTab === 'schema' ? 700 : 500,
                border: activeTab === 'schema' ? '1px solid #2563eb' : '1px solid transparent',
                backgroundColor: activeTab === 'schema' ? '#eff6ff' : 'transparent',
                color: activeTab === 'schema' ? '#1e40af' : '#64748b',
                cursor: 'pointer',
              }}
            >
              ⚙️ Schema JSON-LD
            </button>
          </div>

          {/* TAB 1: EDITORIAL CONTENT EDITOR */}
          {activeTab === 'editor' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Metadata Spec Bar */}
              <div
                style={{
                  backgroundColor: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: '12px',
                  padding: '16px 20px',
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                  gap: '16px',
                }}
              >
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 700, color: '#475569' }}>Meta Title (H1 Proposal):</label>
                    <span style={{ fontSize: '11px', color: editMetaTitle.length >= 50 && editMetaTitle.length <= 60 ? '#16a34a' : '#64748b' }}>
                      {editMetaTitle.length} chars (Target: 50-60)
                    </span>
                  </div>
                  <input
                    type="text"
                    id="draft-meta-title-input"
                    value={editMetaTitle}
                    onChange={(e) => {
                      setEditMetaTitle(e.target.value);
                      setIsDirty(true);
                    }}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: '6px',
                      border: '1px solid #cbd5e1',
                      fontSize: '13px',
                      fontWeight: 600,
                      color: '#0f172a',
                    }}
                  />
                </div>

                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 700, color: '#475569' }}>Meta Description:</label>
                    <span style={{ fontSize: '11px', color: editMetaDesc.length >= 140 && editMetaDesc.length <= 160 ? '#16a34a' : '#b45309' }}>
                      {editMetaDesc.length} chars (Target: 140-160)
                    </span>
                  </div>
                  <input
                    type="text"
                    id="draft-meta-desc-input"
                    value={editMetaDesc}
                    onChange={(e) => {
                      setEditMetaDesc(e.target.value);
                      setIsDirty(true);
                    }}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: '6px',
                      border: '1px solid #cbd5e1',
                      fontSize: '13px',
                      color: '#334155',
                    }}
                  />
                </div>
              </div>

              {/* Title & Slug */}
              <div>
                <label style={{ fontSize: '12px', fontWeight: 700, color: '#475569', display: 'block', marginBottom: '4px' }}>
                  Draft Working Title (H1):
                </label>
                <input
                  type="text"
                  id="draft-title-input"
                  value={editTitle}
                  onChange={(e) => {
                    setEditTitle(e.target.value);
                    setIsDirty(true);
                  }}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    borderRadius: '8px',
                    border: '1px solid #cbd5e1',
                    fontSize: '16px',
                    fontWeight: 700,
                    color: '#0f172a',
                  }}
                />
              </div>

              {/* Introduction */}
              <div>
                <label style={{ fontSize: '12px', fontWeight: 700, color: '#475569', display: 'block', marginBottom: '4px' }}>
                  Opening Introduction / Search Intent Hook:
                </label>
                <textarea
                  id="draft-intro-textarea"
                  rows={3}
                  value={editIntro}
                  onChange={(e) => {
                    setEditIntro(e.target.value);
                    setIsDirty(true);
                  }}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    borderRadius: '8px',
                    border: '1px solid #cbd5e1',
                    fontSize: '14px',
                    lineHeight: '1.6',
                    color: '#334155',
                    fontFamily: 'inherit',
                  }}
                />
              </div>

              {/* Section Outlines & Body Copy */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                    Structured Sections ({editSections.length}):
                  </h3>
                  <button
                    onClick={() => copyToClipboard(activeDraft.content_body, 'Full Markdown Draft')}
                    style={{
                      background: 'none',
                      border: '1px solid #cbd5e1',
                      borderRadius: '6px',
                      padding: '4px 10px',
                      fontSize: '12px',
                      color: '#475569',
                      cursor: 'pointer',
                      fontWeight: 600,
                    }}
                  >
                    📋 Copy All (MD)
                  </button>
                </div>

                {editSections.map((sec, idx) => (
                  <div
                    key={idx}
                    id={`draft-section-editor-${idx}`}
                    style={{
                      border: '1px solid #e2e8f0',
                      borderRadius: '10px',
                      padding: '16px 18px',
                      backgroundColor: '#ffffff',
                    }}
                  >
                    <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '8px' }}>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: 800,
                          backgroundColor: sec.level === 'H1' ? '#f3e8ff' : '#eff6ff',
                          color: sec.level === 'H1' ? '#7c3aed' : '#2563eb',
                          padding: '2px 6px',
                          borderRadius: '4px',
                        }}
                      >
                        {sec.level}
                      </span>
                      <input
                        type="text"
                        value={sec.heading}
                        onChange={(e) => {
                          const updated = [...editSections];
                          updated[idx].heading = e.target.value;
                          setEditSections(updated);
                          setIsDirty(true);
                        }}
                        style={{
                          flex: 1,
                          padding: '6px 10px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          fontWeight: 700,
                          fontSize: '14px',
                          color: '#0f172a',
                        }}
                      />
                    </div>

                    <textarea
                      rows={5}
                      value={sec.content}
                      onChange={(e) => {
                        const updated = [...editSections];
                        updated[idx].content = e.target.value;
                        setEditSections(updated);
                        setIsDirty(true);
                      }}
                      placeholder="Write or edit section body copy..."
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        borderRadius: '6px',
                        border: '1px solid #cbd5e1',
                        fontSize: '13px',
                        lineHeight: '1.6',
                        color: '#334155',
                        fontFamily: 'inherit',
                      }}
                    />
                  </div>
                ))}
              </div>

              {/* FAQs */}
              {editFAQs.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                    ❓ Frequently Asked Questions (SERP Schema Targets)
                  </h3>
                  {editFAQs.map((faq, idx) => (
                    <div
                      key={idx}
                      style={{
                        border: '1px solid #fde68a',
                        borderRadius: '8px',
                        padding: '14px',
                        backgroundColor: '#fdfbf7',
                      }}
                    >
                      <input
                        type="text"
                        value={faq.question}
                        onChange={(e) => {
                          const updated = [...editFAQs];
                          updated[idx].question = e.target.value;
                          setEditFAQs(updated);
                          setIsDirty(true);
                        }}
                        style={{
                          width: '100%',
                          padding: '6px 10px',
                          borderRadius: '6px',
                          border: '1px solid #fde68a',
                          fontWeight: 700,
                          color: '#92400e',
                          marginBottom: '6px',
                          fontSize: '13px',
                        }}
                      />
                      <textarea
                        rows={2}
                        value={faq.answer}
                        onChange={(e) => {
                          const updated = [...editFAQs];
                          updated[idx].answer = e.target.value;
                          setEditFAQs(updated);
                          setIsDirty(true);
                        }}
                        style={{
                          width: '100%',
                          padding: '6px 10px',
                          borderRadius: '6px',
                          border: '1px solid #fde68a',
                          color: '#451a03',
                          fontSize: '13px',
                          lineHeight: '1.5',
                          fontFamily: 'inherit',
                        }}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* TAB 2: SEO OPTIMIZATION & KEYWORD DENSITY */}
          {activeTab === 'optimization' && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
              {/* Primary Target Keyword Metrics */}
              <div
                style={{
                  backgroundColor: '#ffffff',
                  border: '1px solid #e2e8f0',
                  borderRadius: '12px',
                  padding: '20px',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
                }}
              >
                <h4 style={{ margin: '0 0 14px 0', fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                  🎯 Primary Keyword Performance
                </h4>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '13px' }}>
                  <div>
                    <span style={{ color: '#64748b', fontSize: '12px' }}>Target Keyword:</span>
                    <div style={{ fontWeight: 700, fontSize: '16px', color: '#0f172a', marginTop: '2px' }}>
                      🔍 {activeDraft.target_keyword || 'N/A'}
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                    <div style={{ backgroundColor: '#f8fafc', padding: '10px', borderRadius: '8px', border: '1px solid #f1f5f9' }}>
                      <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 600 }}>Occurrences in Body:</span>
                      <div style={{ fontSize: '18px', fontWeight: 800, color: '#2563eb', marginTop: '2px' }}>
                        {activeDraft.keyword_usage?.target_keyword?.occurrences ?? 0}
                      </div>
                    </div>

                    <div style={{ backgroundColor: '#f8fafc', padding: '10px', borderRadius: '8px', border: '1px solid #f1f5f9' }}>
                      <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 600 }}>Keyword Density:</span>
                      <div style={{ fontSize: '18px', fontWeight: 800, color: '#10b981', marginTop: '2px' }}>
                        {activeDraft.keyword_usage?.target_keyword?.density_percent ?? 0}%
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                    <span>{activeDraft.keyword_usage?.target_keyword?.in_title ? '✅' : '⚠️'}</span>
                    <span style={{ color: '#334155', fontWeight: 600 }}>
                      {activeDraft.keyword_usage?.target_keyword?.in_title
                        ? 'Target keyword present in title / headline'
                        : 'Keyword missing from title'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Secondary Keywords Coverage */}
              <div
                style={{
                  backgroundColor: '#ffffff',
                  border: '1px solid #e2e8f0',
                  borderRadius: '12px',
                  padding: '20px',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                  <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                    📊 Secondary Keyword Coverage
                  </h4>
                  <span
                    style={{
                      fontSize: '12px',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: '6px',
                      backgroundColor: '#eff6ff',
                      color: '#1d4ed8',
                    }}
                  >
                    {activeDraft.keyword_usage?.secondary_coverage_percent ?? 0}% Covered
                  </span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '13px' }}>
                  {activeDraft.secondary_keywords && activeDraft.secondary_keywords.length > 0 ? (
                    activeDraft.secondary_keywords.map((kw, idx) => {
                      const count = activeDraft.keyword_usage?.secondary_keywords?.[kw] ?? 0;
                      const isFound = count > 0;
                      return (
                        <div
                          key={idx}
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            padding: '8px 12px',
                            borderRadius: '6px',
                            backgroundColor: isFound ? '#f0fdf4' : '#fef2f2',
                            border: `1px solid ${isFound ? '#bbf7d0' : '#fecaca'}`,
                          }}
                        >
                          <span style={{ fontWeight: 500, color: isFound ? '#166534' : '#991b1b' }}>
                            {isFound ? '✅' : '❌'} {kw}
                          </span>
                          <span style={{ fontSize: '12px', fontWeight: 700, color: isFound ? '#16a34a' : '#ef4444' }}>
                            {count}x
                          </span>
                        </div>
                      );
                    })
                  ) : (
                    <p style={{ color: '#64748b', fontSize: '13px' }}>No secondary keywords defined in brief.</p>
                  )}
                </div>
              </div>

              {/* Internal Link Anchor Opportunities */}
              <div
                style={{
                  backgroundColor: '#ffffff',
                  border: '1px solid #e2e8f0',
                  borderRadius: '12px',
                  padding: '20px',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
                }}
              >
                <h4 style={{ margin: '0 0 14px 0', fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                  🔗 Integrated Internal Links ({activeDraft.internal_links?.length || 0})
                </h4>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '13px' }}>
                  {activeDraft.internal_links && activeDraft.internal_links.length > 0 ? (
                    activeDraft.internal_links.map((link, idx) => (
                      <div
                        key={idx}
                        style={{
                          backgroundColor: '#f8fafc',
                          padding: '10px 12px',
                          borderRadius: '6px',
                          border: '1px solid #e2e8f0',
                        }}
                      >
                        <div style={{ fontWeight: 600, color: '#2563eb' }}>
                          Anchor: "{link.anchor_text}"
                        </div>
                        <div style={{ fontSize: '12px', color: '#64748b' }}>
                          Target: <span style={{ fontFamily: 'monospace' }}>{link.target_url}</span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <p style={{ color: '#64748b', fontSize: '13px' }}>No internal links suggested.</p>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: SCHEMA JSON-LD */}
          {activeTab === 'schema' && (
            <div
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid #e2e8f0',
                borderRadius: '12px',
                padding: '20px 24px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '18px' }}>⚙️</span>
                  <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
                    Structured Schema.org JSON-LD Output
                  </h3>
                </div>
                <button
                  id="copy-schema-btn"
                  onClick={() => copyToClipboard(JSON.stringify(activeDraft.schema_json_ld, null, 2), 'Schema JSON-LD')}
                  style={{
                    backgroundColor: '#ffffff',
                    border: '1px solid #cbd5e1',
                    borderRadius: '6px',
                    padding: '5px 12px',
                    fontSize: '12px',
                    fontWeight: 600,
                    color: '#2563eb',
                    cursor: 'pointer',
                  }}
                >
                  📋 Copy JSON-LD
                </button>
              </div>

              <pre
                style={{
                  backgroundColor: '#0f172a',
                  color: '#38bdf8',
                  padding: '16px',
                  borderRadius: '8px',
                  fontSize: '13px',
                  lineHeight: '1.5',
                  overflowX: 'auto',
                  fontFamily: 'monospace',
                }}
              >
                {JSON.stringify(activeDraft.schema_json_ld, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </section>
  );
};
