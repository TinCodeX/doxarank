import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { Project } from '../types/project';
import type {
  MonitoringState,
  MonitoringSnapshot,
  MonitoringMetrics,
  MonitorType,
  MonitorStatus,
} from '../types/seoMonitoring';
import {
  getMonitoringStates,
  getMonitoringSnapshots,
  getMonitoringChanges,
  getMonitoringMetrics,
  triggerMonitoringCycle,
} from '../api/seoMonitoring';

interface MonitoringActivityPanelProps {
  project: Project;
}

export const MonitoringActivityPanel: React.FC<MonitoringActivityPanelProps> = ({ project }) => {
  const [states, setStates] = useState<MonitoringState[]>([]);
  const [snapshots, setSnapshots] = useState<MonitoringSnapshot[]>([]);
  const [changes, setChanges] = useState<MonitoringSnapshot[]>([]);
  const [metrics, setMetrics] = useState<MonitoringMetrics | null>(null);
  const [selectedState, setSelectedState] = useState<MonitoringState | null>(null);
  const [selectedSnapshot, setSelectedSnapshot] = useState<MonitoringSnapshot | null>(null);

  const [activeTab, setActiveTab] = useState<'states' | 'changes' | 'snapshots'>('states');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isTriggering, setIsTriggering] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Filters
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');

  const pollIntervalRef = useRef<number | null>(null);

  const loadData = useCallback(async () => {
    try {
      setIsLoading(true);
      setErrorMessage(null);
      const [stateList, changeList, snapshotList, metricData] = await Promise.all([
        getMonitoringStates(project.id, {
          monitor_type: typeFilter || undefined,
          status: statusFilter || undefined,
        }),
        getMonitoringChanges(project.id),
        getMonitoringSnapshots(project.id, {
          monitor_type: typeFilter || undefined,
        }),
        getMonitoringMetrics(project.id),
      ]);
      setStates(stateList);
      setChanges(changeList);
      setSnapshots(snapshotList);
      setMetrics(metricData);
    } catch (err: any) {
      console.error('Error loading monitoring activity:', err);
      setErrorMessage(err.message || 'Failed to load autonomous monitoring activity.');
    } finally {
      setIsLoading(false);
    }
  }, [project.id, typeFilter, statusFilter]);

  useEffect(() => {
    loadData();
    pollIntervalRef.current = window.setInterval(loadData, 10000);
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [loadData]);

  const handleRunMonitoring = async () => {
    try {
      setIsTriggering(true);
      setErrorMessage(null);
      setSuccessMessage(null);
      const result = await triggerMonitoringCycle(project.id);
      const res = result.results;
      setSuccessMessage(
        `Monitoring cycle executed successfully! Snapshots: ${res.snapshots_created}, Changes Detected: ${res.changes_detected}, Ignored: ${res.changes_ignored}, Events: ${res.events_generated}, Recoveries: ${res.recoveries_detected}, Duplicates Prevented: ${res.duplicates_prevented}`
      );
      await loadData();
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to run monitoring cycle.');
    } finally {
      setIsTriggering(false);
    }
  };

  const getStatusBadge = (status: MonitorStatus) => {
    switch (status) {
      case 'healthy':
        return <span className="badge badge-healthy">Healthy</span>;
      case 'warning':
        return <span className="badge badge-warning">Warning</span>;
      case 'anomaly':
        return <span className="badge badge-anomaly">Anomaly</span>;
      case 'recovered':
        return <span className="badge badge-recovered">Recovered</span>;
      default:
        return <span className="badge badge-neutral">{status}</span>;
    }
  };

  const getMonitorTypeLabel = (type: MonitorType) => {
    switch (type) {
      case 'ranking':
        return 'Keyword Ranking';
      case 'page_status':
        return 'Page Status (HTTP)';
      case 'seo_audit':
        return 'Site Audit Score';
      case 'keyword_visibility':
        return 'Visibility Index';
      default:
        return type;
    }
  };

  return (
    <div className="monitoring-activity-panel" id="seo-autonomous-monitoring-section">
      {/* Header */}
      <div className="panel-header">
        <div>
          <h2 className="panel-title">
            <span className="pulse-dot-emerald" />
            Autonomous SEO Monitoring
          </h2>
          <p className="panel-subtitle">
            Continuous background health inspection, change detection, and proactive alerts.
          </p>
        </div>
        <div className="header-actions">
          <button
            className="btn btn-secondary"
            onClick={() => loadData()}
            disabled={isLoading}
          >
            {isLoading ? 'Refreshing...' : '↻ Refresh'}
          </button>
          <button
            className="btn btn-emerald"
            onClick={handleRunMonitoring}
            disabled={isTriggering}
          >
            {isTriggering ? 'Running Cycle...' : 'Run Monitoring Now'}
          </button>
        </div>
      </div>

      {/* Messages */}
      {errorMessage && <div className="alert alert-danger">{errorMessage}</div>}
      {successMessage && <div className="alert alert-success">{successMessage}</div>}

      {/* Metrics Row */}
      {metrics && (
        <div className="metrics-strip">
          <div className="metric-card">
            <span className="metric-label">Monitored Targets</span>
            <span className="metric-value">{metrics.monitored_targets_count}</span>
            <span className="metric-sub">{states.length} active states</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Active Anomalies</span>
            <span className={`metric-value ${metrics.active_anomalies_count > 0 ? 'text-danger' : 'text-success'}`}>
              {metrics.active_anomalies_count}
            </span>
            <span className="metric-sub">Pending resolution</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Recoveries Detected</span>
            <span className="metric-value text-emerald">{metrics.recoveries_detected_count}</span>
            <span className="metric-sub">Self-healed / fixed</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Snapshots Captured</span>
            <span className="metric-value text-blue">{metrics.snapshots_captured_count}</span>
            <span className="metric-sub">{metrics.meaningful_changes_detected} changes detected</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Ignored Changes</span>
            <span className="metric-value text-amber">{metrics.insignificant_changes_ignored}</span>
            <span className="metric-sub">Sub-threshold noise</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Deduplicated Anomalies</span>
            <span className="metric-value text-purple">{metrics.duplicate_detections_prevented}</span>
            <span className="metric-sub">Suppressed repeat events</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Events Generated</span>
            <span className="metric-value text-cyan">{metrics.events_generated_count}</span>
            <span className="metric-sub">{metrics.monitoring_event_generation_rate}% dispatch rate</span>
          </div>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="tab-bar">
        <button
          className={`tab-btn ${activeTab === 'states' ? 'active' : ''}`}
          onClick={() => setActiveTab('states')}
        >
          Active Monitored Targets ({states.length})
        </button>
        <button
          className={`tab-btn ${activeTab === 'changes' ? 'active' : ''}`}
          onClick={() => setActiveTab('changes')}
        >
          Detected Changes & Recoveries ({changes.length})
        </button>
        <button
          className={`tab-btn ${activeTab === 'snapshots' ? 'active' : ''}`}
          onClick={() => setActiveTab('snapshots')}
        >
          Observation History ({snapshots.length})
        </button>
      </div>

      {/* Filter Toolbar */}
      <div className="filter-toolbar">
        <div className="filter-group">
          <label htmlFor="filter-mon-type">Monitor Type:</label>
          <select
            id="filter-mon-type"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="">All Monitors</option>
            <option value="ranking">Keyword Ranking</option>
            <option value="page_status">Page Status (HTTP)</option>
            <option value="seo_audit">Site Audit</option>
            <option value="keyword_visibility">Keyword Visibility</option>
          </select>
        </div>
        {activeTab === 'states' && (
          <div className="filter-group">
            <label htmlFor="filter-mon-status">Status:</label>
            <select
              id="filter-mon-status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">All Statuses</option>
              <option value="healthy">Healthy</option>
              <option value="warning">Warning</option>
              <option value="anomaly">Anomaly</option>
              <option value="recovered">Recovered</option>
            </select>
          </div>
        )}
      </div>

      {/* Tab 1: Monitored States Table */}
      {activeTab === 'states' && (
        <div className="table-responsive">
          <table className="monitoring-table">
            <thead>
              <tr>
                <th>Monitor Type</th>
                <th>Target / Metric Key</th>
                <th>Status</th>
                <th>Current Value</th>
                <th>Baseline</th>
                <th>Consecutive Anomalies</th>
                <th>Last Checked</th>
                <th>Linked Event</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {states.length === 0 ? (
                <tr>
                  <td colSpan={9} className="text-center py-6 text-muted">
                    No monitored states found for this project. Click "Run Monitoring Now" to establish baselines.
                  </td>
                </tr>
              ) : (
                states.map((st) => (
                  <tr key={st.id} className={selectedState?.id === st.id ? 'row-selected' : ''}>
                    <td>
                      <span className="badge-monitor-type">{getMonitorTypeLabel(st.monitor_type)}</span>
                    </td>
                    <td className="font-mono text-sm">{st.metric_key}</td>
                    <td>{getStatusBadge(st.status)}</td>
                    <td className="font-mono text-xs">
                      {st.current_value.position !== undefined
                        ? `Pos #${st.current_value.position}`
                        : st.current_value.status_code !== undefined
                        ? `HTTP ${st.current_value.status_code}`
                        : st.current_value.audit_score !== undefined
                        ? `Score ${st.current_value.audit_score}`
                        : st.current_value.average_position !== undefined
                        ? `Avg Pos ${st.current_value.average_position}`
                        : JSON.stringify(st.current_value).slice(0, 24)}
                    </td>
                    <td className="font-mono text-xs text-muted">
                      {st.baseline_value.position !== undefined
                        ? `Pos #${st.baseline_value.position}`
                        : st.baseline_value.status_code !== undefined
                        ? `HTTP ${st.baseline_value.status_code}`
                        : st.baseline_value.audit_score !== undefined
                        ? `Score ${st.baseline_value.audit_score}`
                        : st.baseline_value.average_position !== undefined
                        ? `Avg Pos ${st.baseline_value.average_position}`
                        : JSON.stringify(st.baseline_value).slice(0, 24)}
                    </td>
                    <td>
                      <span
                        className={`badge ${
                          st.consecutive_anomalies > 0 ? 'badge-anomaly' : 'badge-neutral'
                        }`}
                      >
                        {st.consecutive_anomalies}
                      </span>
                    </td>
                    <td className="text-xs text-muted">
                      {new Date(st.last_checked_at).toLocaleTimeString()}
                    </td>
                    <td>
                      {st.last_event ? (
                        <span className="badge badge-cyan text-xs">
                          Event #{st.last_event} ({st.last_event_type})
                        </span>
                      ) : (
                        <span className="text-muted text-xs">—</span>
                      )}
                    </td>
                    <td>
                      <button
                        className="btn-details text-xs"
                        onClick={() => setSelectedState(st)}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab 2: Detected Changes Table */}
      {activeTab === 'changes' && (
        <div className="table-responsive">
          <table className="monitoring-table">
            <thead>
              <tr>
                <th>Monitor Type</th>
                <th>Target / Metric Key</th>
                <th>Classification</th>
                <th>Observed Value</th>
                <th>Baseline</th>
                <th>Delta</th>
                <th>Observed At</th>
              </tr>
            </thead>
            <tbody>
              {changes.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-6 text-muted">
                    No anomalies or recoveries detected yet. Everything is within healthy thresholds.
                  </td>
                </tr>
              ) : (
                changes.map((ch) => (
                  <tr
                    key={ch.id}
                    className={selectedSnapshot?.id === ch.id ? 'row-selected' : ''}
                    onClick={() => setSelectedSnapshot(selectedSnapshot?.id === ch.id ? null : ch)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td>
                      <span className="badge-monitor-type">{getMonitorTypeLabel(ch.monitor_type)}</span>
                    </td>
                    <td className="font-mono text-sm">{ch.metric_key}</td>
                    <td>
                      {ch.is_recovery ? (
                        <span className="badge badge-recovered">Recovery Detected</span>
                      ) : ch.is_anomaly ? (
                        <span className="badge badge-anomaly">Anomaly Detected</span>
                      ) : (
                        getStatusBadge(ch.status)
                      )}
                    </td>
                    <td className="font-mono text-xs">{JSON.stringify(ch.value)}</td>
                    <td className="font-mono text-xs text-muted">{JSON.stringify(ch.baseline_value)}</td>
                    <td className="font-mono text-xs text-amber">{JSON.stringify(ch.delta)}</td>
                    <td className="text-xs text-muted">
                      {new Date(ch.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab 3: Snapshots Table */}
      {activeTab === 'snapshots' && (
        <div className="table-responsive">
          <table className="monitoring-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Monitor Type</th>
                <th>Target Identifier</th>
                <th>Status</th>
                <th>Anomaly</th>
                <th>Recovery</th>
                <th>Recorded At</th>
              </tr>
            </thead>
            <tbody>
              {snapshots.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-6 text-muted">
                    No snapshots captured yet.
                  </td>
                </tr>
              ) : (
                snapshots.map((sn) => (
                  <tr key={sn.id}>
                    <td className="text-muted text-xs">#{sn.id}</td>
                    <td>
                      <span className="badge-monitor-type">{getMonitorTypeLabel(sn.monitor_type)}</span>
                    </td>
                    <td className="font-mono text-xs">{sn.metric_key}</td>
                    <td>{getStatusBadge(sn.status)}</td>
                    <td>
                      {sn.is_anomaly ? (
                        <span className="text-danger font-semibold">Yes</span>
                      ) : (
                        <span className="text-muted">No</span>
                      )}
                    </td>
                    <td>
                      {sn.is_recovery ? (
                        <span className="text-emerald font-semibold">Yes</span>
                      ) : (
                        <span className="text-muted">No</span>
                      )}
                    </td>
                    <td className="text-xs text-muted">
                      {new Date(sn.created_at).toLocaleTimeString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal / State Inspection Drawer */}
      {selectedState && (
        <div className="modal-backdrop" onClick={() => setSelectedState(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">
                Monitor Details: {selectedState.metric_key}
              </h3>
              <button className="btn-close" onClick={() => setSelectedState(null)}>
                ×
              </button>
            </div>
            <div className="modal-body">
              <div className="detail-grid">
                <div>
                  <span className="detail-label">Monitor Type</span>
                  <p>{getMonitorTypeLabel(selectedState.monitor_type)}</p>
                </div>
                <div>
                  <span className="detail-label">Current Status</span>
                  <p>{getStatusBadge(selectedState.status)}</p>
                </div>
                <div>
                  <span className="detail-label">Consecutive Anomalies</span>
                  <p>{selectedState.consecutive_anomalies}</p>
                </div>
                <div>
                  <span className="detail-label">Last Checked</span>
                  <p>{new Date(selectedState.last_checked_at).toLocaleString()}</p>
                </div>
                <div>
                  <span className="detail-label">Last Meaningful Change</span>
                  <p>{new Date(selectedState.last_changed_at).toLocaleString()}</p>
                </div>
                <div>
                  <span className="detail-label">Last Event Dispatched</span>
                  <p>
                    {selectedState.last_event
                      ? `Event #${selectedState.last_event} (${selectedState.last_event_type} - ${selectedState.last_event_status})`
                      : 'None'}
                  </p>
                </div>
              </div>

              <div className="json-box">
                <span className="detail-label">Current Observed Value</span>
                <pre>{JSON.stringify(selectedState.current_value, null, 2)}</pre>
              </div>
              <div className="json-box">
                <span className="detail-label">Baseline Reference Value</span>
                <pre>{JSON.stringify(selectedState.baseline_value, null, 2)}</pre>
              </div>
              <div className="json-box">
                <span className="detail-label">Configured Thresholds / Metadata</span>
                <pre>{JSON.stringify(selectedState.metadata, null, 2)}</pre>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Inline Styles */}
      <style>{`
        .monitoring-activity-panel {
          margin-top: 1.5rem;
          background: #ffffff;
          border: 1px solid #e2e8f0;
          border-radius: 12px;
          padding: 1.5rem;
          color: #0f172a;
          box-shadow: 0 1px 3px 0 rgba(36, 20, 60, 0.06);
        }
        .panel-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1.25rem;
          flex-wrap: wrap;
          gap: 1rem;
        }
        .panel-title {
          font-size: 1.25rem;
          font-weight: 800;
          display: flex;
          align-items: center;
          gap: 0.5rem;
          margin: 0;
          color: #24143C;
        }
        .pulse-dot-emerald {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #10b981;
          box-shadow: 0 0 8px rgba(16, 185, 129, 0.6);
          display: inline-block;
        }
        .panel-subtitle {
          font-size: 0.85rem;
          color: #64748b;
          margin-top: 0.25rem;
          margin-bottom: 0;
        }
        .header-actions {
          display: flex;
          gap: 0.75rem;
        }
        .metrics-strip {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
          gap: 0.75rem;
          margin-bottom: 1.25rem;
        }
        .metric-card {
          background: #f8fafc;
          border: 1px solid #e2e8f0;
          border-radius: 8px;
          padding: 0.75rem 1rem;
          display: flex;
          flex-direction: column;
        }
        .metric-label {
          font-size: 0.75rem;
          color: #64748b;
          text-transform: uppercase;
          font-weight: 600;
          letter-spacing: 0.05em;
        }
        .metric-value {
          font-size: 1.4rem;
          font-weight: 800;
          color: #0f172a;
          margin: 0.2rem 0;
        }
        .metric-sub {
          font-size: 0.75rem;
          color: #64748b;
        }
        .tab-bar {
          display: flex;
          gap: 0.5rem;
          border-bottom: 1px solid #e2e8f0;
          margin-bottom: 1rem;
        }
        .tab-btn {
          background: transparent;
          border: none;
          color: #64748b;
          font-size: 0.875rem;
          font-weight: 600;
          padding: 0.5rem 1rem;
          cursor: pointer;
          border-bottom: 2px solid transparent;
          transition: all 0.2s;
        }
        .tab-btn:hover {
          color: #24143C;
        }
        .tab-btn.active {
          color: #774DA9;
          border-bottom-color: #774DA9;
        }
        .filter-toolbar {
          display: flex;
          gap: 1rem;
          margin-bottom: 1rem;
          align-items: center;
          flex-wrap: wrap;
          background: #f8fafc;
          padding: 0.75rem 1rem;
          border-radius: 8px;
          border: 1px solid #e2e8f0;
        }
        .filter-group {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.85rem;
          color: #334155;
          font-weight: 500;
        }
        .filter-group select {
          background: #ffffff;
          border: 1px solid #cbd5e1;
          color: #0f172a;
          border-radius: 6px;
          padding: 0.35rem 0.6rem;
          font-size: 0.85rem;
          outline: none;
        }
        .table-responsive {
          overflow-x: auto;
        }
        .monitoring-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 0.85rem;
        }
        .monitoring-table th {
          text-align: left;
          padding: 0.6rem 0.75rem;
          background: #f8fafc;
          color: #334155;
          font-weight: 700;
          border-bottom: 1px solid #e2e8f0;
        }
        .monitoring-table td {
          padding: 0.6rem 0.75rem;
          border-bottom: 1px solid #f1f5f9;
          color: #0f172a;
        }
        .monitoring-table tr:hover {
          background: #f8fafc;
        }
        .badge {
          display: inline-block;
          padding: 0.2rem 0.5rem;
          border-radius: 4px;
          font-size: 0.75rem;
          font-weight: 700;
        }
        .badge-healthy {
          background: #ecfdf5;
          color: #065f46;
          border: 1px solid #a7f3d0;
        }
        .badge-warning {
          background: #fffbeb;
          color: #92400e;
          border: 1px solid #fde68a;
        }
        .badge-anomaly {
          background: #fef2f2;
          color: #991b1b;
          border: 1px solid #fecaca;
        }
        .badge-recovered {
          background: #ecfdf5;
          color: #059669;
          border: 1px solid #a7f3d0;
        }
        .badge-monitor-type {
          background: #f6f2fb;
          color: #774DA9;
          border: 1px solid #dac8ee;
          padding: 0.2rem 0.5rem;
          border-radius: 4px;
          font-size: 0.75rem;
          font-weight: 600;
        }
        .badge-neutral {
          background: #f1f5f9;
          color: #475569;
          border: 1px solid #e2e8f0;
        }
        .btn {
          border-radius: 8px;
          padding: 0.5rem 1rem;
          font-size: 0.85rem;
          font-weight: 600;
          cursor: pointer;
          border: none;
          transition: all 0.2s;
        }
        .btn-emerald {
          background: #10b981;
          color: #ffffff;
        }
        .btn-emerald:hover {
          background: #059669;
        }
        .btn-secondary {
          background: #ffffff;
          color: #334155;
          border: 1px solid #cbd5e1;
        }
        .btn-secondary:hover {
          background: #f8fafc;
          border-color: #94a3b8;
        }
        .btn-details {
          background: #f6f2fb;
          color: #774DA9;
          border: 1px solid #dac8ee;
          padding: 0.2rem 0.6rem;
          border-radius: 4px;
          font-size: 0.8rem;
          font-weight: 600;
          cursor: pointer;
        }
        .alert {
          padding: 0.75rem 1rem;
          border-radius: 8px;
          margin-bottom: 1rem;
          font-size: 0.85rem;
        }
        .alert-danger {
          background: #fef2f2;
          color: #991b1b;
          border: 1px solid #fecaca;
        }
        .alert-success {
          background: #ecfdf5;
          color: #065f46;
          border: 1px solid #a7f3d0;
        }
        .text-emerald { color: #059669; }
        .text-success { color: #059669; }
        .text-danger { color: #dc2626; }
        .text-amber { color: #d97706; }
        .text-blue { color: #2563eb; }
        .text-purple { color: #774da9; }
        .text-cyan { color: #0891b2; }
        .text-muted { color: #64748b; }
        .font-mono { font-family: monospace; }
        .modal-backdrop {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(36, 20, 60, 0.65);
          backdrop-filter: blur(4px);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1050;
        }
        .modal-content {
          background: #ffffff;
          border: 1px solid #e2e8f0;
          border-radius: 14px;
          padding: 1.5rem;
          max-width: 600px;
          width: 90%;
          max-height: 85vh;
          overflow-y: auto;
          box-shadow: 0 20px 25px -5px rgba(36, 20, 60, 0.15);
        }
        .modal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1rem;
        }
        .modal-title {
          font-size: 1.15rem;
          font-weight: 800;
          color: #24143C;
          margin: 0;
        }
        .btn-close {
          background: none;
          border: none;
          color: #64748b;
          font-size: 1.25rem;
          font-weight: 700;
          cursor: pointer;
        }
        .detail-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 0.75rem;
          margin-bottom: 1rem;
        }
        .detail-label {
          font-size: 0.75rem;
          color: #64748b;
          font-weight: 600;
          text-transform: uppercase;
        }
        .json-box {
          margin-top: 0.75rem;
        }
        .json-box pre {
          background: #0f172a;
          border: 1px solid #1e293b;
          border-radius: 6px;
          padding: 0.75rem;
          font-size: 0.75rem;
          color: #a5f3fc;
          overflow-x: auto;
        }
      `}</style>
    </div>
  );
};
