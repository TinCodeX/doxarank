/**
 * TechnicalCrawlerPanel — Dashboard component for the DoxaRank Technical SEO Crawler.
 *
 * Features:
 *  - Launch a new crawl for the selected project (Starter/Agency gated)
 *  - Show queued / running / completed / failed status with live progress
 *  - Display crawl summary counters (pages crawled, issues found by category)
 *  - Tabular view of crawled pages with severity-coded issue badges
 *  - Filter pages by broken / slow / all
 *  - Error state with descriptive message
 *  - Empty state with call-to-action
 *  - Auto-polls running jobs every 8 seconds until terminal state
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { Project } from '../types/project';
import type {
  CrawlJob,
  CrawlPage,
  CrawlPageIssue,
  CrawlJobStatus,
} from '../types/crawlJob';
import {
  getCrawlJobs,
  getCrawlJob,
  launchCrawl,
  getCrawlPages,
} from '../api/crawls';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Props {
  project: Project;
  hasCrawlerEntitlement?: boolean;  // set from subscription summary
}

type PageFilter = 'all' | 'broken' | 'slow';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATUS_COLORS: Record<CrawlJobStatus, string> = {
  pending: '#f59e0b',
  running: '#3b82f6',
  completed: '#10b981',
  failed: '#ef4444',
  cancelled: '#6b7280',
};

const STATUS_LABELS: Record<CrawlJobStatus, string> = {
  pending: 'Queued',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#ef4444',
  warning: '#f59e0b',
  notice: '#6b7280',
};

const SEVERITY_BG: Record<string, string> = {
  critical: 'rgba(239,68,68,0.12)',
  warning: 'rgba(245,158,11,0.12)',
  notice: 'rgba(107,114,128,0.12)',
};

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

function fmtMs(ms: number): string {
  if (ms < 1000) return `${ms.toFixed(0)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

function isTerminal(status: CrawlJobStatus): boolean {
  return ['completed', 'failed', 'cancelled'].includes(status);
}

// ---------------------------------------------------------------------------
// Sub-component: Stat card
// ---------------------------------------------------------------------------

const StatCard: React.FC<{
  label: string;
  value: number;
  color?: string;
  icon?: string;
}> = ({ label, value, color = '#a78bfa', icon }) => (
  <div style={{
    background: 'rgba(255,255,255,0.04)',
    border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: 12,
    padding: '14px 18px',
    minWidth: 130,
    flex: 1,
  }}>
    <div style={{ fontSize: 22, fontWeight: 700, color, marginBottom: 4 }}>
      {icon && <span style={{ marginRight: 6 }}>{icon}</span>}
      {value.toLocaleString()}
    </div>
    <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
      {label}
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Sub-component: Issue badge
// ---------------------------------------------------------------------------

const IssueBadge: React.FC<{ issue: CrawlPageIssue }> = ({ issue }) => (
  <span style={{
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: 6,
    fontSize: 11,
    fontWeight: 600,
    color: SEVERITY_COLORS[issue.severity] ?? '#94a3b8',
    background: SEVERITY_BG[issue.severity] ?? 'rgba(107,114,128,0.1)',
    border: `1px solid ${SEVERITY_COLORS[issue.severity] ?? '#6b7280'}33`,
    marginRight: 4,
    marginBottom: 4,
    cursor: 'default',
  }} title={issue.message}>
    {issue.type.replace(/_/g, ' ')}
  </span>
);

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export const TechnicalCrawlerPanel: React.FC<Props> = ({
  project,
  hasCrawlerEntitlement = false,
}) => {
  const [crawlJobs, setCrawlJobs] = useState<CrawlJob[]>([]);
  const [selectedJob, setSelectedJob] = useState<CrawlJob | null>(null);
  const [pages, setPages] = useState<CrawlPage[]>([]);
  const [pageFilter, setPageFilter] = useState<PageFilter>('all');

  const [isLoadingJobs, setIsLoadingJobs] = useState(false);
  const [isLoadingPages, setIsLoadingPages] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);

  const [jobError, setJobError] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [launchSuccess, setLaunchSuccess] = useState<string | null>(null);

  // Crawl config form
  const [maxPages, setMaxPages] = useState(100);
  const [maxDepth, setMaxDepth] = useState(3);
  const [respectRobots, setRespectRobots] = useState(true);
  const [showConfig, setShowConfig] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // -------------------------------------------------------------------------
  // Data fetching
  // -------------------------------------------------------------------------

  const fetchJobs = useCallback(async () => {
    if (!project?.id) return;
    setIsLoadingJobs(true);
    setJobError(null);
    try {
      const data = await getCrawlJobs(project.id);
      setCrawlJobs(data);
      if (data.length > 0 && !selectedJob) {
        setSelectedJob(data[0]);
      }
    } catch (err: any) {
      const msg = err?.data?.detail || err?.data?.error || 'Failed to load crawl history.';
      setJobError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setIsLoadingJobs(false);
    }
  }, [project?.id, selectedJob]);

  const fetchPages = useCallback(async (jobId: number) => {
    setIsLoadingPages(true);
    setPageError(null);
    try {
      const filters =
        pageFilter === 'broken' ? { is_broken: true } :
        pageFilter === 'slow'   ? { is_slow: true }   : undefined;
      const data = await getCrawlPages(jobId, filters);
      setPages(data);
    } catch (err: any) {
      setPageError(err?.data?.detail || 'Failed to load crawl pages.');
    } finally {
      setIsLoadingPages(false);
    }
  }, [pageFilter]);

  const pollJobStatus = useCallback(async (jobId: number) => {
    try {
      const updated = await getCrawlJob(jobId);
      setCrawlJobs(prev => prev.map(j => j.id === updated.id ? updated : j));
      if (selectedJob?.id === updated.id) {
        setSelectedJob(updated);
      }
      if (isTerminal(updated.status)) {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }
    } catch {
      // Silently ignore poll errors
    }
  }, [selectedJob?.id]);

  // -------------------------------------------------------------------------
  // Effects
  // -------------------------------------------------------------------------

  useEffect(() => {
    setSelectedJob(null);
    setCrawlJobs([]);
    setPages([]);
    fetchJobs();
  }, [project?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (selectedJob) {
      fetchPages(selectedJob.id);
    } else {
      setPages([]);
    }
  }, [selectedJob?.id, pageFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  // Start polling when a job is running/pending
  useEffect(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    const runningJob = crawlJobs.find(j => !isTerminal(j.status));
    if (runningJob) {
      pollRef.current = setInterval(() => pollJobStatus(runningJob.id), 8000);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [crawlJobs, pollJobStatus]);

  // -------------------------------------------------------------------------
  // Actions
  // -------------------------------------------------------------------------

  const handleLaunch = async () => {
    setLaunchError(null);
    setLaunchSuccess(null);
    setIsLaunching(true);
    try {
      const result = await launchCrawl({
        project_id: project.id,
        max_pages: maxPages,
        max_depth: maxDepth,
        respect_robots_txt: respectRobots,
      });
      const newJob = result.crawl_job;
      setCrawlJobs(prev => [newJob, ...prev]);
      setSelectedJob(newJob);
      setLaunchSuccess(`Crawl #${newJob.id} queued successfully. It will start within seconds.`);
      setShowConfig(false);
    } catch (err: any) {
      const d = err?.data;
      const msg = d?.error || d?.detail || d?.non_field_errors?.[0] || 'Failed to launch crawl.';
      setLaunchError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setIsLaunching(false);
    }
  };

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------

  const s: Record<string, any> = {
    panel: {
      padding: 24,
      fontFamily: "'Inter', sans-serif",
      color: '#e2e8f0',
    },
    header: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: 24,
      flexWrap: 'wrap',
      gap: 12,
    },
    heading: {
      fontSize: 20,
      fontWeight: 700,
      color: '#f1f5f9',
      display: 'flex',
      alignItems: 'center',
      gap: 8,
    },
    badge: {
      fontSize: 11,
      fontWeight: 600,
      padding: '2px 8px',
      borderRadius: 20,
      background: 'rgba(139,92,246,0.2)',
      color: '#a78bfa',
      border: '1px solid rgba(139,92,246,0.3)',
    },
    btn: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      padding: '8px 16px',
      borderRadius: 8,
      fontWeight: 600,
      fontSize: 13,
      cursor: 'pointer',
      border: 'none',
      transition: 'opacity 0.15s, transform 0.1s',
    },
    btnPrimary: {
      background: 'linear-gradient(135deg,#7c3aed,#6d28d9)',
      color: '#fff',
    },
    btnSecondary: {
      background: 'rgba(255,255,255,0.06)',
      color: '#94a3b8',
      border: '1px solid rgba(255,255,255,0.1)',
    },
    btnDisabled: {
      opacity: 0.4,
      cursor: 'not-allowed',
    },
    jobList: {
      display: 'flex',
      flexDirection: 'column' as const,
      gap: 8,
      marginBottom: 24,
    },
    jobItem: (selected: boolean, status: CrawlJobStatus) => ({
      padding: '12px 16px',
      borderRadius: 10,
      border: `1px solid ${selected ? STATUS_COLORS[status] + '66' : 'rgba(255,255,255,0.08)'}`,
      background: selected ? `${STATUS_COLORS[status]}14` : 'rgba(255,255,255,0.03)',
      cursor: 'pointer',
      transition: 'border-color 0.15s, background 0.15s',
      display: 'flex',
      alignItems: 'center',
      gap: 12,
    }),
    statusDot: (status: CrawlJobStatus) => ({
      width: 8,
      height: 8,
      borderRadius: '50%',
      background: STATUS_COLORS[status],
      boxShadow: status === 'running' ? `0 0 6px ${STATUS_COLORS[status]}` : 'none',
      flexShrink: 0,
    }),
    summaryGrid: {
      display: 'flex',
      flexWrap: 'wrap' as const,
      gap: 12,
      marginBottom: 24,
    },
    tabRow: {
      display: 'flex',
      gap: 8,
      marginBottom: 16,
    },
    tab: (active: boolean) => ({
      padding: '6px 14px',
      borderRadius: 8,
      fontSize: 12,
      fontWeight: 600,
      cursor: 'pointer',
      border: 'none',
      background: active ? 'rgba(124,58,237,0.25)' : 'rgba(255,255,255,0.05)',
      color: active ? '#a78bfa' : '#64748b',
      transition: 'background 0.15s, color 0.15s',
    }),
    table: {
      width: '100%',
      borderCollapse: 'collapse' as const,
      fontSize: 12,
    },
    th: {
      textAlign: 'left' as const,
      padding: '8px 12px',
      color: '#64748b',
      fontWeight: 600,
      borderBottom: '1px solid rgba(255,255,255,0.07)',
      textTransform: 'uppercase' as const,
      letterSpacing: '0.04em',
      fontSize: 11,
    },
    td: {
      padding: '8px 12px',
      borderBottom: '1px solid rgba(255,255,255,0.04)',
      verticalAlign: 'top' as const,
      color: '#cbd5e1',
      maxWidth: 320,
      overflow: 'hidden' as const,
      textOverflow: 'ellipsis' as const,
      whiteSpace: 'nowrap' as const,
    },
    configBox: {
      background: 'rgba(255,255,255,0.03)',
      border: '1px solid rgba(255,255,255,0.08)',
      borderRadius: 12,
      padding: 20,
      marginBottom: 24,
    },
    formRow: {
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      marginBottom: 12,
      flexWrap: 'wrap' as const,
    },
    label: {
      fontSize: 12,
      color: '#94a3b8',
      minWidth: 140,
    },
    input: {
      background: 'rgba(255,255,255,0.06)',
      border: '1px solid rgba(255,255,255,0.12)',
      borderRadius: 8,
      padding: '6px 12px',
      color: '#e2e8f0',
      fontSize: 13,
      width: 100,
    },
    alert: (type: 'error' | 'success') => ({
      padding: '10px 16px',
      borderRadius: 8,
      marginBottom: 16,
      fontSize: 13,
      background: type === 'error' ? 'rgba(239,68,68,0.12)' : 'rgba(16,185,129,0.12)',
      color: type === 'error' ? '#fca5a5' : '#6ee7b7',
      border: `1px solid ${type === 'error' ? 'rgba(239,68,68,0.3)' : 'rgba(16,185,129,0.3)'}`,
    }),
    emptyState: {
      textAlign: 'center' as const,
      padding: '48px 24px',
      color: '#475569',
    },
    emptyIcon: {
      fontSize: 48,
      marginBottom: 12,
    },
    emptyTitle: {
      fontSize: 16,
      fontWeight: 600,
      color: '#64748b',
      marginBottom: 6,
    },
    emptySubtitle: {
      fontSize: 13,
      color: '#475569',
    },
  };

  // -------------------------------------------------------------------------
  // Entitlement gate
  // -------------------------------------------------------------------------

  if (!hasCrawlerEntitlement) {
    return (
      <div style={s.panel}>
        <div style={s.header}>
          <div style={s.heading}>
            <span>🔍</span> Technical SEO Crawler
            <span style={s.badge}>PAID</span>
          </div>
        </div>
        <div style={{
          ...s.emptyState,
          background: 'rgba(124,58,237,0.06)',
          border: '1px dashed rgba(124,58,237,0.3)',
          borderRadius: 16,
        }}>
          <div style={s.emptyIcon}>🔒</div>
          <div style={s.emptyTitle}>Starter or Agency Plan Required</div>
          <div style={s.emptySubtitle}>
            The Technical SEO Crawler is a paid feature available on Starter and Agency plans.
            <br />Upgrade your subscription to run full-site technical audits.
          </div>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Active job in running/pending state
  // -------------------------------------------------------------------------

  const activeJob = crawlJobs.find(j => !isTerminal(j.status));

  // -------------------------------------------------------------------------
  // Main render
  // -------------------------------------------------------------------------

  return (
    <div style={s.panel}>
      {/* Header */}
      <div style={s.header}>
        <div style={s.heading}>
          <span>🔍</span> Technical SEO Crawler
          <span style={s.badge}>PAID</span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            id="crawl-config-toggle-btn"
            style={{ ...s.btn, ...s.btnSecondary }}
            onClick={() => setShowConfig(v => !v)}
          >
            ⚙️ Config
          </button>
          <button
            id="crawl-launch-btn"
            style={{
              ...s.btn,
              ...s.btnPrimary,
              ...(activeJob || isLaunching ? s.btnDisabled : {}),
            }}
            onClick={handleLaunch}
            disabled={!!activeJob || isLaunching}
          >
            {isLaunching ? '⏳ Launching…' : activeJob ? '⏳ Crawl in Progress' : '🚀 Start New Crawl'}
          </button>
        </div>
      </div>

      {/* Alerts */}
      {launchSuccess && (
        <div style={s.alert('success')} id="crawl-launch-success">
          ✅ {launchSuccess}
        </div>
      )}
      {launchError && (
        <div style={s.alert('error')} id="crawl-launch-error">
          ⚠️ {launchError}
        </div>
      )}

      {/* Config panel */}
      {showConfig && (
        <div style={s.configBox} id="crawl-config-box">
          <div style={{ fontSize: 13, fontWeight: 600, color: '#a78bfa', marginBottom: 16 }}>
            Crawl Configuration
          </div>
          <div style={s.formRow}>
            <label style={s.label}>Max Pages (1–500)</label>
            <input
              id="crawl-max-pages"
              type="number"
              min={1}
              max={500}
              value={maxPages}
              onChange={e => setMaxPages(Math.max(1, Math.min(500, Number(e.target.value))))}
              style={s.input}
            />
          </div>
          <div style={s.formRow}>
            <label style={s.label}>Max Depth (0–10)</label>
            <input
              id="crawl-max-depth"
              type="number"
              min={0}
              max={10}
              value={maxDepth}
              onChange={e => setMaxDepth(Math.max(0, Math.min(10, Number(e.target.value))))}
              style={s.input}
            />
          </div>
          <div style={s.formRow}>
            <label style={s.label}>Respect robots.txt</label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input
                id="crawl-respect-robots"
                type="checkbox"
                checked={respectRobots}
                onChange={e => setRespectRobots(e.target.checked)}
                style={{ width: 16, height: 16, cursor: 'pointer' }}
              />
              <span style={{ fontSize: 13, color: '#94a3b8' }}>
                {respectRobots ? 'Yes — follow robots.txt disallow rules' : 'No — crawl all accessible pages'}
              </span>
            </label>
          </div>
        </div>
      )}

      {/* Crawl job list */}
      {isLoadingJobs && (
        <div style={{ color: '#64748b', fontSize: 13, marginBottom: 16 }}>Loading crawl history…</div>
      )}
      {jobError && (
        <div style={s.alert('error')}>{jobError}</div>
      )}

      {!isLoadingJobs && crawlJobs.length === 0 && !jobError && (
        <div style={s.emptyState}>
          <div style={s.emptyIcon}>🕷️</div>
          <div style={s.emptyTitle}>No crawls yet</div>
          <div style={s.emptySubtitle}>
            Start your first technical SEO crawl for <strong>{project.name}</strong> to detect<br />
            broken links, missing titles, H1 issues, slow pages, and more.
          </div>
        </div>
      )}

      {crawlJobs.length > 0 && (
        <>
          {/* Job list */}
          <div style={s.jobList} id="crawl-job-list">
            {crawlJobs.slice(0, 8).map(job => (
              <div
                key={job.id}
                id={`crawl-job-item-${job.id}`}
                style={s.jobItem(selectedJob?.id === job.id, job.status)}
                onClick={() => setSelectedJob(job)}
              >
                <div style={s.statusDot(job.status)} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontWeight: 600, fontSize: 13, color: '#e2e8f0' }}>
                      Crawl #{job.id}
                    </span>
                    <span style={{
                      fontSize: 11,
                      fontWeight: 600,
                      color: STATUS_COLORS[job.status],
                      textTransform: 'uppercase',
                    }}>
                      {STATUS_LABELS[job.status]}
                    </span>
                    {job.status === 'running' && (
                      <span style={{ fontSize: 11, color: '#3b82f6', animation: 'pulse 1.5s infinite' }}>
                        ●
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
                    {fmtDate(job.created_at)}
                    {job.pages_crawled > 0 && ` · ${job.pages_crawled} pages`}
                    {job.duration_seconds && ` · ${job.duration_seconds}s`}
                  </div>
                </div>
                {job.status === 'completed' && (
                  <div style={{ fontSize: 11, color: '#64748b', textAlign: 'right' as const }}>
                    <span style={{ color: '#ef4444', fontWeight: 600 }}>{job.broken_links_count}</span> broken
                    {' · '}
                    <span style={{ color: '#f59e0b', fontWeight: 600 }}>{job.missing_titles_count}</span> no-title
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Selected job detail */}
          {selectedJob && (
            <div id={`crawl-detail-${selectedJob.id}`}>
              {/* Summary stats */}
              {selectedJob.status === 'completed' && (
                <div style={s.summaryGrid} id="crawl-summary-grid">
                  <StatCard label="Pages Crawled" value={selectedJob.pages_crawled} color="#a78bfa" icon="📄" />
                  <StatCard label="Discovered" value={selectedJob.pages_discovered} color="#60a5fa" icon="🔗" />
                  <StatCard label="Broken Pages" value={selectedJob.broken_links_count} color="#ef4444" icon="💔" />
                  <StatCard label="Missing Titles" value={selectedJob.missing_titles_count} color="#f59e0b" icon="📝" />
                  <StatCard label="Missing Meta" value={selectedJob.missing_descriptions_count} color="#f59e0b" icon="ℹ️" />
                  <StatCard label="Missing H1" value={selectedJob.missing_h1_count} color="#f97316" icon="H₁" />
                  <StatCard label="Redirects" value={selectedJob.redirect_chains_count} color="#8b5cf6" icon="↪" />
                  <StatCard label="Slow Pages" value={selectedJob.slow_pages_count} color="#94a3b8" icon="🐢" />
                  <StatCard label="Dup. Titles" value={selectedJob.duplicate_titles_count} color="#6366f1" icon="⎍" />
                </div>
              )}

              {/* Running/pending progress */}
              {(selectedJob.status === 'running' || selectedJob.status === 'pending') && (
                <div style={{
                  background: 'rgba(59,130,246,0.08)',
                  border: '1px solid rgba(59,130,246,0.25)',
                  borderRadius: 12,
                  padding: '16px 20px',
                  marginBottom: 24,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                }} id="crawl-in-progress-banner">
                  <span style={{ fontSize: 22 }}>⏳</span>
                  <div>
                    <div style={{ fontWeight: 600, color: '#93c5fd', marginBottom: 4 }}>
                      {selectedJob.status === 'pending' ? 'Crawl queued — worker will start shortly…' : 'Crawl in progress…'}
                    </div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>
                      Started {fmtDate(selectedJob.started_at)} · Checking status every 8 seconds
                    </div>
                  </div>
                </div>
              )}

              {/* Failed state */}
              {selectedJob.status === 'failed' && (
                <div style={s.alert('error')} id="crawl-failed-banner">
                  ❌ Crawl failed: {selectedJob.error_message || 'Unknown error.'}
                </div>
              )}

              {/* Pages table */}
              {selectedJob.status === 'completed' && (
                <>
                  <div style={s.tabRow}>
                    {(['all', 'broken', 'slow'] as PageFilter[]).map(f => (
                      <button
                        key={f}
                        id={`crawl-filter-${f}`}
                        style={s.tab(pageFilter === f)}
                        onClick={() => setPageFilter(f)}
                      >
                        {f === 'all' ? `All Pages (${selectedJob.pages_crawled})` :
                         f === 'broken' ? `Broken (${selectedJob.broken_links_count})` :
                         `Slow (${selectedJob.slow_pages_count})`}
                      </button>
                    ))}
                  </div>

                  {isLoadingPages && (
                    <div style={{ color: '#64748b', fontSize: 13, marginBottom: 12 }}>Loading pages…</div>
                  )}
                  {pageError && (
                    <div style={s.alert('error')}>{pageError}</div>
                  )}

                  {!isLoadingPages && pages.length === 0 && (
                    <div style={{ ...s.emptyState, padding: '24px' }}>
                      <div style={{ color: '#475569', fontSize: 13 }}>
                        No pages match this filter.
                      </div>
                    </div>
                  )}

                  {pages.length > 0 && (
                    <div style={{ overflowX: 'auto' as const }}>
                      <table style={s.table} id="crawl-pages-table">
                        <thead>
                          <tr>
                            <th style={s.th}>URL</th>
                            <th style={s.th}>Status</th>
                            <th style={s.th}>Resp.</th>
                            <th style={s.th}>Depth</th>
                            <th style={s.th}>Title</th>
                            <th style={s.th}>H1</th>
                            <th style={s.th}>Links</th>
                            <th style={s.th}>Issues</th>
                          </tr>
                        </thead>
                        <tbody>
                          {pages.map(page => (
                            <tr
                              key={page.id}
                              id={`crawl-page-row-${page.id}`}
                              style={{
                                background: page.is_broken
                                  ? 'rgba(239,68,68,0.04)'
                                  : page.is_slow
                                  ? 'rgba(245,158,11,0.04)'
                                  : 'transparent',
                              }}
                            >
                              <td style={{ ...s.td, color: '#a78bfa', maxWidth: 280 }}>
                                <a
                                  href={page.final_url || page.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  style={{ color: 'inherit', textDecoration: 'none' }}
                                  title={page.url}
                                >
                                  {page.url.replace(/^https?:\/\/[^/]+/, '')||'/'}
                                </a>
                              </td>
                              <td style={{
                                ...s.td,
                                color: page.status_code >= 400
                                  ? '#ef4444' : page.status_code >= 300
                                  ? '#f59e0b' : '#10b981',
                                fontWeight: 600,
                              }}>
                                {page.status_code}
                              </td>
                              <td style={s.td}>
                                <span style={{ color: page.is_slow ? '#f59e0b' : '#94a3b8' }}>
                                  {fmtMs(page.response_time_ms)}
                                </span>
                              </td>
                              <td style={{ ...s.td, color: '#64748b' }}>{page.depth}</td>
                              <td style={{ ...s.td, color: page.title ? '#cbd5e1' : '#475569', fontStyle: page.title ? 'normal' : 'italic' }}>
                                {page.title || 'Missing'}
                              </td>
                              <td style={{
                                ...s.td,
                                color: page.h1_count === 0 ? '#ef4444' : page.h1_count > 1 ? '#f59e0b' : '#10b981',
                                fontWeight: 600,
                              }}>
                                {page.h1_count}
                              </td>
                              <td style={{ ...s.td, color: '#64748b' }}>
                                {page.internal_links_count}i / {page.external_links_count}e
                              </td>
                              <td style={{ ...s.td, maxWidth: 260, whiteSpace: 'normal' as const }}>
                                {page.issues.length === 0
                                  ? <span style={{ color: '#10b981', fontSize: 11 }}>✓ OK</span>
                                  : page.issues.map((issue, idx) => (
                                      <IssueBadge key={idx} issue={issue} />
                                    ))
                                }
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </>
      )}

      {/* Pulse animation for running indicator */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>
    </div>
  );
};

export default TechnicalCrawlerPanel;
