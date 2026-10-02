import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { Project } from '../types/project';
import type {
  Competitor,
  CompetitorSnapshotJob,
  LatestCompetitorSnapshot,
} from '../types/competitor';
import {
  getCompetitors,
  createCompetitor,
  deleteCompetitor,
  triggerCompetitorSnapshot,
  getCompetitorSnapshotJobs,
  getLatestCompetitorSnapshots,
} from '../api/competitors';

interface CompetitorSnapshotsPanelProps {
  project: Project;
  hasCompetitorEntitlement: boolean;
}

export const CompetitorSnapshotsPanel: React.FC<CompetitorSnapshotsPanelProps> = ({
  project,
  hasCompetitorEntitlement,
}) => {
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [latestSnapshots, setLatestSnapshots] = useState<LatestCompetitorSnapshot[]>([]);
  const [activeJob, setActiveJob] = useState<CompetitorSnapshotJob | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [triggering, setTriggering] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Add Competitor modal / form state
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [competitorName, setCompetitorName] = useState<string>('');
  const [competitorDomain, setCompetitorDomain] = useState<string>('');
  const [creating, setCreating] = useState<boolean>(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Filter state
  const [selectedCompetitorFilter, setSelectedCompetitorFilter] = useState<string>('all');

  const pollIntervalRef = useRef<any>(null);

  const loadData = useCallback(async () => {
    if (!project || !hasCompetitorEntitlement) return;
    setLoading(true);
    setError(null);
    try {
      const [comps, snaps, jobs] = await Promise.all([
        getCompetitors(project.id),
        getLatestCompetitorSnapshots(project.id),
        getCompetitorSnapshotJobs(project.id),
      ]);
      setCompetitors(comps);
      setLatestSnapshots(snaps);

      // Check if there is an active job running
      const active = jobs.find((j) => j.status === 'pending' || j.status === 'running');
      setActiveJob(active || null);
    } catch (err: any) {
      setError(err?.message || 'Failed to load competitor snapshot data.');
    } finally {
      setLoading(false);
    }
  }, [project, hasCompetitorEntitlement]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Polling effect while job is pending or running
  useEffect(() => {
    if (activeJob && (activeJob.status === 'pending' || activeJob.status === 'running')) {
      pollIntervalRef.current = setInterval(async () => {
        try {
          const jobs = await getCompetitorSnapshotJobs(project.id);
          const current = jobs.find((j) => j.id === activeJob.id);
          if (current) {
            setActiveJob(current);
            if (current.status !== 'pending' && current.status !== 'running') {
              if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
              // Refresh snapshots table when job finishes
              const snaps = await getLatestCompetitorSnapshots(project.id);
              setLatestSnapshots(snaps);
              setSuccessMsg(`Snapshot job #${current.id} finished with status: ${current.status}.`);
            }
          }
        } catch {
          // ignore transient poll error
        }
      }, 3000);
    }

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [activeJob, project.id]);

  const handleTriggerSnapshot = async () => {
    if (!project || triggering) return;
    setTriggering(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await triggerCompetitorSnapshot(project.id);
      setSuccessMsg(res.message || 'Competitor snapshot check queued.');
      // Refresh jobs list to pick up active job
      const jobs = await getCompetitorSnapshotJobs(project.id);
      const active = jobs.find((j) => j.status === 'pending' || j.status === 'running');
      setActiveJob(active || null);
    } catch (err: any) {
      setError(err?.message || 'Failed to trigger competitor snapshot.');
    } finally {
      setTriggering(false);
    }
  };

  const handleAddCompetitor = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!competitorName.trim() || !competitorDomain.trim()) {
      setAddError('Both competitor name and domain are required.');
      return;
    }
    setCreating(true);
    setAddError(null);
    try {
      await createCompetitor({
        project: project.id,
        name: competitorName.trim(),
        domain: competitorDomain.trim(),
      });
      setCompetitorName('');
      setCompetitorDomain('');
      setShowAddModal(false);
      await loadData();
    } catch (err: any) {
      setAddError(err?.message || 'Failed to add competitor.');
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteCompetitor = async (id: number, name: string) => {
    if (!window.confirm(`Are you sure you want to remove competitor "${name}"?`)) return;
    try {
      await deleteCompetitor(id);
      await loadData();
    } catch (err: any) {
      setError(err?.message || 'Failed to remove competitor.');
    }
  };

  const filteredSnapshots = latestSnapshots.filter((snap) => {
    if (selectedCompetitorFilter === 'all') return true;
    return String(snap.competitor_id) === selectedCompetitorFilter;
  });

  return (
    <section
      id="competitor-snapshots-section"
      style={{
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        padding: '24px',
        boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)',
        border: '1px solid #e2e8f0',
        marginBottom: '32px',
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
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a', margin: 0 }}>
              Competitor SERP Snapshots
            </h2>
            <span
              style={{
                fontSize: '12px',
                fontWeight: 600,
                padding: '3px 8px',
                borderRadius: '6px',
                backgroundColor: '#f6f2fb',
                color: '#774da9',
                border: '1px solid #dac8ee',
              }}
            >
              Agency · Weekly google.com.et
            </span>
          </div>
          <p style={{ fontSize: '14px', color: '#64748b', margin: '6px 0 0 0' }}>
            Track competitor ranking visibility on Google Ethiopia for your project's keywords.
          </p>
        </div>

        {hasCompetitorEntitlement && (
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <button
              id="add-competitor-btn"
              onClick={() => setShowAddModal(true)}
              style={{
                padding: '8px 14px',
                backgroundColor: '#f1f5f9',
                color: '#334155',
                border: '1px solid #cbd5e1',
                borderRadius: '8px',
                fontWeight: 600,
                fontSize: '13px',
                cursor: 'pointer',
              }}
            >
              + Add Competitor
            </button>
            <button
              id="run-competitor-snapshot-btn"
              onClick={handleTriggerSnapshot}
              disabled={triggering || Boolean(activeJob && (activeJob.status === 'pending' || activeJob.status === 'running'))}
              style={{
                padding: '8px 16px',
                backgroundColor:
                  activeJob && (activeJob.status === 'pending' || activeJob.status === 'running')
                    ? '#94a3b8'
                    : '#774da9',
                color: '#ffffff',
                border: 'none',
                borderRadius: '8px',
                fontWeight: 600,
                fontSize: '13px',
                cursor:
                  activeJob && (activeJob.status === 'pending' || activeJob.status === 'running')
                    ? 'not-allowed'
                    : 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              {triggering ? 'Queuing...' : 'Run Snapshot Check'}
            </button>
          </div>
        )}
      </div>

      {/* Subscription Paywall Notice */}
      {!hasCompetitorEntitlement && (
        <div
          id="competitor-paywall-notice"
          style={{
            padding: '24px',
            backgroundColor: '#faf5ff',
            borderRadius: '10px',
            border: '1px solid #e9d5ff',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: '28px', marginBottom: '8px' }}>Locked</div>
          <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#24143c', margin: '0 0 6px 0' }}>
            Competitor SERP Snapshots is an Agency Feature
          </h3>
          <p style={{ fontSize: '14px', color: '#593285', margin: '0 0 16px 0', maxWidth: '520px', marginLeft: 'auto', marginRight: 'auto' }}>
            Upgrade to the Agency Plan to track weekly competitor rankings on Google Ethiopia across all your project keywords.
          </p>
          <button
            onClick={() => (window.location.href = '/subscription')}
            style={{
              padding: '8px 18px',
              backgroundColor: '#774da9',
              color: '#ffffff',
              border: 'none',
              borderRadius: '8px',
              fontWeight: 600,
              fontSize: '13px',
              cursor: 'pointer',
            }}
          >
            Upgrade to Agency Plan
          </button>
        </div>
      )}

      {hasCompetitorEntitlement && (
        <>
          {/* Status / Error Alerts */}
          {error && (
            <div
              style={{
                padding: '12px 16px',
                backgroundColor: '#fee2e2',
                color: '#b91c1c',
                borderRadius: '8px',
                fontSize: '13px',
                marginBottom: '16px',
              }}
            >
               {error}
            </div>
          )}

          {successMsg && (
            <div
              style={{
                padding: '12px 16px',
                backgroundColor: '#f0fdf4',
                color: '#15803d',
                borderRadius: '8px',
                fontSize: '13px',
                marginBottom: '16px',
              }}
            >
              Check {successMsg}
            </div>
          )}

          {/* Active Job Progress Banner */}
          {activeJob && (activeJob.status === 'pending' || activeJob.status === 'running') && (
            <div
              id="competitor-job-active-banner"
              style={{
                padding: '14px 18px',
                backgroundColor: '#f6f2fb',
                border: '1px solid #dac8ee',
                borderRadius: '8px',
                marginBottom: '20px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '12px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                
                <div>
                  <div style={{ fontSize: '13px', fontWeight: 700, color: '#24143c' }}>
                    Snapshot Job #{activeJob.id} is {activeJob.status.toUpperCase()}
                  </div>
                  <div style={{ fontSize: '12px', color: '#593285' }}>
                    Processed {activeJob.completed_keywords} of {activeJob.total_keywords} keywords
                    {activeJob.failed_keywords > 0 && ` (${activeJob.failed_keywords} failed)`}...
                  </div>
                </div>
              </div>
              <span
                style={{
                  fontSize: '12px',
                  fontWeight: 600,
                  padding: '4px 10px',
                  backgroundColor: '#774da9',
                  color: '#ffffff',
                  borderRadius: '6px',
                }}
              >
                Auto-refreshing
              </span>
            </div>
          )}

          {/* Active Competitors Chips */}
          <div style={{ marginBottom: '20px' }}>
            <div style={{ fontSize: '13px', fontWeight: 600, color: '#475569', marginBottom: '8px' }}>
              Tracked Competitors ({competitors.length}):
            </div>
            {competitors.length === 0 ? (
              <div style={{ fontSize: '13px', color: '#94a3b8', fontStyle: 'italic' }}>
                No competitors added yet. Click "+ Add Competitor" above to start tracking.
              </div>
            ) : (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {competitors.map((comp) => (
                  <span
                    key={comp.id}
                    id={`competitor-chip-${comp.id}`}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '4px 10px',
                      backgroundColor: '#f8fafc',
                      border: '1px solid #cbd5e1',
                      borderRadius: '20px',
                      fontSize: '12px',
                      color: '#1e293b',
                    }}
                  >
                    <strong>{comp.name}</strong> ({comp.domain})
                    <button
                      onClick={() => handleDeleteCompetitor(comp.id, comp.name)}
                      title={`Remove ${comp.name}`}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: '#94a3b8',
                        cursor: 'pointer',
                        padding: 0,
                        marginLeft: '4px',
                        fontSize: '14px',
                        lineHeight: 1,
                      }}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Filter Bar */}
          {competitors.length > 0 && (
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '12px',
              }}
            >
              <div style={{ fontSize: '14px', fontWeight: 600, color: '#334155' }}>
                Latest SERP Visibility on google.com.et:
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <label style={{ fontSize: '12px', color: '#64748b' }}>Filter Competitor:</label>
                <select
                  value={selectedCompetitorFilter}
                  onChange={(e) => setSelectedCompetitorFilter(e.target.value)}
                  style={{
                    padding: '4px 8px',
                    fontSize: '12px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: '#ffffff',
                  }}
                >
                  <option value="all">All Competitors</option>
                  {competitors.map((c) => (
                    <option key={c.id} value={String(c.id)}>
                      {c.name} ({c.domain})
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {/* Snapshots Table */}
          {loading ? (
            <div style={{ textAlign: 'center', padding: '32px', color: '#64748b', fontSize: '14px' }}>
              Loading competitor snapshots...
            </div>
          ) : filteredSnapshots.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                padding: '36px',
                backgroundColor: '#f8fafc',
                borderRadius: '8px',
                border: '1px dashed #cbd5e1',
                color: '#64748b',
                fontSize: '14px',
              }}
            >
              {competitors.length === 0
                ? 'Add at least one competitor to begin tracking SERP visibility.'
                : 'No snapshot observations recorded yet. Click "Run Snapshot Check" to fetch Google Ethiopia rankings.'}
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #e2e8f0', textAlign: 'left', backgroundColor: '#f8fafc' }}>
                    <th style={{ padding: '10px 12px', color: '#475569' }}>Keyword</th>
                    <th style={{ padding: '10px 12px', color: '#475569' }}>Competitor</th>
                    <th style={{ padding: '10px 12px', color: '#475569', textAlign: 'center' }}>Position</th>
                    <th style={{ padding: '10px 12px', color: '#475569' }}>Status</th>
                    <th style={{ padding: '10px 12px', color: '#475569' }}>Found URL & Title</th>
                    <th style={{ padding: '10px 12px', color: '#475569' }}>Snapshot Date</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSnapshots.map((item, idx) => {
                    const pos = item.position;
                    const isTop3 = pos !== null && pos <= 3;
                    const isTop10 = pos !== null && pos <= 10;
                    return (
                      <tr
                        key={`${item.competitor_id}-${item.keyword_id}-${idx}`}
                        style={{ borderBottom: '1px solid #f1f5f9' }}
                      >
                        <td style={{ padding: '10px 12px', fontWeight: 600, color: '#0f172a' }}>
                          {item.keyword}
                        </td>
                        <td style={{ padding: '10px 12px', color: '#334155' }}>
                          <div><strong>{item.competitor_name}</strong></div>
                          <div style={{ fontSize: '11px', color: '#64748b' }}>{item.competitor_domain}</div>
                        </td>
                        <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                          {pos !== null ? (
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                padding: '4px 10px',
                                borderRadius: '8px',
                                fontWeight: 800,
                                fontSize: '13px',
                                backgroundColor: isTop3 ? '#fef3c7' : isTop10 ? '#f3eef9' : '#f1f5f9',
                                color: isTop3 ? '#92400e' : isTop10 ? '#774da9' : '#475569',
                                border: isTop3 ? '1px solid #fcd34d' : isTop10 ? '1px solid #dac8ee' : '1px solid #e2e8f0',
                              }}
                            >
                              #{pos}
                            </span>
                          ) : (
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                padding: '4px 8px',
                                borderRadius: '6px',
                                fontWeight: 600,
                                fontSize: '11px',
                                backgroundColor: '#fee2e2',
                                color: '#b91c1c',
                              }}
                            >
                              &gt; 100
                            </span>
                          )}
                        </td>
                        <td style={{ padding: '10px 12px' }}>
                          <span
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              padding: '2px 8px',
                              borderRadius: '4px',
                              fontSize: '11px',
                              fontWeight: 600,
                              textTransform: 'capitalize',
                              backgroundColor:
                                item.result_status === 'found'
                                  ? '#dcfce7'
                                  : item.result_status === 'error'
                                  ? '#fee2e2'
                                  : '#f1f5f9',
                              color:
                                item.result_status === 'found'
                                  ? '#15803d'
                                  : item.result_status === 'error'
                                  ? '#b91c1c'
                                  : '#64748b',
                            }}
                          >
                            {item.result_status === 'found'
                              ? 'Found'
                              : item.result_status === 'error'
                              ? 'Error'
                              : 'Not Found'}
                          </span>
                        </td>
                        <td style={{ padding: '10px 12px', maxWidth: '300px' }}>
                          {item.title && (
                            <div
                              style={{
                                fontWeight: 600,
                                color: '#1e293b',
                                fontSize: '12px',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                              }}
                              title={item.title}
                            >
                              {item.title}
                            </div>
                          )}
                          {item.ranking_url ? (
                            <a
                              href={item.ranking_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{
                                color: '#774da9',
                                fontSize: '11px',
                                textDecoration: 'none',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                                display: 'inline-block',
                                maxWidth: '280px',
                              }}
                              title={item.ranking_url}
                            >
                              {item.ranking_url}
                            </a>
                          ) : (
                            <span style={{ color: '#94a3b8', fontSize: '12px' }}>—</span>
                          )}
                        </td>
                        <td style={{ padding: '10px 12px', color: '#64748b', fontSize: '12px' }}>
                          {item.recorded_at
                            ? new Date(item.recorded_at).toLocaleDateString(undefined, {
                                year: 'numeric',
                                month: 'short',
                                day: 'numeric',
                              })
                            : '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Add Competitor Modal */}
      {showAddModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              padding: '24px',
              width: '100%',
              maxWidth: '440px',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
            }}
          >
            <h3 style={{ fontSize: '18px', fontWeight: 700, margin: '0 0 16px 0', color: '#0f172a' }}>
              Add Tracked Competitor
            </h3>
            {addError && (
              <div
                style={{
                  padding: '10px 14px',
                  backgroundColor: '#fee2e2',
                  color: '#b91c1c',
                  borderRadius: '6px',
                  fontSize: '12px',
                  marginBottom: '14px',
                }}
              >
                 {addError}
              </div>
            )}
            <form onSubmit={handleAddCompetitor}>
              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Competitor Name / Brand:
                </label>
                <input
                  type="text"
                  placeholder="e.g. Addis Insight"
                  value={competitorName}
                  onChange={(e) => setCompetitorName(e.target.value)}
                  required
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    fontSize: '13px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Competitor Domain or URL:
                </label>
                <input
                  type="text"
                  placeholder="e.g. addisinsight.net or https://addisinsight.net"
                  value={competitorDomain}
                  onChange={(e) => setCompetitorDomain(e.target.value)}
                  required
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    fontSize: '13px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    boxSizing: 'border-box',
                  }}
                />
                <span style={{ fontSize: '11px', color: '#64748b', marginTop: '4px', display: 'block' }}>
                  Will be normalized to canonical domain for SERP matching.
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  style={{
                    padding: '8px 14px',
                    backgroundColor: '#f1f5f9',
                    color: '#475569',
                    border: 'none',
                    borderRadius: '6px',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  style={{
                    padding: '8px 16px',
                    backgroundColor: '#774da9',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: '6px',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: creating ? 'not-allowed' : 'pointer',
                  }}
                >
                  {creating ? 'Saving...' : 'Add Competitor'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
};
