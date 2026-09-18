import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { Project } from '../types/project';
import type {
  ExternalConnection,
  ExternalOperationRecord,
  ExternalOperationStatus,
} from '../types/externalIntegration';
import {
  getExternalConnections,
  getConnectionOperations,
} from '../api/externalIntegrations';

interface ExternalIntegrationsPanelProps {
  project: Project;
}

export const ExternalIntegrationsPanel: React.FC<ExternalIntegrationsPanelProps> = ({ project }) => {
  const [connections, setConnections] = useState<ExternalConnection[]>([]);
  const [operations, setOperations] = useState<ExternalOperationRecord[]>([]);
  const [selectedConnection, setSelectedConnection] = useState<ExternalConnection | null>(null);
  const [selectedOperation, setSelectedOperation] = useState<ExternalOperationRecord | null>(null);

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [systemTypeFilter, setSystemTypeFilter] = useState<string>('');

  const pollIntervalRef = useRef<number | null>(null);

  const loadData = useCallback(async () => {
    try {
      setIsLoading(true);
      setErrorMessage(null);
      const connList = await getExternalConnections(project.id, systemTypeFilter || undefined);
      setConnections(connList);

      // Load recent operations from first connection or across connections
      if (connList.length > 0) {
        const targetConn = selectedConnection || connList[0];
        if (!selectedConnection) {
          setSelectedConnection(targetConn);
        }
        const ops = await getConnectionOperations(targetConn.id);
        setOperations(ops);
      } else {
        setOperations([]);
      }
    } catch (err: any) {
      console.error('Error loading external integrations:', err);
      setErrorMessage(err.message || 'Failed to load external system integrations.');
    } finally {
      setIsLoading(false);
    }
  }, [project.id, systemTypeFilter, selectedConnection]);

  useEffect(() => {
    loadData();
    pollIntervalRef.current = window.setInterval(loadData, 30000);
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [loadData]);

  const handleSelectConnection = async (conn: ExternalConnection) => {
    setSelectedConnection(conn);
    try {
      setIsLoading(true);
      const ops = await getConnectionOperations(conn.id);
      setOperations(ops);
    } catch (err: any) {
      console.error('Failed to load connection operations:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const getStatusBadge = (status: ExternalOperationStatus) => {
    switch (status) {
      case 'verified':
      case 'completed':
        return <span className="badge badge-success">VERIFIED</span>;
      case 'executing':
        return <span className="badge badge-info">EXECUTING</span>;
      case 'authorized':
        return <span className="badge badge-primary">AUTHORIZED</span>;
      case 'pending':
        return <span className="badge badge-warning">WAITING FOR APPROVAL</span>;
      case 'rate_limited':
        return <span className="badge badge-warning">RATE LIMITED (429)</span>;
      case 'rejected':
      case 'failed':
        return <span className="badge badge-danger">{String(status).toUpperCase()}</span>;
      default:
        return <span className="badge badge-secondary">{String(status).toUpperCase()}</span>;
    }
  };

  const getConnectionStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return <span className="badge badge-success">ACTIVE</span>;
      case 'test_staging':
        return <span className="badge badge-info">TEST / STAGING</span>;
      case 'error':
        return <span className="badge badge-danger">ERROR</span>;
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
        return <span className="risk-pill risk-high">HIGH RISK</span>;
      default:
        return <span className="risk-pill">{risk}</span>;
    }
  };

  return (
    <div className="card shadow-sm border-0 mb-4">
      <div className="card-header bg-white d-flex justify-content-between align-items-center py-3 border-bottom">
        <div>
          <h5 className="mb-0 font-weight-bold d-flex align-items-center gap-2">
            <span>External System Integrations</span>
            <span className="badge badge-pill badge-primary" style={{ fontSize: '0.75rem' }}>
              Milestone 6.5
            </span>
          </h5>
          <small className="text-muted">
            Safe, permission-gated multi-system adapters (CMS, Git, Webhook) with ToolRegistry authority and empirical verification.
          </small>
        </div>
        <div className="d-flex align-items-center gap-2">
          <select
            className="form-control form-control-sm"
            style={{ width: '160px' }}
            value={systemTypeFilter}
            onChange={(e) => setSystemTypeFilter(e.target.value)}
          >
            <option value="">All Systems</option>
            <option value="cms">CMS</option>
            <option value="git">Git</option>
            <option value="webhook">Webhook/API</option>
          </select>
          <button
            className="btn btn-outline-secondary btn-sm"
            onClick={() => loadData()}
            disabled={isLoading}
            title="Refresh integration status"
          >
            {isLoading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      <div className="card-body">
        {errorMessage && (
          <div className="alert alert-danger py-2 mb-3">
            {errorMessage}
          </div>
        )}

        {/* Connected Systems Grid */}
        <h6 className="text-uppercase text-muted font-weight-bold mb-3" style={{ fontSize: '0.8rem', letterSpacing: '0.05em' }}>
          Connected Systems & Staging Adapters
        </h6>

        {connections.length === 0 ? (
          <div className="text-center py-4 bg-light rounded mb-4">
            <p className="text-muted mb-0">No external connections configured for this project.</p>
            <small className="text-muted">Connections allow agents to inspect CMS metadata, stage Git branches, and send deployment webhooks.</small>
          </div>
        ) : (
          <div className="row mb-4">
            {connections.map((conn) => {
              const isSelected = selectedConnection?.id === conn.id;
              return (
                <div key={conn.id} className="col-md-4 mb-3">
                  <div
                    className={`card h-100 p-3 cursor-pointer ${isSelected ? 'border-primary shadow-sm' : 'border'}`}
                    style={{ cursor: 'pointer', transition: 'all 0.15s ease' }}
                    onClick={() => handleSelectConnection(conn)}
                  >
                    <div className="d-flex justify-content-between align-items-start mb-2">
                      <span className="badge badge-dark text-uppercase">{conn.system_type}</span>
                      {getConnectionStatusBadge(conn.status)}
                    </div>
                    <h6 className="font-weight-bold mb-1">{conn.name}</h6>
                    <div className="text-muted small mb-2">Provider: {conn.provider}</div>
                    <div className="mt-auto">
                      <small className="text-muted d-block mb-1">Declared Capabilities:</small>
                      <div className="d-flex flex-wrap gap-1">
                        {conn.capabilities.map((cap) => (
                          <span
                            key={cap}
                            className="badge badge-light border text-muted"
                            style={{ fontSize: '0.65rem' }}
                          >
                            {cap}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Operations History */}
        <div className="d-flex justify-content-between align-items-center mb-3">
          <h6 className="text-uppercase text-muted font-weight-bold mb-0" style={{ fontSize: '0.8rem', letterSpacing: '0.05em' }}>
            Recent External Operations {selectedConnection ? `(${selectedConnection.name})` : ''}
          </h6>
          <small className="text-muted">Zero plaintext secrets or credentials stored or transmitted.</small>
        </div>

        {operations.length === 0 ? (
          <div className="text-center py-4 bg-light rounded">
            <p className="text-muted mb-0">No external operations recorded for this connection yet.</p>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0">
              <thead className="thead-light" style={{ fontSize: '0.8rem' }}>
                <tr>
                  <th>Operation</th>
                  <th>Target</th>
                  <th>System / Provider</th>
                  <th>Risk</th>
                  <th>Status</th>
                  <th>Verification</th>
                  <th>Failure Reason</th>
                  <th>Timestamp</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody style={{ fontSize: '0.85rem' }}>
                {operations.map((op) => (
                  <tr key={op.id}>
                    <td className="font-weight-bold font-monospace">
                      <code>{op.operation}</code>
                    </td>
                    <td className="text-truncate" style={{ maxWidth: '200px' }} title={op.target}>
                      {op.target}
                    </td>
                    <td>
                      <span className="badge badge-light border text-uppercase">{op.system_type}</span>
                      <small className="text-muted ms-1">({op.provider})</small>
                    </td>
                    <td>{getRiskBadge(op.risk_level)}</td>
                    <td>{getStatusBadge(op.status)}</td>
                    <td>
                      {op.verification_status === 'verified' ? (
                        <span className="badge badge-success">VERIFIED</span>
                      ) : op.verification_status === 'failed' ? (
                        <span className="badge badge-danger">VERIF FAILED</span>
                      ) : op.verification_status === 'not_required' ? (
                        <span className="badge badge-light border">N/A</span>
                      ) : (
                        <span className="badge badge-warning">PENDING</span>
                      )}
                    </td>
                    <td>
                      {op.error_message ? (
                        <span className="text-danger small" title={op.error_message}>
                          {op.error_category || 'Error'}: {op.error_message.slice(0, 40)}...
                        </span>
                      ) : (
                        <span className="text-muted small">—</span>
                      )}
                    </td>
                    <td className="text-muted small">
                      {new Date(op.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td>
                      <button
                        className="btn btn-outline-primary btn-sm py-0 px-2"
                        onClick={() => setSelectedOperation(op)}
                        style={{ fontSize: '0.75rem' }}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Operation Detail Modal */}
      {selectedOperation && (
        <div
          className="modal d-block"
          tabIndex={-1}
          style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
          onClick={() => setSelectedOperation(null)}
        >
          <div
            className="modal-dialog modal-lg modal-dialog-scrollable"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title font-weight-bold">
                  External Operation #{selectedOperation.id}: <code>{selectedOperation.operation}</code>
                </h5>
                <button
                  type="button"
                  className="btn-close"
                  onClick={() => setSelectedOperation(null)}
                ></button>
              </div>
              <div className="modal-body">
                <div className="row mb-3">
                  <div className="col-md-6">
                    <small className="text-muted d-block">System & Provider</small>
                    <span className="font-weight-bold text-uppercase">{selectedOperation.system_type}</span> ({selectedOperation.provider})
                  </div>
                  <div className="col-md-6">
                    <small className="text-muted d-block">Target</small>
                    <code className="text-break">{selectedOperation.target}</code>
                  </div>
                </div>

                <div className="row mb-3">
                  <div className="col-md-4">
                    <small className="text-muted d-block">Execution Status</small>
                    {getStatusBadge(selectedOperation.status)}
                  </div>
                  <div className="col-md-4">
                    <small className="text-muted d-block">Verification Status</small>
                    <span className="badge badge-light border">{selectedOperation.verification_status.toUpperCase()}</span>
                  </div>
                  <div className="col-md-4">
                    <small className="text-muted d-block">Idempotency Key</small>
                    <code style={{ fontSize: '0.7rem' }}>{selectedOperation.idempotency_key.slice(0, 16)}...</code>
                  </div>
                </div>

                {selectedOperation.error_message && (
                  <div className="alert alert-danger py-2 mb-3">
                    <strong>Error ({selectedOperation.error_category}):</strong> {selectedOperation.error_message}
                  </div>
                )}

                {/* Before / After State Diff */}
                <h6 className="font-weight-bold mt-4 mb-2">State Diff (Before / After)</h6>
                <div className="row">
                  <div className="col-md-6">
                    <div className="card p-2 bg-light">
                      <small className="text-muted font-weight-bold mb-1 d-block">BEFORE STATE</small>
                      <pre className="mb-0" style={{ fontSize: '0.75rem', maxHeight: '180px', overflowY: 'auto' }}>
                        {JSON.stringify(selectedOperation.before_state || {}, null, 2)}
                      </pre>
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="card p-2 bg-light">
                      <small className="text-muted font-weight-bold mb-1 d-block">AFTER STATE</small>
                      <pre className="mb-0" style={{ fontSize: '0.75rem', maxHeight: '180px', overflowY: 'auto' }}>
                        {JSON.stringify(selectedOperation.after_state || {}, null, 2)}
                      </pre>
                    </div>
                  </div>
                </div>

                {/* Verification Evidence */}
                {selectedOperation.verification_data && Object.keys(selectedOperation.verification_data).length > 0 && (
                  <>
                    <h6 className="font-weight-bold mt-4 mb-2">Empirical Verification Evidence</h6>
                    <div className="card p-2 bg-light">
                      <pre className="mb-0" style={{ fontSize: '0.75rem', maxHeight: '150px', overflowY: 'auto' }}>
                        {JSON.stringify(selectedOperation.verification_data, null, 2)}
                      </pre>
                    </div>
                  </>
                )}
              </div>
              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setSelectedOperation(null)}
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
