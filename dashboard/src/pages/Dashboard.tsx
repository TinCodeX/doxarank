import React, { useState, useEffect, useMemo } from 'react';
import {
  LayoutDashboard,
  Search,
  Activity,
  Building2,
  Lightbulb,
  FileText,
  TrendingUp,
  TrendingDown,
  FileSpreadsheet,
  Wrench,
  Zap,
  FolderKanban,
  ExternalLink,
  RefreshCw,
  LogOut,
  Menu,
  X,
  Plus,
  Monitor,
  Smartphone,
  Globe,
  BarChart2,
  Tag,
  ChevronRight,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getProjects, createProject, updateProject, deleteProject } from '../api/projects';
import { getKeywords, createKeyword, updateKeyword, deleteKeyword, refreshKeywordIntelligence, bulkRefreshKeywordIntelligence } from '../api/keywords';
import { getRankings, createRanking, updateRanking, deleteRanking, triggerRankCheck, getRankingSummary, getRankCheckJobs } from '../api/rankings';
import type { Project, CreateProjectPayload } from '../types/project';
import type { Keyword, CreateKeywordPayload, UpdateKeywordPayload } from '../types/keyword';
import type { Ranking, CreateRankingPayload, UpdateRankingPayload, KeywordRankingSummary, RankCheckJob } from '../types/ranking';
import { ProjectFormModal } from '../components/ProjectFormModal';
import { KeywordFormModal } from '../components/KeywordFormModal';
import { RankingFormModal } from '../components/RankingFormModal';
import { SiteAuditPanel } from '../components/SiteAuditPanel';
import { SearchConsolePanel } from '../components/SearchConsolePanel';
import { SearchConsoleAnalyticsPanel } from '../components/SearchConsoleAnalyticsPanel';
import { SEOInsightsPanel } from '../components/SEOInsightsPanel';
import { AgentOrchestratorPanel } from '../components/AgentOrchestratorPanel';
import { ContinuousOperationsPanel } from '../components/ContinuousOperationsPanel';
import { EventActivityPanel } from '../components/EventActivityPanel';
import { MonitoringActivityPanel } from '../components/MonitoringActivityPanel';
import { RemediationActivityPanel } from '../components/RemediationActivityPanel';
import { LongTermStrategyPanel } from '../components/LongTermStrategyPanel';
import { ProductionOperationsPanel } from '../components/ProductionOperationsPanel';
import { useLanguage } from '../context/LanguageContext';
import { LanguageSelector } from '../components/LanguageSelector';
import { AIRecommendationsPanel } from '../components/AIRecommendationsPanel';
import { SEOContentBriefPanel } from '../components/SEOContentBriefPanel';
import { SEOContentDraftPanel } from '../components/SEOContentDraftPanel';
import { SEOActionsPanel } from '../components/SEOActionsPanel';
import { SEOToolsPanel } from '../components/SEOToolsPanel';
import { TechnicalCrawlerPanel } from '../components/TechnicalCrawlerPanel';
import { CompetitorSnapshotsPanel } from '../components/CompetitorSnapshotsPanel';
import { SEORecommendationsPanel } from '../components/SEORecommendationsPanel';
import { WhiteLabelReportsPanel } from '../components/WhiteLabelReportsPanel';
import type { SearchConsoleConnection } from '../types/searchConsole';

import { getUserSubscription } from '../api/subscriptions';
import type { UserSubscriptionSummary } from '../types/subscription';
import { SubscriptionModal } from '../components/SubscriptionModal';

type DashboardTab =
  | 'overview'
  | 'keywords'
  | 'audits'
  | 'competitors'
  | 'recommendations'
  | 'content'
  | 'analytics'
  | 'reports'
  | 'tools'
  | 'operations'
  | 'projects';

export const Dashboard: React.FC = () => {
  const { user, logout } = useAuth();
  const { t, formatStatus, formatDevice, formatDate, formatNumber } = useLanguage();
  const [subscriptionSummary, setSubscriptionSummary] = useState<UserSubscriptionSummary | null>(null);
  const [isSubscriptionModalOpen, setIsSubscriptionModalOpen] = useState(false);

  // Active navigation tab
  const [activeTab, setActiveTab] = useState<DashboardTab>('overview');
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [keywordFilterText, setKeywordFilterText] = useState('');

  // Sub-tabs for content-heavy and operations pages
  const [recommendationsSubTab, setRecommendationsSubTab] = useState<'all' | 'feed' | 'actions' | 'insights' | 'generator'>('all');
  const [contentSubTab, setContentSubTab] = useState<'all' | 'briefs' | 'drafts'>('all');
  const [operationsSubTab, setOperationsSubTab] = useState<'all' | 'orchestrator' | 'continuous' | 'events' | 'monitoring' | 'remediation' | 'observability' | 'strategy'>('all');

  // Project state
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [gscConnection, setGscConnection] = useState<SearchConsoleConnection | null>(null);
  const [isLoadingProjects, setIsLoadingProjects] = useState<boolean>(true);
  const [projectError, setProjectError] = useState<string | null>(null);

  // Project Modal state
  const [isProjectModalOpen, setIsProjectModalOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [deletingProject, setDeletingProject] = useState<Project | null>(null);
  const [isDeletingProject, setIsDeletingProject] = useState(false);

  // Keyword state
  const [keywords, setKeywords] = useState<Keyword[]>([]);
  const [selectedKeyword, setSelectedKeyword] = useState<Keyword | null>(null);
  const [isLoadingKeywords, setIsLoadingKeywords] = useState<boolean>(false);
  const [keywordError, setKeywordError] = useState<string | null>(null);

  // Keyword Modal state
  const [isKeywordModalOpen, setIsKeywordModalOpen] = useState(false);
  const [editingKeyword, setEditingKeyword] = useState<Keyword | null>(null);
  const [deletingKeyword, setDeletingKeyword] = useState<Keyword | null>(null);
  const [isDeletingKeyword, setIsDeletingKeyword] = useState(false);

  // Ranking state
  const [rankings, setRankings] = useState<Ranking[]>([]);
  const [isLoadingRankings, setIsLoadingRankings] = useState<boolean>(false);
  const [rankingError, setRankingError] = useState<string | null>(null);

  // Ranking Modal state
  const [isRankingModalOpen, setIsRankingModalOpen] = useState(false);
  const [editingRanking, setEditingRanking] = useState<Ranking | null>(null);
  const [deletingRanking, setDeletingRanking] = useState<Ranking | null>(null);
  const [isDeletingRanking, setIsDeletingRanking] = useState(false);

  // Rank Tracker MVP state
  const [rankingSummaries, setRankingSummaries] = useState<Record<number, KeywordRankingSummary>>({});
  const [activeRankJob, setActiveRankJob] = useState<RankCheckJob | null>(null);
  const [isCheckingRankings, setIsCheckingRankings] = useState<boolean>(false);
  const [rankCheckNotice, setRankCheckNotice] = useState<string | null>(null);

  // Keyword Intelligence state (Original SRS: Search Volume & CPC)
  const [refreshingIntelId, setRefreshingIntelId] = useState<number | null>(null);
  const [isBulkRefreshingIntel, setIsBulkRefreshingIntel] = useState<boolean>(false);
  const [intelNotice, setIntelNotice] = useState<string | null>(null);

  // Content Brief state
  const [briefTargetRecId, setBriefTargetRecId] = useState<number | null>(null);

  // Content Draft state
  const [draftTargetBriefId, setDraftTargetBriefId] = useState<number | null>(null);

  // SEO Action state
  const [actionTargetRecId, setActionTargetRecId] = useState<number | null>(null);
  const [actionTargetDraftId, setActionTargetDraftId] = useState<number | null>(null);
  const [actionTargetBriefId, setActionTargetBriefId] = useState<number | null>(null);

  // Load user projects on initial mount
  const fetchUserProjects = async () => {
    setIsLoadingProjects(true);
    setProjectError(null);
    try {
      const data = await getProjects();
      setProjects(data);
      if (data.length > 0) {
        const savedProjectId = localStorage.getItem('doxarank_active_project_id');
        const matched = savedProjectId ? data.find((p) => String(p.id) === savedProjectId) : null;
        const initial = matched || data[0];
        setSelectedProject(initial);
        localStorage.setItem('doxarank_active_project_id', String(initial.id));
      } else {
        setSelectedProject(null);
        localStorage.removeItem('doxarank_active_project_id');
      }
    } catch (err: any) {
      setProjectError(err?.data?.detail || 'Failed to load projects.');
    } finally {
      setIsLoadingProjects(false);
    }
  };

  const fetchSubscription = async () => {
    try {
      const summary = await getUserSubscription();
      setSubscriptionSummary(summary);
    } catch (err) {
      console.warn('Could not load subscription summary:', err);
    }
  };

  useEffect(() => {
    document.title = 'DoxaRank | SEO Audit & Analytics Dashboard';
    fetchUserProjects();
    fetchSubscription();
  }, []);

  // Fetch ranking summaries whenever project changes
  const fetchRankingSummaries = async (projectId: number) => {
    try {
      const summaryList = await getRankingSummary(projectId);
      const map: Record<number, KeywordRankingSummary> = {};
      summaryList.forEach((s) => {
        map[s.keyword_id] = s;
      });
      setRankingSummaries(map);
    } catch (err) {
      console.warn('Could not fetch ranking summaries:', err);
    }
  };

  const fetchRankJobs = async (projectId: number) => {
    try {
      const jobs = await getRankCheckJobs(projectId);
      if (jobs.length > 0) {
        setActiveRankJob(jobs[0]);
      } else {
        setActiveRankJob(null);
      }
    } catch (err) {
      console.warn('Could not load rank check jobs:', err);
    }
  };

  // Poll active rank check job if one is running
  useEffect(() => {
    if (!activeRankJob || !selectedProject) return;
    if (activeRankJob.status !== 'running' && activeRankJob.status !== 'pending') return;

    const intervalId = setInterval(async () => {
      try {
        const jobs = await getRankCheckJobs(selectedProject.id);
        const latestJob = jobs.find((j) => j.id === activeRankJob.id);
        if (latestJob) {
          setActiveRankJob(latestJob);
          if (latestJob.status !== 'running' && latestJob.status !== 'pending') {
            setIsCheckingRankings(false);
            fetchRankingSummaries(selectedProject.id);
            if (selectedKeyword) {
              fetchRankings(selectedKeyword.id);
            }
          }
        }
      } catch (err) {
        console.warn('Could not poll rank check jobs:', err);
      }
    }, 3000);

    return () => clearInterval(intervalId);
  }, [activeRankJob, selectedProject, selectedKeyword]);

  // Trigger Rank Check
  const handleTriggerRankCheck = async (keywordId?: number) => {
    if (!selectedProject) return;
    setIsCheckingRankings(true);
    setRankCheckNotice(null);
    try {
      const res = await triggerRankCheck({
        project_id: keywordId ? undefined : selectedProject.id,
        keyword_id: keywordId,
      });
      setRankCheckNotice(res.message);
      await fetchRankingSummaries(selectedProject.id);
      await fetchRankJobs(selectedProject.id);
      if (selectedKeyword) {
        await fetchRankings(selectedKeyword.id);
      }
    } catch (err: any) {
      const msg = err?.data?.error || err?.data?.detail || err?.message || 'Failed to trigger rank check.';
      setRankCheckNotice(`Notice: ${msg}`);
    } finally {
      setIsCheckingRankings(false);
    }
  };

  // Refresh single keyword intelligence
  const handleRefreshKeywordIntelligence = async (kwId: number, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setRefreshingIntelId(kwId);
    try {
      const updatedIntel = await refreshKeywordIntelligence(kwId, true);
      setKeywords((prev) => prev.map((k) => (k.id === kwId ? { ...k, intelligence: updatedIntel } : k)));
      if (selectedKeyword && selectedKeyword.id === kwId) {
        setSelectedKeyword((prev) => (prev ? { ...prev, intelligence: updatedIntel } : null));
      }
      setIntelNotice(`Intelligence refreshed for keyword #${kwId}.`);
      setTimeout(() => setIntelNotice(null), 4000);
    } catch (err: any) {
      const msg = err?.data?.error || err?.data?.detail || err?.message || 'Failed to refresh keyword intelligence.';
      alert(msg);
    } finally {
      setRefreshingIntelId(null);
    }
  };

  // Bulk refresh keyword intelligence
  const handleBulkRefreshIntelligence = async () => {
    if (!selectedProject) return;
    setIsBulkRefreshingIntel(true);
    try {
      const res = await bulkRefreshKeywordIntelligence(selectedProject.id, true);
      setIntelNotice(`Bulk intelligence refresh queued for ${res.queued_keywords_count ?? 'all'} keywords.`);
      setTimeout(() => setIntelNotice(null), 5000);
      setTimeout(() => {
        if (selectedProject) fetchKeywords(selectedProject.id);
      }, 2000);
    } catch (err: any) {
      const msg = err?.data?.error || err?.data?.detail || err?.message || 'Failed to execute bulk intelligence refresh.';
      alert(msg);
    } finally {
      setIsBulkRefreshingIntel(false);
    }
  };

  // Fetch keywords for active project
  const fetchKeywords = async (projectId: number) => {
    setIsLoadingKeywords(true);
    setKeywordError(null);
    setSelectedKeyword(null);
    setRankings([]);
    try {
      const data = await getKeywords(projectId);
      setKeywords(data);
      if (data.length > 0) {
        setSelectedKeyword(data[0]);
      } else {
        setSelectedKeyword(null);
      }
      fetchRankingSummaries(projectId);
      fetchRankJobs(projectId);
    } catch (err: any) {
      setKeywordError(err?.data?.detail || 'Failed to load tracked keywords.');
    } finally {
      setIsLoadingKeywords(false);
    }
  };

  // Fetch rankings for selected keyword
  const fetchRankings = async (keywordId: number) => {
    setIsLoadingRankings(true);
    setRankingError(null);
    try {
      const data = await getRankings(keywordId);
      setRankings(data);
    } catch (err: any) {
      setRankingError(err?.data?.detail || 'Failed to load ranking history.');
    } finally {
      setIsLoadingRankings(false);
    }
  };

  // When selected project changes, re-fetch keywords
  useEffect(() => {
    if (selectedProject) {
      fetchKeywords(selectedProject.id);
    } else {
      setKeywords([]);
      setSelectedKeyword(null);
      setRankings([]);
      setRankingSummaries({});
    }
  }, [selectedProject]);

  // When selected keyword changes, fetch rankings
  useEffect(() => {
    if (selectedKeyword) {
      fetchRankings(selectedKeyword.id);
    } else {
      setRankings([]);
    }
  }, [selectedKeyword]);

  // Project Handlers
  const handleSelectProject = (project: Project) => {
    setSelectedProject(project);
    localStorage.setItem('doxarank_active_project_id', String(project.id));
  };

  const handleOpenCreateProjectModal = () => {
    setEditingProject(null);
    setIsProjectModalOpen(true);
  };

  const handleOpenEditProjectModal = (project: Project) => {
    setEditingProject(project);
    setIsProjectModalOpen(true);
  };

  const handleSaveProject = async (payload: CreateProjectPayload) => {
    if (editingProject) {
      const updated = await updateProject(editingProject.id, payload);
      setProjects((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      if (selectedProject?.id === updated.id) {
        setSelectedProject(updated);
      }
    } else {
      const created = await createProject(payload);
      setProjects((prev) => [created, ...prev]);
      setSelectedProject(created);
      localStorage.setItem('doxarank_active_project_id', String(created.id));
    }
  };

  const handleConfirmDeleteProject = async () => {
    if (!deletingProject) return;
    setIsDeletingProject(true);
    try {
      await deleteProject(deletingProject.id);
      const remaining = projects.filter((p) => p.id !== deletingProject.id);
      setProjects(remaining);
      if (selectedProject?.id === deletingProject.id) {
        const next = remaining.length > 0 ? remaining[0] : null;
        setSelectedProject(next);
        if (next) {
          localStorage.setItem('doxarank_active_project_id', String(next.id));
        } else {
          localStorage.removeItem('doxarank_active_project_id');
        }
      }
      setDeletingProject(null);
    } catch (err: any) {
      alert(err?.data?.detail || 'Failed to delete project.');
    } finally {
      setIsDeletingProject(false);
    }
  };

  // Keyword Handlers
  const handleOpenCreateKeywordModal = () => {
    setEditingKeyword(null);
    setIsKeywordModalOpen(true);
  };

  const handleOpenEditKeywordModal = (keyword: Keyword, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setEditingKeyword(keyword);
    setIsKeywordModalOpen(true);
  };

  const handleSaveKeyword = async (payload: CreateKeywordPayload | UpdateKeywordPayload) => {
    if (editingKeyword) {
      const updated = await updateKeyword(editingKeyword.id, payload as UpdateKeywordPayload);
      setKeywords((prev) => prev.map((k) => (k.id === updated.id ? updated : k)));
      if (selectedKeyword?.id === updated.id) {
        setSelectedKeyword(updated);
      }
    } else {
      const created = await createKeyword(payload as CreateKeywordPayload);
      setKeywords((prev) => [created, ...prev]);
      setSelectedKeyword(created);
    }
  };

  const handleConfirmDeleteKeyword = async () => {
    if (!deletingKeyword) return;
    setIsDeletingKeyword(true);
    try {
      await deleteKeyword(deletingKeyword.id);
      const remaining = keywords.filter((k) => k.id !== deletingKeyword.id);
      setKeywords(remaining);
      if (selectedKeyword?.id === deletingKeyword.id) {
        setSelectedKeyword(remaining.length > 0 ? remaining[0] : null);
      }
      setDeletingKeyword(null);
    } catch (err: any) {
      alert(err?.data?.detail || 'Failed to delete keyword.');
    } finally {
      setIsDeletingKeyword(false);
    }
  };

  // Ranking Handlers
  const handleOpenCreateRankingModal = () => {
    setEditingRanking(null);
    setIsRankingModalOpen(true);
  };

  const handleOpenEditRankingModal = (ranking: Ranking) => {
    setEditingRanking(ranking);
    setIsRankingModalOpen(true);
  };

  const handleSaveRanking = async (payload: CreateRankingPayload | UpdateRankingPayload) => {
    if (editingRanking) {
      const updated = await updateRanking(editingRanking.id, payload as UpdateRankingPayload);
      setRankings((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
    } else {
      const created = await createRanking(payload as CreateRankingPayload);
      setRankings((prev) => [created, ...prev]);
    }
  };

  const handleConfirmDeleteRanking = async () => {
    if (!deletingRanking) return;
    setIsDeletingRanking(true);
    try {
      await deleteRanking(deletingRanking.id);
      setRankings((prev) => prev.filter((r) => r.id !== deletingRanking.id));
      setDeletingRanking(null);
    } catch (err: any) {
      alert(err?.data?.detail || 'Failed to delete ranking observation.');
    } finally {
      setIsDeletingRanking(false);
    }
  };

  // Filtered keywords for table
  const filteredKeywords = useMemo(() => {
    if (!keywordFilterText.trim()) return keywords;
    const lower = keywordFilterText.toLowerCase();
    return keywords.filter(
      (k) =>
        k.keyword.toLowerCase().includes(lower) ||
        k.language.toLowerCase().includes(lower) ||
        k.device.toLowerCase().includes(lower)
    );
  }, [keywords, keywordFilterText]);

  // Derived KPI metrics for Executive Overview
  const kpiStats = useMemo(() => {
    const totalKeywords = keywords.length;
    let inTop3 = 0;
    let inTop10 = 0;
    let inTop100 = 0;
    let totalSearchVolume = 0;

    keywords.forEach((kw) => {
      const summary = rankingSummaries[kw.id];
      const pos = summary?.current_position;
      if (pos !== undefined && pos !== null) {
        if (pos <= 3) inTop3++;
        if (pos <= 10) inTop10++;
        if (pos <= 100) inTop100++;
      }
      if (kw.intelligence?.search_volume) {
        totalSearchVolume += kw.intelligence.search_volume;
      }
    });

    const visibilityScore = totalKeywords > 0 ? Math.round((inTop10 / totalKeywords) * 100) : 0;

    return {
      totalKeywords,
      inTop3,
      inTop10,
      inTop100,
      visibilityScore,
      totalSearchVolume,
    };
  }, [keywords, rankingSummaries]);

  // Navigation Items
  const navItems: { id: DashboardTab; label: string; icon: React.ReactNode; badge?: string }[] = [
    { id: 'overview', label: t('nav.overview', 'Executive Overview'), icon: <LayoutDashboard size={17} /> },
    { id: 'keywords', label: t('nav.keywords', 'Keywords & SERP'), icon: <Search size={17} />, badge: keywords.length > 0 ? String(keywords.length) : undefined },
    { id: 'audits', label: t('nav.audits', 'Audits & Crawler'), icon: <Activity size={17} /> },
    { id: 'competitors', label: t('nav.competitors', 'Competitor Intel'), icon: <Building2 size={17} /> },
    { id: 'recommendations', label: t('nav.recommendations', 'Recommendations'), icon: <Lightbulb size={17} /> },
    { id: 'content', label: t('nav.content', 'Content AI & Briefs'), icon: <FileText size={17} /> },
    { id: 'analytics', label: t('nav.analytics', 'Search Analytics'), icon: <TrendingUp size={17} /> },
    { id: 'reports', label: t('nav.reports', 'White-Label Reports'), icon: <FileSpreadsheet size={17} /> },
    { id: 'tools', label: t('nav.tools', 'Free SEO Tools'), icon: <Wrench size={17} /> },
    { id: 'operations', label: t('nav.operations', 'Autonomous Agents'), icon: <Zap size={17} /> },
    { id: 'projects', label: t('nav.projects', 'Projects Manager'), icon: <FolderKanban size={17} />, badge: projects.length > 0 ? String(projects.length) : undefined },
  ];

  return (
    <div style={shellContainerStyle}>
      {/* ------------------------------------------------------------- */}
      {/* LEFT SIDEBAR NAVIGATION (Doxa Deep Purple: #24143C)           */}
      {/* ------------------------------------------------------------- */}
      <aside
        style={{
          ...sidebarStyle,
          transform: isMobileMenuOpen ? 'translateX(0)' : undefined,
        }}
      >
        {/* Brand Header */}
        <div style={sidebarHeaderStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <img
              src="/doxa-logo.png"
              alt="Doxa Logo"
              style={{ width: '42px', height: '42px', objectFit: 'contain', borderRadius: '10px' }}
            />
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ fontSize: '18px', fontWeight: 800, color: '#ffffff', letterSpacing: '-0.02em' }}>
                  Doxa<span style={{ color: '#a372df' }}>Rank</span>
                </span>
                <span style={etBadgeStyle}>ET</span>
              </div>
              <span style={{ fontSize: '11px', color: '#cbd5e1', display: 'block' }}>
                {t('brand.subtitle', 'Ethiopia SEO Intelligence')}
              </span>
            </div>
          </div>
          {/* Close button on mobile */}
          <button
            onClick={() => setIsMobileMenuOpen(false)}
            style={mobileCloseBtnStyle}
            aria-label="Close sidebar"
          >
            <X size={18} />
          </button>
        </div>

        {/* Project Quick Selector in Sidebar */}
        <div style={projectSelectorContainerStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
            <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: '#a372df', letterSpacing: '0.05em' }}>
              {t('header.current_project', 'Current Project')}
            </span>
            <button
              onClick={handleOpenCreateProjectModal}
              style={quickAddProjectBtnStyle}
              title="Add New Website Project"
            >
              {t('projects.new', '+ New')}
            </button>
          </div>

          {isLoadingProjects ? (
            <div style={{ fontSize: '12px', color: '#cbd5e1', padding: '6px 0' }}>{t('projects.loading', 'Loading projects...')}</div>
          ) : projects.length === 0 ? (
            <button
              onClick={handleOpenCreateProjectModal}
              style={noProjectsBoxStyle}
            >
              {t('projects.create_first', '+ Create first website')}
            </button>
          ) : (
            <select
              value={selectedProject?.id ?? ''}
              onChange={(e) => {
                const p = projects.find((x) => x.id === Number(e.target.value));
                if (p) handleSelectProject(p);
              }}
              style={projectSelectStyle}
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id} style={{ color: '#0f172a', backgroundColor: '#ffffff' }}>
                  {p.name} ({p.website_url.replace(/^https?:\/\//, '')})
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Navigation Menu Links */}
        <nav style={sidebarNavStyle} aria-label="Dashboard views">
          {navItems.map((item) => {
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => {
                  setActiveTab(item.id);
                  setIsMobileMenuOpen(false);
                }}
                style={{
                  ...navButtonStyle,
                  backgroundColor: isActive ? 'rgba(119, 77, 169, 0.28)' : 'transparent',
                  color: isActive ? '#ffffff' : '#cbd5e1',
                  fontWeight: isActive ? 700 : 500,
                  borderLeft: isActive ? '3px solid #a372df' : '3px solid transparent',
                }}
              >
                <span style={{ display: 'inline-flex', alignItems: 'center' }}>{item.icon}</span>
                <span style={{ flex: 1, textAlign: 'left', fontSize: '13px' }}>{item.label}</span>
                {item.badge && (
                  <span
                    style={{
                      ...navBadgeStyle,
                      backgroundColor: isActive ? '#774DA9' : 'rgba(255, 255, 255, 0.1)',
                      color: '#ffffff',
                    }}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Sidebar Footer: Plan Badge & User Actions */}
        <div style={sidebarFooterStyle}>
          {subscriptionSummary && (
            <div
              id="dashboard-plan-badge"
              onClick={() => setIsSubscriptionModalOpen(true)}
              title="Click to manage subscription and billing"
              style={sidebarPlanBoxStyle}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <span style={{
                  fontSize: '11px',
                  fontWeight: 800,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  color: subscriptionSummary.plan.code === 'AGENCY' ? '#c084fc' : subscriptionSummary.plan.code === 'STARTER' ? '#a372df' : '#cbd5e1'
                }}>
                  {subscriptionSummary.plan.name} PLAN
                </span>
                <span style={{ fontSize: '10px', color: '#a372df', fontWeight: 600 }}>{t('header.manage', 'Manage')} &rarr;</span>
              </div>
              <div style={{ fontSize: '11px', color: '#cbd5e1' }}>
                Sites: <strong style={{ color: '#ffffff' }}>{subscriptionSummary.usage.projects.current}</strong>/{subscriptionSummary.usage.projects.limit}
                <span style={{ margin: '0 6px', color: '#64748b' }}>|</span>
                KWs: <strong style={{ color: '#ffffff' }}>{subscriptionSummary.usage.keywords.current}</strong>/{subscriptionSummary.usage.keywords.limit}
              </div>
            </div>
          )}

          <div style={{ padding: '0 0 10px 0', borderBottom: '1px solid rgba(255, 255, 255, 0.08)', marginBottom: '8px' }}>
            <LanguageSelector variant="dark" />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '4px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
              <div style={userAvatarStyle}>
                {(user?.first_name?.[0] || user?.email?.[0] || 'D').toUpperCase()}
              </div>
              <div style={{ overflow: 'hidden' }}>
                <div style={{ fontSize: '12px', fontWeight: 700, color: '#ffffff', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                  {user?.full_name || 'DoxaRank User'}
                </div>
                <div style={{ fontSize: '11px', color: '#cbd5e1', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                  {user?.email}
                </div>
              </div>
            </div>

            <button
              id="logout-button"
              onClick={logout}
              style={sidebarLogoutBtnStyle}
              title={t('header.sign_out', 'Sign Out')}
              aria-label={t('header.sign_out', 'Sign Out')}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      {/* Mobile Drawer Overlay */}
      {isMobileMenuOpen && (
        <div
          onClick={() => setIsMobileMenuOpen(false)}
          style={mobileBackdropStyle}
        />
      )}

      {/* ------------------------------------------------------------- */}
      {/* MAIN VIEW AREA                                                */}
      {/* ------------------------------------------------------------- */}
      <div style={mainAreaStyle}>
        {/* Top Header Bar */}
        <header style={topHeaderStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button
              onClick={() => setIsMobileMenuOpen(true)}
              style={mobileToggleBtnStyle}
              aria-label="Open navigation menu"
            >
              <Menu size={20} />
            </button>

            {/* Active Project Breadcrumb */}
            {selectedProject ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '12px', color: '#64748b', fontWeight: 600 }}>Project:</span>
                <span style={{ fontSize: '15px', fontWeight: 800, color: '#24143C' }}>
                  {selectedProject.name}
                </span>
                <a
                  href={selectedProject.website_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ ...websiteLinkBadgeStyle, display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                  title="Open live website"
                >
                  <ExternalLink size={12} />
                  <span>{selectedProject.website_url.replace(/^https?:\/\//, '')}</span>
                </a>
              </div>
            ) : (
              <span style={{ fontSize: '14px', color: '#64748b', fontWeight: 600 }}>
                No active project selected
              </span>
            )}
          </div>

          {/* Quick Action Buttons & Language Selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <LanguageSelector variant="light" />

            <button
              id="nav-seo-tools-btn"
              onClick={() => {
                setActiveTab('tools');
                setTimeout(() => {
                  const el = document.getElementById('seo-tools-section');
                  if (el) el.scrollIntoView({ behavior: 'smooth' });
                }, 50);
              }}
              style={{ ...headerToolBtnStyle, display: 'inline-flex', alignItems: 'center', gap: '6px' }}
              title="Free Ethiopian SEO Utilities"
            >
              <Wrench size={14} />
              <span>{t('header.tools', 'Tools')}</span>
            </button>

            {selectedProject && (
              <>
                <button
                  id="check-all-rankings-button"
                  onClick={() => handleTriggerRankCheck()}
                  disabled={isCheckingRankings || keywords.length === 0}
                  style={{
                    ...headerActionBtnStyle,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    backgroundColor: isCheckingRankings ? '#94a3b8' : '#774DA9',
                    cursor: isCheckingRankings || keywords.length === 0 ? 'not-allowed' : 'pointer',
                  }}
                  title="Run automated rank check across google.com.et"
                >
                  <Zap size={14} />
                  <span>{isCheckingRankings ? t('header.checking', 'Checking...') : t('header.check_serp', 'Check SERP')}</span>
                </button>

                <button
                  id="header-track-keyword-button"
                  onClick={handleOpenCreateKeywordModal}
                  style={{ ...headerPrimaryBtnStyle, display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                  title="Track new search query on Google Ethiopia"
                >
                  <Plus size={14} />
                  <span>{t('header.track_keyword', 'Track Keyword')}</span>
                </button>
              </>
            )}

            <button
              id="open-billing-modal-btn"
              onClick={() => setIsSubscriptionModalOpen(true)}
              style={headerBillingBtnStyle}
            >
              {t('header.upgrade', 'Upgrade')}
            </button>
          </div>
        </header>

        {/* Global Notices & Alerts */}
        <div style={{ padding: '0 24px', marginTop: '16px' }}>
          {rankCheckNotice && (
            <div style={noticeSuccessStyle}>
              <span>{rankCheckNotice}</span>
              <button onClick={() => setRankCheckNotice(null)} style={closeNoticeBtnStyle} aria-label="Close"><X size={14} /></button>
            </div>
          )}

          {intelNotice && (
            <div style={{ ...noticeInfoStyle, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Lightbulb size={16} color="#774DA9" />
                <span>{intelNotice}</span>
              </div>
              <button onClick={() => setIntelNotice(null)} style={closeNoticeBtnStyle} aria-label="Close"><X size={14} /></button>
            </div>
          )}

          {activeRankJob && activeRankJob.status === 'running' && (
            <div style={{ ...noticeRunningStyle, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <RefreshCw size={15} style={{ animation: 'spin 1s linear infinite' }} />
              <span><strong>Rank check in progress:</strong> {activeRankJob.completed_keywords} / {activeRankJob.total_keywords} keywords verified on Google Ethiopia...</span>
            </div>
          )}

          {projectError && <div style={alertDangerStyle}>{projectError}</div>}
          {keywordError && <div style={alertDangerStyle}>{keywordError}</div>}
          {rankingError && <div style={alertDangerStyle}>{rankingError}</div>}
        </div>

        {/* Tab Content Body */}
        <main style={mainContentAreaStyle}>
          {/* TAB 1: EXECUTIVE OVERVIEW */}
          {activeTab === 'overview' && (
            <section style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {selectedProject ? (
                <>
                  {/* Overview Hero Bar */}
                  <div style={overviewHeroCardStyle}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                          <span style={doxaPillBadgeStyle}>Google Ethiopia Live Context</span>
                          <span style={{ fontSize: '12px', color: '#cbd5e1' }}>ID: #{selectedProject.id}</span>
                        </div>
                        <h2 style={{ fontSize: '22px', fontWeight: 800, color: '#ffffff', margin: 0 }}>
                          {selectedProject.name}
                        </h2>
                        <p style={{ fontSize: '13px', color: '#cbd5e1', margin: '4px 0 0 0' }}>
                          Auditing Google Ethiopia (google.com.et) for Amharic &amp; English queries
                        </p>
                      </div>

                      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                        <button
                          onClick={() => setActiveTab('keywords')}
                          style={overviewSecondaryBtnStyle}
                        >
                          View Keywords ({keywords.length})
                        </button>
                        <button
                          onClick={() => setActiveTab('audits')}
                          style={overviewSecondaryBtnStyle}
                        >
                          Crawl Audit
                        </button>
                        <button
                          onClick={() => handleOpenEditProjectModal(selectedProject)}
                          style={overviewSecondaryBtnStyle}
                        >
                          Edit Settings
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* 4 Compact KPI Metric Cards */}
                  <div style={kpiGridStyle}>
                    <div style={kpiCardStyle}>
                      <div style={kpiLabelStyle}>{t('kpi.avg_position', 'Visibility Score')}</div>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '4px' }}>
                        <span style={{ fontSize: '26px', fontWeight: 800, color: '#24143C' }}>
                          {kpiStats.visibilityScore}%
                        </span>
                        <span style={{ fontSize: '12px', fontWeight: 700, color: '#10b981' }}>Top 10 Rate</span>
                      </div>
                      <span style={kpiSubtextStyle}>{kpiStats.inTop10} of {kpiStats.totalKeywords} keywords on Page 1</span>
                    </div>

                    <div style={kpiCardStyle}>
                      <div style={kpiLabelStyle}>{t('kpi.top_3', 'Top 3 Rankings')}</div>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '4px' }}>
                        <span style={{ fontSize: '26px', fontWeight: 800, color: '#774DA9' }}>
                          {kpiStats.inTop3}
                        </span>
                        <span style={{ fontSize: '12px', color: '#64748b' }}>Podium spots</span>
                      </div>
                      <span style={kpiSubtextStyle}>{t('kpi.prime_visibility', 'Highest CTR positions on google.com.et')}</span>
                    </div>

                    <div style={kpiCardStyle}>
                      <div style={kpiLabelStyle}>{t('kpi.total_keywords', 'Total Tracked Keywords')}</div>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '4px' }}>
                        <span style={{ fontSize: '26px', fontWeight: 800, color: '#0f172a' }}>
                          {kpiStats.totalKeywords}
                        </span>
                        <span style={{ fontSize: '12px', color: '#64748b' }}>active queries</span>
                      </div>
                      <span style={kpiSubtextStyle}>{t('kpi.multilingual_demand', 'Amharic, Afaan Oromoo & English')}</span>
                    </div>

                    <div style={kpiCardStyle}>
                      <div style={kpiLabelStyle}>{t('kpi.search_demand', 'Aggregate Search Demand')}</div>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '4px' }}>
                        <span style={{ fontSize: '26px', fontWeight: 800, color: '#10b981' }}>
                          {kpiStats.totalSearchVolume > 0 ? kpiStats.totalSearchVolume.toLocaleString() : 'Live'}
                        </span>
                        <span style={{ fontSize: '12px', color: '#64748b' }}>mo/est</span>
                      </div>
                      <span style={kpiSubtextStyle}>Estimated monthly search volume</span>
                    </div>
                  </div>

                  {/* Overview Keywords Quick Table & Integrations Summary */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(450px, 1fr))', gap: '20px' }}>
                    {/* Top Keyword Performers */}
                    <div style={dashboardSectionCardStyle}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                        <h3 style={{ fontSize: '15px', fontWeight: 700, color: '#24143C' }}>
                          Rankings Snapshot (google.com.et)
                        </h3>
                        <button
                          onClick={() => setActiveTab('keywords')}
                          style={{ background: 'none', border: 'none', color: '#774DA9', fontSize: '12px', fontWeight: 700, cursor: 'pointer' }}
                        >
                          View all &rarr;
                        </button>
                      </div>

                      {keywords.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: '24px 0', color: '#64748b' }}>
                          <p style={{ fontSize: '13px', marginBottom: '10px' }}>No keywords tracked yet.</p>
                          <button
                            id="empty-add-keyword-button"
                            onClick={handleOpenCreateKeywordModal}
                            style={headerPrimaryBtnStyle}
                          >
                            Track first keyword
                          </button>
                        </div>
                      ) : (
                        <div style={{ overflowX: 'auto' }}>
                          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                            <thead>
                              <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', textAlign: 'left' }}>
                                <th style={{ padding: '8px 10px', fontWeight: 600 }}>{t('table.query', 'Query')}</th>
                                <th style={{ padding: '8px 10px', fontWeight: 600 }}>{t('table.rank', 'Rank')}</th>
                                <th style={{ padding: '8px 10px', fontWeight: 600 }}>{t('table.change', 'Change')}</th>
                                <th style={{ padding: '8px 10px', fontWeight: 600 }}>{t('table.volume', 'Volume')}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {keywords.slice(0, 5).map((kw) => {
                                const summary = rankingSummaries[kw.id];
                                const currPos = summary?.current_position;
                                const change = summary?.change;
                                return (
                                  <tr
                                    key={kw.id}
                                    onClick={() => {
                                      setSelectedKeyword(kw);
                                      setActiveTab('keywords');
                                    }}
                                    style={{ borderBottom: '1px solid #f1f5f9', cursor: 'pointer' }}
                                  >
                                    <td style={{ padding: '8px 10px', fontWeight: 600, color: '#0f172a' }}>
                                      {kw.keyword}
                                    </td>
                                    <td style={{ padding: '8px 10px' }}>
                                      {currPos ? (
                                        <span style={{
                                          fontWeight: 800,
                                          padding: '2px 7px',
                                          borderRadius: '6px',
                                          fontSize: '12px',
                                          backgroundColor: currPos <= 3 ? '#fef3c7' : currPos <= 10 ? '#f3eef9' : '#f1f5f9',
                                          color: currPos <= 3 ? '#92400e' : currPos <= 10 ? '#774DA9' : '#475569',
                                        }}>
                                          #{currPos}
                                        </span>
                                      ) : (
                                        <span style={{ color: '#64748b' }}>—</span>
                                      )}
                                    </td>
                                    <td style={{ padding: '8px 10px', fontSize: '12px' }}>
                                      {typeof change === 'number' && change !== 0 ? (
                                        <span style={{ color: change > 0 ? '#10b981' : '#ef4444', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: '2px' }}>
                                          {change > 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                                          <span>{change > 0 ? `+${change}` : `${change}`}</span>
                                        </span>
                                      ) : (
                                        <span style={{ color: '#64748b' }}>0</span>
                                      )}
                                    </td>
                                    <td style={{ padding: '8px 10px', color: '#64748b' }}>
                                      {kw.intelligence?.search_volume?.toLocaleString() ?? '—'}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>

                    {/* Integrated Platform Services Status */}
                    <div style={dashboardSectionCardStyle}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                        <h3 style={{ fontSize: '15px', fontWeight: 700, color: '#24143C' }}>
                          Integrated Telemetry Status
                        </h3>
                        <button
                          onClick={() => setActiveTab('analytics')}
                          style={{ background: 'none', border: 'none', color: '#774DA9', fontSize: '12px', fontWeight: 700, cursor: 'pointer' }}
                        >
                          Configure &rarr;
                        </button>
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        <div style={telemetryItemStyle}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <Globe size={18} color="#774DA9" />
                            <div>
                              <div style={{ fontWeight: 600, fontSize: '13px', color: '#0f172a' }}>Google Ethiopia SERP</div>
                              <div style={{ fontSize: '11px', color: '#64748b' }}>Live SERP polling engine</div>
                            </div>
                          </div>
                          <span style={telemetryConnectedStyle}>● Active</span>
                        </div>

                        <div style={telemetryItemStyle}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <BarChart2 size={18} color="#774DA9" />
                            <div>
                              <div style={{ fontWeight: 600, fontSize: '13px', color: '#0f172a' }}>Google Search Console</div>
                              <div style={{ fontSize: '11px', color: '#64748b' }}>OAuth2 query &amp; impression sync</div>
                            </div>
                          </div>
                          <span style={gscConnection ? telemetryConnectedStyle : telemetryPendingStyle}>
                            {gscConnection ? '● Connected' : '○ Not Linked'}
                          </span>
                        </div>

                        <div style={telemetryItemStyle}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <Search size={18} color="#774DA9" />
                            <div>
                              <div style={{ fontWeight: 600, fontSize: '13px', color: '#0f172a' }}>Microsoft Clarity</div>
                              <div style={{ fontSize: '11px', color: '#64748b' }}>Session recording &amp; heatmaps</div>
                            </div>
                          </div>
                          <span style={telemetryConnectedStyle}>● Ready</span>
                        </div>

                        <div style={telemetryItemStyle}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <Tag size={18} color="#774DA9" />
                            <div>
                              <div style={{ fontWeight: 600, fontSize: '13px', color: '#0f172a' }}>Google Tag Manager</div>
                              <div style={{ fontSize: '11px', color: '#64748b' }}>Container tag verification</div>
                            </div>
                          </div>
                          <span style={telemetryPendingStyle}>○ Available</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <div style={welcomePromptStyle}>
                  <img src="/doxa-logo.png" alt="Doxa" style={{ width: '48px', height: '48px', margin: '0 auto 12px', objectFit: 'contain' }} />
                  <h2 style={{ margin: '0 0 8px 0', fontSize: '20px', fontWeight: 800, color: '#24143C' }}>
                    Welcome to DoxaRank, {user?.first_name || user?.email}!
                  </h2>
                  <p style={{ margin: '0 0 16px 0', color: '#64748b', fontSize: '13px', maxWidth: '460px' }}>
                    Create your first website project to begin tracking Google Ethiopia rankings and technical site health.
                  </p>
                  <button
                    id="empty-add-project-button"
                    onClick={handleOpenCreateProjectModal}
                    style={headerPrimaryBtnStyle}
                  >
                    + Create Website Project
                  </button>
                </div>
              )}
            </section>
          )}

          {/* TAB 2: KEYWORDS & SERP TRACKING */}
          {activeTab === 'keywords' && selectedProject && (
            <section style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Header and Controls */}
              <div style={dashboardSectionCardStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', marginBottom: '14px' }}>
                  <div>
                    <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 800, color: '#24143C' }}>
                      Tracked Keywords {keywords.length > 0 && `(${keywords.length})`}
                    </h3>
                    <p style={{ margin: '2px 0 0 0', fontSize: '13px', color: '#64748b' }}>
                      Daily positions on <strong>google.com.et</strong> for {selectedProject.name}.
                    </p>
                  </div>

                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                    <input
                      type="text"
                      placeholder="Filter queries..."
                      value={keywordFilterText}
                      onChange={(e) => setKeywordFilterText(e.target.value)}
                      style={filterInputStyle}
                    />

                    <button
                      id="bulk-refresh-intel-button"
                      onClick={handleBulkRefreshIntelligence}
                      disabled={isBulkRefreshingIntel || keywords.length === 0}
                      style={{
                        ...actionSmallBtnStyle,
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                        backgroundColor: isBulkRefreshingIntel ? '#94a3b8' : '#774DA9',
                        color: '#ffffff',
                      }}
                      title="Bulk refresh search volume and CPC intelligence"
                    >
                      <RefreshCw size={13} style={{ animation: isBulkRefreshingIntel ? 'spin 1s linear infinite' : 'none' }} />
                      <span>{isBulkRefreshingIntel ? 'Refreshing...' : 'Bulk Intel'}</span>
                    </button>

                    <button
                      id="add-keyword-button"
                      onClick={handleOpenCreateKeywordModal}
                      style={{
                        ...actionSmallBtnStyle,
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                        backgroundColor: '#24143C',
                        color: '#ffffff',
                      }}
                    >
                      <Plus size={14} />
                      <span>Add Keyword</span>
                    </button>
                  </div>
                </div>

                {isLoadingKeywords ? (
                  <div style={loadingBoxStyle}>Loading keywords for {selectedProject.name}...</div>
                ) : filteredKeywords.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '32px 16px' }}>
                    <Search size={32} color="#94a3b8" style={{ margin: '0 auto 8px', display: 'block' }} />
                    <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#24143C', margin: '0 0 4px' }}>
                      No matching keywords found
                    </h4>
                    <p style={{ fontSize: '13px', color: '#64748b', marginBottom: '14px' }}>
                      Add search terms in Amharic, Oromo, or English to monitor SERP visibility.
                    </p>
                    <button onClick={handleOpenCreateKeywordModal} style={headerPrimaryBtnStyle}>
                      Track a keyword
                    </button>
                  </div>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
                      <thead>
                        <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>
                          <th style={thStyle}>{t('table.keyword', 'Keyword Query')}</th>
                          <th style={thStyle}>{t('table.position', 'Position')}</th>
                          <th style={thStyle}>{t('table.delta', 'Delta')}</th>
                          <th style={thStyle}>{t('table.search_vol', 'Search Vol')}</th>
                          <th style={thStyle}>{t('table.cpc', 'Est. CPC')}</th>
                          <th style={thStyle}>{t('table.target_et', 'Target (ET)')}</th>
                          <th style={thStyle}>{t('table.device', 'Device')}</th>
                          <th style={thStyle}>{t('table.status', 'Status')}</th>
                          <th style={{ ...thStyle, textAlign: 'right' }}>{t('table.actions', 'Actions')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredKeywords.map((kw) => {
                          const isSelected = selectedKeyword?.id === kw.id;
                          const summary = rankingSummaries[kw.id];
                          const currPos = summary?.current_position;
                          const change = summary?.change;
                          const intel = kw.intelligence;

                          return (
                            <tr
                              key={kw.id}
                              id={`keyword-row-${kw.id}`}
                              onClick={() => setSelectedKeyword(kw)}
                              style={{
                                borderBottom: '1px solid #f1f5f9',
                                backgroundColor: isSelected ? '#f5f0fb' : 'transparent',
                                cursor: 'pointer',
                                transition: 'background-color 0.15s ease',
                              }}
                            >
                              <td style={tdStyle}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                  {isSelected && <ChevronRight size={14} color="#774DA9" style={{ flexShrink: 0 }} />}
                                  <span style={{ fontWeight: 700, color: isSelected ? '#774DA9' : '#0f172a' }}>
                                    {kw.keyword}
                                  </span>
                                </div>
                              </td>
                              <td style={tdStyle}>
                                {currPos !== undefined && currPos !== null ? (
                                  <span
                                    style={{
                                      display: 'inline-flex',
                                      alignItems: 'center',
                                      padding: '2px 8px',
                                      borderRadius: '6px',
                                      fontWeight: 800,
                                      fontSize: '12px',
                                      backgroundColor: currPos <= 3 ? '#fef3c7' : currPos <= 10 ? '#f3eef9' : '#f1f5f9',
                                      color: currPos <= 3 ? '#92400e' : currPos <= 10 ? '#774DA9' : '#475569',
                                    }}
                                  >
                                    #{currPos}
                                  </span>
                                ) : (
                                  <span style={{ color: '#64748b' }}>—</span>
                                )}
                              </td>
                              <td style={tdStyle}>
                                {typeof change === 'number' && change !== 0 ? (
                                  <span style={{ fontWeight: 700, color: change > 0 ? '#10b981' : '#ef4444', display: 'inline-flex', alignItems: 'center', gap: '2px' }}>
                                    {change > 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                                    <span>{change > 0 ? `+${change}` : `${change}`}</span>
                                  </span>
                                ) : (
                                  <span style={{ color: '#64748b' }}>0</span>
                                )}
                              </td>
                              <td style={tdStyle}>
                                {intel?.search_volume !== null && intel?.search_volume !== undefined ? (
                                  <span style={{ fontWeight: 600, color: '#334155' }}>{formatNumber(intel.search_volume)}</span>
                                ) : (
                                  <span style={{ color: '#64748b' }}>—</span>
                                )}
                              </td>
                              <td style={tdStyle}>
                                {intel?.cpc ? (
                                  <span style={{ fontWeight: 700, color: '#10b981' }}>${intel.cpc}</span>
                                ) : (
                                  <span style={{ color: '#64748b' }}>—</span>
                                )}
                              </td>
                              <td style={tdStyle}>
                                <span style={countryBadgeStyle}>ET</span>
                              </td>
                              <td style={tdStyle}>
                                <span style={{ fontSize: '12px', color: '#475569', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                  {kw.device === 'desktop' ? <Monitor size={13} /> : <Smartphone size={13} />}
                                  <span>{formatDevice(kw.device)}</span>
                                </span>
                              </td>
                              <td style={tdStyle}>
                                <span style={kw.is_active ? activeStatusStyle : inactiveStatusStyle}>
                                  {formatStatus(kw.is_active ? 'active' : 'paused')}
                                </span>
                              </td>
                              <td style={{ ...tdStyle, textAlign: 'right' }}>
                                <button
                                  id={`edit-keyword-${kw.id}`}
                                  onClick={(e) => handleOpenEditKeywordModal(kw, e)}
                                  style={actionInlineBtnStyle}
                                >
                                  {t('action.edit', 'Edit')}
                                </button>
                                <button
                                  id={`delete-keyword-${kw.id}`}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setDeletingKeyword(kw);
                                  }}
                                  style={{ ...actionInlineBtnStyle, color: '#ef4444' }}
                                >
                                  {t('action.delete', 'Delete')}
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Selected Keyword Detailed Intelligence & Ranking History */}
              {selectedKeyword && (
                <div style={dashboardSectionCardStyle}>
                  {/* Selected Keyword Top Strip */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px', marginBottom: '16px' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={doxaPillBadgeStyle}>Active Query</span>
                        <span style={{ fontSize: '12px', color: '#64748b' }}>
                          Target: Google Ethiopia · {selectedKeyword.language.toUpperCase()} · {selectedKeyword.device}
                        </span>
                      </div>
                      <h3 style={{ fontSize: '20px', fontWeight: 800, color: '#24143C', margin: '4px 0 0' }}>
                        "{selectedKeyword.keyword}"
                      </h3>
                    </div>

                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        id="check-selected-keyword-button"
                        onClick={() => handleTriggerRankCheck(selectedKeyword.id)}
                        disabled={isCheckingRankings}
                        style={{ ...actionSmallBtnStyle, display: 'inline-flex', alignItems: 'center', gap: '6px', backgroundColor: '#774DA9', color: '#ffffff' }}
                      >
                        <Zap size={13} />
                        <span>Check Now</span>
                      </button>
                      <button
                        id="record-ranking-button"
                        onClick={handleOpenCreateRankingModal}
                        style={{ ...actionSmallBtnStyle, display: 'inline-flex', alignItems: 'center', gap: '4px', backgroundColor: '#774DA9', color: '#ffffff' }}
                      >
                        <Plus size={13} />
                        <span>Record Observation</span>
                      </button>
                    </div>
                  </div>

                  {/* Keyword Intelligence Cards */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', marginBottom: '20px' }}>
                    <div style={subMetricCardStyle}>
                      <span style={subMetricLabelStyle}>Monthly Search Volume</span>
                      <span style={subMetricValStyle}>
                        {selectedKeyword.intelligence?.search_volume !== null && selectedKeyword.intelligence?.search_volume !== undefined
                          ? selectedKeyword.intelligence.search_volume.toLocaleString()
                          : 'N/A'}
                      </span>
                      <span style={{ fontSize: '11px', color: '#64748b' }}>google.com.et demand</span>
                    </div>

                    <div style={subMetricCardStyle}>
                      <span style={subMetricLabelStyle}>Advertiser CPC</span>
                      <span style={{ ...subMetricValStyle, color: '#10b981' }}>
                        {selectedKeyword.intelligence?.cpc ? `$${selectedKeyword.intelligence.cpc} USD` : 'N/A'}
                      </span>
                      <span style={{ fontSize: '11px', color: '#64748b' }}>Est. commercial bid</span>
                    </div>

                    <div style={subMetricCardStyle}>
                      <span style={subMetricLabelStyle}>Search Intent</span>
                      <span style={{ ...subMetricValStyle, color: '#774DA9', textTransform: 'capitalize' }}>
                        {selectedKeyword.intelligence?.intent || 'Commercial'}
                      </span>
                      <span style={{ fontSize: '11px', color: '#64748b' }}>Intent classification</span>
                    </div>

                    <div style={subMetricCardStyle}>
                      <span style={subMetricLabelStyle}>Competition Level</span>
                      <span style={{ ...subMetricValStyle, fontSize: '14px' }}>
                        {selectedKeyword.intelligence?.competition || 'Low'}
                      </span>
                      <button
                        id={`refresh-intel-card-btn-${selectedKeyword.id}`}
                        onClick={(e) => handleRefreshKeywordIntelligence(selectedKeyword.id, e)}
                        disabled={refreshingIntelId === selectedKeyword.id}
                        style={{ ...refreshMiniBtnStyle, display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                      >
                        <RefreshCw size={11} style={{ animation: refreshingIntelId === selectedKeyword.id ? 'spin 1s linear infinite' : 'none' }} />
                        <span>{refreshingIntelId === selectedKeyword.id ? 'Refreshing...' : 'Refresh Intel'}</span>
                      </button>
                    </div>
                  </div>

                  {/* Ranking History Observation Table */}
                  <h4 style={{ fontSize: '14px', fontWeight: 700, color: '#24143C', marginBottom: '8px' }}>
                    Historical SERP Observations
                  </h4>

                  {isLoadingRankings ? (
                    <div style={loadingBoxStyle}>Loading ranking history...</div>
                  ) : rankings.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '20px', backgroundColor: '#faf7fd', borderRadius: '8px', color: '#64748b' }}>
                      <p style={{ fontSize: '13px', margin: '0 0 10px' }}>No recorded rankings for this keyword yet.</p>
                      <button
                        id="empty-check-ranking-button"
                        onClick={() => handleTriggerRankCheck(selectedKeyword.id)}
                        style={{ ...actionSmallBtnStyle, display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                      >
                        <Zap size={13} />
                        <span>Check SERP on Google Ethiopia</span>
                      </button>
                    </div>
                  ) : (
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
                        <thead>
                          <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>
                            <th style={thStyle}>{t('table.rank', 'Rank')}</th>
                            <th style={thStyle}>{t('table.status', 'Status')}</th>
                            <th style={thStyle}>{t('table.indexed_title', 'Indexed Title & URL')}</th>
                            <th style={thStyle}>{t('table.engine', 'Search Engine')}</th>
                            <th style={thStyle}>{t('table.device', 'Device')}</th>
                            <th style={thStyle}>{t('table.recorded_at', 'Recorded At')}</th>
                            <th style={{ ...thStyle, textAlign: 'right' }}>{t('table.actions', 'Actions')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rankings.map((ranking) => (
                            <tr key={ranking.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                              <td style={tdStyle}>
                                <span style={{
                                  fontWeight: 800,
                                  fontSize: '13px',
                                  padding: '2px 7px',
                                  borderRadius: '6px',
                                  backgroundColor: ranking.position && ranking.position <= 3 ? '#fef3c7' : ranking.position && ranking.position <= 10 ? '#f3eef9' : '#f1f5f9',
                                  color: ranking.position && ranking.position <= 3 ? '#92400e' : ranking.position && ranking.position <= 10 ? '#774DA9' : '#475569',
                                }}>
                                  #{ranking.position ?? '—'}
                                </span>
                              </td>
                              <td style={tdStyle}>
                                <span style={{
                                  padding: '2px 6px',
                                  borderRadius: '4px',
                                  fontSize: '11px',
                                  fontWeight: 700,
                                  backgroundColor: ranking.result_status === 'found' ? '#ecfdf5' : '#fef2f2',
                                  color: ranking.result_status === 'found' ? '#065f46' : '#991b1b',
                                }}>
                                  {formatStatus(ranking.result_status || 'found')}
                                </span>
                              </td>
                              <td style={tdStyle}>
                                <div style={{ maxWidth: '320px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                  {ranking.title && <div style={{ fontWeight: 600, color: '#0f172a' }}>{ranking.title}</div>}
                                  {ranking.ranking_url && (
                                    <a href={ranking.ranking_url} target="_blank" rel="noopener noreferrer" style={{ color: '#774DA9', fontSize: '11px' }}>
                                      {ranking.ranking_url}
                                    </a>
                                  )}
                                </div>
                              </td>
                              <td style={tdStyle}>google.com.et</td>
                              <td style={tdStyle}>{formatDevice(ranking.device)}</td>
                              <td style={tdStyle}>{formatDate(ranking.recorded_at)}</td>
                              <td style={{ ...tdStyle, textAlign: 'right' }}>
                                <button
                                  id={`edit-ranking-${ranking.id}`}
                                  onClick={() => handleOpenEditRankingModal(ranking)}
                                  style={actionInlineBtnStyle}
                                >
                                  {t('action.edit', 'Edit')}
                                </button>
                                <button
                                  id={`delete-ranking-${ranking.id}`}
                                  onClick={() => setDeletingRanking(ranking)}
                                  style={{ ...actionInlineBtnStyle, color: '#ef4444' }}
                                >
                                  {t('action.delete', 'Delete')}
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </section>
          )}

          {/* TAB 3: AUDITS & TECHNICAL CRAWLER */}
          {activeTab === 'audits' && selectedProject && (
            <section style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <SiteAuditPanel project={selectedProject} />
              <TechnicalCrawlerPanel
                project={selectedProject}
                hasCrawlerEntitlement={!!(subscriptionSummary?.plan?.features ?? []).includes('TECHNICAL_CRAWLER')}
              />
            </section>
          )}

          {/* TAB 4: COMPETITOR SNAPSHOTS */}
          {activeTab === 'competitors' && selectedProject && (
            <section style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <CompetitorSnapshotsPanel
                project={selectedProject}
                hasCompetitorEntitlement={!!(subscriptionSummary?.plan?.features ?? []).includes('COMPETITOR_SNAPSHOTS')}
              />
            </section>
          )}

          {/* TAB 5: RECOMMENDATIONS & AI ACTIONS */}
          {activeTab === 'recommendations' && selectedProject && (
            <section style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* Sub-tab navigation */}
              <div style={subTabNavContainerStyle}>
                <button
                  onClick={() => setRecommendationsSubTab('all')}
                  style={getSubTabBtnStyle(recommendationsSubTab === 'all')}
                >
                  {t('subtab.all_views', 'All Views')}
                </button>
                <button
                  onClick={() => setRecommendationsSubTab('feed')}
                  style={getSubTabBtnStyle(recommendationsSubTab === 'feed')}
                >
                  {t('subtab.audit_feed', 'Audit Feed')}
                </button>
                <button
                  onClick={() => setRecommendationsSubTab('actions')}
                  style={getSubTabBtnStyle(recommendationsSubTab === 'actions')}
                >
                  {t('subtab.action_plan', 'Action Plan & Tasks')}
                </button>
                <button
                  onClick={() => setRecommendationsSubTab('insights')}
                  style={getSubTabBtnStyle(recommendationsSubTab === 'insights')}
                >
                  {t('subtab.serp_insights', 'SERP Insights')}
                </button>
                <button
                  onClick={() => setRecommendationsSubTab('generator')}
                  style={getSubTabBtnStyle(recommendationsSubTab === 'generator')}
                >
                  {t('subtab.ai_strategy', 'AI Strategy Generator')}
                </button>
              </div>

              {(recommendationsSubTab === 'all' || recommendationsSubTab === 'feed') && (
                <SEORecommendationsPanel project={selectedProject} />
              )}
              {(recommendationsSubTab === 'all' || recommendationsSubTab === 'actions' || actionTargetRecId !== null) && (
                <div id="seo-actions-section">
                  <SEOActionsPanel
                    project={selectedProject}
                    targetRecommendationId={actionTargetRecId}
                    targetDraftId={actionTargetDraftId}
                    targetBriefId={actionTargetBriefId}
                    onClearTargets={() => {
                      setActionTargetRecId(null);
                      setActionTargetDraftId(null);
                      setActionTargetBriefId(null);
                    }}
                  />
                </div>
              )}
              {(recommendationsSubTab === 'all' || recommendationsSubTab === 'insights') && (
                <SEOInsightsPanel project={selectedProject} />
              )}
              {(recommendationsSubTab === 'all' || recommendationsSubTab === 'generator') && (
                <AIRecommendationsPanel
                  project={selectedProject}
                  onGenerateBrief={(recId: number) => {
                    setBriefTargetRecId(recId);
                    setActiveTab('content');
                    setContentSubTab('briefs');
                  }}
                  onCreateAction={(recId: number) => {
                    setActionTargetRecId(recId);
                    setRecommendationsSubTab('actions');
                  }}
                />
              )}
            </section>
          )}

          {/* TAB 6: CONTENT AI & BRIEFS */}
          {activeTab === 'content' && selectedProject && (
            <section style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={subTabNavContainerStyle}>
                <button
                  onClick={() => setContentSubTab('all')}
                  style={getSubTabBtnStyle(contentSubTab === 'all')}
                >
                  {t('subtab.all_content', 'All Content')}
                </button>
                <button
                  onClick={() => setContentSubTab('briefs')}
                  style={getSubTabBtnStyle(contentSubTab === 'briefs')}
                >
                  {t('subtab.content_briefs', 'Content Briefs & Outlines')}
                </button>
                <button
                  onClick={() => setContentSubTab('drafts')}
                  style={getSubTabBtnStyle(contentSubTab === 'drafts')}
                >
                  {t('subtab.content_drafts', 'Drafts & Generated Articles')}
                </button>
              </div>

              {(contentSubTab === 'all' || contentSubTab === 'briefs' || briefTargetRecId !== null) && (
                <div id="seo-content-briefs-section">
                  <SEOContentBriefPanel
                    project={selectedProject}
                    selectedRecommendationId={briefTargetRecId}
                    onClearSelectedRecId={() => setBriefTargetRecId(null)}
                    onSelectBriefForDraft={(briefId: number) => {
                      setDraftTargetBriefId(briefId);
                      setContentSubTab('drafts');
                    }}
                    onCreateAction={(briefId: number) => {
                      setActionTargetBriefId(briefId);
                      setActiveTab('recommendations');
                      setRecommendationsSubTab('actions');
                    }}
                  />
                </div>
              )}
              {(contentSubTab === 'all' || contentSubTab === 'drafts' || draftTargetBriefId !== null) && (
                <div id="seo-content-drafts-section">
                  <SEOContentDraftPanel
                    currentProject={selectedProject}
                    targetBriefId={draftTargetBriefId}
                    onClearTargetBrief={() => setDraftTargetBriefId(null)}
                    onCreateAction={(draftId: number) => {
                      setActionTargetDraftId(draftId);
                      setActiveTab('recommendations');
                      setRecommendationsSubTab('actions');
                    }}
                  />
                </div>
              )}
            </section>
          )}

          {/* TAB 7: SEARCH ANALYTICS */}
          {activeTab === 'analytics' && selectedProject && (
            <section style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <SearchConsolePanel project={selectedProject} onConnectionChange={setGscConnection} />
              <SearchConsoleAnalyticsPanel project={selectedProject} connection={gscConnection} />
            </section>
          )}

          {/* TAB 8: WHITE-LABEL REPORTS */}
          {activeTab === 'reports' && selectedProject && (
            <section style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <WhiteLabelReportsPanel
                project={selectedProject}
                hasReportsEntitlement={!!(subscriptionSummary?.plan?.features ?? []).includes('WHITE_LABEL_REPORTS')}
                onUpgrade={() => setIsSubscriptionModalOpen(true)}
              />
            </section>
          )}

          {/* TAB 9: FREE SEO TOOLS */}
          {activeTab === 'tools' && (
            <section id="seo-tools-section" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <SEOToolsPanel />
            </section>
          )}

          {/* TAB 10: AUTONOMOUS OPERATIONS */}
          {activeTab === 'operations' && selectedProject && (
            <section style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={subTabNavContainerStyle}>
                <button
                  onClick={() => setOperationsSubTab('all')}
                  style={getSubTabBtnStyle(operationsSubTab === 'all')}
                >
                  {t('subtab.all_operations', 'All Operations')}
                </button>
                <button
                  onClick={() => setOperationsSubTab('orchestrator')}
                  style={getSubTabBtnStyle(operationsSubTab === 'orchestrator')}
                >
                  {t('subtab.specialized_agents', 'Specialized Agents')}
                </button>
                <button
                  onClick={() => setOperationsSubTab('continuous')}
                  style={getSubTabBtnStyle(operationsSubTab === 'continuous')}
                >
                  {t('subtab.continuous_ops', 'Continuous Ops')}
                </button>
                <button
                  onClick={() => setOperationsSubTab('events')}
                  style={getSubTabBtnStyle(operationsSubTab === 'events')}
                >
                  {t('subtab.event_logs', 'Event Logs')}
                </button>
                <button
                  onClick={() => setOperationsSubTab('monitoring')}
                  style={getSubTabBtnStyle(operationsSubTab === 'monitoring')}
                >
                  {t('subtab.live_monitoring', 'Live Monitoring')}
                </button>
                <button
                  onClick={() => setOperationsSubTab('remediation')}
                  style={getSubTabBtnStyle(operationsSubTab === 'remediation')}
                >
                  {t('subtab.auto_remediation', 'Auto-Remediation')}
                </button>
                <button
                  onClick={() => setOperationsSubTab('observability')}
                  style={getSubTabBtnStyle(operationsSubTab === 'observability')}
                >
                  {t('subtab.observability', 'Observability & Sentry')}
                </button>
                <button
                  onClick={() => setOperationsSubTab('strategy')}
                  style={getSubTabBtnStyle(operationsSubTab === 'strategy')}
                >
                  {t('subtab.long_term_strategy', 'Long-Term Strategy')}
                </button>
              </div>

              {(operationsSubTab === 'all' || operationsSubTab === 'orchestrator') && (
                <AgentOrchestratorPanel
                  project={selectedProject}
                  onActionCreated={() => {
                    setActiveTab('recommendations');
                    setRecommendationsSubTab('actions');
                    setTimeout(() => {
                      const el = document.getElementById('seo-actions-section');
                      if (el) el.scrollIntoView({ behavior: 'smooth' });
                    }, 50);
                  }}
                />
              )}
              {(operationsSubTab === 'all' || operationsSubTab === 'continuous') && (
                <ContinuousOperationsPanel project={selectedProject} />
              )}
              {(operationsSubTab === 'all' || operationsSubTab === 'events') && (
                <EventActivityPanel project={selectedProject} />
              )}
              {(operationsSubTab === 'all' || operationsSubTab === 'monitoring') && (
                <MonitoringActivityPanel project={selectedProject} />
              )}
              {(operationsSubTab === 'all' || operationsSubTab === 'remediation') && (
                <RemediationActivityPanel project={selectedProject} />
              )}
              {(operationsSubTab === 'all' || operationsSubTab === 'observability') && (
                <ProductionOperationsPanel project={selectedProject} />
              )}
              {(operationsSubTab === 'all' || operationsSubTab === 'strategy') && (
                <LongTermStrategyPanel project={selectedProject} />
              )}
            </section>
          )}

          {/* TAB 11: PROJECTS MANAGER */}
          {activeTab === 'projects' && (
            <section style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div style={dashboardSectionCardStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <div>
                    <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 800, color: '#24143C' }}>
                      All Website Projects ({projects.length})
                    </h3>
                    <p style={{ margin: '2px 0 0', fontSize: '13px', color: '#64748b' }}>
                      Manage monitored web properties across Google Ethiopia.
                    </p>
                  </div>
                  <button
                    id="add-project-button"
                    onClick={handleOpenCreateProjectModal}
                    style={headerPrimaryBtnStyle}
                  >
                    + Add New Project
                  </button>
                </div>

                {isLoadingProjects ? (
                  <div style={loadingBoxStyle}>Loading projects...</div>
                ) : projects.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '32px 0' }}>
                    <p style={{ color: '#64748b', fontSize: '14px', marginBottom: '12px' }}>No projects created yet.</p>
                    <button
                      id="empty-add-project-button"
                      onClick={handleOpenCreateProjectModal}
                      style={headerPrimaryBtnStyle}
                    >
                      Create First Project
                    </button>
                  </div>
                ) : (
                  <div style={projectsGridStyle}>
                    {projects.map((p) => {
                      const isSelected = selectedProject?.id === p.id;
                      return (
                        <div
                          key={p.id}
                          style={{
                            ...projectCardStyle,
                            borderColor: isSelected ? '#774DA9' : '#e2e8f0',
                            backgroundColor: isSelected ? '#faf7fd' : '#ffffff',
                          }}
                        >
                          <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                              <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#24143C' }}>
                                {p.name}
                              </h4>
                              {isSelected && <span style={activeTagStyle}>Active</span>}
                            </div>
                            <a
                              href={p.website_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{ color: '#774DA9', fontSize: '13px', wordBreak: 'break-all', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                            >
                              <ExternalLink size={12} />
                              <span>{p.website_url}</span>
                            </a>
                            <p style={{ fontSize: '12px', color: '#64748b', marginTop: '6px' }}>
                              Created {new Date(p.created_at).toLocaleDateString()}
                            </p>
                          </div>

                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px', paddingTop: '12px', borderTop: '1px solid #f1f5f9' }}>
                            {!isSelected ? (
                              <button
                                onClick={() => handleSelectProject(p)}
                                style={actionSmallBtnStyle}
                              >
                                Set Active
                              </button>
                            ) : (
                              <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 700 }}>● Currently Viewing</span>
                            )}
                            <div style={{ display: 'flex', gap: '4px' }}>
                              <button
                                id={`edit-project-${p.id}`}
                                onClick={() => handleOpenEditProjectModal(p)}
                                style={actionInlineBtnStyle}
                              >
                                Edit
                              </button>
                              <button
                                id={`delete-project-${p.id}`}
                                onClick={() => setDeletingProject(p)}
                                style={{ ...actionInlineBtnStyle, color: '#ef4444' }}
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
              </div>
            </section>
          )}
        </main>
      </div>

      {/* ------------------------------------------------------------- */}
      {/* MODALS & OVERLAYS                                             */}
      {/* ------------------------------------------------------------- */}
      <ProjectFormModal
        isOpen={isProjectModalOpen}
        onClose={() => setIsProjectModalOpen(false)}
        onSave={handleSaveProject}
        projectToEdit={editingProject}
      />

      {selectedProject && (
        <KeywordFormModal
          isOpen={isKeywordModalOpen}
          onClose={() => setIsKeywordModalOpen(false)}
          onSave={handleSaveKeyword}
          projectId={selectedProject.id}
          projectName={selectedProject.name}
          keywordToEdit={editingKeyword}
        />
      )}

      {selectedProject && selectedKeyword && (
        <RankingFormModal
          isOpen={isRankingModalOpen}
          onClose={() => setIsRankingModalOpen(false)}
          onSave={handleSaveRanking}
          keyword={selectedKeyword}
          projectName={selectedProject.name}
          rankingToEdit={editingRanking}
        />
      )}

      {isSubscriptionModalOpen && (
        <SubscriptionModal
          isOpen={isSubscriptionModalOpen}
          onClose={() => setIsSubscriptionModalOpen(false)}
          subscriptionSummary={subscriptionSummary}
          onSubscriptionUpdated={() => fetchSubscription()}
        />
      )}

      {/* Confirm Delete Project Modal */}
      {deletingProject && (
        <div style={modalOverlayStyle}>
          <div style={deleteModalBoxStyle}>
            <h3 style={{ margin: '0 0 10px', fontSize: '18px', fontWeight: 800, color: '#24143C' }}>
              Delete Project "{deletingProject.name}"?
            </h3>
            <p style={{ margin: '0 0 20px', color: '#64748b', fontSize: '13px' }}>
              This will permanently delete this website project along with all associated tracked keywords, ranking histories, and site crawl data.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setDeletingProject(null)}
                disabled={isDeletingProject}
                style={cancelBtnStyle}
              >
                Cancel
              </button>
              <button
                id="confirm-delete-project-button"
                type="button"
                onClick={handleConfirmDeleteProject}
                disabled={isDeletingProject}
                style={dangerBtnStyle}
              >
                {isDeletingProject ? 'Deleting...' : 'Delete Project'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm Delete Keyword Modal */}
      {deletingKeyword && (
        <div style={modalOverlayStyle}>
          <div style={deleteModalBoxStyle}>
            <h3 style={{ margin: '0 0 10px', fontSize: '18px', fontWeight: 800, color: '#24143C' }}>
              Delete Keyword "{deletingKeyword.keyword}"?
            </h3>
            <p style={{ margin: '0 0 20px', color: '#64748b', fontSize: '13px' }}>
              This will remove this query from automated daily tracking on Google Ethiopia and delete all historical ranking records.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setDeletingKeyword(null)}
                disabled={isDeletingKeyword}
                style={cancelBtnStyle}
              >
                Cancel
              </button>
              <button
                id="confirm-delete-keyword-button"
                type="button"
                onClick={handleConfirmDeleteKeyword}
                disabled={isDeletingKeyword}
                style={dangerBtnStyle}
              >
                {isDeletingKeyword ? 'Deleting...' : 'Delete Keyword'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm Delete Ranking Modal */}
      {deletingRanking && (
        <div style={modalOverlayStyle}>
          <div style={deleteModalBoxStyle}>
            <h3 style={{ margin: '0 0 10px', fontSize: '18px', fontWeight: 800, color: '#24143C' }}>
              Delete Ranking Observation?
            </h3>
            <p style={{ margin: '0 0 20px', color: '#64748b', fontSize: '13px' }}>
              Are you sure you want to remove this recorded position from the ranking timeline?
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setDeletingRanking(null)}
                disabled={isDeletingRanking}
                style={cancelBtnStyle}
              >
                Cancel
              </button>
              <button
                id="confirm-delete-ranking-button"
                type="button"
                onClick={handleConfirmDeleteRanking}
                disabled={isDeletingRanking}
                style={dangerBtnStyle}
              >
                {isDeletingRanking ? 'Deleting...' : 'Delete Observation'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// -------------------------------------------------------------
// STYLES OBJECTS FOR MODERN SAAS DASHBOARD
// -------------------------------------------------------------

const shellContainerStyle: React.CSSProperties = {
  display: 'flex',
  minHeight: '100vh',
  width: '100%',
  backgroundColor: '#f8fafc',
  fontFamily: "'Plus Jakarta Sans', system-ui, -apple-system, sans-serif",
  boxSizing: 'border-box',
};

const sidebarStyle: React.CSSProperties = {
  width: '260px',
  backgroundColor: '#24143C',
  color: '#ffffff',
  display: 'flex',
  flexDirection: 'column',
  flexShrink: 0,
  borderRight: '1px solid #3b1d5f',
  position: 'sticky',
  top: 0,
  height: '100vh',
  overflowY: 'auto',
  zIndex: 100,
  transition: 'transform 0.25s ease-in-out',
};

const sidebarHeaderStyle: React.CSSProperties = {
  padding: '18px 16px',
  borderBottom: '1px solid #3b1d5f',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
};

const etBadgeStyle: React.CSSProperties = {
  fontSize: '10px',
  fontWeight: 800,
  backgroundColor: '#ecfdf5',
  color: '#065f46',
  padding: '2px 6px',
  borderRadius: '9999px',
};

const projectSelectorContainerStyle: React.CSSProperties = {
  padding: '14px 16px',
  borderBottom: '1px solid #3b1d5f',
  backgroundColor: '#1b0d2f',
};

const quickAddProjectBtnStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: '#a372df',
  fontSize: '11px',
  fontWeight: 700,
  cursor: 'pointer',
  padding: 0,
};

const projectSelectStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  backgroundColor: '#2f194d',
  color: '#ffffff',
  border: '1px solid #4d267f',
  borderRadius: '8px',
  fontSize: '12px',
  fontWeight: 600,
  outline: 'none',
  cursor: 'pointer',
};

const noProjectsBoxStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  backgroundColor: 'rgba(119, 77, 169, 0.2)',
  color: '#a372df',
  border: '1px dashed #774DA9',
  borderRadius: '8px',
  fontSize: '12px',
  fontWeight: 600,
  cursor: 'pointer',
  textAlign: 'center',
};

const sidebarNavStyle: React.CSSProperties = {
  flex: 1,
  padding: '12px 8px',
  display: 'flex',
  flexDirection: 'column',
  gap: '3px',
};

const navButtonStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '10px',
  width: '100%',
  padding: '9px 12px',
  border: 'none',
  borderRadius: '6px',
  cursor: 'pointer',
  transition: 'background-color 0.15s',
  outline: 'none',
};

const navBadgeStyle: React.CSSProperties = {
  fontSize: '10px',
  fontWeight: 700,
  padding: '2px 6px',
  borderRadius: '9999px',
};

const sidebarFooterStyle: React.CSSProperties = {
  padding: '14px 16px',
  borderTop: '1px solid #3b1d5f',
  backgroundColor: '#1b0d2f',
};

const sidebarPlanBoxStyle: React.CSSProperties = {
  backgroundColor: 'rgba(255, 255, 255, 0.05)',
  border: '1px solid #3b1d5f',
  borderRadius: '8px',
  padding: '10px 12px',
  marginBottom: '10px',
  cursor: 'pointer',
};

const userAvatarStyle: React.CSSProperties = {
  width: '32px',
  height: '32px',
  borderRadius: '8px',
  backgroundColor: '#774DA9',
  color: '#ffffff',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontSize: '13px',
  fontWeight: 800,
  flexShrink: 0,
};

const sidebarLogoutBtnStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  fontSize: '16px',
  cursor: 'pointer',
  padding: '6px',
  borderRadius: '6px',
  color: '#cbd5e1',
};

const mainAreaStyle: React.CSSProperties = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  minWidth: 0,
};

const topHeaderStyle: React.CSSProperties = {
  height: '60px',
  backgroundColor: '#ffffff',
  borderBottom: '1px solid #e2e8f0',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '0 24px',
  position: 'sticky',
  top: 0,
  zIndex: 90,
  boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.03)',
};

const websiteLinkBadgeStyle: React.CSSProperties = {
  fontSize: '12px',
  color: '#774DA9',
  backgroundColor: '#f3eef9',
  border: '1px solid #dac8ee',
  padding: '2px 8px',
  borderRadius: '6px',
  textDecoration: 'none',
  fontWeight: 600,
};

const headerPrimaryBtnStyle: React.CSSProperties = {
  backgroundColor: '#774DA9',
  color: '#ffffff',
  border: 'none',
  borderRadius: '8px',
  padding: '7px 14px',
  fontSize: '12px',
  fontWeight: 700,
  cursor: 'pointer',
  transition: 'background-color 0.15s',
};

const headerActionBtnStyle: React.CSSProperties = {
  color: '#ffffff',
  border: 'none',
  borderRadius: '8px',
  padding: '7px 12px',
  fontSize: '12px',
  fontWeight: 700,
};

const headerToolBtnStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  color: '#24143C',
  border: '1px solid #cbd5e1',
  borderRadius: '8px',
  padding: '6px 12px',
  fontSize: '12px',
  fontWeight: 600,
  cursor: 'pointer',
};

const headerBillingBtnStyle: React.CSSProperties = {
  backgroundColor: '#24143C',
  color: '#ffffff',
  border: 'none',
  borderRadius: '8px',
  padding: '7px 12px',
  fontSize: '12px',
  fontWeight: 700,
  cursor: 'pointer',
};

const mobileToggleBtnStyle: React.CSSProperties = {
  display: 'none',
  background: 'none',
  border: 'none',
  fontSize: '20px',
  cursor: 'pointer',
  color: '#24143C',
};

const mobileCloseBtnStyle: React.CSSProperties = {
  display: 'none',
  background: 'none',
  border: 'none',
  color: '#ffffff',
  fontSize: '16px',
  cursor: 'pointer',
};

const mobileBackdropStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  backgroundColor: 'rgba(36, 20, 60, 0.65)',
  backdropFilter: 'blur(2px)',
  zIndex: 95,
};

const mainContentAreaStyle: React.CSSProperties = {
  padding: '24px',
  flex: 1,
  boxSizing: 'border-box',
};

const overviewHeroCardStyle: React.CSSProperties = {
  background: 'linear-gradient(135deg, #24143C 0%, #3b1d5f 60%, #774DA9 100%)',
  borderRadius: '14px',
  padding: '24px',
  boxShadow: '0 4px 14px rgba(36, 20, 60, 0.15)',
};

const doxaPillBadgeStyle: React.CSSProperties = {
  fontSize: '10px',
  fontWeight: 800,
  backgroundColor: 'rgba(255, 255, 255, 0.15)',
  color: '#ffffff',
  padding: '2px 8px',
  borderRadius: '9999px',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};

const overviewSecondaryBtnStyle: React.CSSProperties = {
  backgroundColor: 'rgba(255, 255, 255, 0.12)',
  color: '#ffffff',
  border: '1px solid rgba(255, 255, 255, 0.25)',
  borderRadius: '8px',
  padding: '6px 12px',
  fontSize: '12px',
  fontWeight: 600,
  cursor: 'pointer',
};

const kpiGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
  gap: '14px',
};

const kpiCardStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  border: '1px solid #e2e8f0',
  borderRadius: '12px',
  padding: '16px',
  boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
};

const kpiLabelStyle: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 700,
  textTransform: 'uppercase',
  color: '#64748b',
  letterSpacing: '0.04em',
};

const kpiSubtextStyle: React.CSSProperties = {
  fontSize: '11px',
  color: '#64748b',
  display: 'block',
  marginTop: '4px',
};

const subTabNavContainerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '6px',
  background: '#ffffff',
  padding: '6px 8px',
  borderRadius: '10px',
  border: '1px solid #e2e8f0',
  marginBottom: '8px',
  overflowX: 'auto',
};

const getSubTabBtnStyle = (isActive: boolean): React.CSSProperties => ({
  padding: '6px 14px',
  borderRadius: '8px',
  fontSize: '13px',
  fontWeight: isActive ? 700 : 500,
  background: isActive ? '#774DA9' : 'transparent',
  color: isActive ? '#ffffff' : '#475569',
  border: 'none',
  cursor: 'pointer',
  transition: 'all 0.15s ease',
  whiteSpace: 'nowrap',
});

const dashboardSectionCardStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  border: '1px solid #e2e8f0',
  borderRadius: '12px',
  padding: '20px',
  boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
};

const telemetryItemStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '10px 12px',
  backgroundColor: '#f8fafc',
  borderRadius: '8px',
  border: '1px solid #e2e8f0',
};

const telemetryConnectedStyle: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 700,
  color: '#065f46',
  backgroundColor: '#ecfdf5',
  border: '1px solid #a7f3d0',
  padding: '2px 8px',
  borderRadius: '9999px',
};

const telemetryPendingStyle: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 600,
  color: '#64748b',
  backgroundColor: '#f1f5f9',
  border: '1px solid #e2e8f0',
  padding: '2px 8px',
  borderRadius: '9999px',
};

const welcomePromptStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  border: '1px solid #e2e8f0',
  borderRadius: '16px',
  padding: '48px 24px',
  textAlign: 'center',
  boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
};

const filterInputStyle: React.CSSProperties = {
  padding: '6px 12px',
  borderRadius: '8px',
  border: '1px solid #cbd5e1',
  fontSize: '13px',
  outline: 'none',
  width: '160px',
};

const actionSmallBtnStyle: React.CSSProperties = {
  padding: '6px 12px',
  borderRadius: '8px',
  border: 'none',
  fontSize: '12px',
  fontWeight: 600,
  cursor: 'pointer',
};

const actionInlineBtnStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: '#774DA9',
  fontSize: '12px',
  fontWeight: 700,
  cursor: 'pointer',
  padding: '2px 6px',
};

const thStyle: React.CSSProperties = {
  padding: '10px 12px',
  fontSize: '11px',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};

const tdStyle: React.CSSProperties = {
  padding: '10px 12px',
};

const countryBadgeStyle: React.CSSProperties = {
  fontSize: '10px',
  fontWeight: 800,
  backgroundColor: '#ecfdf5',
  color: '#065f46',
  padding: '2px 6px',
  borderRadius: '4px',
};

const activeStatusStyle: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 700,
  color: '#065f46',
  backgroundColor: '#ecfdf5',
  padding: '2px 6px',
  borderRadius: '9999px',
};

const inactiveStatusStyle: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 600,
  color: '#64748b',
  backgroundColor: '#f1f5f9',
  padding: '2px 6px',
  borderRadius: '9999px',
};

const subMetricCardStyle: React.CSSProperties = {
  backgroundColor: '#f8fafc',
  border: '1px solid #e2e8f0',
  borderRadius: '8px',
  padding: '12px',
  display: 'flex',
  flexDirection: 'column',
  gap: '2px',
};

const subMetricLabelStyle: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 700,
  textTransform: 'uppercase',
  color: '#64748b',
};

const subMetricValStyle: React.CSSProperties = {
  fontSize: '18px',
  fontWeight: 800,
  color: '#24143C',
};

const refreshMiniBtnStyle: React.CSSProperties = {
  marginTop: '4px',
  background: 'none',
  border: 'none',
  color: '#774DA9',
  fontSize: '11px',
  fontWeight: 700,
  cursor: 'pointer',
  padding: 0,
  textAlign: 'left',
};

const loadingBoxStyle: React.CSSProperties = {
  textAlign: 'center',
  padding: '24px 0',
  color: '#64748b',
  fontSize: '13px',
};

const noticeSuccessStyle: React.CSSProperties = {
  marginBottom: '14px',
  padding: '10px 14px',
  borderRadius: '8px',
  backgroundColor: '#ecfdf5',
  border: '1px solid #a7f3d0',
  color: '#065f46',
  fontSize: '13px',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
};

const noticeInfoStyle: React.CSSProperties = {
  marginBottom: '14px',
  padding: '10px 14px',
  borderRadius: '8px',
  backgroundColor: '#f3eef9',
  border: '1px solid #dac8ee',
  color: '#24143C',
  fontSize: '13px',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
};

const noticeRunningStyle: React.CSSProperties = {
  marginBottom: '14px',
  padding: '10px 14px',
  borderRadius: '8px',
  backgroundColor: '#f6f2fb',
  border: '1px solid #dac8ee',
  color: '#593285',
  fontSize: '13px',
};

const alertDangerStyle: React.CSSProperties = {
  marginBottom: '14px',
  padding: '10px 14px',
  borderRadius: '8px',
  backgroundColor: '#fef2f2',
  border: '1px solid #fecaca',
  color: '#991b1b',
  fontSize: '13px',
};

const closeNoticeBtnStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  fontWeight: 800,
  color: 'inherit',
};

const projectsGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
  gap: '16px',
};

const projectCardStyle: React.CSSProperties = {
  borderRadius: '12px',
  padding: '16px',
  border: '1px solid #e2e8f0',
  display: 'flex',
  flexDirection: 'column',
  justifyContent: 'space-between',
  boxShadow: '0 1px 2px rgba(0, 0, 0, 0.04)',
};

const activeTagStyle: React.CSSProperties = {
  fontSize: '10px',
  fontWeight: 800,
  backgroundColor: '#f3eef9',
  color: '#774DA9',
  border: '1px solid #dac8ee',
  padding: '2px 6px',
  borderRadius: '9999px',
  textTransform: 'uppercase',
};

const modalOverlayStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  backgroundColor: 'rgba(36, 20, 60, 0.65)',
  backdropFilter: 'blur(3px)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1050,
  padding: '16px',
};

const deleteModalBoxStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '14px',
  padding: '24px',
  width: '100%',
  maxWidth: '440px',
  boxShadow: '0 20px 25px -5px rgba(36, 20, 60, 0.15)',
};

const cancelBtnStyle: React.CSSProperties = {
  padding: '8px 14px',
  backgroundColor: '#f1f5f9',
  color: '#334155',
  border: '1px solid #cbd5e1',
  borderRadius: '8px',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
};

const dangerBtnStyle: React.CSSProperties = {
  padding: '8px 14px',
  backgroundColor: '#ef4444',
  color: '#ffffff',
  border: 'none',
  borderRadius: '8px',
  fontSize: '13px',
  fontWeight: 700,
  cursor: 'pointer',
};

export default Dashboard;
