import React, { useState, useEffect } from 'react';
import {
  getPlatformHealth,
  getPlatformMetrics,
  getCircuitBreakers,
  getPlatformAlerts,
  resolvePlatformAlert,
  operateCircuitBreaker,
  executeOperatorAction,
  inspectPlatformRun,
} from '../api/platform';
import type {
  PlatformHealthResponse,
  PlatformMetricsResponse,
  CircuitBreakerItem,
  PlatformAlertItem,
  RunInspectionPayload,
} from '../api/platform';
import type { Project } from '../types/project';


interface ProductionOperationsPanelProps {
  project: Project | null;
}

export const ProductionOperationsPanel: React.FC<ProductionOperationsPanelProps> = ({ project }) => {
  const [health, setHealth] = useState<PlatformHealthResponse | null>(null);
  const [metrics, setMetrics] = useState<PlatformMetricsResponse | null>(null);
  const [breakers, setBreakers] = useState<CircuitBreakerItem[]>([]);
  const [alerts, setAlerts] = useState<PlatformAlertItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  // Run Inspector State
  const [inspectRunId, setInspectRunId] = useState<string>('');
  const [inspectionData, setInspectionData] = useState<RunInspectionPayload | null>(null);
  const [isInspecting, setIsInspecting] = useState(false);

  // Operator Action State
  const [operatorRationale, setOperatorRationale] = useState('');

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [h, m, b, a] = await Promise.all([
        getPlatformHealth(),
        getPlatformMetrics(project?.id),
        getCircuitBreakers(),
        getPlatformAlerts(false),
      ]);
      setHealth(h);
      setMetrics(m);
      setBreakers(b);
      setAlerts(a);
    } catch (err: any) {
      console.error('Failed to load platform data:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 15000); // 15s auto-refresh
    return () => clearInterval(interval);
  }, [project?.id]);

  const handleBreakerAction = async (serviceName: string, action: 'reset' | 'trip') => {
    try {
      await operateCircuitBreaker(serviceName, action, operatorRationale || 'Manual dashboard intervention');
      setActionMessage(`Circuit breaker for '${serviceName}' successfully ${action === 'reset' ? 'reset' : 'tripped'}.`);
      loadData();
    } catch (err: any) {
      setActionMessage(`Failed to ${action} breaker: ${err?.response?.data?.detail || err.message}`);
    }
  };

  const handleInspectRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inspectRunId) return;
    setIsInspecting(true);
    try {
      const data = await inspectPlatformRun(Number(inspectRunId));
      setInspectionData(data);
    } catch (err: any) {
      setActionMessage(`Failed to inspect run #${inspectRunId}: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setIsInspecting(false);
    }
  };

  const handleResolveAlert = async (alertId: number) => {
    try {
      await resolvePlatformAlert(alertId);
      setAlerts((prev) => prev.filter((a) => a.id !== alertId));
      setActionMessage(`Alert #${alertId} marked as resolved.`);
    } catch (err: any) {
      setActionMessage(`Failed to resolve alert: ${err?.message}`);
    }
  };

  const handleOperatorAction = async (action: 'pause_continuous_ops' | 'resume_continuous_ops' | 'compact_data') => {
    try {
      const res = await executeOperatorAction({
        action,
        project_id: project?.id,
        rationale: operatorRationale || 'Operator dashboard action'
      });
      setActionMessage(`Action '${action}' completed: ${res?.detail || 'Success'}`);
      loadData();
    } catch (err: any) {
      setActionMessage(`Operator action failed: ${err?.response?.data?.detail || err.message}`);
    }
  };

  return (
    <div style={{ padding: '24px', background: '#ffffff', color: '#0f172a', borderRadius: '12px', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px 0 rgba(36, 20, 60, 0.06)', marginBottom: '24px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1.4rem', fontWeight: 800, color: '#24143C', display: 'flex', alignItems: 'center', gap: '8px' }}>
            System Platform Health
            <span style={{
              fontSize: '0.75rem',
              fontWeight: 700,
              padding: '2px 8px',
              borderRadius: '9999px',
              background: health?.status === 'healthy' ? '#ecfdf5' : '#fef2f2',
              color: health?.status === 'healthy' ? '#065f46' : '#991b1b',
              border: `1px solid ${health?.status === 'healthy' ? '#a7f3d0' : '#fecaca'}`,
            }}>
              {health?.status ? health.status.toUpperCase() : 'CHECKING'}
            </span>
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: '0.85rem', color: '#64748b' }}>
            Observability, operational circuit breakers, and platform resource governance.
          </p>
        </div>
        <button
          onClick={loadData}
          disabled={isLoading}
          style={{
            background: '#ffffff',
            color: '#334155',
            border: '1px solid #cbd5e1',
            padding: '6px 14px',
            borderRadius: '8px',
            cursor: 'pointer',
            fontSize: '0.85rem',
            fontWeight: 600,
          }}
        >
          {isLoading ? 'Refreshing...' : '↻ Refresh'}
        </button>
      </div>

      {actionMessage && (
        <div style={{ padding: '10px 14px', background: '#f6f2fb', borderLeft: '4px solid #774da9', border: '1px solid #dac8ee', borderRadius: '8px', marginBottom: '16px', fontSize: '0.85rem', color: '#593285', fontWeight: 500 }}>
          {actionMessage}
        </div>
      )}

      {/* System Health Component Cards */}
      <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#24143C', marginBottom: '10px' }}>Core Subsystems</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px', marginBottom: '20px' }}>
        {health?.components && [
          { name: 'Database', status: health.components.database.status, detail: `${health.components.database.latency_ms || 0}ms` },
          { name: 'Redis Broker', status: health.components.redis.status, detail: health.components.redis.note || `${health.components.redis.latency_ms || 0}ms` },
          { name: 'Celery Workers', status: health.components.celery.status, detail: health.components.celery.mode || 'active' },
          { name: 'Scheduler Beat', status: health.components.scheduler.status, detail: `${health.components.scheduler.registered_jobs || 0} jobs` },
          { name: 'Agent Runtime', status: health.components.agent_runtime.status, detail: `${health.components.agent_runtime.registered_tools || 0} tools` },
          { name: 'Subsystems', status: health.components.external_subsystem.status, detail: `${health.components.external_subsystem.tripped_breakers.length} tripped` },
        ].map((item, idx) => (
          <div key={idx} style={{ background: '#f8fafc', padding: '12px 14px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748b' }}>{item.name}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}>
              <span style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: item.status === 'healthy' ? '#10b981' : item.status === 'degraded' ? '#f59e0b' : '#ef4444'
              }} />
              <span style={{ fontWeight: 700, fontSize: '0.9rem', color: '#0f172a' }}>
                {item.status.toUpperCase()}
              </span>
            </div>
            <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '2px' }}>{item.detail}</div>
          </div>
        ))}
      </div>

      {/* Runtime Telemetry Metrics */}
      <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#24143C', marginBottom: '10px' }}>Platform Runtime Metrics</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '10px', marginBottom: '24px' }}>
        <div style={{ background: '#f8fafc', padding: '12px 10px', borderRadius: '8px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
          <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#774DA9' }}>{metrics?.active_runs || 0}</div>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748b' }}>Active Runs</div>
        </div>
        <div style={{ background: '#f8fafc', padding: '12px 10px', borderRadius: '8px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
          <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#0f172a' }}>{metrics?.queued_tasks || 0}</div>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748b' }}>Queued Tasks</div>
        </div>
        <div style={{ background: '#f8fafc', padding: '12px 10px', borderRadius: '8px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
          <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#059669' }}>{metrics?.success_rate_pct || 100}%</div>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748b' }}>Success Rate</div>
        </div>
        <div style={{ background: '#f8fafc', padding: '12px 10px', borderRadius: '8px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
          <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#774DA9' }}>{metrics?.recovered_runs || 0}</div>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748b' }}>Recovered Runs</div>
        </div>
        <div style={{ background: '#f8fafc', padding: '12px 10px', borderRadius: '8px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
          <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#d97706' }}>{metrics?.total_tool_calls || 0}</div>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748b' }}>Tool Calls</div>
        </div>
        <div style={{ background: '#f8fafc', padding: '12px 10px', borderRadius: '8px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
          <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#64748b' }}>{metrics?.average_run_duration_sec || 0}s</div>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748b' }}>Avg Duration</div>
        </div>
      </div>

      {/* Circuit Breakers */}
      <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#24143C', marginBottom: '10px' }}>External Dependency Circuit Breakers</h3>
      <div style={{ background: '#ffffff', borderRadius: '8px', overflow: 'hidden', marginBottom: '24px', border: '1px solid #e2e8f0' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
          <thead>
            <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#334155' }}>
              <th style={{ padding: '10px 14px', fontWeight: 700 }}>Service</th>
              <th style={{ padding: '10px 14px', fontWeight: 700 }}>Status</th>
              <th style={{ padding: '10px 14px', fontWeight: 700 }}>Failures</th>
              <th style={{ padding: '10px 14px', fontWeight: 700 }}>Lifetime Trips</th>
              <th style={{ padding: '10px 14px', fontWeight: 700 }}>Diagnostics</th>
              <th style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 700 }}>Controls</th>
            </tr>
          </thead>
          <tbody>
            {breakers.map((b) => (
              <tr key={b.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={{ padding: '10px 14px', fontWeight: 700, color: '#0f172a' }}>{b.service_name.toUpperCase()}</td>
                <td style={{ padding: '10px 14px' }}>
                  <span style={{
                    padding: '2px 8px',
                    borderRadius: '4px',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    background: b.state === 'closed' ? '#ecfdf5' : b.state === 'half_open' ? '#fffbeb' : '#fef2f2',
                    color: b.state === 'closed' ? '#065f46' : b.state === 'half_open' ? '#92400e' : '#991b1b',
                    border: `1px solid ${b.state === 'closed' ? '#a7f3d0' : b.state === 'half_open' ? '#fde68a' : '#fecaca'}`,
                  }}>
                    {b.state.toUpperCase()}
                  </span>
                </td>
                <td style={{ padding: '10px 14px', color: '#334155' }}>{b.failure_count} / {b.failure_threshold}</td>
                <td style={{ padding: '10px 14px', color: '#334155' }}>{b.trip_count}</td>
                <td style={{ padding: '10px 14px', color: '#64748b', maxWidth: '240px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {b.opened_reason || 'Operating nominally'}
                </td>
                <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                  {b.state !== 'closed' ? (
                    <button
                      onClick={() => handleBreakerAction(b.service_name, 'reset')}
                      style={{ background: '#774da9', color: '#fff', border: 'none', padding: '4px 10px', borderRadius: '6px', cursor: 'pointer', fontSize: '0.75rem', fontWeight: 600 }}
                    >
                      Reset
                    </button>
                  ) : (
                    <button
                      onClick={() => handleBreakerAction(b.service_name, 'trip')}
                      style={{ background: '#dc2626', color: '#fff', border: 'none', padding: '4px 10px', borderRadius: '6px', cursor: 'pointer', fontSize: '0.75rem', fontWeight: 600 }}
                    >
                      Trip Breaker
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Operator Controls */}
      <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#24143C', marginBottom: '10px' }}>Platform Controls & Governance</h3>
      <div style={{ background: '#f8fafc', padding: '16px', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: '24px' }}>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ fontSize: '0.8rem', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '4px' }}>
            Administrative Rationale (Required for Audit Logging):
          </label>
          <input
            type="text"
            value={operatorRationale}
            onChange={(e) => setOperatorRationale(e.target.value)}
            placeholder="Reason for administrative intervention..."
            style={{ width: '100%', padding: '8px 12px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '6px', color: '#0f172a', fontSize: '0.85rem', boxSizing: 'border-box' }}
          />
        </div>
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          <button
            onClick={() => handleOperatorAction('pause_continuous_ops')}
            style={{ background: '#f59e0b', color: '#ffffff', border: 'none', padding: '8px 14px', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600 }}
          >
            Pause Recurring Ops
          </button>
          <button
            onClick={() => handleOperatorAction('resume_continuous_ops')}
            style={{ background: '#774da9', color: '#ffffff', border: 'none', padding: '8px 14px', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600 }}
          >
            Resume Recurring Ops
          </button>
          <button
            onClick={() => handleOperatorAction('compact_data')}
            style={{ background: '#ffffff', color: '#334155', border: '1px solid #cbd5e1', padding: '8px 14px', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600 }}
          >
            Compact Cache Data
          </button>
        </div>
      </div>

      {/* Run Inspection Drilldown */}
      <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#24143C', marginBottom: '10px' }}>Run Inspector & Diagnostics</h3>
      <div style={{ background: '#f8fafc', padding: '16px', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: '24px' }}>
        <form onSubmit={handleInspectRun} style={{ display: 'flex', gap: '10px', marginBottom: '16px' }}>
          <input
            type="number"
            value={inspectRunId}
            onChange={(e) => setInspectRunId(e.target.value)}
            placeholder="Enter AgentRun ID to inspect..."
            style={{ flex: 1, padding: '8px 12px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '6px', color: '#0f172a', fontSize: '0.85rem' }}
          />
          <button
            type="submit"
            disabled={isInspecting || !inspectRunId}
            style={{ background: '#774da9', color: '#fff', border: 'none', padding: '8px 18px', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600 }}
          >
            {isInspecting ? 'Inspecting...' : 'Inspect Run'}
          </button>
        </form>

        {inspectionData && (
          <div style={{ background: '#ffffff', padding: '16px', borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '0.85rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #e2e8f0', paddingBottom: '8px', marginBottom: '12px' }}>
              <div>
                <span style={{ fontWeight: 700, color: '#24143C' }}>Run #{inspectionData.run.id}</span> — {inspectionData.run.goal}
                <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '2px' }}>
                  Correlation ID: <code>{inspectionData.run.correlation_id || 'N/A'}</code> | Status: {inspectionData.run.status} | Worker: {inspectionData.run.worker_id || 'unassigned'}
                </div>
              </div>
              <span style={{ color: '#059669', fontWeight: 700 }}>Steps: {inspectionData.steps.length} | Ext Ops: {inspectionData.external_operations.length}</span>
            </div>

            {/* Steps & Tool hierarchy */}
            <h4 style={{ fontSize: '0.9rem', color: '#24143C', fontWeight: 700, margin: '8px 0' }}>Step Hierarchy:</h4>
            {inspectionData.steps.map((s) => (
              <div key={s.step_number} style={{ marginBottom: '10px', paddingLeft: '12px', borderLeft: '3px solid #774da9' }}>
                <div style={{ fontWeight: 600, color: '#0f172a' }}>Step #{s.step_number} [{s.action_type}] — {s.status}</div>
                <div style={{ color: '#64748b', fontSize: '0.8rem', fontStyle: 'italic', margin: '2px 0' }}>{s.thought}</div>
                {s.tool_calls.map((tc) => (
                  <div key={tc.id} style={{ marginLeft: '12px', fontSize: '0.75rem', color: tc.error ? '#dc2626' : '#059669' }}>
                    ↳ Tool: <code>{tc.tool_name}</code> ({tc.duration_ms}ms) {tc.error && `[ERROR: ${tc.error}]`}
                  </div>
                ))}
              </div>
            ))}

            {inspectionData.external_operations.length > 0 && (
              <>
                <h4 style={{ fontSize: '0.9rem', color: '#24143C', fontWeight: 700, margin: '12px 0 6px' }}>External Operations:</h4>
                {inspectionData.external_operations.map((op) => (
                  <div key={op.id} style={{ marginLeft: '12px', fontSize: '0.75rem', color: '#334155' }}>
                    ↳ Op #{op.id}: <b>{op.operation_type}</b> (Status: {op.status}, Verified: {op.verification_status})
                  </div>
                ))}
              </>
            )}
          </div>
        )}
      </div>

      {/* Active Alerts */}
      {alerts.length > 0 && (
        <>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#dc2626', marginBottom: '10px' }}>Active Platform Alerts ({alerts.length})</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '16px' }}>
            {alerts.map((al) => (
              <div key={al.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#fef2f2', border: '1px solid #fecaca', padding: '10px 14px', borderRadius: '8px' }}>
                <div>
                  <span style={{ fontWeight: 700, color: '#991b1b' }}>[{al.severity.toUpperCase()}] {al.alert_type}</span>: <span style={{ color: '#0f172a' }}>{al.message}</span>
                  <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{new Date(al.created_at).toLocaleString()}</div>
                </div>
                <button
                  onClick={() => handleResolveAlert(al.id)}
                  style={{ background: '#ffffff', color: '#334155', border: '1px solid #cbd5e1', padding: '4px 10px', borderRadius: '6px', cursor: 'pointer', fontSize: '0.75rem', fontWeight: 600 }}
                >
                  Acknowledge
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
};
