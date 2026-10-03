import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { Project } from '../types/project';
import type {
  LongTermSEOStrategy,
  StrategicObjective,
  StrategicInitiative,
  StrategyReviewRecord,
  StrategyMetrics,
} from '../types/strategy';
import {
  getStrategies,
  getStrategyObjectives,
  getStrategyInitiatives,
  getStrategyVersions,
  getStrategyReviews,
  getStrategyMetrics,
  approveStrategy,
  rejectStrategy,
  triggerStrategyReview,
} from '../api/strategy';

interface LongTermStrategyPanelProps {
  project: Project;
}

export const LongTermStrategyPanel: React.FC<LongTermStrategyPanelProps> = ({ project }) => {
  const [strategies, setStrategies] = useState<LongTermSEOStrategy[]>([]);
  const [activeStrategy, setActiveStrategy] = useState<LongTermSEOStrategy | null>(null);
  const [objectives, setObjectives] = useState<StrategicObjective[]>([]);
  const [initiatives, setInitiatives] = useState<StrategicInitiative[]>([]);
  const [versions, setVersions] = useState<LongTermSEOStrategy[]>([]);
  const [reviews, setReviews] = useState<StrategyReviewRecord[]>([]);
  const [metrics, setMetrics] = useState<StrategyMetrics | null>(null);

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isActionLoading, setIsActionLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const pollIntervalRef = useRef<number | null>(null);

  const loadStrategyData = useCallback(async () => {
    try {
      setIsLoading(true);
      setErrorMessage(null);

      const stratList = await getStrategies(project.id);
      setStrategies(stratList);

      const current = stratList.find((s) => s.status === 'active') || stratList[0] || null;
      setActiveStrategy(current);

      if (current) {
        const [objs, inits, vers, revs] = await Promise.all([
          getStrategyObjectives(current.id),
          getStrategyInitiatives(current.id),
          getStrategyVersions(current.id),
          getStrategyReviews(current.id),
        ]);
        setObjectives(objs);
        setInitiatives(inits);
        setVersions(vers);
        setReviews(revs);
      } else {
        setObjectives([]);
        setInitiatives([]);
        setVersions([]);
        setReviews([]);
      }

      const met = await getStrategyMetrics(project.id);
      setMetrics(met);
    } catch (err: any) {
      console.error('Error loading long-term strategy:', err);
      setErrorMessage(err.message || 'Failed to load long-term SEO strategy.');
    } finally {
      setIsLoading(false);
    }
  }, [project.id]);

  useEffect(() => {
    loadStrategyData();
    pollIntervalRef.current = window.setInterval(loadStrategyData, 30000);
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [loadStrategyData]);

  const handleTriggerReview = async () => {
    try {
      setIsActionLoading(true);
      setErrorMessage(null);
      const res = await triggerStrategyReview(project.id, 'dashboard_operator');
      setSuccessMessage(`Strategic Review cycle #${res.cycle} completed. Decision: ${res.decision.toUpperCase()}.`);
      await loadStrategyData();
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to trigger strategic review.');
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleApproveAdjustment = async (stratId: number) => {
    try {
      setIsActionLoading(true);
      setErrorMessage(null);
      const res = await approveStrategy(stratId);
      setSuccessMessage(res.message);
      await loadStrategyData();
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to approve strategy adjustment.');
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleRejectAdjustment = async (stratId: number) => {
    try {
      setIsActionLoading(true);
      setErrorMessage(null);
      const res = await rejectStrategy(stratId, 'Rejected by operator in dashboard.');
      setSuccessMessage(res.message);
      await loadStrategyData();
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to reject strategy adjustment.');
    } finally {
      setIsActionLoading(false);
    }
  };

  const pendingReview = reviews.find((r) => r.approval_status === 'pending_approval');
  const proposedStrategy = strategies.find((s) => s.status === 'proposed');

  const getHealthBadgeStyle = (health: string = 'no_data') => {
    switch (health) {
      case 'on_track':
        return { background: '#059669', color: '#ffffff' };
      case 'at_risk':
        return { background: '#d97706', color: '#ffffff' };
      case 'off_track':
        return { background: '#dc2626', color: '#ffffff' };
      default:
        return { background: '#4b5563', color: '#ffffff' };
    }
  };

  return (
    <div
      style={{
        background: '#ffffff',
        color: '#0f172a',
        borderRadius: '12px',
        padding: '24px',
        marginTop: '20px',
        boxShadow: '0 1px 3px rgba(0, 0, 0, 0.05)',
        border: '1px solid #e2e8f0',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, margin: 0, color: '#24143C' }}>
              Long-Term SEO Strategy
            </h2>
            {activeStrategy && (
              <span
                style={{
                  padding: '4px 10px',
                  borderRadius: '9999px',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  ...getHealthBadgeStyle(activeStrategy.health),
                }}
              >
                {activeStrategy.health.replace('_', ' ')}
              </span>
            )}
            {activeStrategy && (
              <span style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 600 }}>
                v{activeStrategy.version} ({activeStrategy.status})
              </span>
            )}
            {isLoading && (
              <span style={{ fontSize: '0.8rem', color: '#64748b', fontStyle: 'italic' }}>
                (Updating...)
              </span>
            )}
          </div>
          <p style={{ margin: '6px 0 0 0', fontSize: '0.85rem', color: '#64748b' }}>
            Evidence-backed multi-horizon strategy, objective progress tracking, and governed adaptation cycles.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={handleTriggerReview}
            disabled={isActionLoading}
            style={{
              background: '#774da9',
              color: '#ffffff',
              border: 'none',
              padding: '8px 16px',
              borderRadius: '6px',
              cursor: isActionLoading ? 'not-allowed' : 'pointer',
              fontWeight: 600,
              fontSize: '0.85rem',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              boxShadow: '0 2px 4px rgba(119, 77, 169, 0.2)',
            }}
          >
            {isActionLoading ? 'Evaluating...' : 'Trigger Review Cycle'}
          </button>
        </div>
      </div>

      {/* Notifications */}
      {errorMessage && (
        <div
          style={{
            background: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#991b1b',
            padding: '10px 14px',
            borderRadius: '6px',
            marginBottom: '16px',
            fontSize: '0.85rem',
            fontWeight: 500,
          }}
        >
          {errorMessage}
        </div>
      )}
      {successMessage && (
        <div
          style={{
            background: '#f0fdf4',
            border: '1px solid #bbf7d0',
            color: '#166534',
            padding: '10px 14px',
            borderRadius: '6px',
            marginBottom: '16px',
            fontSize: '0.85rem',
            fontWeight: 500,
          }}
        >
          {successMessage}
        </div>
      )}

      {/* HITL Strategy Adjustment Banner */}
      {pendingReview && proposedStrategy && (
        <div
          style={{
            background: '#faf5ff',
            border: '1px solid #c084fc',
            borderRadius: '8px',
            padding: '16px',
            marginBottom: '20px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span
                style={{
                  background: '#d97706',
                  color: '#ffffff',
                  padding: '2px 8px',
                  borderRadius: '4px',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  marginRight: '8px',
                }}
              >
                HITL APPROVAL REQUIRED
              </span>
              <strong style={{ fontSize: '0.95rem', color: '#581c87' }}>
                Strategic Adaptation Proposed: Version {proposedStrategy.version}
              </strong>
              <p style={{ margin: '6px 0 0 0', fontSize: '0.85rem', color: '#6b21a8' }}>
                {proposedStrategy.rationale || 'Strategic adaptation review triggered changes to objectives or priorities.'}
              </p>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={() => handleApproveAdjustment(proposedStrategy.id)}
                disabled={isActionLoading}
                style={{
                  background: '#059669',
                  color: '#ffffff',
                  border: 'none',
                  padding: '8px 14px',
                  borderRadius: '6px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                }}
              >
                Approve v{proposedStrategy.version}
              </button>
              <button
                onClick={() => handleRejectAdjustment(proposedStrategy.id)}
                disabled={isActionLoading}
                style={{
                  background: '#dc2626',
                  color: '#ffffff',
                  border: 'none',
                  padding: '8px 14px',
                  borderRadius: '6px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                }}
              >
                Reject
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Metrics Strip */}
      {metrics && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
            gap: '12px',
            marginBottom: '20px',
          }}
        >
          <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', padding: '14px', borderRadius: '8px' }}>
            <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 600 }}>Active Objectives</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#24143C' }}>
              {metrics.active_objectives} / {metrics.total_objectives}
            </div>
          </div>
          <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', padding: '14px', borderRadius: '8px' }}>
            <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 600 }}>Avg Progress</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#059669' }}>
              {metrics.average_objective_progress_pct}%
            </div>
          </div>
          <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', padding: '14px', borderRadius: '8px' }}>
            <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 600 }}>Achieved Goals</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#059669' }}>
              {metrics.achieved_objectives}
            </div>
          </div>
          <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', padding: '14px', borderRadius: '8px' }}>
            <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 600 }}>Active Initiatives</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#d97706' }}>
              {metrics.active_initiatives}
            </div>
          </div>
          <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', padding: '14px', borderRadius: '8px' }}>
            <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 600 }}>Strategy Versions</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#774da9' }}>
              v{metrics.current_strategy_version} ({metrics.total_strategy_versions})
            </div>
          </div>
        </div>
      )}

      {/* Grid: Objectives & Initiatives */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px', marginBottom: '24px' }}>
        {/* Column 1: Strategic Objectives */}
        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', padding: '16px', borderRadius: '8px' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: '0 0 12px 0', color: '#24143C' }}>
            Strategic Objectives ({objectives.length})
          </h3>
          {objectives.length === 0 ? (
            <p style={{ color: '#64748b', fontSize: '0.85rem' }}>No strategic objectives formulated yet.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {objectives.map((obj) => (
                <div
                  key={obj.id}
                  style={{
                    background: '#ffffff',
                    padding: '12px',
                    borderRadius: '6px',
                    border: '1px solid #e2e8f0',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <strong style={{ fontSize: '0.9rem', color: '#0f172a' }}>{obj.name}</strong>
                      <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '2px' }}>
                        Metric: {obj.metric} | Baseline: {obj.baseline} → Target: {obj.target}
                      </div>
                    </div>
                    <span
                      style={{
                        padding: '2px 6px',
                        borderRadius: '4px',
                        fontSize: '0.7rem',
                        fontWeight: 700,
                        background:
                          obj.status === 'achieved'
                            ? '#dcfce7'
                            : obj.status === 'at_risk'
                            ? '#fef3c7'
                            : '#f3eef9',
                        color:
                          obj.status === 'achieved'
                            ? '#15803d'
                            : obj.status === 'at_risk'
                            ? '#b45309'
                            : '#774da9',
                      }}
                    >
                      {obj.status.toUpperCase()}
                    </span>
                  </div>

                  {/* Progress Bar */}
                  <div style={{ marginTop: '8px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#64748b', marginBottom: '3px' }}>
                      <span>Current: <strong>{obj.current_value}</strong></span>
                      <span style={{ fontWeight: 600 }}>{Math.round(obj.progress * 100)}%</span>
                    </div>
                    <div style={{ background: '#e2e8f0', height: '6px', borderRadius: '3px', overflow: 'hidden' }}>
                      <div
                        style={{
                          background: obj.status === 'achieved' ? '#10b981' : obj.status === 'at_risk' ? '#f59e0b' : '#774da9',
                          height: '100%',
                          width: `${Math.min(obj.progress * 100, 100)}%`,
                          transition: 'width 0.3s ease',
                        }}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Column 2: Strategic Initiatives */}
        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', padding: '16px', borderRadius: '8px' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: '0 0 12px 0', color: '#24143C' }}>
            Active Initiatives ({initiatives.length})
          </h3>
          {initiatives.length === 0 ? (
            <p style={{ color: '#64748b', fontSize: '0.85rem' }}>No initiatives currently active.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {initiatives.map((init) => (
                <div
                  key={init.id}
                  style={{
                    background: '#ffffff',
                    padding: '12px',
                    borderRadius: '6px',
                    border: '1px solid #e2e8f0',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <strong style={{ fontSize: '0.9rem', color: '#0f172a' }}>{init.name}</strong>
                      <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '2px' }}>
                        Horizon: {init.horizon.replace('_', ' ')} | Priority: {init.priority}
                      </div>
                    </div>
                    <span
                      style={{
                        padding: '2px 6px',
                        borderRadius: '4px',
                        fontSize: '0.7rem',
                        fontWeight: 700,
                        background: init.status === 'completed' ? '#dcfce7' : '#f1f5f9',
                        color: init.status === 'completed' ? '#15803d' : '#475569',
                      }}
                    >
                      {init.status.toUpperCase()}
                    </span>
                  </div>

                  {init.target_action_types && init.target_action_types.length > 0 && (
                    <div style={{ marginTop: '8px', display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                      {init.target_action_types.map((type, idx) => (
                        <span
                          key={idx}
                          style={{
                            background: '#f1f5f9',
                            color: '#475569',
                            fontSize: '0.7rem',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            border: '1px solid #e2e8f0',
                          }}
                        >
                          {type}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Historical Versions & Decisions */}
      {versions.length > 1 && (
        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', padding: '16px', borderRadius: '8px' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: '0 0 10px 0', color: '#24143C' }}>
            Historical Strategy Versions ({versions.length})
          </h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', fontSize: '0.8rem', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#475569', background: '#f1f5f9' }}>
                  <th style={{ padding: '8px 12px' }}>Version</th>
                  <th style={{ padding: '8px 12px' }}>Status</th>
                  <th style={{ padding: '8px 12px' }}>Health</th>
                  <th style={{ padding: '8px 12px' }}>Effective Period</th>
                  <th style={{ padding: '8px 12px' }}>Rationale Summary</th>
                </tr>
              </thead>
              <tbody>
                {versions.map((ver) => (
                  <tr key={ver.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px 12px', fontWeight: 700, color: '#0f172a' }}>v{ver.version}</td>
                    <td style={{ padding: '8px 12px' }}>
                      <span
                        style={{
                          padding: '2px 6px',
                          borderRadius: '4px',
                          fontSize: '0.7rem',
                          fontWeight: 700,
                          background: ver.status === 'active' ? '#dcfce7' : '#f1f5f9',
                          color: ver.status === 'active' ? '#15803d' : '#475569',
                        }}
                      >
                        {ver.status}
                      </span>
                    </td>
                    <td style={{ padding: '8px 12px', color: '#334155' }}>{ver.health}</td>
                    <td style={{ padding: '8px 12px', color: '#64748b' }}>
                      {new Date(ver.effective_from).toLocaleDateString()} –{' '}
                      {ver.effective_until ? new Date(ver.effective_until).toLocaleDateString() : 'Current'}
                    </td>
                    <td style={{ padding: '8px 12px', color: '#334155', maxWidth: '300px' }}>
                      {ver.rationale.substring(0, 120)}...
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
