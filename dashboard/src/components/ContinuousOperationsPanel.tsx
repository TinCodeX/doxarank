import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { Project } from '../types/project';
import type { AgentRun } from '../types/agentRun';
import type {
  ContinuousOperation,
  ContinuousOperationScheduleType,
} from '../types/continuousOperation';
import {
  getContinuousOperations,
  createContinuousOperation,
  pauseContinuousOperation,
  resumeContinuousOperation,
  triggerContinuousOperationRun,
  getContinuousOperationRuns,
} from '../api/continuousOperations';

interface ContinuousOperationsPanelProps {
  project: Project;
}

export const ContinuousOperationsPanel: React.FC<ContinuousOperationsPanelProps> = ({ project }) => {
  const [operations, setOperations] = useState<ContinuousOperation[]>([]);
  const [selectedOp, setSelectedOp] = useState<ContinuousOperation | null>(null);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isActionLoading, setIsActionLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Modal / Form state
  const [isCreating, setIsCreating] = useState<boolean>(false);
  const [newGoal, setNewGoal] = useState<string>('Monitor organic search health, query shifts, and site audit issues.');
  const [newScheduleType, setNewScheduleType] = useState<ContinuousOperationScheduleType>('interval_minutes');
  const [newIntervalValue, setNewIntervalValue] = useState<number>(30);

  const pollingTimerRef = useRef<number | null>(null);

  const loadOperations = useCallback(async (selectFirstIfNone = true) => {
    try {
      setIsLoading(true);
      setErrorMessage(null);
      const data = await getContinuousOperations(project.id);
      setOperations(data);
      if (data.length > 0) {
        setSelectedOp((prev) => {
          if (prev) {
            const found = data.find((o) => o.id === prev.id);
            return found || data[0];
          }
          return selectFirstIfNone ? data[0] : null;
        });
      } else {
        setSelectedOp(null);
        setRuns([]);
      }
    } catch (err: any) {
      console.error('Error loading continuous operations:', err);
      setErrorMessage(err.message || 'Failed to load continuous operations.');
    } finally {
      setIsLoading(false);
    }
  }, [project.id]);

  const loadRuns = useCallback(async (opId: number) => {
    try {
      const runData = await getContinuousOperationRuns(opId);
      setRuns(runData);
    } catch (err: any) {
      console.error('Error loading runs for operation:', err);
    }
  }, []);

  useEffect(() => {
    loadOperations();
  }, [loadOperations]);

  useEffect(() => {
    if (selectedOp) {
      loadRuns(selectedOp.id);
    }
  }, [selectedOp?.id, loadRuns]);

  // Periodic polling for status and runs
  useEffect(() => {
    if (pollingTimerRef.current) {
      window.clearInterval(pollingTimerRef.current);
    }
    pollingTimerRef.current = window.setInterval(() => {
      loadOperations(false);
      if (selectedOp) {
        loadRuns(selectedOp.id);
      }
    }, 8000);

    return () => {
      if (pollingTimerRef.current) {
        window.clearInterval(pollingTimerRef.current);
      }
    };
  }, [loadOperations, selectedOp, loadRuns]);

  const handlePause = async () => {
    if (!selectedOp) return;
    try {
      setIsActionLoading(true);
      setErrorMessage(null);
      const updated = await pauseContinuousOperation(selectedOp.id);
      setSelectedOp(updated);
      setOperations((prev) => prev.map((o) => (o.id === updated.id ? updated : o)));
      setSuccessMessage(`Operation #${updated.id} paused.`);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to pause operation.');
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleResume = async () => {
    if (!selectedOp) return;
    try {
      setIsActionLoading(true);
      setErrorMessage(null);
      const updated = await resumeContinuousOperation(selectedOp.id);
      setSelectedOp(updated);
      setOperations((prev) => prev.map((o) => (o.id === updated.id ? updated : o)));
      setSuccessMessage(`Operation #${updated.id} resumed.`);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to resume operation.');
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleTriggerNow = async () => {
    if (!selectedOp) return;
    try {
      setIsActionLoading(true);
      setErrorMessage(null);
      await triggerContinuousOperationRun(selectedOp.id);
      setSuccessMessage(`Scheduled run dispatched for Operation #${selectedOp.id}.`);
      await loadOperations(false);
      await loadRuns(selectedOp.id);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to trigger run.');
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleCreateOperation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newGoal.trim()) return;
    try {
      setIsActionLoading(true);
      setErrorMessage(null);
      const created = await createContinuousOperation({
        project: project.id,
        goal: newGoal.trim(),
        schedule_type: newScheduleType,
        interval_value: Number(newIntervalValue),
        auto_activate: true,
      });
      setIsCreating(false);
      setSuccessMessage(`Continuous Operation #${created.id} created and active.`);
      await loadOperations(true);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to create continuous operation.');
    } finally {
      setIsActionLoading(false);
    }
  };

  const formatRelativeTime = (isoString?: string | null) => {
    if (!isoString) return 'Never';
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSec = Math.round(diffMs / 1000);

    if (diffSec < 0) {
      const absSec = Math.abs(diffSec);
      if (absSec < 60) return `in ${absSec}s`;
      const absMin = Math.round(absSec / 60);
      if (absMin < 60) return `in ${absMin}m`;
      const absHours = Math.round(absMin / 60);
      return `in ${absHours}h`;
    }

    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.round(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHours = Math.round(diffMin / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString();
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return '#10b981';
      case 'running':
        return '#774da9';
      case 'paused':
        return '#f59e0b';
      case 'waiting':
        return '#f97316';
      case 'failed':
        return '#ef4444';
      default:
        return '#6b7280';
    }
  };

  return (
    <div
      id="continuous-seo-operations-section"
      style={{
        background: '#ffffff',
        borderRadius: '12px',
        border: '1px solid #e2e8f0',
        padding: '24px',
        marginBottom: '24px',
        boxShadow: '0 1px 3px 0 rgba(36, 20, 60, 0.06)',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '16px',
          marginBottom: '20px',
          borderBottom: '1px solid #e2e8f0',
          paddingBottom: '16px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h2 style={{ margin: 0, fontSize: '20px', color: '#24143C', fontWeight: 800 }}>
              Recurring SEO Operations
            </h2>
            <span
              style={{
                fontSize: '11px',
                fontWeight: 700,
                textTransform: 'uppercase',
                padding: '2px 8px',
                borderRadius: '999px',
                background: '#f6f2fb',
                color: '#774DA9',
                border: '1px solid #dac8ee',
              }}
            >
              Active Schedules
            </span>
          </div>
          <p style={{ margin: '6px 0 0 0', fontSize: '14px', color: '#64748b' }}>
            Autonomous recurring agent lifecycle monitoring and strategy execution for <strong>{project.name}</strong>.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={() => setIsCreating(true)}
            style={{
              background: '#774da9',
              color: '#fff',
              border: 'none',
              borderRadius: '8px',
              padding: '8px 16px',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span>+</span> New Operation
          </button>
        </div>
      </div>

      {/* Alerts */}
      {errorMessage && (
        <div
          style={{
            background: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#991b1b',
            padding: '10px 14px',
            borderRadius: '8px',
            fontSize: '13px',
            marginBottom: '16px',
          }}
        >
          {errorMessage}
        </div>
      )}
      {successMessage && (
        <div
          style={{
            background: '#ecfdf5',
            border: '1px solid #a7f3d0',
            color: '#065f46',
            padding: '10px 14px',
            borderRadius: '8px',
            fontSize: '13px',
            marginBottom: '16px',
          }}
        >
          {successMessage}
        </div>
      )}

      {/* Creation Modal / Form */}
      {isCreating && (
        <div
          style={{
            background: 'rgba(36, 20, 60, 0.65)',
            backdropFilter: 'blur(4px)',
            position: 'fixed',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1050,
            padding: '16px',
          }}
        >
          <div
            style={{
              background: '#ffffff',
              border: '1px solid #e2e8f0',
              borderRadius: '14px',
              padding: '24px',
              width: '100%',
              maxWidth: '520px',
              boxShadow: '0 20px 25px -5px rgba(36, 20, 60, 0.15)',
            }}
          >
            <h3 style={{ margin: '0 0 16px 0', color: '#24143C', fontSize: '18px', fontWeight: 800 }}>Configure Recurring Operation</h3>
            <form onSubmit={handleCreateOperation}>
              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px', color: '#334155', fontWeight: 600 }}>
                  Operational Goal / Mission
                </label>
                <textarea
                  value={newGoal}
                  onChange={(e) => setNewGoal(e.target.value)}
                  placeholder="e.g. Audit top high-value Ethiopian keywords and optimize hreflang tags"
                  rows={3}
                  required
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    borderRadius: '8px',
                    border: '1px solid #cbd5e1',
                    background: '#f8fafc',
                    color: '#0f172a',
                    fontSize: '13px',
                    boxSizing: 'border-box',
                    outline: 'none',
                  }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '18px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px', color: '#334155', fontWeight: 600 }}>
                    Recurrence Schedule
                  </label>
                  <select
                    value={newScheduleType}
                    onChange={(e) => setNewScheduleType(e.target.value as ContinuousOperationScheduleType)}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: '8px',
                      border: '1px solid #cbd5e1',
                      background: '#f8fafc',
                      color: '#0f172a',
                      fontSize: '13px',
                      boxSizing: 'border-box',
                    }}
                  >
                    <option value="interval_minutes">Every N Minutes</option>
                    <option value="interval_hours">Every N Hours</option>
                    <option value="daily">Daily</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px', color: '#334155', fontWeight: 600 }}>
                    Interval Value
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={newIntervalValue}
                    onChange={(e) => setNewIntervalValue(parseInt(e.target.value) || 1)}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: '8px',
                      border: '1px solid #cbd5e1',
                      background: '#f8fafc',
                      color: '#0f172a',
                      fontSize: '13px',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => setIsCreating(false)}
                  style={{
                    padding: '8px 16px',
                    background: '#f1f5f9',
                    border: '1px solid #cbd5e1',
                    borderRadius: '8px',
                    color: '#334155',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isActionLoading}
                  style={{
                    padding: '8px 18px',
                    background: '#774da9',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '8px',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: isActionLoading ? 'not-allowed' : 'pointer',
                  }}
                >
                  {isActionLoading ? 'Activating...' : 'Create & Activate'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Main Content Area */}
      {isLoading && operations.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '30px', color: '#64748b' }}>
          Loading recurring operational states...
        </div>
      ) : operations.length === 0 ? (
        <div
          style={{
            textAlign: 'center',
            padding: '36px 20px',
            border: '1px dashed #cbd5e1',
            borderRadius: '10px',
            background: '#f8fafc',
          }}
        >
          <h3 style={{ margin: '0 0 6px 0', color: '#24143C', fontSize: '16px', fontWeight: 700 }}>No Recurring Operations Configured</h3>
          <p style={{ margin: '0 0 16px 0', fontSize: '14px', color: '#64748b' }}>
            Configure autonomous recurring SEO cycles to periodically audit, investigate, and plan optimizations.
          </p>
          <button
            onClick={() => setIsCreating(true)}
            style={{
              background: '#774da9',
              color: '#fff',
              border: 'none',
              borderRadius: '8px',
              padding: '8px 18px',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Start Recurring Operation
          </button>
        </div>
      ) : (
        <div>
          {/* Operation Selector Tabs if multiple operations */}
          {operations.length > 1 && (
            <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', overflowX: 'auto' }}>
              {operations.map((op) => (
                <button
                  key={op.id}
                  onClick={() => setSelectedOp(op)}
                  style={{
                    padding: '6px 14px',
                    borderRadius: '8px',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    background: selectedOp?.id === op.id ? '#774da9' : '#f8fafc',
                    color: selectedOp?.id === op.id ? '#fff' : '#334155',
                    border: selectedOp?.id === op.id ? '1px solid #774da9' : '1px solid #cbd5e1',
                  }}
                >
                  Op #{op.id} ({op.status.toUpperCase()})
                </button>
              ))}
            </div>
          )}

          {/* Active Operation Card */}
          {selectedOp && (
            <div
              style={{
                background: '#f8fafc',
                borderRadius: '10px',
                border: '1px solid #e2e8f0',
                padding: '20px',
                marginBottom: '24px',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                  flexWrap: 'wrap',
                  gap: '12px',
                  marginBottom: '16px',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                        padding: '4px 10px',
                        borderRadius: '999px',
                        fontSize: '12px',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        background: `${getStatusColor(selectedOp.status)}22`,
                        color: getStatusColor(selectedOp.status),
                        border: `1px solid ${getStatusColor(selectedOp.status)}55`,
                      }}
                    >
                      <span
                        style={{
                          width: '6px',
                          height: '6px',
                          borderRadius: '50%',
                          background: getStatusColor(selectedOp.status),
                        }}
                      />
                      Status: {selectedOp.status}
                    </span>

                    <span style={{ fontSize: '13px', color: '#64748b' }}>
                      Schedule: {selectedOp.schedule_type_display} ({selectedOp.interval_value})
                    </span>
                  </div>

                  <div style={{ fontSize: '15px', fontWeight: 600, color: '#0f172a' }}>
                    Goal: <span style={{ fontWeight: 400, color: '#334155' }}>{selectedOp.goal}</span>
                  </div>
                </div>

                {/* Actions: Pause / Resume / Trigger */}
                <div style={{ display: 'flex', gap: '8px' }}>
                  {selectedOp.status === 'paused' ? (
                    <button
                      onClick={handleResume}
                      disabled={isActionLoading}
                      style={{
                        padding: '6px 14px',
                        borderRadius: '6px',
                        background: '#10b981',
                        color: '#fff',
                        border: 'none',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: isActionLoading ? 'not-allowed' : 'pointer',
                      }}
                    >
                      Resume
                    </button>
                  ) : (
                    <button
                      onClick={handlePause}
                      disabled={isActionLoading}
                      style={{
                        padding: '6px 14px',
                        borderRadius: '6px',
                        background: '#f59e0b',
                        color: '#fff',
                        border: 'none',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: isActionLoading ? 'not-allowed' : 'pointer',
                      }}
                    >
                      Pause
                    </button>
                  )}

                  <button
                    onClick={handleTriggerNow}
                    disabled={isActionLoading || selectedOp.status === 'running'}
                    style={{
                      padding: '6px 14px',
                      borderRadius: '6px',
                      background: selectedOp.status === 'running' ? '#64748b' : '#774da9',
                      color: '#fff',
                      border: 'none',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: selectedOp.status === 'running' || isActionLoading ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {selectedOp.status === 'running' ? 'Running...' : 'Run Now'}
                  </button>
                </div>
              </div>

              {/* Stats & Schedule Indicators */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                  gap: '12px',
                  background: '#ffffff',
                  padding: '14px',
                  borderRadius: '8px',
                  border: '1px solid #e2e8f0',
                }}
              >
                <div>
                  <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>Last Run</div>
                  <div style={{ fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
                    {formatRelativeTime(selectedOp.last_run_at)}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>Next Run</div>
                  <div style={{ fontSize: '14px', fontWeight: 700, color: selectedOp.status === 'paused' ? '#64748b' : '#774DA9' }}>
                    {selectedOp.status === 'paused' ? 'Paused' : formatRelativeTime(selectedOp.next_run_at)}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>Total Runs</div>
                  <div style={{ fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
                    {selectedOp.total_runs}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '11px', color: '#059669', textTransform: 'uppercase', fontWeight: 600 }}>Successful</div>
                  <div style={{ fontSize: '14px', fontWeight: 700, color: '#059669' }}>
                    {selectedOp.successful_runs}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '11px', color: '#dc2626', textTransform: 'uppercase', fontWeight: 600 }}>Failed</div>
                  <div style={{ fontSize: '14px', fontWeight: 700, color: '#dc2626' }}>
                    {selectedOp.failed_runs}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>Prevented Duplicates</div>
                  <div style={{ fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
                    {selectedOp.metrics?.duplicate_prevention_count || 0}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Recent Runs Section */}
          <div>
            <h3 style={{ margin: '0 0 12px 0', fontSize: '16px', fontWeight: 700, color: '#24143C' }}>
              Recent Operational Runs
            </h3>

            {runs.length === 0 ? (
              <div style={{ fontSize: '13px', color: '#64748b', padding: '12px 0' }}>
                No execution sessions recorded yet.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {runs.slice(0, 10).map((run) => (
                  <div
                    key={run.id}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '12px 16px',
                      borderRadius: '8px',
                      background: '#ffffff',
                      border: '1px solid #e2e8f0',
                      flexWrap: 'wrap',
                      gap: '8px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <span style={{ fontWeight: 700, fontSize: '13px', color: '#0f172a' }}>
                        Run #{run.id}
                      </span>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: 600,
                          padding: '2px 8px',
                          borderRadius: '4px',
                          textTransform: 'uppercase',
                          background: `${getStatusColor(run.status)}22`,
                          color: getStatusColor(run.status),
                        }}
                      >
                        {run.status.replace('_', ' ')}
                      </span>
                      <span style={{ fontSize: '12px', color: '#64748b' }}>
                        Started: {new Date(run.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                      {run.completed_at && (
                        <span style={{ fontSize: '12px', color: '#64748b' }}>
                          Duration: {Math.max(1, Math.round((new Date(run.completed_at).getTime() - new Date(run.created_at).getTime()) / 1000))}s
                        </span>
                      )}

                      {run.status === 'failed' && (
                        <span
                          style={{
                            fontSize: '11px',
                            color: '#dc2626',
                            maxWidth: '300px',
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}
                          title={run.summary}
                        >
                          Reason: {run.summary || 'Execution error'}
                        </span>
                      )}

                      {run.status === 'waiting_for_approval' && (
                        <span style={{ fontSize: '11px', color: '#d97706', fontWeight: 600 }}>
                          Action pending human approval
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
