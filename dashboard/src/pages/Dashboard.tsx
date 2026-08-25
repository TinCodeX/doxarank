import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { getProjects, createProject, updateProject, deleteProject } from '../api/projects';
import { getKeywords, createKeyword, updateKeyword, deleteKeyword } from '../api/keywords';
import { getRankings, createRanking, updateRanking, deleteRanking } from '../api/rankings';
import type { Project, CreateProjectPayload } from '../types/project';
import type { Keyword, CreateKeywordPayload, UpdateKeywordPayload } from '../types/keyword';
import type { Ranking, CreateRankingPayload, UpdateRankingPayload } from '../types/ranking';
import { ProjectFormModal } from '../components/ProjectFormModal';
import { KeywordFormModal } from '../components/KeywordFormModal';
import { RankingFormModal } from '../components/RankingFormModal';
import { SiteAuditPanel } from '../components/SiteAuditPanel';
import { SearchConsolePanel } from '../components/SearchConsolePanel';
import { SearchAnalyticsPanel } from '../components/SearchAnalyticsPanel';

export const Dashboard: React.FC = () => {

  const { user, logout } = useAuth();

  // Project state
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
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

  useEffect(() => {
    fetchUserProjects();
  }, []);

  // Fetch keywords whenever active project changes
  const fetchProjectKeywords = async (projectId: number) => {
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
    } catch (err: any) {
      setKeywordError(err?.data?.detail || 'Failed to load keywords for this project.');
    } finally {
      setIsLoadingKeywords(false);
    }
  };

  useEffect(() => {
    if (selectedProject) {
      fetchProjectKeywords(selectedProject.id);
    } else {
      setKeywords([]);
      setSelectedKeyword(null);
      setRankings([]);
    }
  }, [selectedProject?.id]);

  // Fetch rankings whenever selected keyword changes
  const fetchKeywordRankings = async (keywordId: number) => {
    setIsLoadingRankings(true);
    setRankingError(null);
    setRankings([]); // Clear old ranking data immediately when switching keywords
    try {
      const data = await getRankings(keywordId);
      setRankings(data);
    } catch (err: any) {
      setRankingError(err?.data?.detail || 'Failed to load ranking history for this keyword.');
    } finally {
      setIsLoadingRankings(false);
    }
  };

  useEffect(() => {
    if (selectedKeyword) {
      fetchKeywordRankings(selectedKeyword.id);
    } else {
      setRankings([]);
    }
  }, [selectedKeyword?.id]);

  // Project Handlers
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
        setSelectedProject(remaining.length > 0 ? remaining[0] : null);
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

  const handleOpenEditKeywordModal = (keyword: Keyword) => {
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

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f9fafb', fontFamily: 'system-ui, sans-serif', width: '100%', boxSizing: 'border-box' }}>
      {/* Navigation Header */}
      <header style={headerStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={logoIconStyle}>D</div>
            <div>
              <h1 style={{ fontSize: '18px', margin: 0, fontWeight: 700, color: '#111827' }}>DoxaRank</h1>
              <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 600 }}>● Ethiopia-First SEO</span>
            </div>
          </div>

          {selectedProject && (
            <div style={activeProjectBadgeStyle}>
              <span style={{ color: '#6b7280', fontSize: '12px', marginRight: '4px' }}>Active Project:</span>
              <span style={{ fontWeight: 700, color: '#1d4ed8' }}>{selectedProject.name}</span>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '14px', fontWeight: 600, color: '#111827' }}>
              {user?.full_name || 'DoxaRank User'}
            </div>
            <div style={{ fontSize: '12px', color: '#6b7280' }}>
              {user?.email}
            </div>
          </div>
          <button
            id="logout-button"
            onClick={logout}
            style={logoutButtonStyle}
          >
            Log out
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main style={{ maxWidth: '1120px', margin: '32px auto', padding: '0 20px', textAlign: 'left' }}>
        
        {/* Selected Project Overview Card */}
        {selectedProject ? (
          <div style={selectedProjectCardStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
              <div>
                <span style={{ fontSize: '12px', textTransform: 'uppercase', fontWeight: 700, color: '#2563eb', letterSpacing: '0.05em' }}>
                  Current Project Context
                </span>
                <h2 style={{ margin: '4px 0', fontSize: '26px', fontWeight: 700, color: '#111827' }}>
                  {selectedProject.name}
                </h2>
                <a
                  href={selectedProject.website_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: '#4b5563', fontSize: '14px', textDecoration: 'none' }}
                >
                  🔗 {selectedProject.website_url}
                </a>
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  id="header-track-keyword-button"
                  onClick={handleOpenCreateKeywordModal}
                  style={primaryAddBtnStyle}
                >
                  + Track Keyword
                </button>
                <button
                  onClick={() => handleOpenEditProjectModal(selectedProject)}
                  style={secondaryActionBtnStyle}
                >
                  Edit Project
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div style={welcomePromptStyle}>
            <h2 style={{ margin: '0 0 8px 0', fontSize: '22px', color: '#111827' }}>
              Welcome to DoxaRank, {user?.first_name || user?.email}! 👋
            </h2>
            <p style={{ margin: 0, color: '#4b5563', fontSize: '14px' }}>
              Get started by creating your first project to track keyword rankings and SEO health.
            </p>
          </div>
        )}

        {/* SECTION 1: KEYWORDS MANAGEMENT (Visible when a project is selected) */}
        {selectedProject && (
          <section style={{ marginTop: '36px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: '#111827' }}>
                  Tracked Keywords {keywords.length > 0 && `(${keywords.length})`}
                </h3>
                <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#6b7280' }}>
                  SEO queries monitored for <strong>{selectedProject.name}</strong> on Ethiopian Google search. Select a keyword to view ranking history.
                </p>
              </div>
              <button
                id="add-keyword-button"
                onClick={handleOpenCreateKeywordModal}
                style={primaryAddBtnStyle}
              >
                + Track Keyword
              </button>
            </div>

            {keywordError && (
              <div style={errorAlertStyle}>
                {keywordError}
              </div>
            )}

            {isLoadingKeywords ? (
              <div style={loadingStateStyle}>
                <p style={{ color: '#6b7280', fontSize: '14px' }}>Loading keywords for {selectedProject.name}...</p>
              </div>
            ) : keywords.length === 0 ? (
              <div style={emptyStateCardStyle}>
                <div style={{ fontSize: '36px', marginBottom: '10px' }}>🔍</div>
                <h4 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 600, color: '#111827' }}>
                  No keywords tracked yet
                </h4>
                <p style={{ margin: '0 0 16px 0', fontSize: '14px', color: '#6b7280', maxWidth: '420px' }}>
                  Add search terms (e.g. "seo agency addis ababa") to monitor your ranking positions on Google Ethiopia.
                </p>
                <button
                  id="empty-add-keyword-button"
                  onClick={handleOpenCreateKeywordModal}
                  style={primaryAddBtnStyle}
                >
                  Track your first keyword
                </button>
              </div>
            ) : (
              <div style={tableContainerStyle}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '14px' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>
                      <th style={thStyle}>Keyword / Query</th>
                      <th style={thStyle}>Search Engine</th>
                      <th style={thStyle}>Location & Lang</th>
                      <th style={thStyle}>Device</th>
                      <th style={thStyle}>Status</th>
                      <th style={{ ...thStyle, textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {keywords.map((kw) => {
                      const isSelected = selectedKeyword?.id === kw.id;
                      return (
                        <tr
                          key={kw.id}
                          id={`keyword-row-${kw.id}`}
                          onClick={() => setSelectedKeyword(kw)}
                          style={{
                            borderBottom: '1px solid #f1f5f9',
                            backgroundColor: isSelected ? '#eff6ff' : 'transparent',
                            cursor: 'pointer',
                            transition: 'background-color 0.15s ease',
                          }}
                        >
                          <td style={tdStyle}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              {isSelected && (
                                <span style={{ color: '#2563eb', fontWeight: 700, fontSize: '14px' }}>▶</span>
                              )}
                              <span style={{ fontWeight: 600, color: isSelected ? '#1d4ed8' : '#0f172a', fontSize: '15px' }}>
                                {kw.keyword}
                              </span>
                            </div>
                          </td>
                          <td style={tdStyle}>
                            <span style={engineBadgeStyle}>
                              Google
                            </span>
                          </td>
                          <td style={tdStyle}>
                            <span style={countryBadgeStyle}>
                              🇪🇹 {kw.country} · {kw.language.toUpperCase()}
                            </span>
                          </td>
                          <td style={tdStyle}>
                            <span style={deviceBadgeStyle}>
                              {kw.device === 'desktop' ? '💻 Desktop' : '📱 Mobile'}
                            </span>
                          </td>
                          <td style={tdStyle}>
                            {kw.is_active ? (
                              <span style={activeStatusStyle}>● Active</span>
                            ) : (
                              <span style={inactiveStatusStyle}>○ Paused</span>
                            )}
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'right' }}>
                            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '6px', alignItems: 'center' }}>
                              <button
                                id={`select-kw-${kw.id}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setSelectedKeyword(kw);
                                }}
                                style={{
                                  ...actionInlineBtnStyle,
                                  color: isSelected ? '#1d4ed8' : '#6b7280',
                                  fontWeight: isSelected ? 700 : 500,
                                }}
                              >
                                {isSelected ? 'Viewing Rankings' : 'Select'}
                              </button>
                              <button
                                id={`edit-kw-${kw.id}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleOpenEditKeywordModal(kw);
                                }}
                                style={actionInlineBtnStyle}
                              >
                                Edit
                              </button>
                              <button
                                id={`delete-kw-${kw.id}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setDeletingKeyword(kw);
                                }}
                                style={{ ...actionInlineBtnStyle, color: '#ef4444' }}
                              >
                                Delete
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {/* SECTION 2: RANKING HISTORY (Visible when a keyword is selected) */}
        {selectedProject && selectedKeyword && (
          <section style={{ marginTop: '40px', backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', padding: '24px', boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.05)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px', marginBottom: '20px', borderBottom: '1px solid #f1f5f9', paddingBottom: '16px' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 700, color: '#2563eb', backgroundColor: '#eff6ff', padding: '2px 8px', borderRadius: '4px' }}>
                    Rank Tracking
                  </span>
                  <span style={{ fontSize: '13px', color: '#6b7280' }}>
                    Project: <strong>{selectedProject.name}</strong>
                  </span>
                </div>
                <h3 style={{ margin: '6px 0 2px 0', fontSize: '22px', fontWeight: 700, color: '#0f172a' }}>
                  Ranking History for "{selectedKeyword.keyword}"
                </h3>
                <p style={{ margin: 0, fontSize: '13px', color: '#64748b' }}>
                  Target: Google ({selectedKeyword.country}) · {selectedKeyword.language.toUpperCase()} · {selectedKeyword.device}
                </p>
              </div>
              <button
                id="record-ranking-button"
                onClick={handleOpenCreateRankingModal}
                style={primaryAddBtnStyle}
              >
                + Record Ranking
              </button>
            </div>

            {rankingError && (
              <div style={errorAlertStyle}>
                {rankingError}
              </div>
            )}

            {isLoadingRankings ? (
              <div style={loadingStateStyle}>
                <p style={{ color: '#6b7280', fontSize: '14px' }}>Loading ranking history for "{selectedKeyword.keyword}"...</p>
              </div>
            ) : rankings.length === 0 ? (
              <div style={{ ...emptyStateCardStyle, border: '1px dashed #cbd5e1', backgroundColor: '#f8fafc' }}>
                <div style={{ fontSize: '32px', marginBottom: '8px' }}>📊</div>
                <h4 style={{ margin: '0 0 6px 0', fontSize: '16px', fontWeight: 600, color: '#111827' }}>
                  No ranking observations recorded yet
                </h4>
                <p style={{ margin: '0 0 16px 0', fontSize: '13px', color: '#6b7280', maxWidth: '420px' }}>
                  Record your website's position in search results for <strong>"{selectedKeyword.keyword}"</strong> to track historical progress.
                </p>
                <button
                  id="empty-record-ranking-button"
                  onClick={handleOpenCreateRankingModal}
                  style={primaryAddBtnStyle}
                >
                  Record First Ranking
                </button>
              </div>
            ) : (
              <div style={tableContainerStyle}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '14px' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>
                      <th style={thStyle}>Position</th>
                      <th style={thStyle}>Ranking URL</th>
                      <th style={thStyle}>Engine</th>
                      <th style={thStyle}>Location & Lang</th>
                      <th style={thStyle}>Device</th>
                      <th style={thStyle}>Recorded Date</th>
                      <th style={{ ...thStyle, textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rankings.map((ranking) => {
                      const isTop3 = ranking.position <= 3;
                      const isTop10 = ranking.position <= 10;
                      return (
                        <tr key={ranking.id} id={`ranking-row-${ranking.id}`} style={{ borderBottom: '1px solid #f1f5f9' }}>
                          <td style={tdStyle}>
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                padding: '4px 10px',
                                borderRadius: '8px',
                                fontWeight: 800,
                                fontSize: '14px',
                                backgroundColor: isTop3 ? '#fef3c7' : isTop10 ? '#dbeafe' : '#f1f5f9',
                                color: isTop3 ? '#92400e' : isTop10 ? '#1e40af' : '#475569',
                                border: isTop3 ? '1px solid #fcd34d' : isTop10 ? '1px solid #bfdbfe' : '1px solid #e2e8f0',
                              }}
                            >
                              #{ranking.position}
                            </span>
                          </td>
                          <td style={tdStyle}>
                            {ranking.ranking_url ? (
                              <a
                                href={ranking.ranking_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{
                                  color: '#2563eb',
                                  textDecoration: 'none',
                                  fontSize: '13px',
                                  display: 'inline-block',
                                  maxWidth: '280px',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                }}
                                title={ranking.ranking_url}
                              >
                                🔗 {ranking.ranking_url}
                              </a>
                            ) : (
                              <span style={{ color: '#9ca3af', fontSize: '13px' }}>—</span>
                            )}
                          </td>
                          <td style={tdStyle}>
                            <span style={engineBadgeStyle}>
                              Google
                            </span>
                          </td>
                          <td style={tdStyle}>
                            <span style={countryBadgeStyle}>
                              🇪🇹 {ranking.country} · {ranking.language.toUpperCase()}
                            </span>
                          </td>
                          <td style={tdStyle}>
                            <span style={deviceBadgeStyle}>
                              {ranking.device === 'desktop' ? '💻 Desktop' : '📱 Mobile'}
                            </span>
                          </td>
                          <td style={tdStyle}>
                            <span style={{ fontSize: '13px', color: '#334155', fontWeight: 500 }}>
                              {new Date(ranking.recorded_at).toLocaleString(undefined, {
                                year: 'numeric',
                                month: 'short',
                                day: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </span>
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'right' }}>
                            <button
                              id={`edit-ranking-${ranking.id}`}
                              onClick={() => handleOpenEditRankingModal(ranking)}
                              style={actionInlineBtnStyle}
                            >
                              Edit
                            </button>
                            <button
                              id={`delete-ranking-${ranking.id}`}
                              onClick={() => setDeletingRanking(ranking)}
                              style={{ ...actionInlineBtnStyle, color: '#ef4444' }}
                            >
                              Delete
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {/* SECTION 3: SITE AUDIT (Visible when a project is selected) */}
        {selectedProject && (
          <SiteAuditPanel project={selectedProject} />
        )}

        {/* SECTION 4: GOOGLE SEARCH CONSOLE (Visible when a project is selected) */}
        {selectedProject && (
          <SearchConsolePanel project={selectedProject} />
        )}

        {/* SECTION 5: SEARCH CONSOLE SEARCH ANALYTICS (Visible when a project is selected) */}
        {selectedProject && (
          <SearchAnalyticsPanel project={selectedProject} />
        )}

        {/* SECTION 6: PROJECTS MANAGEMENT */}
        <section style={{ marginTop: '48px', borderTop: '1px solid #e5e7eb', paddingTop: '32px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <div>
              <h3 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: '#111827' }}>
                All Projects {projects.length > 0 && `(${projects.length})`}
              </h3>

              <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#6b7280' }}>
                Select or manage your tracked websites.
              </p>
            </div>
            <button
              id="add-project-button"
              onClick={handleOpenCreateProjectModal}
              style={primaryAddBtnStyle}
            >
              + Add Project
            </button>
          </div>

          {projectError && (
            <div style={errorAlertStyle}>
              {projectError}
            </div>
          )}

          {isLoadingProjects ? (
            <div style={loadingStateStyle}>
              <p style={{ color: '#6b7280', fontSize: '14px' }}>Loading projects from Neon PostgreSQL...</p>
            </div>
          ) : projects.length === 0 ? (
            <div style={emptyStateCardStyle}>
              <div style={{ fontSize: '36px', marginBottom: '10px' }}>📁</div>
              <h4 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 600, color: '#111827' }}>
                No projects yet
              </h4>
              <p style={{ margin: '0 0 16px 0', fontSize: '14px', color: '#6b7280', maxWidth: '400px' }}>
                Create your first project to start tracking keywords and rankings.
              </p>
              <button
                id="empty-add-project-button"
                onClick={handleOpenCreateProjectModal}
                style={primaryAddBtnStyle}
              >
                Create your first project
              </button>
            </div>
          ) : (
            <div style={projectsGridStyle}>
              {projects.map((project) => {
                const isSelected = selectedProject?.id === project.id;
                return (
                  <div
                    key={project.id}
                    style={{
                      ...projectCardStyle,
                      borderColor: isSelected ? '#3b82f6' : '#e5e7eb',
                      backgroundColor: isSelected ? '#f8faff' : '#ffffff',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                      <div>
                        <h4 style={{ margin: '0 0 4px 0', fontSize: '17px', fontWeight: 700, color: '#111827' }}>
                          {project.name}
                        </h4>
                        <a
                          href={project.website_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ color: '#2563eb', fontSize: '13px', textDecoration: 'none', wordBreak: 'break-all' }}
                        >
                          {project.website_url}
                        </a>
                      </div>
                      {isSelected && (
                        <span style={activeTagStyle}>Active</span>
                      )}
                    </div>

                    <div style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '16px' }}>
                      Created on {new Date(project.created_at).toLocaleDateString()}
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid #f3f4f6', paddingTop: '12px' }}>
                      {!isSelected ? (
                        <button
                          id={`select-project-${project.id}`}
                          onClick={() => {
                            setSelectedProject(project);
                            localStorage.setItem('doxarank_active_project_id', String(project.id));
                          }}
                          style={selectBtnStyle}
                        >
                          Select
                        </button>
                      ) : (
                        <span style={{ fontSize: '13px', fontWeight: 600, color: '#2563eb' }}>● Selected</span>
                      )}

                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button
                          onClick={() => handleOpenEditProjectModal(project)}
                          style={cardActionBtnStyle}
                        >
                          Edit
                        </button>
                        <button
                          id={`delete-btn-${project.id}`}
                          onClick={() => setDeletingProject(project)}
                          style={{ ...cardActionBtnStyle, color: '#ef4444' }}
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
      </main>

      {/* Create / Edit Project Modal */}
      <ProjectFormModal
        isOpen={isProjectModalOpen}
        onClose={() => setIsProjectModalOpen(false)}
        onSave={handleSaveProject}
        projectToEdit={editingProject}
      />

      {/* Create / Edit Keyword Modal */}
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

      {/* Create / Edit Ranking Modal */}
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

      {/* Project Delete Modal */}
      {deletingProject && (
        <div style={modalOverlayStyle}>
          <div style={deleteModalBoxStyle}>
            <h3 style={{ margin: '0 0 12px 0', fontSize: '18px', fontWeight: 700, color: '#111827' }}>
              Delete Project
            </h3>
            <p style={{ margin: '0 0 20px 0', fontSize: '14px', color: '#4b5563', lineHeight: 1.5 }}>
              Are you sure you want to delete <strong>{deletingProject.name}</strong> ({deletingProject.website_url})? All tracked keywords and rankings under this project will also be removed.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <button
                type="button"
                onClick={() => setDeletingProject(null)}
                style={cancelDeleteBtnStyle}
              >
                Cancel
              </button>
              <button
                id="confirm-delete-project-button"
                type="button"
                onClick={handleConfirmDeleteProject}
                disabled={isDeletingProject}
                style={{
                  ...confirmDeleteBtnStyle,
                  opacity: isDeletingProject ? 0.7 : 1,
                  cursor: isDeletingProject ? 'not-allowed' : 'pointer',
                }}
              >
                {isDeletingProject ? 'Deleting...' : 'Confirm Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Keyword Delete Modal */}
      {deletingKeyword && (
        <div style={modalOverlayStyle}>
          <div style={deleteModalBoxStyle}>
            <h3 style={{ margin: '0 0 12px 0', fontSize: '18px', fontWeight: 700, color: '#111827' }}>
              Delete Keyword
            </h3>
            <p style={{ margin: '0 0 20px 0', fontSize: '14px', color: '#4b5563', lineHeight: 1.5 }}>
              Are you sure you want to stop tracking <strong>"{deletingKeyword.keyword}"</strong>? All ranking history for this keyword will also be deleted.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <button
                type="button"
                onClick={() => setDeletingKeyword(null)}
                style={cancelDeleteBtnStyle}
              >
                Cancel
              </button>
              <button
                id="confirm-delete-keyword-button"
                type="button"
                onClick={handleConfirmDeleteKeyword}
                disabled={isDeletingKeyword}
                style={{
                  ...confirmDeleteBtnStyle,
                  opacity: isDeletingKeyword ? 0.7 : 1,
                  cursor: isDeletingKeyword ? 'not-allowed' : 'pointer',
                }}
              >
                {isDeletingKeyword ? 'Deleting...' : 'Confirm Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Ranking Delete Modal */}
      {deletingRanking && (
        <div style={modalOverlayStyle}>
          <div style={deleteModalBoxStyle}>
            <h3 style={{ margin: '0 0 12px 0', fontSize: '18px', fontWeight: 700, color: '#111827' }}>
              Delete Ranking Observation
            </h3>
            <p style={{ margin: '0 0 20px 0', fontSize: '14px', color: '#4b5563', lineHeight: 1.5 }}>
              Are you sure you want to delete the ranking observation for position <strong>#{deletingRanking.position}</strong> recorded on <strong>{new Date(deletingRanking.recorded_at).toLocaleDateString()}</strong>?
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <button
                type="button"
                onClick={() => setDeletingRanking(null)}
                style={cancelDeleteBtnStyle}
              >
                Cancel
              </button>
              <button
                id="confirm-delete-ranking-button"
                type="button"
                onClick={handleConfirmDeleteRanking}
                disabled={isDeletingRanking}
                style={{
                  ...confirmDeleteBtnStyle,
                  opacity: isDeletingRanking ? 0.7 : 1,
                  cursor: isDeletingRanking ? 'not-allowed' : 'pointer',
                }}
              >
                {isDeletingRanking ? 'Deleting...' : 'Confirm Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// Styles
const headerStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderBottom: '1px solid #e5e7eb',
  padding: '14px 24px',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
};

const logoIconStyle: React.CSSProperties = {
  width: '34px',
  height: '34px',
  backgroundColor: '#2563eb',
  color: '#ffffff',
  borderRadius: '8px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontWeight: 700,
  fontSize: '18px',
};

const activeProjectBadgeStyle: React.CSSProperties = {
  backgroundColor: '#eff6ff',
  border: '1px solid #bfdbfe',
  borderRadius: '20px',
  padding: '4px 12px',
  fontSize: '13px',
};

const logoutButtonStyle: React.CSSProperties = {
  padding: '8px 14px',
  backgroundColor: '#f3f4f6',
  color: '#374151',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
};

const selectedProjectCardStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  padding: '24px',
  border: '1px solid #e5e7eb',
  boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.05)',
};

const welcomePromptStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  padding: '24px',
  border: '1px solid #e5e7eb',
};

const primaryAddBtnStyle: React.CSSProperties = {
  padding: '10px 18px',
  backgroundColor: '#2563eb',
  color: '#ffffff',
  border: 'none',
  borderRadius: '6px',
  fontSize: '14px',
  fontWeight: 600,
  cursor: 'pointer',
};

const secondaryActionBtnStyle: React.CSSProperties = {
  padding: '10px 16px',
  backgroundColor: '#ffffff',
  color: '#374151',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  fontSize: '14px',
  fontWeight: 600,
  cursor: 'pointer',
};

const errorAlertStyle: React.CSSProperties = {
  backgroundColor: '#fef2f2',
  color: '#b91c1c',
  padding: '12px',
  borderRadius: '8px',
  fontSize: '14px',
  marginBottom: '16px',
  border: '1px solid #fca5a5',
};

const loadingStateStyle: React.CSSProperties = {
  textAlign: 'center',
  padding: '36px 0',
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  border: '1px solid #e5e7eb',
};

const emptyStateCardStyle: React.CSSProperties = {
  textAlign: 'center',
  padding: '40px 24px',
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  border: '1px dashed #d1d5db',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
};

const tableContainerStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  border: '1px solid #e2e8f0',
  overflow: 'hidden',
  boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.05)',
};

const thStyle: React.CSSProperties = {
  padding: '14px 16px',
  fontSize: '12px',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
};

const tdStyle: React.CSSProperties = {
  padding: '14px 16px',
  verticalAlign: 'middle',
};

const engineBadgeStyle: React.CSSProperties = {
  display: 'inline-block',
  fontSize: '12px',
  fontWeight: 600,
  color: '#1e293b',
  backgroundColor: '#f1f5f9',
  padding: '3px 8px',
  borderRadius: '6px',
};

const countryBadgeStyle: React.CSSProperties = {
  display: 'inline-block',
  fontSize: '12px',
  fontWeight: 600,
  color: '#0369a1',
  backgroundColor: '#e0f2fe',
  padding: '3px 8px',
  borderRadius: '6px',
};

const deviceBadgeStyle: React.CSSProperties = {
  display: 'inline-block',
  fontSize: '12px',
  fontWeight: 500,
  color: '#475569',
};

const activeStatusStyle: React.CSSProperties = {
  fontSize: '12px',
  fontWeight: 700,
  color: '#16a34a',
  backgroundColor: '#dcfce7',
  padding: '3px 8px',
  borderRadius: '12px',
};

const inactiveStatusStyle: React.CSSProperties = {
  fontSize: '12px',
  fontWeight: 600,
  color: '#64748b',
  backgroundColor: '#f1f5f9',
  padding: '3px 8px',
  borderRadius: '12px',
};

const actionInlineBtnStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: '#2563eb',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
  padding: '4px 8px',
};

const projectsGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
  gap: '20px',
};

const projectCardStyle: React.CSSProperties = {
  borderRadius: '12px',
  padding: '20px',
  border: '1px solid #e5e7eb',
  boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
  display: 'flex',
  flexDirection: 'column',
  justifyContent: 'space-between',
};

const activeTagStyle: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 700,
  backgroundColor: '#dbeafe',
  color: '#1d4ed8',
  padding: '2px 8px',
  borderRadius: '12px',
  textTransform: 'uppercase',
};

const selectBtnStyle: React.CSSProperties = {
  padding: '6px 12px',
  backgroundColor: '#ffffff',
  color: '#374151',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  fontSize: '12px',
  fontWeight: 600,
  cursor: 'pointer',
};

const cardActionBtnStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: '#4b5563',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
  padding: '4px 8px',
};

const modalOverlayStyle: React.CSSProperties = {
  position: 'fixed',
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  backgroundColor: 'rgba(0, 0, 0, 0.5)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
  padding: '16px',
};

const deleteModalBoxStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  padding: '24px',
  width: '100%',
  maxWidth: '420px',
  boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
};

const cancelDeleteBtnStyle: React.CSSProperties = {
  padding: '8px 16px',
  backgroundColor: '#f3f4f6',
  color: '#374151',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  fontSize: '14px',
  fontWeight: 600,
  cursor: 'pointer',
};

const confirmDeleteBtnStyle: React.CSSProperties = {
  padding: '8px 16px',
  backgroundColor: '#dc2626',
  color: '#ffffff',
  border: 'none',
  borderRadius: '6px',
  fontSize: '14px',
  fontWeight: 600,
};
