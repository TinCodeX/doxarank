import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { Project } from '../types/project';
import type {
  RemediationRecord,
  RemediationMetrics,
  ProjectRemediationPolicy,
  RemediationStatus,
} from '../types/seoRemediation';
import {
  getRemediationRecords,
  getRemediationMetrics,
  getRemediationPolicy,
} from '../api/seoRemediation';

interface RemediationActivityPanelProps {
  project: Project;
}

export const RemediationActivityPanel: React.FC<RemediationActivityPanelProps> = ({ project }) => {
  const [records, setRecords] = useState<RemediationRecord[]>([]);
  const [metrics, setMetrics] = useState<RemediationMetrics | null>(null);
  const [policy, setPolicy] = useState<ProjectRemediationPolicy | null>(null);
  const [selectedRecord, setSelectedRecord] = useState<RemediationRecord | null>(null);

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [riskFilter, setRiskFilter] = useState<string>('');
  const [autoFilter, setAutoFilter] = useState<boolean | undefined>(undefined);

  const pollIntervalRef = useRef<number | null>(null);

  const loadData = useCallback(async () => {
    try {
      setIsLoading(true);
      setErrorMessage(null);
      const [recordList, metricData, policyData] = await Promise.all([
        getRemediationRecords(project.id, {
          status: statusFilter || undefined,
          risk_level: riskFilter || undefined,
          is_autonomous: autoFilter,
        }),
        getRemediationMetrics(project.id),
        getRemediationPolicy(project.id),
      ]);
      setRecords(recordList);
      setMetrics(metricData);
      setPolicy(policyData);
    } catch (err: any) {
      console.error('Error loading remediation activity:', err);
      setErrorMessage(err.message || 'Failed to load autonomous remediation records.');
    } finally {
      setIsLoading(false);
    }
  }, [project.id, statusFilter, riskFilter, autoFilter]);

  useEffect(() => {
    loadData();
    pollIntervalRef.current = window.setInterval(loadData, 30000);
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [loadData]);

  const getStatusBadge = (status: RemediationStatus) => {
    switch (status) {
      case 'verified':
      case 'completed':
        return <span className="badge badge-success">VERIFIED</span>;
      case 'executing':
      case 'verifying':
        return <span className="badge badge-info">{status.toUpperCase()}</span>;
      case 'authorized':
        return <span className="badge badge-primary">AUTHORIZED</span>;
      case 'proposed':
        return <span className="badge badge-secondary">PROPOSED</span>;
      case 'pending_approval':
        return <span className="badge badge-warning">WAITING FOR APPROVAL</span>;
      case 'rejected':
        return <span className="badge badge-danger">REJECTED</span>;
      case 'blocked':
        return <span className="badge badge-danger">BLOCKED</span>;
      case 'rolled_back':
        return <span className="badge badge-dark">ROLLED BACK</span>;
      case 'failed':
        return <span className="badge badge-danger">FAILED</span>;
      default:
        return <span className="badge badge-secondary">{status.toUpperCase()}</span>;
    }
  };

  const getRiskBadge = (risk: string) => {
    switch (risk?.toLowerCase()) {
      case 'low':
        return <span className="risk-pill risk-low">LOW RISK</span>;
      case 'medium':
        return <span className="risk-pill risk-medium">MEDIUM RISK</span>;
      case 'high':
      case 'critical':
        return <span className="risk-pill risk-high">{risk.toUpperCase()} RISK</span>;
      default:
        return <span className="risk-pill">{risk}</span>;
    }
  };

  return (
    <div className="remediation-activity-panel" id="seo-autonomous-remediation-section">
      <div className="panel-header">
        <div className="title-area">
          <h3>Autonomous SEO Remediation</h3>
          <p className="subtitle">
            Policy-governed automated fixes, HITL approval boundaries, empirical verification, and safety controls for <strong>{project.name}</strong>.
          </p>
        </div>
        <div className="header-actions">
          <button
            className="btn btn-secondary btn-sm"
            onClick={loadData}
            disabled={isLoading}
          >
            {isLoading ? 'Refreshing...' : 'Refresh Activity'}
          </button>
        </div>
      </div>

      {errorMessage && (
        <div className="alert alert-danger" role="alert">
          {errorMessage}
        </div>
      )}

      {/* Runtime Evaluation Metrics Cards */}
      {metrics && (
        <div className="metrics-grid">
          <div className="metric-card">
            <span className="metric-label">Remediations</span>
            <span className="metric-value">{metrics.total_remediations}</span>
            <span className="metric-sub">{metrics.remediation_attempt_rate}% attempt rate</span>
          </div>

          <div className="metric-card">
            <span className="metric-label">Success Rate</span>
            <span className="metric-value">{metrics.remediation_success_rate}%</span>
            <span className="metric-sub">{metrics.remediation_successes} verified fixes</span>
          </div>

          <div className="metric-card">
            <span className="metric-label">Verification Rate</span>
            <span className="metric-value">{metrics.verification_success_rate}%</span>
            <span className="metric-sub">{metrics.verification_failures} verification failures</span>
          </div>

          <div className="metric-card">
            <span className="metric-label">Autonomous Share</span>
            <span className="metric-value">{metrics.autonomous_execution_rate}%</span>
            <span className="metric-sub">{metrics.autonomous_executed_count} auto executed</span>
          </div>

          <div className="metric-card">
            <span className="metric-label">Human Approvals</span>
            <span className="metric-value">{metrics.human_approval_rate}%</span>
            <span className="metric-sub">{metrics.human_approved_count} approved / {metrics.human_rejected_count} rejected</span>
          </div>

          <div className="metric-card">
            <span className="metric-label">Safety & Blocks</span>
            <span className="metric-value">{metrics.policy_blocked_count}</span>
            <span className="metric-sub">{metrics.duplicates_prevented} dups prevented, {metrics.rollback_count} rollbacks</span>
          </div>
        </div>
      )}

      {/* Policy Summary Badge */}
      {policy && (
        <div className="policy-banner">
          <div className="policy-info">
            <span className="policy-badge">
              Autonomous Mode: <strong>{policy.is_autonomous_enabled ? 'ENABLED' : 'DISABLED'}</strong>
            </span>
            <span className="policy-stat">
              Daily Quota: <strong>{policy.max_daily_autonomous_actions}</strong>
            </span>
            <span className="policy-stat">
              Min Confidence: <strong>{Math.round(policy.min_confidence_threshold * 100)}%</strong>
            </span>
          </div>
        </div>
      )}

      {/* Filter Controls */}
      <div className="filter-bar">
        <div className="filter-group">
          <label>Status:</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">All Statuses</option>
            <option value="proposed">Proposed</option>
            <option value="pending_approval">Waiting for Approval</option>
            <option value="authorized">Authorized</option>
            <option value="executing">Executing</option>
            <option value="executed">Executed</option>
            <option value="verifying">Verifying</option>
            <option value="verified">Verified</option>
            <option value="failed">Failed</option>
            <option value="blocked">Blocked</option>
            <option value="rejected">Rejected</option>
            <option value="rolled_back">Rolled Back</option>
          </select>
        </div>

        <div className="filter-group">
          <label>Risk Level:</label>
          <select
            value={riskFilter}
            onChange={(e) => setRiskFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">All Risks</option>
            <option value="low">Low Risk</option>
            <option value="medium">Medium Risk</option>
            <option value="high">High Risk</option>
            <option value="critical">Critical Risk</option>
          </select>
        </div>

        <div className="filter-group">
          <label>Mode:</label>
          <select
            value={autoFilter === undefined ? '' : autoFilter ? 'true' : 'false'}
            onChange={(e) => {
              const v = e.target.value;
              setAutoFilter(v === '' ? undefined : v === 'true');
            }}
            className="filter-select"
          >
            <option value="">All Modes</option>
            <option value="true">Autonomous Only</option>
            <option value="false">Human Supervised Only</option>
          </select>
        </div>
      </div>

      {/* Remediation Records Table */}
      <div className="table-responsive">
        {records.length === 0 ? (
          <div className="empty-state">
            <p>No remediation records match the selected criteria.</p>
          </div>
        ) : (
          <table className="remediation-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Proposed Action</th>
                <th>Target URL</th>
                <th>Risk</th>
                <th>Mode</th>
                <th>Policy Decision</th>
                <th>Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {records.map((rec) => (
                <tr
                  key={rec.id}
                  onClick={() => setSelectedRecord(rec)}
                  className={selectedRecord?.id === rec.id ? 'row-selected' : ''}
                >
                  <td>{getStatusBadge(rec.status)}</td>
                  <td>
                    <strong>{rec.action_title}</strong>
                    <div className="text-muted small">{rec.action_type}</div>
                  </td>
                  <td className="url-cell">
                    <span className="url-text" title={rec.target_url}>
                      {rec.target_url || 'Sitewide'}
                    </span>
                  </td>
                  <td>{getRiskBadge(rec.risk_level)}</td>
                  <td>
                    <span className={`mode-badge ${rec.is_autonomous ? 'mode-auto' : 'mode-hitl'}`}>
                      {rec.is_autonomous ? 'Autonomous' : 'HITL'}
                    </span>
                  </td>
                  <td>
                    <span className="policy-text" title={rec.policy_explanation}>
                      {rec.policy_decision.replace('_', ' ').toUpperCase()}
                    </span>
                  </td>
                  <td className="text-muted small">
                    {new Date(rec.created_at).toLocaleString()}
                  </td>
                  <td>
                    <button
                      className="btn btn-outline-primary btn-xs"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedRecord(rec);
                      }}
                    >
                      Details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Remediation Record Detail Modal / Drawer */}
      {selectedRecord && (
        <div className="modal-backdrop" onClick={() => setSelectedRecord(null)}>
          <div className="detail-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h4>Remediation #{selectedRecord.id}: {selectedRecord.action_title}</h4>
              <button
                className="close-btn"
                onClick={() => setSelectedRecord(null)}
              >
                &times;
              </button>
            </div>
            <div className="modal-body">
              <div className="detail-grid">
                <div className="detail-item">
                  <label>Status:</label>
                  <div>{getStatusBadge(selectedRecord.status)}</div>
                </div>
                <div className="detail-item">
                  <label>Risk Level:</label>
                  <div>{getRiskBadge(selectedRecord.risk_level)}</div>
                </div>
                <div className="detail-item">
                  <label>Execution Mode:</label>
                  <div>{selectedRecord.is_autonomous ? 'Autonomous Policy Execution' : 'Human-in-the-Loop Review'}</div>
                </div>
                <div className="detail-item">
                  <label>Target URL:</label>
                  <div className="code-font">{selectedRecord.target_url || 'Sitewide'}</div>
                </div>
                <div className="detail-item full-width">
                  <label>Policy Determination & Rationale:</label>
                  <p className="policy-rationale">{selectedRecord.policy_explanation || 'Approved via standard policy evaluation.'}</p>
                </div>
                {selectedRecord.error_category && (
                  <div className="detail-item full-width alert alert-warning">
                    <label>Failure Category:</label>
                    <div><strong>{selectedRecord.error_category.toUpperCase()}</strong></div>
                  </div>
                )}
                {selectedRecord.rollback_data && Object.keys(selectedRecord.rollback_data).length > 0 && (
                  <div className="detail-item full-width">
                    <label>Pre-Execution State (Rollback Snapshot):</label>
                    <pre className="code-block">
                      {JSON.stringify(selectedRecord.rollback_data, null, 2)}
                    </pre>
                  </div>
                )}
                {selectedRecord.verification_data && Object.keys(selectedRecord.verification_data).length > 0 && (
                  <div className="detail-item full-width">
                    <label>Live Verification Evidence:</label>
                    <pre className="code-block">
                      {JSON.stringify(selectedRecord.verification_data, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            </div>
            <div className="modal-footer">
              <button
                className="btn btn-secondary"
                onClick={() => setSelectedRecord(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        .remediation-activity-panel {
          background: #ffffff;
          border-radius: 12px;
          padding: 24px;
          margin-bottom: 28px;
          box-shadow: 0 4px 16px rgba(0, 0, 0, 0.05);
          border: 1px solid #e9ecef;
        }
        .panel-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 20px;
        }
        .title-area h3 {
          margin: 0 0 6px 0;
          font-size: 1.25rem;
          font-weight: 700;
          color: #1a202c;
        }
        .subtitle {
          margin: 0;
          color: #718096;
          font-size: 0.875rem;
        }
        .metrics-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 16px;
          margin-bottom: 20px;
        }
        .metric-card {
          background: #f8fafc;
          border-radius: 8px;
          padding: 14px 16px;
          display: flex;
          flex-direction: column;
          border: 1px solid #e2e8f0;
        }
        .metric-label {
          font-size: 0.75rem;
          color: #64748b;
          text-transform: uppercase;
          font-weight: 600;
          letter-spacing: 0.5px;
        }
        .metric-value {
          font-size: 1.5rem;
          font-weight: 700;
          color: #0f172a;
          margin: 4px 0 2px 0;
        }
        .metric-sub {
          font-size: 0.75rem;
          color: #94a3b8;
        }
        .policy-banner {
          background: #f0fdf4;
          border: 1px solid #bbf7d0;
          border-radius: 8px;
          padding: 10px 16px;
          margin-bottom: 20px;
        }
        .policy-info {
          display: flex;
          gap: 20px;
          font-size: 0.85rem;
          color: #166534;
        }
        .filter-bar {
          display: flex;
          gap: 16px;
          flex-wrap: wrap;
          background: #f8fafc;
          padding: 12px 16px;
          border-radius: 8px;
          margin-bottom: 16px;
          align-items: center;
        }
        .filter-group {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .filter-group label {
          font-size: 0.8rem;
          color: #475569;
          font-weight: 500;
          margin: 0;
        }
        .filter-select {
          padding: 6px 12px;
          border: 1px solid #cbd5e1;
          border-radius: 6px;
          font-size: 0.85rem;
          background: #ffffff;
        }
        .remediation-table {
          width: 100%;
          border-collapse: collapse;
        }
        .remediation-table th {
          background: #f1f5f9;
          color: #475569;
          font-size: 0.75rem;
          text-transform: uppercase;
          font-weight: 600;
          padding: 10px 14px;
          border-bottom: 1px solid #e2e8f0;
          text-align: left;
        }
        .remediation-table td {
          padding: 12px 14px;
          border-bottom: 1px solid #f1f5f9;
          font-size: 0.875rem;
          vertical-align: middle;
        }
        .remediation-table tr:hover {
          background: #f8fafc;
          cursor: pointer;
        }
        .badge {
          display: inline-block;
          padding: 4px 8px;
          border-radius: 4px;
          font-size: 0.7rem;
          font-weight: 700;
          letter-spacing: 0.4px;
        }
        .badge-success { background: #dcfce7; color: #15803d; }
        .badge-info { background: #e0f2fe; color: #0369a1; }
        .badge-primary { background: #dbeafe; color: #1d4ed8; }
        .badge-warning { background: #fef3c7; color: #b45309; }
        .badge-danger { background: #fee2e2; color: #b91c1c; }
        .badge-dark { background: #e2e8f0; color: #334155; }
        .badge-secondary { background: #f1f5f9; color: #64748b; }
        .risk-pill {
          display: inline-block;
          padding: 3px 8px;
          border-radius: 12px;
          font-size: 0.7rem;
          font-weight: 600;
        }
        .risk-low { background: #ecfdf5; color: #047857; }
        .risk-medium { background: #fffbeb; color: #b45309; }
        .risk-high { background: #fef2f2; color: #b91c1c; }
        .mode-badge {
          font-size: 0.75rem;
          font-weight: 600;
          padding: 2px 6px;
          border-radius: 4px;
        }
        .mode-auto { background: #eff6ff; color: #2563eb; }
        .mode-hitl { background: #faf5ff; color: #7e22ce; }
        .url-cell {
          max-width: 220px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .modal-backdrop {
          position: fixed;
          top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(15, 23, 42, 0.6);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1050;
        }
        .detail-modal {
          background: #ffffff;
          border-radius: 12px;
          width: 90%;
          max-width: 720px;
          max-height: 85vh;
          overflow-y: auto;
          box-shadow: 0 20px 25px -5px rgba(0,0,0,0.2);
        }
        .modal-header {
          padding: 16px 20px;
          border-bottom: 1px solid #e2e8f0;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .modal-header h4 { margin: 0; font-size: 1.1rem; }
        .close-btn {
          background: none; border: none; font-size: 1.5rem; cursor: pointer; color: #94a3b8;
        }
        .modal-body { padding: 20px; }
        .modal-footer {
          padding: 12px 20px;
          border-top: 1px solid #e2e8f0;
          display: flex;
          justify-content: flex-end;
        }
        .detail-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 16px;
        }
        .detail-item label {
          font-size: 0.75rem;
          font-weight: 600;
          color: #64748b;
          text-transform: uppercase;
          display: block;
          margin-bottom: 4px;
        }
        .full-width { grid-column: 1 / -1; }
        .code-block {
          background: #0f172a;
          color: #f8fafc;
          padding: 12px;
          border-radius: 6px;
          font-size: 0.75rem;
          max-height: 200px;
          overflow-y: auto;
        }
        .btn-xs { padding: 2px 8px; font-size: 0.75rem; }
      `}</style>
    </div>
  );
};
