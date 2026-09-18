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
        background: '#111827',
        color: '#f3f4f6',
        borderRadius: '12px',
        padding: '24px',
        marginTop: '24px',
        boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.3)',
        border: '1px solid #1f2937',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 600, margin: 0, color: '#f9fafb' }}>
              Long-Term SEO Strategy
            </h2>
            {activeStrategy && (
              <span
                style={{
                  padding: '4px 10px',
                  borderRadius: '9999px',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  ...getHealthBadgeStyle(activeStrategy.health),
                }}
              >
                {activeStrategy.health.replace('_', ' ')}
              </span>
            )}
            {activeStrategy && (
              <span style={{ fontSize: '0.85rem', color: '#9ca3af' }}>
                v{activeStrategy.version} ({activeStrategy.status})
              </span>
            )}
            {isLoading && (
              <span style={{ fontSize: '0.8rem', color: '#9ca3af', fontStyle: 'italic' }}>
                (Updating...)
              </span>
            )}
          </div>
          <p style={{ margin: '6px 0 0 0', fontSize: '0.85rem', color: '#9ca3af' }}>
            Evidence-backed multi-horizon strategy, objective progress tracking, and governed adaptation cycles.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={handleTriggerReview}
            disabled={isActionLoading}
            style={{
              background: '#2563eb',
              color: '#ffffff',
              border: 'none',
              padding: '8px 16px',
              borderRadius: '6px',
              cursor: isActionLoading ? 'not-allowed' : 'pointer',
              fontWeight: 500,
              fontSize: '0.85rem',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
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
            background: '#7f1d1d',
            border: '1px solid #b91c1c',
            color: '#fecaca',
            padding: '10px 14px',
            borderRadius: '6px',
            marginBottom: '16px',
            fontSize: '0.85rem',
          }}
        >
          {errorMessage}
        </div>
      )}
      {successMessage && (
        <div
          style={{
            background: '#064e3b',
            border: '1px solid #059669',
            color: '#a7f3d0',
            padding: '10px 14px',
            borderRadius: '6px',
            marginBottom: '16px',
            fontSize: '0.85rem',
          }}
        >
          {successMessage}
        </div>
      )}

      {/* HITL Strategy Adjustment Banner */}
      {pendingReview && proposedStrategy && (
        <div
          style={{
            background: '#312e81',
            border: '1px solid #4f46e5',
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
              <strong style={{ fontSize: '0.95rem' }}>
                Strategic Adaptation Proposed: Version {proposedStrategy.version}
              </strong>
              <p style={{ margin: '6px 0 0 0', fontSize: '0.85rem', color: '#c7d2fe' }}>
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
          <div style={{ background: '#1f2937', padding: '12px', borderRadius: '8px' }}>
            <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>Active Objectives</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#f9fafb' }}>
              {metrics.active_objectives} / {metrics.total_objectives}
            </div>
          </div>
          <div style={{ background: '#1f2937', padding: '12px', borderRadius: '8px' }}>
            <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>Avg Progress</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#10b981' }}>
              {metrics.average_objective_progress_pct}%
            </div>
          </div>
          <div style={{ background: '#1f2937', padding: '12px', borderRadius: '8px' }}>
            <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>Achieved Goals</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#38bdf8' }}>
              {metrics.achieved_objectives}
            </div>
          </div>
          <div style={{ background: '#1f2937', padding: '12px', borderRadius: '8px' }}>
            <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>Active Initiatives</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#f59e0b' }}>
              {metrics.active_initiatives}
            </div>
          </div>
          <div style={{ background: '#1f2937', padding: '12px', borderRadius: '8px' }}>
            <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>Strategy Versions</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#a855f7' }}>
              v{metrics.current_strategy_version} ({metrics.total_strategy_versions})
            </div>
          </div>
        </div>
      )}

      {/* Grid: Objectives & Initiatives */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '24px' }}>
        {/* Column 1: Strategic Objectives */}
        <div style={{ background: '#1f2937', padding: '16px', borderRadius: '8px' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 600, margin: '0 0 12px 0', color: '#f3f4f6' }}>
            Strategic Objectives ({objectives.length})
          </h3>
          {objectives.length === 0 ? (
            <p style={{ color: '#6b7280', fontSize: '0.85rem' }}>No strategic objectives formulated yet.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {objectives.map((obj) => (
                <div
                  key={obj.id}
                  style={{
                    background: '#111827',
                    padding: '12px',
                    borderRadius: '6px',
                    border: '1px solid #374151',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <strong style={{ fontSize: '0.9rem', color: '#f9fafb' }}>{obj.name}</strong>
                      <div style={{ fontSize: '0.75rem', color: '#9ca3af', marginTop: '2px' }}>
                        Metric: {obj.metric} | Baseline: {obj.baseline} → Target: {obj.target}
                      </div>
                    </div>
                    <span
                      style={{
                        padding: '2px 6px',
                        borderRadius: '4px',
                        fontSize: '0.7rem',
                        fontWeight: 600,
                        background:
                          obj.status === 'achieved'
                            ? '#059669'
                            : obj.status === 'at_risk'
                            ? '#d97706'
                            : '#3b82f6',
                        color: '#ffffff',
                      }}
                    >
                      {obj.status.toUpperCase()}
                    </span>
                  </div>

                  {/* Progress Bar */}
                  <div style={{ marginTop: '8px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#9ca3af', marginBottom: '3px' }}>
                      <span>Current: {obj.current_value}</span>
                      <span>{Math.round(obj.progress * 100)}%</span>
                    </div>
                    <div style={{ background: '#374151', height: '6px', borderRadius: '3px', overflow: 'hidden' }}>
                      <div
                        style={{
                          background: obj.status === 'achieved' ? '#10b981' : obj.status === 'at_risk' ? '#f59e0b' : '#3b82f6',
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
        <div style={{ background: '#1f2937', padding: '16px', borderRadius: '8px' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 600, margin: '0 0 12px 0', color: '#f3f4f6' }}>
            Active Initiatives ({initiatives.length})
          </h3>
          {initiatives.length === 0 ? (
            <p style={{ color: '#6b7280', fontSize: '0.85rem' }}>No initiatives currently active.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {initiatives.map((init) => (
                <div
                  key={init.id}
                  style={{
                    background: '#111827',
                    padding: '12px',
                    borderRadius: '6px',
                    border: '1px solid #374151',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <strong style={{ fontSize: '0.9rem', color: '#f9fafb' }}>{init.name}</strong>
                      <div style={{ fontSize: '0.75rem', color: '#9ca3af', marginTop: '2px' }}>
                        Horizon: {init.horizon.replace('_', ' ')} | Priority: {init.priority}
                      </div>
                    </div>
                    <span
                      style={{
                        padding: '2px 6px',
                        borderRadius: '4px',
                        fontSize: '0.7rem',
                        fontWeight: 600,
                        background: init.status === 'completed' ? '#059669' : '#4b5563',
                        color: '#ffffff',
                      }}
                    >
                      {init.status.toUpperCase()}
                    </span>
                  </div>

                  {init.target_action_types && init.target_action_types.length > 0 && (
                    <div style={{ marginTop: '6px', display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                      {init.target_action_types.map((type, idx) => (
                        <span
                          key={idx}
                          style={{
                            background: '#374151',
                            color: '#d1d5db',
                            fontSize: '0.7rem',
                            padding: '1px 6px',
                            borderRadius: '4px',
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
        <div style={{ background: '#1f2937', padding: '16px', borderRadius: '8px' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 600, margin: '0 0 10px 0', color: '#f3f4f6' }}>
            Historical Strategy Versions ({versions.length})
          </h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', fontSize: '0.8rem', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #374151', color: '#9ca3af' }}>
                  <th style={{ padding: '8px' }}>Version</th>
                  <th style={{ padding: '8px' }}>Status</th>
                  <th style={{ padding: '8px' }}>Health</th>
                  <th style={{ padding: '8px' }}>Effective Period</th>
                  <th style={{ padding: '8px' }}>Rationale Summary</th>
                </tr>
              </thead>
              <tbody>
                {versions.map((ver) => (
                  <tr key={ver.id} style={{ borderBottom: '1px solid #1f2937' }}>
                    <td style={{ padding: '8px', fontWeight: 600 }}>v{ver.version}</td>
                    <td style={{ padding: '8px' }}>
                      <span
                        style={{
                          padding: '2px 6px',
                          borderRadius: '4px',
                          fontSize: '0.7rem',
                          background: ver.status === 'active' ? '#059669' : '#4b5563',
                          color: '#ffffff',
                        }}
                      >
                        {ver.status}
                      </span>
                    </td>
                    <td style={{ padding: '8px' }}>{ver.health}</td>
                    <td style={{ padding: '8px', color: '#9ca3af' }}>
                      {new Date(ver.effective_from).toLocaleDateString()} –{' '}
                      {ver.effective_until ? new Date(ver.effective_until).toLocaleDateString() : 'Current'}
                    </td>
                    <td style={{ padding: '8px', color: '#d1d5db', maxWidth: '300px' }}>
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
