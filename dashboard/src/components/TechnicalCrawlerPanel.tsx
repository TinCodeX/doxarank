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
import {
  Lock,
  Play,
  Settings,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  Globe,
  ExternalLink,
} from 'lucide-react';
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
  onUpgrade?: () => void;
}

type PageFilter = 'all' | 'broken' | 'slow';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATUS_COLORS: Record<CrawlJobStatus, string> = {
  pending: '#d97706',
  running: '#774da9',
  completed: '#059669',
  failed: '#dc2626',
  cancelled: '#64748b',
};

const STATUS_THEME: Record<CrawlJobStatus, { bg: string; text: string; border: string }> = {
  pending: { bg: '#fffbeb', text: '#b45309', border: '#fde68a' },
  running: { bg: '#f3e8ff', text: '#6b21a8', border: '#d8b4fe' },
  completed: { bg: '#ecfdf5', text: '#065f46', border: '#a7f3d0' },
  failed: { bg: '#fef2f2', text: '#991b1b', border: '#fecaca' },
  cancelled: { bg: '#f1f5f9', text: '#475569', border: '#e2e8f0' },
};

const STATUS_LABELS: Record<CrawlJobStatus, string> = {
  pending: 'Queued',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

const SEVERITY_COLORS: Record<string, { text: string; bg: string; border: string }> = {
  critical: { text: '#991b1b', bg: '#fef2f2', border: '#fecaca' },
  warning: { text: '#92400e', bg: '#fffbeb', border: '#fde68a' },
  notice: { text: '#374151', bg: '#f1f5f9', border: '#e2e8f0' },
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
  icon?: React.ReactNode;
}> = ({ label, value, color = '#774da9', icon }) => (
  <div style={{
    backgroundColor: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: '12px',
    padding: '14px 18px',
    minWidth: '130px',
    flex: '1 1 130px',
    boxShadow: '0 1px 2px rgba(0, 0, 0, 0.02)',
  }}>
    <div style={{ fontSize: '22px', fontWeight: 800, color, marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
      {icon}
      <span>{value.toLocaleString()}</span>
    </div>
    <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
      {label}
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Sub-component: Issue badge
// ---------------------------------------------------------------------------

const IssueBadge: React.FC<{ issue: CrawlPageIssue }> = ({ issue }) => {
  const theme = SEVERITY_COLORS[issue.severity] ?? { text: '#374151', bg: '#f1f5f9', border: '#e2e8f0' };
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: '6px',
        fontSize: '11px',
        fontWeight: 600,
        color: theme.text,
        backgroundColor: theme.bg,
        border: `1px solid ${theme.border}`,
        marginRight: '4px',
        marginBottom: '4px',
        cursor: 'default',
      }}
      title={issue.message}
    >
      {issue.type.replace(/_/g, ' ')}
    </span>
  );
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export const TechnicalCrawlerPanel: React.FC<Props> = ({
  project,
  hasCrawlerEntitlement = false,
  onUpgrade,
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
  // Render styles
  // -------------------------------------------------------------------------

  const s: Record<string, any> = {
    panel: {
      backgroundColor: '#ffffff',
      borderRadius: '16px',
      border: '1px solid #e2e8f0',
      padding: '24px',
      boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.04)',
      fontFamily: "'Inter', sans-serif",
      color: '#1e293b',
    },
    header: {
      display: 'flex',
      alignItems: 'flex-start',
      justifyContent: 'space-between',
      marginBottom: '20px',
      flexWrap: 'wrap' as const,
      gap: '12px',
    },
    heading: {
      fontSize: '20px',
      fontWeight: 700,
      color: '#0f172a',
      display: 'flex',
      alignItems: 'center',
      gap: '10px',
    },
    badge: {
      fontSize: '11px',
      fontWeight: 700,
      padding: '2px 8px',
      borderRadius: '20px',
      backgroundColor: '#f3eef9',
      color: '#774da9',
      border: '1px solid #dac8ee',
      letterSpacing: '0.04em',
    },
    btn: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: '6px',
      padding: '8px 16px',
      borderRadius: '8px',
      fontWeight: 600,
      fontSize: '13px',
      cursor: 'pointer',
      border: 'none',
      transition: 'all 0.15s ease',
    },
    btnPrimary: {
      backgroundColor: '#774da9',
      color: '#ffffff',
      boxShadow: '0 1px 2px rgba(119, 77, 169, 0.2)',
    },
    btnSecondary: {
      backgroundColor: '#f8fafc',
      color: '#334155',
      border: '1px solid #cbd5e1',
    },
    btnDisabled: {
      opacity: 0.5,
      cursor: 'not-allowed',
    },
    jobList: {
      display: 'flex',
      flexDirection: 'column' as const,
      gap: '8px',
      marginBottom: '24px',
    },
    jobItem: (selected: boolean) => ({
      padding: '12px 16px',
      borderRadius: '10px',
      border: selected ? '2px solid #774da9' : '1px solid #e2e8f0',
      backgroundColor: selected ? '#fcfaff' : '#ffffff',
      cursor: 'pointer',
      transition: 'all 0.15s ease',
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      boxShadow: selected ? '0 1px 3px rgba(119, 77, 169, 0.1)' : 'none',
    }),
    statusDot: (status: CrawlJobStatus) => ({
      width: '9px',
      height: '9px',
      borderRadius: '50%',
      backgroundColor: STATUS_COLORS[status],
      boxShadow: status === 'running' ? `0 0 6px ${STATUS_COLORS[status]}` : 'none',
      flexShrink: 0,
    }),
    summaryGrid: {
      display: 'flex',
      flexWrap: 'wrap' as const,
      gap: '12px',
      marginBottom: '24px',
    },
    tabRow: {
      display: 'flex',
      gap: '8px',
      marginBottom: '16px',
    },
    tab: (active: boolean) => ({
      padding: '7px 14px',
      borderRadius: '8px',
      fontSize: '12px',
      fontWeight: 700,
      cursor: 'pointer',
      border: active ? '1px solid #774da9' : '1px solid #cbd5e1',
      backgroundColor: active ? '#774da9' : '#ffffff',
      color: active ? '#ffffff' : '#475569',
      transition: 'all 0.15s ease',
    }),
    table: {
      width: '100%',
      borderCollapse: 'collapse' as const,
      fontSize: '12px',
    },
    th: {
      textAlign: 'left' as const,
      padding: '10px 12px',
      backgroundColor: '#f8fafc',
      color: '#475569',
      fontWeight: 700,
      borderBottom: '1px solid #e2e8f0',
      textTransform: 'uppercase' as const,
      letterSpacing: '0.04em',
      fontSize: '11px',
    },
    td: {
      padding: '10px 12px',
      borderBottom: '1px solid #f1f5f9',
      verticalAlign: 'top' as const,
      color: '#1e293b',
      maxWidth: '320px',
      overflow: 'hidden' as const,
      textOverflow: 'ellipsis' as const,
      whiteSpace: 'nowrap' as const,
    },
    configBox: {
      backgroundColor: '#f8fafc',
      border: '1px solid #e2e8f0',
      borderRadius: '12px',
      padding: '20px',
      marginBottom: '20px',
    },
    formRow: {
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      marginBottom: '12px',
      flexWrap: 'wrap' as const,
    },
    label: {
      fontSize: '13px',
      fontWeight: 600,
      color: '#334155',
      minWidth: '140px',
    },
    input: {
      backgroundColor: '#ffffff',
      border: '1px solid #cbd5e1',
      borderRadius: '8px',
      padding: '6px 12px',
      color: '#0f172a',
      fontSize: '13px',
      fontWeight: 500,
      width: '100px',
      outline: 'none',
    },
    alert: (type: 'error' | 'success') => ({
      padding: '12px 16px',
      borderRadius: '8px',
      marginBottom: '16px',
      fontSize: '13px',
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      backgroundColor: type === 'error' ? '#fef2f2' : '#f0fdf4',
      color: type === 'error' ? '#991b1b' : '#166534',
      border: `1px solid ${type === 'error' ? '#fecaca' : '#bbf7d0'}`,
    }),
    emptyState: {
      textAlign: 'center' as const,
      padding: '40px 24px',
      backgroundColor: '#f8fafc',
      borderRadius: '12px',
      border: '1px dashed #cbd5e1',
    },
    emptyIcon: {
      width: '44px',
      height: '44px',
      borderRadius: '50%',
      backgroundColor: '#ede9fe',
      color: '#774da9',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: '12px',
    },
    emptyTitle: {
      fontSize: '15px',
      fontWeight: 700,
      color: '#0f172a',
      marginBottom: '6px',
    },
    emptySubtitle: {
      fontSize: '13px',
      color: '#64748b',
      lineHeight: 1.5,
    },
  };

  // -------------------------------------------------------------------------
  // Entitlement gate
  // -------------------------------------------------------------------------

  if (!hasCrawlerEntitlement) {
    return (
      <div style={s.panel}>
        <div style={s.header}>
          <div>
            <div style={s.heading}>
              Technical SEO Crawler
              <span style={s.badge}>PAID</span>
            </div>
            <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#64748b' }}>
              Full-site technical crawler for link audits, status code validation, and SEO health.
            </p>
          </div>
        </div>
        <div
          id="crawl-paywall-notice"
          style={{
            padding: '32px 24px',
            backgroundColor: '#faf5ff',
            borderRadius: '12px',
            border: '1px solid #e9d5ff',
            textAlign: 'center',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
          }}
        >
          <div
            style={{
              width: '48px',
              height: '48px',
              borderRadius: '50%',
              backgroundColor: '#f3e8ff',
              color: '#774da9',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: '12px',
            }}
          >
            <Lock size={24} />
          </div>
          <h3 style={{ fontSize: '17px', fontWeight: 700, color: '#24143c', margin: '0 0 6px 0' }}>
            Starter or Agency Plan Required
          </h3>
          <p style={{ fontSize: '14px', color: '#593285', margin: '0 0 18px 0', maxWidth: '520px', lineHeight: 1.5 }}>
            The Technical SEO Crawler is a paid feature available on Starter and Agency plans.
            Upgrade your subscription to run full-site technical audits, discover broken links, and analyze on-page structure.
          </p>
          {onUpgrade ? (
            <button
              id="crawl-upgrade-btn"
              onClick={onUpgrade}
              style={{
                ...s.btn,
                ...s.btnPrimary,
                padding: '10px 22px',
                fontSize: '13px',
              }}
            >
              Upgrade Subscription
            </button>
          ) : (
            <a
              href="/subscription"
              style={{
                ...s.btn,
                ...s.btnPrimary,
                padding: '10px 22px',
                fontSize: '13px',
                textDecoration: 'none',
              }}
            >
              Upgrade Subscription
            </a>
          )}
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
        <div>
          <div style={s.heading}>
            Technical SEO Crawler
            <span style={s.badge}>PAID</span>
          </div>
          <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#64748b' }}>
            Deep technical crawler to analyze broken URLs, metadata, slow pages, and crawling health.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button
            id="crawl-config-toggle-btn"
            style={{ ...s.btn, ...s.btnSecondary }}
            onClick={() => setShowConfig(v => !v)}
          >
            <Settings size={14} />
            <span>Config</span>
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
            {isLaunching ? (
              <>
                <RefreshCw size={14} style={{ animation: 'spin 1.5s linear infinite' }} />
                <span>Launching…</span>
              </>
            ) : activeJob ? (
              <>
                <RefreshCw size={14} style={{ animation: 'spin 2s linear infinite' }} />
                <span>Crawl in Progress</span>
              </>
            ) : (
              <>
                <Play size={14} />
                <span>Start New Crawl</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Alerts */}
      {launchSuccess && (
        <div style={s.alert('success')} id="crawl-launch-success">
          <CheckCircle2 size={16} />
          <span>{launchSuccess}</span>
        </div>
      )}
      {launchError && (
        <div style={s.alert('error')} id="crawl-launch-error">
          <AlertCircle size={16} />
          <span>{launchError}</span>
        </div>
      )}

      {/* Config panel */}
      {showConfig && (
        <div style={s.configBox} id="crawl-config-box">
          <div style={{ fontSize: 14, fontWeight: 700, color: '#0f172a', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Settings size={16} color="#774da9" />
            <span>Crawl Configuration</span>
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
                style={{ width: 16, height: 16, cursor: 'pointer', accentColor: '#774da9' }}
              />
              <span style={{ fontSize: 13, color: '#334155', fontWeight: 500 }}>
                {respectRobots ? 'Yes — follow robots.txt disallow rules' : 'No — crawl all accessible pages'}
              </span>
            </label>
          </div>
        </div>
      )}

      {/* Crawl job list */}
      {isLoadingJobs && (
        <div style={{ color: '#64748b', fontSize: 13, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
          <RefreshCw size={14} style={{ animation: 'spin 1.5s linear infinite' }} />
          <span>Loading crawl history…</span>
        </div>
      )}
      {jobError && (
        <div style={s.alert('error')}>{jobError}</div>
      )}

      {!isLoadingJobs && crawlJobs.length === 0 && !jobError && (
        <div style={s.emptyState}>
          <div style={s.emptyIcon}>
            <Globe size={22} />
          </div>
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
                style={s.jobItem(selectedJob?.id === job.id)}
                onClick={() => setSelectedJob(job)}
              >
                <div style={s.statusDot(job.status)} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontWeight: 700, fontSize: 13, color: '#0f172a' }}>
                      Crawl #{job.id}
                    </span>
                    <span style={{
                      fontSize: 11,
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: 12,
                      backgroundColor: STATUS_THEME[job.status].bg,
                      color: STATUS_THEME[job.status].text,
                      border: `1px solid ${STATUS_THEME[job.status].border}`,
                      textTransform: 'uppercase',
                    }}>
                      {STATUS_LABELS[job.status]}
                    </span>
                    {job.status === 'running' && (
                      <span style={{ fontSize: 11, color: '#774da9', animation: 'pulse 1.5s infinite' }}>
                        ●
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 12, color: '#64748b', marginTop: 3 }}>
                    {fmtDate(job.created_at)}
                    {job.pages_crawled > 0 && ` · ${job.pages_crawled} pages`}
                    {job.duration_seconds && ` · ${job.duration_seconds}s`}
                  </div>
                </div>
                {job.status === 'completed' && (
                  <div style={{ fontSize: 12, color: '#64748b', textAlign: 'right' as const }}>
                    <span style={{ color: '#dc2626', fontWeight: 700 }}>{job.broken_links_count}</span> broken
                    {' · '}
                    <span style={{ color: '#d97706', fontWeight: 700 }}>{job.missing_titles_count}</span> no-title
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
                  <StatCard label="Pages Crawled" value={selectedJob.pages_crawled} color="#774da9" />
                  <StatCard label="Discovered" value={selectedJob.pages_discovered} color="#24143c" />
                  <StatCard label="Broken Pages" value={selectedJob.broken_links_count} color="#dc2626" />
                  <StatCard label="Missing Titles" value={selectedJob.missing_titles_count} color="#d97706" />
                  <StatCard label="Missing Meta" value={selectedJob.missing_descriptions_count} color="#d97706" />
                  <StatCard label="Missing H1" value={selectedJob.missing_h1_count} color="#ea580c" />
                  <StatCard label="Redirects" value={selectedJob.redirect_chains_count} color="#774da9" />
                  <StatCard label="Slow Pages" value={selectedJob.slow_pages_count} color="#64748b" />
                  <StatCard label="Dup. Titles" value={selectedJob.duplicate_titles_count} color="#8b5cf6" />
                </div>
              )}

              {/* Running/pending progress */}
              {(selectedJob.status === 'running' || selectedJob.status === 'pending') && (
                <div style={{
                  backgroundColor: '#f6f2fb',
                  border: '1px solid #dac8ee',
                  borderRadius: 12,
                  padding: '16px 20px',
                  marginBottom: 24,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                }} id="crawl-in-progress-banner">
                  <RefreshCw size={18} color="#774da9" style={{ animation: 'spin 2s linear infinite' }} />
                  <div>
                    <div style={{ fontWeight: 700, color: '#24143c', marginBottom: 2 }}>
                      {selectedJob.status === 'pending' ? 'Crawl queued — worker will start shortly…' : 'Crawl in progress…'}
                    </div>
                    <div style={{ fontSize: 12, color: '#593285' }}>
                      Started {fmtDate(selectedJob.started_at)} · Checking status every 8 seconds
                    </div>
                  </div>
                </div>
              )}

              {/* Failed state */}
              {selectedJob.status === 'failed' && (
                <div style={s.alert('error')} id="crawl-failed-banner">
                  <AlertCircle size={16} />
                  <span>Crawl failed: {selectedJob.error_message || 'Unknown error.'}</span>
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
                    <div style={{ color: '#64748b', fontSize: 13, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <RefreshCw size={13} style={{ animation: 'spin 1.5s linear infinite' }} />
                      <span>Loading pages…</span>
                    </div>
                  )}
                  {pageError && (
                    <div style={s.alert('error')}>{pageError}</div>
                  )}

                  {!isLoadingPages && pages.length === 0 && (
                    <div style={{ ...s.emptyState, padding: '24px' }}>
                      <div style={{ color: '#64748b', fontSize: 13 }}>
                        No pages match this filter.
                      </div>
                    </div>
                  )}

                  {pages.length > 0 && (
                    <div style={{ overflowX: 'auto' as const, border: '1px solid #e2e8f0', borderRadius: '10px' }}>
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
                                backgroundColor: page.is_broken
                                  ? '#fef2f2'
                                  : page.is_slow
                                  ? '#fffbeb'
                                  : '#ffffff',
                              }}
                            >
                              <td style={{ ...s.td, maxWidth: 280 }}>
                                <a
                                  href={page.final_url || page.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  style={{ color: '#774da9', fontWeight: 600, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                                  title={page.url}
                                >
                                  <span>{page.url.replace(/^https?:\/\/[^/]+/, '') || '/'}</span>
                                  <ExternalLink size={11} color="#a372df" />
                                </a>
                              </td>
                              <td style={{
                                ...s.td,
                                color: page.status_code >= 400
                                  ? '#dc2626' : page.status_code >= 300
                                  ? '#d97706' : '#059669',
                                fontWeight: 700,
                              }}>
                                {page.status_code}
                              </td>
                              <td style={s.td}>
                                <span style={{ color: page.is_slow ? '#d97706' : '#475569', fontWeight: 600 }}>
                                  {fmtMs(page.response_time_ms)}
                                </span>
                              </td>
                              <td style={{ ...s.td, color: '#475569' }}>{page.depth}</td>
                              <td style={{ ...s.td, color: page.title ? '#1e293b' : '#94a3b8', fontStyle: page.title ? 'normal' : 'italic' }}>
                                {page.title || 'Missing'}
                              </td>
                              <td style={{
                                ...s.td,
                                color: page.h1_count === 0 ? '#dc2626' : page.h1_count > 1 ? '#d97706' : '#059669',
                                fontWeight: 700,
                              }}>
                                {page.h1_count}
                              </td>
                              <td style={{ ...s.td, color: '#475569' }}>
                                {page.internal_links_count}i / {page.external_links_count}e
                              </td>
                              <td style={{ ...s.td, maxWidth: 260, whiteSpace: 'normal' as const }}>
                                {page.issues.length === 0
                                  ? <span style={{ color: '#059669', fontSize: 11, fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                                      <CheckCircle2 size={13} /> OK
                                    </span>
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

      {/* Pulse and spin animations */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export default TechnicalCrawlerPanel;
